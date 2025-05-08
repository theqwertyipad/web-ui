import asyncio
import datetime
import json
import os
import uuid
import logging
from importlib import resources
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContextConfig
from browser_use.dom.views import DOMElementNode
from src.utils import utils

@dataclass
class WorkflowStep:
	step_number: int
	type: str
	timestamp: int
	url: str
	cssSelector: Optional[str] = None
	def __init__(self, step_number: int, type: str, url: str, timestamp: int = 0, cssSelector: Optional[str] = None, **kwargs):
		self.step_number = step_number
		self.type = type
		self.url = url
		self.timestamp = timestamp
		self.cssSelector = cssSelector
		# Store additional attributes
		for key, value in kwargs.items():
			setattr(self, key, value)

logger = logging.getLogger(__name__)

class WorkflowRecorder:
	def __init__(self, output_dir: Path, browser_config: Optional[BrowserConfig] = None):
		self.browser_config = browser_config
		self.js_overlay = resources.read_text('src.recorder', 'gui.js')
		self.steps: List[WorkflowStep] = []
		self._overlay_logs: List[str] = []
		self._active_input: Optional[dict] = None
		self._recording_complete = asyncio.Event()
		self.recording = False
		self._should_exit = False
		self._workflow_saved = False
		self.output_dir = output_dir
		self.description = ''
		self.action_name = ''
		self.current_url = ''

	async def update_state(self, context, page):
		await page.evaluate('AgentRecorder.refreshListeners()')
		await self.expose_notify_python(page)

	async def set_recording_state(self, page, state: bool):
		self.recording = state
		await page.evaluate('AgentRecorder.setRecording', state)
		self._active_input = None

	async def ensure_overlay_ready(self, page, timeout=2000):
		try:
			await page.wait_for_selector('#agent-recorder-ui', timeout=timeout)
		except Exception as e:
			await page.evaluate(self.js_overlay, self.recording)
			await page.evaluate('AgentRecorder.setRecording', self.recording)
			await page.wait_for_selector('#agent-recorder-ui', timeout=2000)

	async def overlay_print(self, message: str, page):
		logger.info(message)
		self._overlay_logs.append(message)
		await self.ensure_overlay_ready(page)
		await page.evaluate('(msg) => AgentRecorder.requestOutput(msg)', message)

	async def overlay_input(self, page, mode: str, question: str, placeholder: str = '', choices: list = []) -> str:
		logger.info(f'GUI asking for: {question}')
		if self._should_exit:
			return ''

		await self.ensure_overlay_ready(page)
		self._input_future = asyncio.Future()

		input_data = {
			'mode': mode,
			'question': question,
			'placeholder': placeholder,
			'choices': choices,
		}

		self._active_input = input_data
		await page.evaluate('(data) => AgentRecorder.requestInput(data)', input_data)

		try:
			return await self._input_future
		except asyncio.CancelledError:
			return ''
	
	async def add_step(self, step: WorkflowStep, page):
		self.steps.append(step)
		selector = step.cssSelector if step.cssSelector else "no_selector"
		await page.evaluate(
			'(data) => AgentRecorder.addWorkflowStep(data.action, data.cssSelector)',
			{"action": step.type, "cssSelector": selector}
		)

	async def expose_notify_python(self, page, max_attempts=2, delay=0.2):
		"""Attempt to expose the notifyPython function with retries."""
		for attempt in range(max_attempts):
			try:
				await page.expose_function('notifyPython', self._notify_python)
				logger.info(f'[🔗] notifyPython exposed on attempt {attempt + 1}')
				# Mock evaluation to check if the function is exposed
				is_exposed = await page.evaluate('typeof window.notifyPython === "function"')
				if is_exposed:
					logger.info('[✅] notifyPython is callable from the page')
					# Set up a future to capture the mock call
					self._mock_future = asyncio.Future()
					for mock_attempt in range(max_attempts):
						try:
							await page.evaluate('window.notifyPython("mock_test", {})')
							await asyncio.wait_for(self._mock_future, timeout=1.0)
							logger.info('[✅] Mock call successfully received')
							return
						except Exception as mock_err:
							logger.info('[⚠️] Mock call attempt {mock_attempt + 1} failed: {mock_err}')
							await page.reload()
							logger.info('[🔄] Page reloaded, retrying the process...')
							await asyncio.sleep(delay)
					logger.info('[❌] Failed to receive mock call after maximum attempts')
					continue
				else:
					logger.info('[⚠️] notifyPython is not callable, retrying...')
			except Exception as expose_err:
				if 'has been already registered' in str(expose_err):
					return
				else:
					logger.info(f'[⚠️] Attempt {attempt + 1} failed: {expose_err}')
			await asyncio.sleep(delay)
		logger.info('[❌] Failed to expose notifyPython after maximum attempts')

	async def record_workflow(self, url: str, context_config: Optional[BrowserContextConfig] = None):
		"""Record a workflow by following user clicks and keyboard input"""
		browser = Browser(config=self.browser_config or BrowserConfig())

		context = None
		try:
			merged_config = context_config or BrowserContextConfig(
				highlight_elements=True,
				viewport_expansion=500,
				minimum_wait_page_load_time=1.0,
				wait_for_network_idle_page_load_time=2.0,
				maximum_wait_page_load_time=30.0,
				disable_security=True,
			)
			context = await browser.new_context(config=merged_config)
			page = await context.get_current_page()
			page.set_default_navigation_timeout(10000)
			await page.evaluate(self.js_overlay, self.recording)

			async def handle_page_load(page) -> None:
				# Let patchright load
				await asyncio.sleep(1)
				# Check if the overlay is already present
				is_overlay_present = await page.evaluate('document.querySelector("#agent-recorder-ui") !== null')
				if not is_overlay_present:
					# Reinject overlay if not present
					await page.evaluate(self.js_overlay, self.recording)
				await page.wait_for_selector('#agent-recorder-ui', timeout=2000)
				
				# Restore recording state
				await page.evaluate('(state) => AgentRecorder.setRecording(state)', self.recording)
				
				# Re-expose notifyPython function with retry
				await self.expose_notify_python(page)
				
				for msg in self._overlay_logs:
					await page.evaluate('(msg) => AgentRecorder.requestOutput(msg)', msg)
				
				# Restore input
				if self._active_input:
					await page.evaluate('(data) => AgentRecorder.requestInput(data)', self._active_input)
				# Restore steps in the side panel
				for step in self.steps:
					selector = step.cssSelector if step.cssSelector else "no_selector"
					await page.evaluate(
						'(data) => AgentRecorder.addWorkflowStep(data.action, data.cssSelector)',
						{"action": step.type, "cssSelector": selector}
					)
			page.on('load', handle_page_load)

			async def handle_navigation(frame):
				if frame == page.main_frame: 
					if self.current_url != page.url:
						logger.info(f'Navigation detected: {page.url}')
						await self.update_state(context, page)
						new_url = page.url
						self.current_url = new_url
						if self.recording:
							step = WorkflowStep(
								step_number=len(self.steps) + 1,
								type='navigation',
								url=new_url,
								timestamp=int(datetime.datetime.now().timestamp() * 1000)
							)
							await self.add_step(step, page)
							self.current_url = new_url
			page.on('framenavigated', handle_navigation)

			await asyncio.sleep(1)
			await self.overlay_print(f'Navigating to {url}...', page)
			await self.overlay_print(f'If the actions are not recorded, refresh the page!', page)
			try:
				await page.goto(url, wait_until='domcontentloaded', timeout=10000)
			except Exception as e:
				await self.overlay_print(f'Error navigating to {url}: {str(e)}', page)
				return

			async def notify_python(event_type, payload):
				page = await context.get_current_page()
				# 🔓 Allow control and submitOverlayInput events always
				if event_type not in ['control', 'submitOverlayInput', 'mock_test'] and not self.recording:
					await self.overlay_print(f"[[⚠️]] Received '{event_type}' while not recording — ignoring.", page)
					return
				# Handle mock_test for connection verification
				if event_type == 'mock_test':
					if hasattr(self, '_mock_future') and not self._mock_future.done():
						self._mock_future.set_result(True)
						return

				if event_type == 'submitOverlayInput':
					if hasattr(self, '_input_future') and not self._input_future.done():
						self._input_future.set_result(payload)

				elif event_type == 'elementClick':
					attributes = {
						'frameUrl': payload.get('frameUrl', ''),
						'xpath': payload.get('xpath', ''),
						'cssSelector': payload.get('cssSelector', ''),
						'elementTag': payload.get('elementTag', ''),
						'elementText': payload.get('elementText', '')
					}
					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						type='click',
						url=payload.get('url', ''),
						timestamp=int(datetime.datetime.now().timestamp() * 1000),
						**attributes
					)
					await self.add_step(step, page)
					await self.overlay_print(f'[🖱️] Recorded click', page)
					await self.update_state(context, page)

				elif event_type == 'elementInput':
					attributes = {
						'frameUrl': payload.get('frameUrl', ''),
						'xpath': payload.get('xpath', ''),
						'cssSelector': payload.get('cssSelector', ''),
						'elementTag': payload.get('elementTag', ''),
						'value': payload.get('value', ''),
					}
					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						type='input',
						url=payload.get('url', ''),
						timestamp=payload.get('timestamp', int(datetime.datetime.now().timestamp() * 1000)),
						**attributes
					)
					await self.add_step(step, page)
					await self.overlay_print(f'[⌨️] Recorded {getattr(step, "elementTag", "unknown element")} into', page)
					await self.update_state(context, page)
				elif event_type == 'elementChange':
					attributes = {
						'frameUrl': payload.get('frameUrl', ''),
						'xpath': payload.get('xpath', ''),
						'cssSelector': payload.get('cssSelector', ''),
						'elementTag': payload.get('elementTag', ''),
						'selected_value': payload.get('selectedValue', ''),
						'selected_text ': payload.get('selectedText', '')
					}
					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						type='select_change',
						url=payload.get('url', ''),
						timestamp=payload.get('timestamp', int(datetime.datetime.now().timestamp() * 1000)),
						**attributes
					)
					await self.add_step(step, page)
					await self.overlay_print(f'[☑️] Recorded a selection', page)
					await self.update_state(context, page)
				elif event_type == 'keydownEvent':
					attributes = {
						'frameUrl': payload.get('frameUrl', ''),
						'key':payload.get('key', ''),
						'xpath': payload.get('xpath', ''),
						'cssSelector': payload.get('cssSelector', ''),
						'elementTag': payload.get('elementTag', '')
					}
					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						type='key_press',
						url=payload.get('url', ''),
						timestamp=payload.get('timestamp', int(datetime.datetime.now().timestamp() * 1000)),
						**attributes
					)
					await self.add_step(step, page)
					await self.overlay_print(f'[⌨️] Recorded keydown: {payload.get("key", "")}', page)
					await self.update_state(context, page)

				elif event_type == 'navigation':
					url = payload.get('url', '')
					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						type='navigation',
						url=url,
						timestamp=int(datetime.datetime.now().timestamp() * 1000)
					)
					await self.add_step(step, page)
					await self.overlay_print(f'[🌐] Recorded navigation to {url}', page)
					await self.update_state(context, page)
				
				elif event_type == 'deleteStep':
					index = payload.get('index', '')
					if isinstance(index, int) and 0 <= index < len(self.steps):
						removed_step = self.steps.pop(index)
						await self.overlay_print(f'Deleted step {removed_step.step_number}: {removed_step.type}', page)
						# Update step numbers for remaining steps
						for idx, step in enumerate(self.steps):
							step.step_number = idx + 1
					else:
						await self.overlay_print('[⚠️] Invalid index for deletion', page)
					await self.update_state(context, page)
				
				elif event_type == 'reorderSteps':
					step_data = payload.get('step', {})
					if not step_data:
						await self.overlay_print('[⚠️] No step provided for reordering', page)
						return

					action = step_data.get('action', '')
					css_selector = step_data.get('cssSelector', '')
					original_index = step_data.get('originalIndex')
					new_index = step_data.get('newIndex')

					# Validate indices
					if not isinstance(original_index, int) or not isinstance(new_index, int):
						await self.overlay_print('[⚠️] Invalid or missing indices for reordering', page)
						return
					if original_index < 0 or original_index >= len(self.steps) or new_index < 0 or new_index >= len(self.steps):
						await self.overlay_print('[⚠️] Index out of bounds for reordering', page)
						return
					if original_index == new_index:
						await self.overlay_print('[ℹ️] No change in step position', page)
						return

					# Validate the step at original_index matches action and cssSelector
					moved_step = self.steps[original_index]
					expected_key = (action, css_selector) if action.lower() != 'navigation' else (action,)
					actual_key = (moved_step.type, moved_step.cssSelector) if moved_step.type.lower() != 'navigation' else (moved_step.type,)
					if expected_key != actual_key:
						await self.overlay_print(f'[⚠️] Step at index {original_index} does not match provided action or selector', page)
						return

					# Move the step
					self.steps.pop(original_index)
					self.steps.insert(new_index, moved_step)

					# Update step_number for all steps
					for idx, step in enumerate(self.steps):
						step.step_number = idx + 1

					await self.overlay_print(f'[🔄] Moved step', page)
					await self.update_state(context, page)

				elif event_type == 'control':
					action = payload.get('action')
					if action == 'start':
						await self.set_recording_state(page, True)
						self._workflow_saved = False
						await self.overlay_print(f'[🟢] Recording started.', page)
						# Setting as first step the URL
						step = WorkflowStep(
							step_number=1,
							type='navigation',
							url=page.url,
							timestamp=int(datetime.datetime.now().timestamp() * 1000)
						)
						await self.add_step(step, page)
					elif action == 'finish':
						await self.set_recording_state(page, False)
						self._active_input = None  # This can cause problems in the future
						await self.overlay_print('[⛔️] Recording stopped. Saving recording...', page)
						await self.save_workflow(page)

						# Delay to allow the GUI to render non-recording mode fully. This is important
						await asyncio.sleep(1)
						self.steps =[]
						await self.update_state(context, page)

					elif action == 'update':
						await self.overlay_print('Updating state', page)
						await self.update_state(context, page)
						await self.overlay_print('State updated', page)
					elif action == 'back':
						if self.steps:
							removed = self.steps.pop()
							await self.overlay_print(f'[↩️] Removed step {removed.step_number}: {removed.type}', page)
							await self.update_state(context, page)
					elif action == 'close':
						await self.set_recording_state(page, False)
						self._active_input = None

						if hasattr(self, '_input_future') and not self._input_future.done():
							self._input_future.cancel()

						await self.overlay_print('[⛔️] Recording stopped. Saving recording...', page)
						await self.save_workflow(page)
						await self.overlay_print('[[📁]] Closing recorder session...', page)
						self._should_exit = True
						await context.remove_highlights()
						self._recording_complete.set()

			self._notify_python = notify_python
			await self.expose_notify_python(page)

			def handle_browser_close(page):
				logger.info('Recorder browser instance closed by user forcefully.')
				self._should_exit = True
				self._recording_complete.set()
			page.on('close', handle_browser_close)

			await self._recording_complete.wait()

		except Exception as e:
			await self.overlay_print(f'[🔴] An unexpected error occurred during recording: {str(e)}', page)
			if self.steps:
				await self.overlay_print('Attempting to save partial recording due to error...', page)
				await self.save_workflow(page)
			raise

		finally:
			self.recording = False
			if self.steps and not self._workflow_saved:
				await self.overlay_print('Finalizing recodring save...', page)
				await self.save_workflow(page)
			elif not self.steps:
				await self.overlay_print('No steps were recorded.', page)
			
			# Clear steps after all operations
			if self._should_exit:
				self.steps = []

			if context:
				try:
					await context.close()
					logger.info('Recorder browser context closed.')
				except Exception as close_err:
					await self.overlay_print(f'Warning: Error closing browser context: {str(close_err)}', page)
			

	async def save_workflow(self, page):
		"""Save the recorded workflow to a file and return success status"""
		if self._workflow_saved:
			await self.overlay_print('[↩️] Recording already saved, skipping.', page)
		# Check if there are no steps or only one step with 'navigation' type
		if not self.steps or (len(self.steps) == 1 and self.steps[0].type == 'navigation'):
			self._workflow_saved = True
			await self.overlay_print('[↩️] No meaningful steps to save, skipping recording save.', page)
		try:
			# Use a default directory for the output
			output_dir_path = self.output_dir
			os.makedirs(output_dir_path, exist_ok=True)

			# Use a timestamp and UUID for the filename
			filename = f'recording_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
			filepath = os.path.join(output_dir_path, filename)

			logger.info(f'Attempting to save recording to: {filepath}')

			workflow_data = {
				'timestamp': datetime.datetime.now().isoformat(),
				'name': self.action_name,
				'total_steps': len(self.steps),
				'description': self.description,
				'steps': [
					{
						**step.__dict__,
					}
					for step in self.steps
				],
			}

			with open(filepath, 'w', encoding='utf-8') as f:
				json.dump(workflow_data, f, indent=4, ensure_ascii=False)

			# Verify the file was created
			if os.path.exists(filepath):
				file_size = os.path.getsize(filepath)
				self._workflow_saved = True
				await self.overlay_print('[✅] Workflow saved successfully.', page)
			else:
				await self.overlay_print('[❌] Failed to save workflow.', page)

		except Exception as e:
			logger.info(f'[❌] Error saving recording: {str(e)}')
			# Try to save to a fallback location
			try:
				fallback_path = os.path.join(os.getcwd(), 'workflow_fallback.json')
				logger.info(f'Attempting to save to fallback location: {fallback_path}')
				with open(fallback_path, 'w', encoding='utf-8') as f:
					json.dump(workflow_data, f, indent=4, ensure_ascii=False)
				self._workflow_saved = True
				await self.overlay_print('[✅] Workflow saved successfully.', page)
			except Exception as fallback_error:
				await self.overlay_print(f'[❌] Failed to save workflow: {str(fallback_error)}', page)
