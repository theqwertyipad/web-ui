import logging

from browser_use.agent.views import ActionResult
from browser_use.browser.context import BrowserContext
from browser_use.controller.service import Controller

from .views import (
	ClickElementByCssSelectorAction,
	InputTextActionCssSelector,
	SelectDropdownOptionBySelectorAndText,
)

logger = logging.getLogger(__name__)


class WorkflowController(Controller):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.__register_actions()

	def __register_actions(self):
		# Click element by CSS selector --------------------------------------------------
		@self.registry.action('Click element by CSS selector', param_model=ClickElementByCssSelectorAction)
		async def click_element_by_css_selector(params: ClickElementByCssSelectorAction, browser: BrowserContext) -> ActionResult:
			"""Click the first element matching *params.selector*."""
			timeout_ms = 5000  # 5 seconds
			page = await browser.get_current_page()
			print(f"Clicking element with selector: {params.selector}")
			await page.click(params.selector, timeout=timeout_ms)
			msg = f'🖱️  Clicked element with CSS selector: {params.selector}'
			logger.info(msg)
			return ActionResult(extracted_content=msg, include_in_memory=True)

		# Input text into element --------------------------------------------------------
		@self.registry.action('Input text into an element by CSS selector', param_model=InputTextActionCssSelector)
		async def input_text_by_css_selector(
			params: InputTextActionCssSelector, browser: BrowserContext, has_sensitive_data: bool = False
		) -> ActionResult:
			"""Fill text into the element located with *params.selector*."""
			timeout_ms = 5000  # 5 seconds
			page = await browser.get_current_page()
			print(f"Filling text into element with selector: {params.selector}")
			await page.fill(params.selector, params.text, timeout=timeout_ms)
			msg = f'⌨️  Input "{params.text}" into element with CSS selector: {params.selector}'
			logger.info(msg)
			return ActionResult(extracted_content=msg, include_in_memory=True)

		# Select dropdown option ---------------------------------------------------------
		@self.registry.action(
			'Select dropdown option by selector and visible text',
			param_model=SelectDropdownOptionBySelectorAndText,
		)
		async def select_dropdown_option_by_selector_and_text(
			params: SelectDropdownOptionBySelectorAndText, browser: BrowserContext
		) -> ActionResult:
			"""Select dropdown option whose visible text equals *params.text*."""
			timeout_ms = 5000  # 5 seconds
			page = await browser.get_current_page()
			print(f"Selecting option in dropdown with selector: {params.selector}")
			await page.select_option(params.selector, label=params.text, timeout=timeout_ms)
			msg = f'Selected option "{params.text}" in dropdown {params.selector}'
			logger.info(msg)
			return ActionResult(extracted_content=msg, include_in_memory=True)
