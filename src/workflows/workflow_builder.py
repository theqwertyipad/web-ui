import base64
import json
import logging
from pathlib import Path
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate

from browser_use.controller.service import Controller
from browser_use.workflows.prompts import workflow_builder_template
from browser_use.workflows.workflow import Workflow

EXAMPLE_YAML_PATH = Path(__file__).with_name('linkedin_workflow.yaml')

logger = logging.getLogger(__name__)


def _available_actions_markdown() -> str:
	"""Return a bullet list with available deterministic actions and their descriptions."""
	controller = Controller()
	lines: list[str] = []
	for action in controller.registry.registry.actions.values():
		lines.append(f'- **{action.name}**: {action.description}')
		lines.append(f'  - params: {action.param_model.model_json_schema()}')
	return '\n'.join(lines)


def _prune_event(event: dict) -> dict:
	"""Return a shallow copy of *event* with any screenshot payload removed.

	Some recorders store the base-64 screenshot on the top-level ``screenshot`` key,
	or inside a nested ``data`` mapping.  Because the raw payload can be very large
	(and thus very expensive to send to the LLM in text form) we strip it out
	before serialising the event JSON for the prompt.  We keep the *original* event
	object untouched so that the binary data can still be attached to the prompt
	as an *image_url* when screenshots are enabled.
	"""
	event = event.copy()
	event.pop('screenshot', None)
	if isinstance(event.get('data'), dict):
		event['data'] = event['data'].copy()
		event['data'].pop('screenshot', None)
	return event


# -----------------------------------------------------------------------------
# Prompt helpers
# -----------------------------------------------------------------------------


def _event_to_messages(event: dict, include_screenshot: bool) -> list[dict[str, Any]]:
	"""Convert a *single* session *event* into a list of OpenAI vision messages.

	The first message is always a ``text`` chunk containing the pruned JSON of the
	event.  If *include_screenshot* is ``True`` **and** the event contains a valid
	Base-64 screenshot, two additional messages are appended: a short textual
	caption followed by the binary image payload encoded as a ``data:` URI.  Doing
	it this way keeps the screenshot *adjacent* to its corresponding event, which
	greatly helps the model associate the visual context with the structured log
	entry.
	"""
	messages: list[dict[str, Any]] = []

	# 1) textual representation of the event without the bulky screenshot field
	pruned = _prune_event(event)
	messages.append({'type': 'text', 'text': json.dumps(pruned, indent=2)})

	# 2-3) optional screenshot if requested and available
	if not include_screenshot:
		return messages

	# Accept both top-level and nested variants
	screenshot: str | None = event.get('screenshot') or event.get('data', {}).get('screenshot')
	if screenshot and screenshot.startswith('data:'):
		# The recorder may have stored a full data-URI.  Strip the scheme/prefix so
		# that we are left with *just* the raw Base-64 payload that
		# ``base64.b64decode`` expects.
		screenshot = screenshot.split(',', 1)[-1]

	# Validate base-64 payload – discard if invalid to avoid API errors
	try:
		base64.b64decode(cast(str, screenshot), validate=True)
	except Exception:
		logger.warning(f'Invalid screenshot for event {event.get("type", "unknown")} @ {event.get("timestamp", "")}')
		return messages

	meta = f'Screenshot for event {event.get("type", "unknown")} @ {event.get("timestamp", "")}'
	logger.warning(meta)
	messages.append({'type': 'text', 'text': meta})
	messages.append(
		{
			'type': 'image_url',
			'image_url': {'url': f'data:image/png;base64,{screenshot}'},
		}
	)

	return messages


def _prepare_event_messages(events: list[dict], include_screenshots: bool, max_images: int = 100) -> list[dict[str, Any]]:
	"""Return a flattened list of vision messages for *events*.

	The function walks over the events in chronological order, emitting the text
	record (and optional screenshot) for each.  To stay within the token and
	cost budget we cap the *total* number of screenshots that will be attached
	via the *max_images* parameter (default: 8).
	"""
	messages: list[dict[str, Any]] = []
	images_used = 0

	for evt in events:
		# Decide whether we can still attach screenshots for this event
		attach_image = include_screenshots and images_used < max_images

		chunk = _event_to_messages(evt, attach_image)
		messages.extend(chunk)

		# Update image counter – each _event_to_messages attaches at most *one*
		# image so a simple increment is sufficient.
		if attach_image and len(chunk) > 1:
			images_used += 1

	return messages


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

