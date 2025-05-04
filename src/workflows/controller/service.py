import logging

from browser_use.agent.views import ActionResult
from browser_use.browser.context import BrowserContext
from browser_use.controller.service import Controller

from .views import (
    ClickElementDeterministicAction,
    InputTextDeterministicAction,
    KeyPressDeterministicAction,
    NavigationAction,
    ScrollDeterministicAction,
    SelectDropdownOptionDeterministicAction,
)
from .utlis import get_best_element_handle

logger = logging.getLogger(__name__)

DEFAULT_ACTION_TIMEOUT_MS = 1000

class WorkflowController(Controller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__register_actions()

    def __register_actions(self):
        # Navigate to URL ------------------------------------------------------------
        @self.registry.action("Navigate to URL", param_model=NavigationAction)
        async def navigation(
            params: NavigationAction, browser: BrowserContext
        ) -> ActionResult:
            """Navigate to the given URL."""
            await self.registry.execute_action(
                action_name="go_to_url", params=params.model_dump(), browser=browser
            )
            msg = f"🔗  Navigated to URL: {params.url}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)

        # Click element by CSS selector --------------------------------------------------

        @self.registry.action(
            "Click element by all available selectors", param_model=ClickElementDeterministicAction
        )
        async def click(
            params: ClickElementDeterministicAction, browser: BrowserContext
        ) -> ActionResult:
            """Click the first element matching *params.cssSelector* with fallback mechanisms."""
            page = await browser.get_current_page()
            original_selector = params.cssSelector

            try:
                locator, selector_used = await get_best_element_handle(
                    page, params.cssSelector, params, timeout_ms=DEFAULT_ACTION_TIMEOUT_MS
                )
                await locator.click(force=True)

                msg = f"🖱️  Clicked element with CSS selector: {selector_used} (original: {original_selector})"
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            except Exception as e:
                error_msg = f"Failed to click element. Original selector: {original_selector}. Error: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)

        # Input text into element --------------------------------------------------------
        @self.registry.action(
            "Input text into an element by all available selectors",
            param_model=InputTextDeterministicAction,
        )
        async def input(
            params: InputTextDeterministicAction,
            browser: BrowserContext,
            has_sensitive_data: bool = False,
        ) -> ActionResult:
            """Fill text into the element located with *params.cssSelector*."""
            page = await browser.get_current_page()
            original_selector = params.cssSelector

            try:
                locator, selector_used = await get_best_element_handle(
                    page,
                    params.cssSelector,
                    params,
                    timeout_ms=DEFAULT_ACTION_TIMEOUT_MS,
                )

                # Check if it's a SELECT element
                is_select = await locator.evaluate('(el) => el.tagName === "SELECT"')
                if is_select:
                    return ActionResult(
                        extracted_content="Ignored input into select element",
                        include_in_memory=True,
                    )

                await locator.fill(params.value)

                msg = f'⌨️  Input "{params.value}" into element with CSS selector: {selector_used} (original: {original_selector})'
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            except Exception as e:
                error_msg = f"Failed to input text. Original selector: {original_selector}. Error: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)

        # Select dropdown option ---------------------------------------------------------
        @self.registry.action(
            "Select dropdown option by all available selectors and visible text",
            param_model=SelectDropdownOptionDeterministicAction,
        )
        async def select_change(
            params: SelectDropdownOptionDeterministicAction, browser: BrowserContext
        ) -> ActionResult:
            """Select dropdown option whose visible text equals *params.value*."""
            page = await browser.get_current_page()
            original_selector = params.cssSelector

            try:
                locator, selector_used = await get_best_element_handle(
                    page,
                    params.cssSelector,
                    params,
                    timeout_ms=DEFAULT_ACTION_TIMEOUT_MS,
                )

                await locator.select_option(label=params.selectedText)

                msg = f'Selected option "{params.selectedText}" in dropdown {selector_used} (original: {original_selector})'
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            except Exception as e:
                error_msg = f"Failed to select option. Original selector: {original_selector}. Error: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)

        # Key press action ------------------------------------------------------------
        @self.registry.action(
            "Press key on element by all available selectors", param_model=KeyPressDeterministicAction
        )
        async def key_press(
            params: KeyPressDeterministicAction, browser: BrowserContext
        ) -> ActionResult:
            """Press *params.key* on the element identified by *params.cssSelector*."""
            page = await browser.get_current_page()
            original_selector = params.cssSelector

            try:
                locator, selector_used = await get_best_element_handle(
                    page, params.cssSelector, params, timeout_ms=5000
                )

                await locator.press(params.key)

                msg = f"🔑  Pressed key '{params.key}' on element with CSS selector: {selector_used} (original: {original_selector})"
                logger.info(msg)
                return ActionResult(extracted_content=msg, include_in_memory=True)
            except Exception as e:
                error_msg = f"Failed to press key. Original selector: {original_selector}. Error: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)

        # Scroll action --------------------------------------------------------------
        @self.registry.action("Scroll page", param_model=ScrollDeterministicAction)
        async def scroll(
            params: ScrollDeterministicAction, browser: BrowserContext
        ) -> ActionResult:
            """Scroll the page by the given x/y pixel offsets."""
            page = await browser.get_current_page()
            await page.evaluate(f"window.scrollBy({params.scrollX}, {params.scrollY});")
            msg = f"📜  Scrolled page by (x={params.scrollX}, y={params.scrollY})"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)
