import asyncio
import datetime
import json
import os
from importlib import resources
from typing import List, Optional
from dataclasses import dataclass

from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContextConfig
from browser_use.dom.views import DOMElementNode
from src.utils import utils

@dataclass
class WorkflowStep:
	step_number: int
	action_type: str
	clicked_element: dict
	url_before: str
	url_after: str
	typed_text: str = ''


class WorkflowRecorder:
	def __init__(self):
		self.output_dir = ''
		self.steps: List[WorkflowStep] = []
		self.recording = False
		self.typed_text = ''
		self.js_overlay = resources.read_text('src.recorder', 'gui.js')
		self._overlay_logs: List[str] = []
		self._active_input: Optional[dict] = None
		self.has_navigated = False
		self._validated_elements = {}
		self._recording_complete = asyncio.Event()
		self._should_exit = False
		self.description = ''

	async def update_state(self, context, page):
		self.current_state = await context._get_updated_state()
		await page.evaluate('AgentRecorder.refreshListeners()')
		await self.overlay_print('[🔄] State and listeners refreshed.', page)
		try:
			await page.expose_function('notifyPython', self._notify_python)
			print('[🔗] Re-exposed notifyPython')
		except Exception as expose_err:
			print(f'[⚠️] Could not re-expose notifyPython: {expose_err}')

	async def set_recording_state(self, page, state: bool):
		self.recording = state
		await page.evaluate('AgentRecorder.setRecording', state)
		self._active_input = None

	async def ensure_overlay_ready(self, page):
		try:
			await page.wait_for_selector('#agent-recorder-ui', timeout=2000)
		except Exception as e:
			await page.evaluate(self.js_overlay, self.recording)
			await page.evaluate('AgentRecorder.setRecording', self.recording)
			await page.wait_for_selector('#agent-recorder-ui', timeout=2000)

	async def overlay_print(self, message: str, page):
		print(message)
		self._overlay_logs.append(message)
		await self.ensure_overlay_ready(page)
		await page.evaluate('(msg) => AgentRecorder.requestOutput(msg)', message)

	async def overlay_input(self, page, mode: str, question: str, placeholder: str = '', choices: list = []) -> str:
		print(f'[🔧 overlay_input] Asking for: {question}')
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

	async def monitor_gui_and_state(self, page, context, interval=2.0):
		"""Continuously check if the GUI is present and update the state if recording."""
		last_path_hashes = set()
		while not self._should_exit:  # Check for exit condition
			try:
				# Check for GUI presence
				is_overlay_visible = await page.evaluate("document.querySelector('#agent-recorder-ui') !== null")
				if not is_overlay_visible:
					print('[🔁] Reinjecting GUI overlay...')
					await page.evaluate(self.js_overlay, self.recording)
					await page.evaluate('AgentRecorder.setRecording', self.recording)
					await asyncio.sleep(1.0)  # Wait for DOM to stabilize

					# Re-expose notifyPython function
					try:
						await page.expose_function('notifyPython', self._notify_python)
						print('[🔗] Re-exposed notifyPython')
					except Exception as expose_err:
						print(f'[⚠️] Could not re-expose notifyPython: {expose_err}')

					# Restore logs
					for msg in self._overlay_logs:
						await page.evaluate('(msg) => AgentRecorder.requestOutput(msg)', msg)

					# Restore input
					if self._active_input:
						await page.evaluate('(data) => AgentRecorder.requestInput(data)', self._active_input)
					# Restore steps in the side panel
					for step in self.steps:
						if step.action_type.startswith('type'):
							action = 'Type text'
							validator = step.typed_text
						else:
							action = f'{step.action_type.title()} on {step.clicked_element.get("tag_name", "element")}'
							validator = step.clicked_element.get('validator', '')

						await page.evaluate(
							'(action, validator) => AgentRecorder.addWorkflowStep(action, validator)',
							action,
							validator,
						)

			except Exception as e:
				print(f'[⚠️] Background monitor error: {str(e)}')

			await asyncio.sleep(interval)

	async def get_element_info(self, element: DOMElementNode, page, element_handle) -> dict:
		"""Get comprehensive info about an element"""
		if element.xpath in self._validated_elements:
			await self.overlay_print('Using a preknown validator', page)
			return self._validated_elements[element.xpath]  # 💾 Reuse!
		visual_marker = await utils.get_visual_marker_for_xpath(page, element.xpath)

		# Gather potential validators
		potential_validators = []
		if element.attributes.get('href'):
			potential_validators.append((element.attributes['href'], 'href'))
		if element_handle:
			element_text = await element_handle.inner_text()
			if element_text:
				potential_validators.append((element_text, 'text'))
		if visual_marker != '':
			potential_validators.append((visual_marker, 'visual_element'))
		if element.attributes.get('title'):
			potential_validators.append((element.attributes['title'], 'title'))
		if element.attributes.get('aria-label'):
			potential_validators.append((element.attributes['aria-label'], 'aria-label'))
		if element.attributes.get('id'):
			potential_validators.append((element.attributes['id'], 'id'))
		if element.attributes.get('class'):
			potential_validators.append((element.attributes['class'], 'class'))
		if element.attributes.get('src'):
			potential_validators.append((element.attributes['src'], 'src'))
		if element.attributes.get('placeholder'):
			potential_validators.append((element.attributes['placeholder'], 'placeholder'))
		if element.attributes.get('name'):
			potential_validators.append((element.attributes['name'], 'name'))
		if element.attributes.get('role'):
			potential_validators.append((element.attributes['role'], 'role'))
		if element.attributes.get('alt'):
			potential_validators.append((element.attributes['alt'], 'alt'))

		choices = [f'{v[1]}: {v[0]}' for v in potential_validators] + ['Abort: None of the validators are good enough']

		selected_validator = await self.overlay_input(
			page, mode='radio', question='Select a validator for this element', choices=choices
		)
		selected_validator = selected_validator if selected_validator else None

		# Determine the selected validator and its type
		validator, validator_type = None, None
		if selected_validator:
			for v in potential_validators:
				if f'{v[1]}: {v[0]}' == selected_validator:
					validator, validator_type = v
					break

		# Allow editing of the validator if 'href' or 'text' is chosen
		if validator_type in ['href', 'text']:
			new_value = await self.overlay_input(
				page, mode='text', question=f'Edit the {validator_type} value', placeholder=validator or ''
			)
			if new_value:
				validator = new_value

		if selected_validator == "Abort: The validators are bad or there aren't any":
			await self.overlay_print('User aborted the usage of the element due to unsatisfactory validators.', page)
			return {}

		result = {
			'text': element_text or '',
			'title': element.attributes.get('title', ''),
			'xpath': element.xpath,
			'href': element.attributes.get('href', ''),
			'visual_marker': visual_marker,
			'tag_name': element.tag_name,
			'attributes': element.attributes,
			'validator': validator,
			'validator_type': validator_type,
		}
		self._validated_elements[element.xpath] = result
		return result

	async def get_state_info(self, state, page) -> dict:
		"""Get comprehensive info about all elements in the state"""
		state_info = {}
		for k, v in state.selector_map.items():
			state_info[str(k)] = await self.get_element_info(v, page, v.element_handle)
		return state_info

	async def switch_tab(self, context):
		"""Switch to the next tab in line, wrapping around if necessary."""
		await context.switch_to_tab(0)

	async def record_workflow(self, url: str):
		"""Record a workflow by following user clicks and keyboard input"""
		browser = Browser(
			# config=BrowserConfig(browser_binary_path='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'),
		)

		context_config = BrowserContextConfig(
			highlight_elements=True,
			viewport_expansion=500,
			minimum_wait_page_load_time=1.0,
			wait_for_network_idle_page_load_time=2.0,
			maximum_wait_page_load_time=30.0,
			disable_security=True,
		)

		context = None
		try:
			context = await browser.new_context(config=context_config)
			page = await context.get_current_page()
			page.set_default_navigation_timeout(10000)
			await page.evaluate(self.js_overlay, self.recording)
			await page.evaluate('AgentRecorder.setRecording', self.recording)
			asyncio.create_task(self.monitor_gui_and_state(page, context))

			await asyncio.sleep(1)
			if not self.has_navigated:
				self.has_navigated = True
				await self.overlay_print(f'Navigating to {url}...', page)
				try:
					await page.goto(url, wait_until='domcontentloaded', timeout=10000)
					await self.overlay_print('Page loaded!', page)
				except Exception as e:
					await self.overlay_print(f'Error navigating to {url}: {str(e)}', page)
					return
			await self.set_recording_state(page, False)

			async def notify_python(event_type, payload):
				page = await context.get_current_page()
				# 🔓 Allow control and submitOverlayInput events always
				if event_type not in ['control', 'submitOverlayInput'] and not self.recording:
					await self.overlay_print(f"⚠️ Received '{event_type}' while not recording — ignoring.", page)
					return

				if event_type == 'submitOverlayInput':
					if hasattr(self, '_input_future') and not self._input_future.done():
						self._input_future.set_result(payload)

				elif event_type == 'elementClick':
					index = int(payload.get('index'))
					state = self.current_state
					clicked_element = state.selector_map.get(index)
					if not clicked_element:
						await self.overlay_print(f'⚠️ No element found at index {index}', page)
						return

					element_handle = await page.query_selector(f'xpath={clicked_element.xpath}')
					clicked_element_info = await self.get_element_info(clicked_element, page, element_handle)
					if not clicked_element_info:
						await self.overlay_print('⚠️ Skipping click: user rejected validator.', page)
						return
					try:
						download_path = await context._click_element_node(clicked_element)
						if download_path:
							print(f'💾  Downloaded file to {download_path}')
						else:
							print(f'🖱️  Clicked button with index {index}: {clicked_element_info["text"]}')
					except Exception as e:
						print(f'Element not clickable with index {index}: {str(e)}')
					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						action_type='click',
						clicked_element=clicked_element_info,
						url_before=page.url,
						url_after=page.url,
					)
					self.steps.append(step)
					print('setting to gui')
					await page.evaluate(
						'(args) => AgentRecorder.addWorkflowStep(args[0], args[1])',
						[
							step.action_type if not step.typed_text else 'Type text',
							step.typed_text or step.clicked_element.get('validator', ''),
						],
					)
					print('setting to gui')
					await self.overlay_print(f'🖱️ Recorded click {index}', page)
					await self.update_state(context, page)

				elif event_type == 'elementType':
					index = int(payload.get('index'))
					text = payload.get('text', '')
					mode = payload.get('mode', 'enter')  # Default to enter if not specified

					# KEEPING OUT THE ELEMENT FOR NOW FOR EASIER EXECUTION
					# state = self.current_state
					# typed_element = state.selector_map.get(index)
					# if not typed_element:
					#     await self.overlay_print(f"⚠️ No element found at index {index}", page)
					#     return

					# element_handle = await page.query_selector(f'xpath={typed_element.xpath}')
					# typed_element_info = await self.get_element_info(typed_element, page, element_handle)
					# if not typed_element_info:
					#     await self.overlay_print("⚠️ Skipping type: user rejected validator.", page)
					#     return

					action_type = 'type-enter' if mode == 'enter' else 'type-then-click'

					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						action_type=action_type,
						clicked_element={},
						url_before=page.url,
						url_after=page.url,
						typed_text=text,
					)
					self.steps.append(step)
					print('setting to gui')
					await page.evaluate(
						'(args) => AgentRecorder.addWorkflowStep(args[0], args[1])',
						[
							step.action_type if not step.typed_text else 'Type text',
							step.typed_text or step.clicked_element.get('validator', ''),
						],
					)
					print('setting to gui')
					await self.overlay_print(f"⌨️ Recorded {action_type} into index {index}: '{text}'", page)
					await self.update_state(context, page)

				elif event_type == 'control':
					action = payload.get('action')
					if action == 'start':
						await self.set_recording_state(page, True)
						await self.overlay_print('🟢 Recording started.', page)
					elif action == 'finish':
						await self.set_recording_state(page, False)
						self._active_input = None  # This can cause problems in the future
						await self.overlay_print('⛔️ Recording stopped. Saving workflow...', page)
						self.save_workflow()

						# Delay to allow the GUI to render non-recording mode fully. This is important
						await asyncio.sleep(1)
						await context.remove_highlights()

						action_name = await self.overlay_input(page, 'text', 'Enter the name for this workflow:')
						if not action_name:
							await self.overlay_print('Workflow name cannot be empty. Please enter a valid name.', page)
							return

						self.action_name = action_name

						output_dir = await self.overlay_input(page, 'text', 'Enter the output directory for this workflow:')
						if not output_dir:
							await self.overlay_print('Output directory cannot be empty. Please enter a valid directory.', page)
							return

						self.output_dir = output_dir

						action_description = await self.overlay_input(
							page, 'text', 'Enter a description for this action and start recording:'
						)
						if not action_description:
							await self.overlay_print(
								'Action description cannot be empty. Please enter a valid description.', page
							)
							return

						self.description = action_description

						await self.set_recording_state(page, True)
						await self.update_state(context, page)

					elif action == 'update':
						await self.overlay_print('Updating state', page)
						await self.update_state(context, page)
						await self.overlay_print('State updated', page)
					elif action == 'back':
						if self.steps:
							removed = self.steps.pop()
							await self.overlay_print(f'↩️ Removed step {removed.step_number}: {removed.action_type}', page)
							await self.update_state(context, page)
					elif action == 'close':
						await self.set_recording_state(page, False)
						self._active_input = None
						self._should_exit = True

						if hasattr(self, '_input_future') and not self._input_future.done():
							self._input_future.cancel()

						self.save_workflow()
						await self.overlay_print('⛔️ Recording stopped. Saving workflow...', page)
						await self.overlay_print('📁 Closing recorder session...', page)
						await context.remove_highlights()
						self._recording_complete.set()

			self._notify_python = notify_python
			await page.expose_function('notifyPython', self._notify_python)

			action_name = await self.overlay_input(page, 'text', 'Enter the name for this workflow:')
			if not action_name:
				await self.overlay_print('Workflow name cannot be empty. Please enter a valid name.', page)
				return

			self.action_name = action_name

			output_dir = await self.overlay_input(page, 'text', 'Enter the output directory for this workflow:')
			if not output_dir:
				await self.overlay_print('Output directory cannot be empty. Please enter a valid directory.', page)
				return

			self.output_dir = output_dir

			action_description = await self.overlay_input(
				page, 'text', 'Enter a description for this action and start recording:'
			)
			if not action_description:
				await self.overlay_print('Action description cannot be empty. Please enter a valid description.', page)
				return

			self.description = action_description

			await self.set_recording_state(page, True)
			await self.update_state(context, page)

			await self._recording_complete.wait()
			print('DONE')

		except Exception as e:
			await self.overlay_print(f'An unexpected error occurred during recording: {str(e)}', page)
			if self.steps:
				await self.overlay_print('Attempting to save partial workflow due to error...', page)
				self.save_workflow()
			raise

		finally:
			self.recording = False
			if self.steps:
				await self.overlay_print('Finalizing workflow save...', page)
				self.save_workflow()
				await self.overlay_print('Workflow saving process complete.', page)
			else:
				await self.overlay_print('No steps were recorded.', page)

			if context:
				try:
					await context.close()
					await self.overlay_print('Browser context closed.', page)
				except Exception as close_err:
					await self.overlay_print(f'Warning: Error closing browser context: {str(close_err)}', page)

	def save_workflow(self):
		"""Save the recorded workflow to a file"""
		try:
			# Ensure the output directory exists
			output_dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.output_dir)
			os.makedirs(output_dir_path, exist_ok=True)

			workflow_data = {
				'timestamp': datetime.datetime.now().isoformat(),
				'action_name': self.action_name,
				'total_steps': len(self.steps),
				'description': self.description,
				'steps': [
					{
						'step_number': step.step_number,
						'action_type': step.action_type,
						'clicked_element': {
							**step.clicked_element,
							'validator': step.clicked_element.get('validator'),
							'validator_type': step.clicked_element.get('validator_type'),
						},
						'url_before': step.url_before,
						'url_after': step.url_after,
						'typed_text': step.typed_text,
					}
					for step in self.steps
				],
			}

			# Use the workflow name for the filename
			filename = f'{self.action_name}.json'
			filepath = os.path.join(output_dir_path, filename)

			print(f'Attempting to save workflow to: {filepath}')

			with open(filepath, 'w', encoding='utf-8') as f:
				json.dump(workflow_data, f, indent=4, ensure_ascii=False)

			# Verify the file was created
			if os.path.exists(filepath):
				file_size = os.path.getsize(filepath)
				print(f'✅ Workflow successfully saved to {filepath} ({file_size} bytes)')
			else:
				print(f'❌ Error: File was not created at {filepath}')

		except Exception as e:
			print(f'❌ Error saving workflow: {str(e)}')
			# Try to save to a fallback location
			try:
				fallback_path = os.path.join(os.getcwd(), 'workflow_fallback.json')
				print(f'Attempting to save to fallback location: {fallback_path}')
				with open(fallback_path, 'w', encoding='utf-8') as f:
					json.dump(workflow_data, f, indent=4, ensure_ascii=False)
				print(f'✅ Workflow saved to fallback location: {fallback_path}')
			except Exception as fallback_error:
				print(f'❌ Failed to save to fallback location: {str(fallback_error)}')