# NOTE: Screenshots can significantly increase token usage (and cost). They are
# therefore disabled by default and can be enabled explicitly via the
# *use_screenshots* parameter or the CLI flag ``--use-screenshots``.


def parse_session(
	session_path: str,
	user_goal: str | None = None,
	use_screenshots: bool = True,
	llm: BaseChatModel | None = None,
) -> Workflow:
	"""Generate a Workflow YAML from a *simplified session* JSON file using an LLM.

	The resulting YAML is saved next to *session_path* with suffix ``.yaml`` and a
	:class:`Workflow` instance is returned for immediate use.
	"""

	assert llm is not None, 'A ``BaseChatModel`` instance must be supplied to ``parse_session``'

	session_file = Path(session_path)
	with session_file.open('r', encoding='utf-8') as fp:
		session_events: list[dict] = json.load(fp)

	# Ask user for goal description if not supplied
	if user_goal is None:
		try:
			user_goal = input(
				'Please describe the high-level task you want the workflow to accomplish (press Enter to skip): '
			).strip()
		except EOFError:
			# In non-interactive environments just fall back to empty string
			user_goal = ''
	user_goal = user_goal or ''

	# Read example YAML (truncate if very large)
	example_yaml = ''
	if EXAMPLE_YAML_PATH.exists():
		example_yaml = EXAMPLE_YAML_PATH.read_text(encoding='utf-8')

	prompt = PromptTemplate.from_template(workflow_builder_template)

	# Instead of inlining the entire event log in the main prompt we will stream
	# each event (and its nearby screenshot) as *separate* messages.  This keeps
	# related visual context tightly coupled to the structured data and avoids
	# the pathological "events first, screenshots last" ordering.
	prompt_str = prompt.format(
		actions=_available_actions_markdown(),
		example=example_yaml,
		events='Events will follow one-by-one in subsequent messages.',
		goal=user_goal,
	)

	vision_messages: list[dict[str, Any]] = [
		{
			'type': 'text',
			'text': prompt_str,
		}
	]

	# Always append the chronological event stream – with or without images – so
	# that the model can rely on a consistent structure.
	vision_messages.extend(_prepare_event_messages(session_events, include_screenshots=use_screenshots))

	yaml_response = llm.invoke([HumanMessage(content=cast(Any, vision_messages))])

	yaml_content: str = str(yaml_response.content).strip()

	# Validate that action types match the model
	prompt_str = (
		prompt_str
		+ "\n\nIMPORTANT: Please ensure that all parameter types in the generated YAML strictly conform to the input models defined for each action. For example, if an action expects a 'url' parameter of type string, the YAML must provide a string value, not a number or boolean. Check each parameter against its corresponding model definition."
	)

	# Ask model to validate types
	validation_messages: list[dict[str, Any]] = [{'type': 'text', 'text': prompt_str + '\n\nGenerated YAML:\n' + yaml_content}]
	validation_response = llm.invoke([HumanMessage(content=cast(Any, validation_messages))])
	yaml_content = str(validation_response.content).strip()

	# Persist YAML next to original JSON file
	yaml_path = session_file.with_suffix('.workflow.yaml')
	yaml_path.write_text(yaml_content, encoding='utf-8')

	# Return a ready-to-use Workflow instance
	return Workflow(yaml_path=str(yaml_path))


if __name__ == '__main__':
	import argparse

	parser = argparse.ArgumentParser(description='Generate a browser-use workflow from a recorded session JSON file.')
	parser.add_argument('session_json', help='Path to the simplified session JSON file')
	parser.add_argument('--goal', dest='goal', help='High-level goal description for the workflow', default=None)
	parser.add_argument(
		'--use-screenshots',
		action='store_true',
		help='Include up to 8 screenshots in the LLM prompt (higher token usage)',
	)

	args = parser.parse_args()

	workflow = parse_session(
		session_path=args.session_json,
		user_goal=args.goal,
		use_screenshots=args.use_screenshots,
	)
	print(workflow.yaml_path)
