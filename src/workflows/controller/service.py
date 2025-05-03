import logging

from browser_use.agent.views import ActionResult
from browser_use.browser.context import BrowserContext
from browser_use.controller.service import Controller

from .views import (
    ClickElementDeterministicAction,
    InputTextDeterministicAction,
    KeyPressDeterministicAction,
    NavigateAction,
    ScrollDeterministicAction,
    SelectDropdownOptionDeterministicAction,
)

logger = logging.getLogger(__name__)


class WorkflowController(Controller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__register_actions()

    def __register_actions(self):
        # Navigate to URL ------------------------------------------------------------
        @self.registry.action("Navigate to URL", param_model=NavigateAction)
        async def navigate(
            params: NavigateAction, browser: BrowserContext
        ) -> ActionResult:
            """Navigate to the given URL."""
            await self.registry.execute_action(
                action_name="open_tab", params=params.model_dump(), browser=browser
            )
            msg = f"🔗  Navigated to URL: {params.url}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)

        # Click element by CSS selector --------------------------------------------------
        @self.registry.action(
            "Click element by selector", param_model=ClickElementDeterministicAction
        )
        async def click(
            params: ClickElementDeterministicAction, browser: BrowserContext
        ) -> ActionResult:
            """Click the first element matching *params.selector*."""
            timeout_ms = 5000  # 5 seconds
            page = await browser.get_current_page()
            print(f"Clicking element with selector: {params.selector}")
            await page.click(params.selector, timeout=timeout_ms, force=True)
            msg = f"🖱️  Clicked element with CSS selector: {params.selector}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)

        # Input text into element --------------------------------------------------------
        @self.registry.action(
            "Input text into an element by CSS selector",
            param_model=InputTextDeterministicAction,
        )
        async def input(
            params: InputTextDeterministicAction,
            browser: BrowserContext,
            has_sensitive_data: bool = False,
        ) -> ActionResult:
            """Fill text into the element located with *params.selector*."""
            timeout_ms = 5000  # 5 seconds
            page = await browser.get_current_page()
            print(f"Filling text into element with selector: {params.selector}")
            print("Params: ", params)
            is_select = await page.locator(params.selector).evaluate(
                '(el) => el.tagName === "SELECT"'
            )
            if is_select:
                # TODO: Not sure why there is an input event before a select event
                return ActionResult(extracted_content="Ignored input into select element", include_in_memory=True)
            else:
                await page.fill(params.selector, params.text, timeout=timeout_ms)

            msg = f'⌨️  Input "{params.text}" into element with CSS selector: {params.selector}'
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)

        # Select dropdown option ---------------------------------------------------------
        @self.registry.action(
            "Select dropdown option by selector and visible text",
            param_model=SelectDropdownOptionDeterministicAction,
        )
        async def select_change(
            params: SelectDropdownOptionDeterministicAction, browser: BrowserContext
        ) -> ActionResult:
            """Select dropdown option whose visible text equals *params.text*."""
            timeout_ms = 5000  # 5 seconds
            page = await browser.get_current_page()
            print(f"Selecting option in dropdown with selector: {params.selector}")
            await page.select_option(
                params.selector, label=params.text, timeout=timeout_ms
            )
            msg = f'Selected option "{params.text}" in dropdown {params.selector}'
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)

        # Key press action ------------------------------------------------------------
        @self.registry.action(
            "Press key on element by selector", param_model=KeyPressDeterministicAction
        )
        async def key_press(
            params: KeyPressDeterministicAction, browser: BrowserContext
        ) -> ActionResult:
            """Press *params.key* on the element identified by *params.selector*."""
            timeout_ms = 5000  # 5 seconds
            page = await browser.get_current_page()
            print(
                f"Pressing key '{params.key}' on element with selector: {params.selector}"
            )
            await page.press(params.selector, params.key, timeout=timeout_ms)
            msg = f"🔑  Pressed key '{params.key}' on element with CSS selector: {params.selector}"
            logger.info(msg)
            return ActionResult(extracted_content=msg, include_in_memory=True)

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