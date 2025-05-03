from __future__ import annotations

import asyncio
import json
import json as _json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from browser_use.agent.service import Agent
from browser_use.agent.views import ActionResult, AgentHistoryList
from browser_use.browser.browser import Browser
from browser_use.browser.context import BrowserContext

from .controller.service import WorkflowController

logger = logging.getLogger(__name__)

FALLBACK_PROMPT = (
	'While executing step {step_index}/{total_steps} in the workflow:\n\n{workflow_details}\n\n'
	'The deterministic action failed with the following context:\n{fail_details}\n\n'
	'Please analyze the situation and achieve the objective of step {step_index} using the available browser actions. '
	'You do not have to use the same action – feel free to choose any suitable action(s) to accomplish the same goal. '
	'Once the objective of step {step_index} is reached, call the Done action to complete the step.'
	'Do not attempt to use the same action again – choose a different one.'
	'Do not continue with the next step, just complete step {step_index}.'
)


class Workflow:
	"""Simple orchestrator that executes a list of workflow *steps* defined in a YAML file."""

	def __init__(
		self,
		yaml_path: str | Path,
		*,
		controller: WorkflowController | None = None,
		browser: Browser | None = None,
		llm: BaseChatModel | None = None,
		fallback_to_agent: bool = True,
	) -> None:
		self.yaml_path = Path(yaml_path)
		if not self.yaml_path.exists():
			raise FileNotFoundError(self.yaml_path)

		self.controller = controller or WorkflowController()
		logger.info(self.controller.registry.registry.actions)
		self.browser = browser or Browser()
		self.llm = llm
		self.fallback_to_agent = fallback_to_agent

		self.browser_context = BrowserContext(browser=self.browser, config=self.browser.config.new_context_config)

		self.context: dict[str, Any] = {}

		self.steps: List[Dict[str, Any]]
		self.inputs_def: Dict[str, Any]  # Definition of expected inputs
		self.steps, self.inputs_def = self._parse_yaml()
		self._input_model: type[BaseModel] = self._build_input_model()

	def _parse_yaml(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
		"""Load and validate the YAML workflow file returning steps and input schema definition."""
		with self.yaml_path.open('r', encoding='utf-8') as fp:
			data = yaml.safe_load(fp)

		if not data or 'steps' not in data or not isinstance(data['steps'], list):
			raise ValueError("YAML workflow must contain a top-level 'steps' list")

		steps = data['steps']
		inputs_def = data.get('inputs', {})  # Inputs are optional

		if not isinstance(inputs_def, dict):
			raise ValueError("YAML 'inputs' section must be a dictionary (map).")

		# Validate the basic structure of the input schema if present
		if inputs_def:
			if inputs_def.get('type') != 'object':
				raise ValueError("YAML 'inputs' section must have type: object")
			if 'properties' not in inputs_def or not isinstance(inputs_def.get('properties'), dict):
				raise ValueError("YAML 'inputs' section must have a 'properties' dictionary.")
			if 'required' in inputs_def and not isinstance(inputs_def.get('required'), list):
				raise ValueError("YAML 'inputs.required' must be a list of strings.")

		return steps, inputs_def

	async def _run_deterministic_step(self, step: Dict[str, Any]) -> ActionResult:
		"""Execute a deterministic (controller) action."""
		action_name: str = step['action']
		params: Dict[str, Any] = step.get('params', {})

		ActionModel = self.controller.registry.create_action_model(include_actions=[action_name])
		action_model = ActionModel(**{action_name: params})

		try:
			# Execute the controller action
			return await self.controller.act(action_model, self.browser_context)
			
		except Exception as e:
			# Catch any errors from the controller action
			raise RuntimeError(f"Deterministic action '{action_name}' failed: {str(e)}")

	async def _run_agent_step(self, step: Dict[str, Any]) -> AgentHistoryList | dict[str, Any]:
		"""Spin-up a one-off Agent to accomplish an open-ended task OR direct structured-output call."""
		if self.llm is None:
			raise ValueError("An 'llm' instance must be supplied for agent-based steps")

		task: str = step['task']
		# Remove workflow-specific keys that are **not** constructor kwargs for Agent
		agent = Agent(
			task=task,
			llm=self.llm,
			browser=self.browser,
			browser_context=self.browser_context,
			controller=self.controller,
			use_vision=True,
		)
		max_steps: int = step.get('max_steps', 5)
		return await agent.run(max_steps=max_steps)

	async def _fallback_to_agent(
		self, step_resolved: Dict[str, Any], step_index: int, error: Exception | str | None = None
	) -> AgentHistoryList | dict[str, Any]:
		"""Handle deterministic step failure by delegating to an on-the-fly agent.

		This helper contains the shared logic for constructing a descriptive fallback
		task, building a temporary *agent step* configuration and ultimately
		invoking :py:meth:`_run_agent_step`.
		Added *error* parameter to capture the exception message so that the prompt
		provides richer context (step position + error string).
		"""
		# Ensure LLM availability first – callers already checked for `fallback_to_agent`
		if self.llm is None:
			raise ValueError("Cannot fall back to agent: An 'llm' instance must be supplied for agent-based steps")

		# Build failure details for the prompt -------------------------------
		failed_action_name = step_resolved.get('action', 'unknown_action')
		failed_params = step_resolved.get('params', {})
		error_msg = str(error) if error else 'Unknown error'
		total_steps = len(self.steps)
		fail_details = (
			f"step={step_index + 1}/{total_steps}, action='{failed_action_name}', description='{step_resolved.get('description', 'No description provided')}', "
			f"params={str(failed_params)}, error='{error_msg}'"
		)

		# Build a compact overview of the entire workflow for additional context
		workflow_overview_lines: list[str] = []
		for i, st in enumerate(self.steps):
			desc = st.get('description') or st.get('task') or st.get('action') or 'No details'
			step_type_info = st.get('type', 'deterministic')
			action_name = st.get('action')
			action_params = st.get('params')
			workflow_overview_lines.append(f'  {i + 1}. ({step_type_info}) {desc} {action_name} {action_params}')
		workflow_overview = '\n'.join(workflow_overview_lines)

		# Compose the fallback task ----------------------------------------
		fallback_task = FALLBACK_PROMPT.format(
			step_index=step_index + 1,
			total_steps=len(self.steps),
			workflow_details=workflow_overview,
			fail_details=fail_details,
		)
		logger.info(f'Agent fallback task: {fallback_task}')

		# Prepare an *agent* step configuration mirroring the failed deterministic one
		agent_step_config = step_resolved.copy()
		agent_step_config['type'] = 'agent'
		agent_step_config['task'] = fallback_task
		agent_step_config.setdefault('max_steps', 5)

		# Delegate to the regular agent-step runner
		return await self._run_agent_step(agent_step_config)

	def _validate_inputs(self, inputs: dict[str, Any]) -> None:
		"""Validate provided inputs against the workflow's input schema definition."""
		# If no inputs are defined in the schema, no validation needed
		if not self.inputs_def:
			return

		try:
			# Let Pydantic perform the heavy lifting – this covers both presence and
			# type validation based on the YAML-derived model.
			self._input_model(**inputs)
		except Exception as e:
			raise ValueError(f'Invalid workflow inputs: {e}') from e

	def _resolve_placeholders(self, data: Any) -> Any:
		"""Recursively replace placeholders in *data* using current context variables.

		String placeholders are written using Python format syntax, e.g. "{index}".
		"""

		if isinstance(data, str):
			try:
				return data.format(**self.context)
			except KeyError:
				# variable not yet available – leave as-is
				return data
		elif isinstance(data, dict):
			return {k: self._resolve_placeholders(v) for k, v in data.items()}
		elif isinstance(data, list):
			return [self._resolve_placeholders(v) for v in data]
		else:
			return data

	def _store_output(self, step_cfg: Dict[str, Any], result: Any) -> None:
		"""Store output from *result* into the context according to `output` key in *step_cfg*."""
		output_key = step_cfg.get('output')
		if not output_key:
			return

		# Helper to extract raw content we want to store

		value: Any = None

		if isinstance(result, ActionResult):
			# Prefer JSON in extracted_content if available
			content = result.extracted_content
			if content is None:
				value = {
					'success': result.success,
					'is_done': result.is_done,
				}
			else:
				try:
					value = json.loads(content)
				except Exception:
					value = content
		elif isinstance(result, AgentHistoryList):
			# Try to pull last ActionResult with extracted_content
			try:
				last_item = result.history[-1]
				last_action_result = next(
					(r for r in reversed(last_item.result) if r.extracted_content is not None),
					None,
				)
				if last_action_result and last_action_result.extracted_content:
					try:
						value = json.loads(last_action_result.extracted_content)
					except Exception:
						value = last_action_result.extracted_content
			except Exception:
				value = None
		else:
			value = str(result)

		self.context[output_key] = value

	async def _execute_step(self, step_index: int, step_resolved: Dict[str, Any]) -> Any:
		"""Execute the *already placeholder-resolved* step and return its result.

		This method contains the core branching logic that decides whether the
		step is deterministic (controller call) or an agent task and handles
		the deterministic-»agent fallback when requested.  It purposefully
		*does not* persist the output into :pyattr:`context` so that callers
		can decide when to do that (the wrapping helpers take care of it).
		"""
		step_type = step_resolved.get('type', 'deterministic').lower()
		result: Any | None = None

		if step_type == 'deterministic':
			# Local import to avoid circular dependencies at module import time
			from browser_use.agent.views import ActionResult

			try:
				logger.info(f'Attempting deterministic action: {step_resolved.get("action")}')
				result = await self._run_deterministic_step(step_resolved)
				# Check if the deterministic action itself indicated failure
				if isinstance(result, ActionResult) and result.error:
					logger.warning(f'Deterministic action reported error: {result.error}')
					raise ValueError(f'Deterministic action {step_resolved.get("action")} failed: {result.error}')
			except Exception as e:
				logger.warning(
					f'Deterministic step {step_index + 1} ({step_resolved.get("action")}) failed: {e}. '
					'Attempting fallback with agent.'
				)
				if self.llm is None:
					raise ValueError("Cannot fall back to agent: An 'llm' instance must be supplied for agent-based steps")
				if self.fallback_to_agent:
					result = await self._fallback_to_agent(step_resolved, step_index, e)
				else:
					raise ValueError(f'Deterministic step {step_index + 1} ({step_resolved.get("action")}) failed: {e}')
		elif step_type == 'agent':
			logger.info(f'Running agent task: {step_resolved.get("task")}')
			result = await self._run_agent_step(step_resolved)
		else:
			raise ValueError(f'Unknown step type in step {step_index + 1}: {step_type}')

		return result

	async def run_step_async(self, step_index: int, inputs: dict[str, Any] | None = None) -> Any:
		"""Run a *single* workflow step asynchronously and return its result.

		Parameters
		----------
		step_index:
			Zero-based index of the step to execute.
		inputs:
			Optional workflow-level inputs.  If provided on the first call they
			are validated and injected into :pyattr:`context`.  Subsequent
			calls can omit *inputs* as :pyattr:`context` is already populated.
		"""
		if not (0 <= step_index < len(self.steps)):
			raise IndexError(f'step_index {step_index} is out of range for workflow with {len(self.steps)} steps')

		# Initialise/augment context once with the provided inputs
		if inputs is not None or not self.context:
			runtime_inputs = inputs or {}
			self._validate_inputs(runtime_inputs)
			# If context is empty we assume this is the first invocation – start fresh;
			# otherwise merge new inputs on top (explicitly overriding duplicates)
			if not self.context:
				self.context = runtime_inputs.copy()
			else:
				self.context.update(runtime_inputs)

		async with self.browser_context:
			raw_step_cfg = self.steps[step_index]
			step_resolved = self._resolve_placeholders(raw_step_cfg)
			result = await self._execute_step(step_index, step_resolved)
			# Persist outputs (if declared) for future steps
			self._store_output(step_resolved, result)
		# Each invocation opens a new browser context – we close the browser to
		# release resources right away.  This keeps the single-step API
		# self-contained.
		await self.browser.close()
		return result

	async def run_async(self, inputs: dict[str, Any] | None = None) -> List[Any]:
		"""Asynchronously execute the workflow returning a list of results.

		Args:
			inputs: Dictionary of input values required by the workflow (defined in YAML).
		"""
		runtime_inputs = inputs or {}
		# 1. Validate inputs against definition
		self._validate_inputs(runtime_inputs)
		# 2. Initialize context with validated inputs
		self.context = runtime_inputs.copy()  # Start with a fresh context

		results: List[Any] = []

		async with self.browser_context:
			for step_index, step in enumerate(self.steps):
				logger.info(
					f'--- Running Step {step_index + 1}/{len(self.steps)} -- {step.get("description", "No description provided")} ---'
				)
				# Resolve placeholders using the current context
				step_resolved = self._resolve_placeholders(step)
				logger.info(f'Step resolved: {step_resolved}')
				step_type = step_resolved.get('type', 'deterministic').lower()
				result: Any = None

				if step_type == 'deterministic':
					try:
						logger.info(f'Attempting deterministic action: {step_resolved.get("action")}')
						result = await self._run_deterministic_step(step_resolved)
						# Check if the deterministic action itself indicated failure
						if isinstance(result, ActionResult) and result.error:
							logger.warning(f'Deterministic action reported error: {result.error}')
							raise ValueError(f'Deterministic action {step_resolved.get("action")} failed: {result.error}')
					except Exception as e:
						logger.warning(
							f'Deterministic step {step_index + 1} ({step_resolved.get("action")}) failed: {e}. '
							'Attempting fallback with agent.'
						)
						if self.llm is None:
							raise ValueError(
								"Cannot fall back to agent: An 'llm' instance must be supplied for agent-based steps"
							)
						if self.fallback_to_agent:
							result = await self._fallback_to_agent(step_resolved, step_index, e)
						else:
							raise ValueError(f'Deterministic step {step_index + 1} ({step_resolved.get("action")}) failed: {e}')
				elif step_type == 'agent':
					logger.info(f'Running agent task: {step_resolved.get("task")}')
					result = await self._run_agent_step(step_resolved)
				else:
					raise ValueError(f'Unknown step type in step {step_index + 1}: {step_type}')

				results.append(result)
				# Persist outputs (if declared) for future steps
				self._store_output(step_resolved, result)
				logger.info(f'--- Finished Step {step_index + 1} ---')

		# Clean-up browser after finishing workflow
		await self.browser.close()
		return results

	# Convenience synchronous wrapper ------------------------------------------------
	def run(self, inputs: dict[str, Any] | None = None) -> List[Any]:
		"""Synchronously execute :py:meth:`run_async` with ``asyncio.run``.

		Args:
			inputs: Dictionary of input values required by the workflow (defined in YAML).
		"""
		return asyncio.run(self.run_async(inputs=inputs))

	# Convenience wrapper to execute a single step synchronously -----------------
	def run_step(self, step_index: int, inputs: dict[str, Any] | None = None) -> Any:
		"""Synchronously execute :py:meth:`run_step_async` for *step_index*."""
		return asyncio.run(self.run_step_async(step_index, inputs=inputs))

	# ------------------------------------------------------------------
	# LangChain tool wrapper
	# ------------------------------------------------------------------

	def _build_input_model(self) -> type[BaseModel]:
		"""Return a *pydantic* model matching the workflow's ``inputs`` section.

		The YAML schema uses a very small subset of JSON-Schema – each property maps
		to a primitive *type string* (``string``, ``number``, ``bool``).  We convert
		that to a dynamic Pydantic model so it can be plugged directly into
		``StructuredTool`` as the ``args_schema``.
		"""
		if not self.inputs_def:
			# No declared inputs → generate an empty model so the tool still works.
			return create_model(f'{self.yaml_path.stem}_NoInputs')  # type: ignore[call-arg]

		props = self.inputs_def.get('properties', {})
		required = set(self.inputs_def.get('required', []))

		type_mapping = {
			'string': str,
			'number': float,
			'bool': bool,
		}
		fields: Dict[str, tuple[type, Any]] = {}
		for name, spec in props.items():
			type_str = spec if isinstance(spec, str) else spec.get('type')  # spec may be string or dict
			py_type = type_mapping.get(type_str)
			if py_type is None:
				raise ValueError(f'Unsupported input type: {type_str!r} for field {name!r}')
			default = ... if name in required else None
			fields[name] = (py_type, default)

		from typing import cast as _cast

		# The raw ``create_model`` helper from Pydantic deliberately uses *dynamic*
		# signatures, which the static type checker cannot easily verify.  We cast
		# the **fields** mapping to **Any** to silence these warnings.
		return create_model(  # type: ignore[arg-type]
			f'{self.yaml_path.stem}_Inputs',
			**_cast(Dict[str, Any], fields),
		)

	def as_tool(self, *, name: str | None = None, description: str | None = None):  # noqa: D401
		"""Expose the entire workflow as a LangChain *StructuredTool* instance.

		The generated tool validates its arguments against the workflow's input
		schema (if present) and then returns the JSON-serialised output of
		:py:meth:`run`.
		"""

		InputModel = self._build_input_model()
		tool_name = name or f'{self.yaml_path.stem}_workflow'
		doc = description or f'Execute the workflow defined in {self.yaml_path.name}'

		# `self` is closed over via the inner function so we can keep state.
		async def _invoke(**kwargs):  # type: ignore[override]
			logger.info(f'Running workflow as tool with inputs: {kwargs}')
			result = await self.run_async(inputs=kwargs if kwargs else None)
			# Serialise non-string output so models that expect a string tool
			# response still work.
			try:
				return _json.dumps(result, default=str)
			except Exception:
				return str(result)

		return StructuredTool.from_function(
			coroutine=_invoke,
			name=tool_name,
			description=doc,
			args_schema=InputModel,
		)

	async def run_as_tool(self, input: str) -> str:
		"""Run the workflow as a tool with the given input.
		Uses AgentExecutor to properly handle the tool invocation loop.
		"""
		# For now I kept it simpel but one could think of using a react agent here.
		if self.llm is None:
			raise ValueError("Cannot run as tool: An 'llm' instance must be supplied for tool-based steps")
		prompt = ChatPromptTemplate.from_messages(
			[
				('system', 'You are a helpful assistant'),
				('human', '{input}'),
				# Placeholders fill up a **list** of messages
				('placeholder', '{agent_scratchpad}'),
			]
		)

		# Create the workflow tool
		workflow_tool = self.as_tool()
		agent = create_tool_calling_agent(self.llm, [workflow_tool], prompt)
		agent_executor = AgentExecutor(agent=agent, tools=[workflow_tool])
		result = await agent_executor.ainvoke({'input': input})
		return result['output']