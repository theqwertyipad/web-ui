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
		logger.info("OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO")

	def __register_actions(self):
		# Click element by CSS selector --------------------------------------------------
		@self.registry.action('Click element by CSS selector', param_model=ClickElementByCssSelectorAction)
		async def click_element_by_css_selector(params: ClickElementByCssSelectorAction, browser: BrowserContext) -> ActionResult:
			"""Click the first element matching *params.selector*."""
			page = await browser.get_current_page()
			await page.click(params.selector)
			msg = f'🖱️  Clicked element with CSS selector: {params.selector}'
			logger.info(msg)
			return ActionResult(extracted_content=msg, include_in_memory=True)

		# Input text into element --------------------------------------------------------
		@self.registry.action('Input text into an element by CSS selector', param_model=InputTextActionCssSelector)
		async def input_text_by_css_selector(
			params: InputTextActionCssSelector, browser: BrowserContext, has_sensitive_data: bool = False
		) -> ActionResult:
			"""Fill text into the element located with *params.selector*."""
			page = await browser.get_current_page()
			handle = page.locator(f'css={params.selector}').first
			await handle.fill(params.text)
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
			page = await browser.get_current_page()
			handle = await page.query_selector(params.selector)
			if handle:
				result = await handle.select_option(label=params.text)
				msg = f'Selected option "{params.text}" (value={result}) in dropdown {params.selector}'
				logger.info(msg)
				return ActionResult(extracted_content=msg, include_in_memory=True)

			msg = f'Cannot select option: Element with selector {params.selector} not found'
			return ActionResult(extracted_content=msg, include_in_memory=True)
