import asyncio
import datetime
import json
import os
import uuid
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
	type: str
	clicked_element: dict
	url: str
	timestamp: int = 0

class WorkflowRecorder:
	def __init__(self, browser_config: Optional[BrowserConfig] = None):
		self.browser_config = browser_config
		self.js_overlay = resources.read_text('src.recorder', 'gui.js')
		self.steps: List[WorkflowStep] = []
		self._overlay_logs: List[str] = []
		self._active_input: Optional[dict] = None
		self._recording_complete = asyncio.Event()
		self.recording = False
		self._should_exit = False
		self._workflow_saved = False
		self.output_dir = ''
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

	async def expose_notify_python(self, page, max_attempts=2, delay=0.2):
		"""Attempt to expose the notifyPython function with retries."""
		for attempt in range(max_attempts):
			try:
				await page.expose_function('notifyPython', self._notify_python)
				print(f'[🔗] notifyPython exposed on attempt {attempt + 1}')
				# Mock evaluation to check if the function is exposed
				is_exposed = await page.evaluate('typeof window.notifyPython === "function"')
				if is_exposed:
					print('[✅] notifyPython is callable from the page')
					return
				else:
					print('[⚠️] notifyPython is not callable, retrying...')
			except Exception as expose_err:
				print(f'[⚠️] Attempt {attempt + 1} failed: {expose_err}')
			await asyncio.sleep(delay)
		print('[❌] Failed to expose notifyPython after maximum attempts')

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
					action = step.type
					await page.evaluate(
						'(action) => AgentRecorder.addWorkflowStep(action)',
						action,
					)
			page.on('load', handle_page_load)

			async def handle_navigation(frame):
				if frame == page.main_frame: 
					if self.current_url != page.url:
						print(f'Navigation detected: {page.url}')
						new_url = page.url
						self.current_url = new_url
						if self.recording:
							step = WorkflowStep(
								step_number=len(self.steps) + 1,
								type='navigation',
								clicked_element={},
								url=new_url,
								timestamp=int(datetime.datetime.now().timestamp() * 1000)
							)
							self.steps.append(step)
							self.current_url = new_url
			page.on('framenavigated', handle_navigation)

			await asyncio.sleep(1)
			await self.overlay_print(f'Navigating to {url}...', page)
			await self.overlay_print(f'If the actions are not recorded, refresh the page!', page) # This isn't the best solution, but the reload is sometimes needed to initialize the eventhandlers correctly
			try:
				await page.goto(url, wait_until='domcontentloaded', timeout=10000)
				print('Page loaded!')
			except Exception as e:
				await self.overlay_print(f'Error navigating to {url}: {str(e)}', page)
				return

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
						clicked_element=attributes,
						url=payload.get('url', ''),
						timestamp=int(datetime.datetime.now().timestamp() * 1000)
					)
					self.steps.append(step)
					await page.evaluate(
						'(action) => AgentRecorder.addWorkflowStep(action)',
						step.type,
					)
					await self.overlay_print(f'🖱️ Recorded click', page)
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
						clicked_element=attributes,
						url=payload.get('url', ''),
						timestamp=payload.get('timestamp', int(datetime.datetime.now().timestamp() * 1000))
					)
					self.steps.append(step)
					await page.evaluate(
						'(action) => AgentRecorder.addWorkflowStep(action)',
						step.type,
					)
					await self.overlay_print(f"⌨️ Recorded {type} into", page)
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
						clicked_element=attributes,
						url=payload.get('url', ''),
						timestamp=payload.get('timestamp', int(datetime.datetime.now().timestamp() * 1000))
					)
					self.steps.append(step)
					await page.evaluate(
						'(action) => AgentRecorder.addWorkflowStep(action)',
						step.type,
					)
					await self.overlay_print(f'🔽 Recorded select change', page)
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
						clicked_element=attributes,
						url=page.url,
						timestamp=payload.get('timestamp', int(datetime.datetime.now().timestamp() * 1000))
					)
					self.steps.append(step)
					await page.evaluate(
						'(action) => AgentRecorder.addWorkflowStep(action)',
						step.type,
					)
					await self.overlay_print(f'⌨️ Recorded keydown: {payload.get("key", "")}', page)
					await self.update_state(context, page)

				elif event_type == 'navigation':
					url = payload.get('url', '')
					step = WorkflowStep(
						step_number=len(self.steps) + 1,
						type='navigation',
						clicked_element={},
						url=url,
						timestamp=int(datetime.datetime.now().timestamp() * 1000)
					)
					self.steps.append(step)
					await page.evaluate(
						'(action) => AgentRecorder.addWorkflowStep(action)',
						step.type,
					)
					await self.overlay_print(f'🌐 Recorded navigation to {url}', page)
					await self.update_state(context, page)

				elif event_type == 'control':
					action = payload.get('action')
					if action == 'start':
						await self.set_recording_state(page, True)
						self._workflow_saved = False
						await self.overlay_print('🟢 Recording started.', page)
						# Setting as first step the URL
						step = WorkflowStep(
							step_number=len(self.steps) + 1,
							type='navigation',
							clicked_element={},
							url=page.url,
							timestamp=int(datetime.datetime.now().timestamp() * 1000)
						)
						self.steps.append(step)
					elif action == 'finish':
						await self.set_recording_state(page, False)
						self._active_input = None  # This can cause problems in the future
						await self.overlay_print('⛔️ Recording stopped. Saving workflow...', page)
						self.save_workflow()

						# Delay to allow the GUI to render non-recording mode fully. This is important
						await asyncio.sleep(1)
						self.steps =[]
						await context.remove_highlights()
						await self.update_state(context, page)

					elif action == 'update':
						await self.overlay_print('Updating state', page)
						await self.update_state(context, page)
						await self.overlay_print('State updated', page)
					elif action == 'back':
						if self.steps:
							removed = self.steps.pop()
							await self.overlay_print(f'↩️ Removed step {removed.step_number}: {removed.type}', page)
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
			await self.expose_notify_python(page)

			def handle_browser_close(page):
				print('Browser closed by user.')
				self._should_exit = True
				self._recording_complete.set()
			page.on('close', handle_browser_close)

			await self._recording_complete.wait()

		except Exception as e:
			await self.overlay_print(f'An unexpected error occurred during recording: {str(e)}', page)
			if self.steps:
				await self.overlay_print('Attempting to save partial workflow due to error...', page)
				self.save_workflow()
			raise

		finally:
			self.recording = False
			if self.steps and not self._workflow_saved:
				await self.overlay_print('Finalizing workflow save...', page)
				self.save_workflow()
				await self.overlay_print('Workflow saving process complete.', page)
			elif not self.steps:
				await self.overlay_print('No steps were recorded.', page)
			
			# Clear steps after all operations
			if self._should_exit:
				self.steps = []

			if context:
				try:
					await context.close()
					print('Browser context closed.')
				except Exception as close_err:
					await self.overlay_print(f'Warning: Error closing browser context: {str(close_err)}', page)
			

	def save_workflow(self):
		"""Save the recorded workflow to a file"""
		if self._workflow_saved:
			print('Workflow already saved, skipping.')
			return
		# Check if there are no steps or only one step with 'navigation' type
		if not self.steps or (len(self.steps) == 1 and self.steps[0].type == 'navigation'):
			print('No meaningful steps to save, skipping workflow save.')
			self._workflow_saved = True
			return
		try:
			# Use a default directory for the output
			default_output_dir = 'workflows'
			output_dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), default_output_dir)
			os.makedirs(output_dir_path, exist_ok=True)

			# Use a timestamp and UUID for the filename
			filename = f'workflow_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex}.json'
			filepath = os.path.join(output_dir_path, filename)

			print(f'Attempting to save workflow to: {filepath}')

			workflow_data = {
				'timestamp': datetime.datetime.now().isoformat(),
				'action_name': self.action_name,
				'total_steps': len(self.steps),
				'description': self.description,
				'steps': [
					{
						'step_number': step.step_number,
						'type': step.type,
						'timestamp': step.timestamp,
						'clicked_element': {
							**step.clicked_element,
						},
						'url': step.url,
					}
					for step in self.steps
				],
			}

			with open(filepath, 'w', encoding='utf-8') as f:
				json.dump(workflow_data, f, indent=4, ensure_ascii=False)

			# Verify the file was created
			if os.path.exists(filepath):
				file_size = os.path.getsize(filepath)
				print(f'✅ Workflow successfully saved to {filepath} ({file_size} bytes)')
				self._workflow_saved = True
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
				self._workflow_saved = True
			except Exception as fallback_error:
				print(f'❌ Failed to save to fallback location: {str(fallback_error)}')
