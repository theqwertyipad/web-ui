import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import gradio as gr
from gradio.components import Component

from src.utils import extension_loader, workflow_recorder
from src.webui.webui_manager import WebuiManager

logger = logging.getLogger(__name__)

# Define default workflow paths
DEFAULT_WORKFLOWS_PATH = "./tmp/workflows"


def _get_config_value(
    webui_manager: WebuiManager,
    comp_dict: Dict[Component, Any],
    comp_id_suffix: str,
    default: Any = None,
) -> Any:
    """Safely get value from component dictionary using its ID suffix relative to the tab."""
    # Assumes component ID format is "tab_name.comp_name"
    tab_name = "browser_settings"  # Hardcode or derive if needed
    comp_id = f"{tab_name}.{comp_id_suffix}"
    # Need to find the component object first using the ID from the manager
    try:
        comp = webui_manager.get_component_by_id(comp_id)
        return comp_dict.get(comp, default)
    except KeyError:
        logger.warning(
            f"Component with suffix '{comp_id_suffix}' not found in manager for value lookup."
        )
        return default


class WorkflowRecorder:
    """Class to manage recording and editing of browser workflows"""

    def __init__(self, webui_manager: WebuiManager):
        self.webui_manager = webui_manager
        self.recording = False
        self.current_workflow = []
        self.workflow_name = f"workflow_{int(time.time())}"
        self.workflows_path = DEFAULT_WORKFLOWS_PATH
        os.makedirs(self.workflows_path, exist_ok=True)
        self.active_page = None

    async def get_active_page(self, browser_context):
        """Get the active page from the browser context"""
        # For CustomBrowserContext, we need to get the page differently
        # First check if we have a playwright context
        if (
            hasattr(browser_context, "playwright_context")
            and browser_context.playwright_context
        ):
            # Get pages from playwright context
            pages = await browser_context.playwright_context.pages()
            if pages:
                return pages[0]  # Return the first page

        # If we can't get pages directly, check if there's a _page or page attribute
        if hasattr(browser_context, "_page") and browser_context._page:
            return browser_context._page

        # Try to access the active page if it exists
        try:
            # This is a workaround to get the active page from various browser contexts
            pages = await browser_context.browser._browser.contexts[0].pages()
            if pages:
                return pages[0]
        except Exception as e:
            logger.warning(f"Could not get active page: {e}")

        return None

    async def start_recording(self, browser_obj, browser_context):
        """Start recording browser interactions"""
        if self.recording:
            return "Already recording"

        try:
            # Get the active page
            self.active_page = await self.get_active_page(browser_context)

            if not self.active_page:
                return (
                    "No active browser page. Please start a browser with a page first."
                )

            # Inject the recorder extension
            inject_result = await workflow_recorder.inject_recorder_extension(
                self.active_page
            )
            if "successfully" not in inject_result.lower():
                return inject_result

            # Start the recording
            result = await workflow_recorder.start_recording(self.active_page)

            self.recording = True
            self.current_workflow = []

            # Add initial navigation event
            url = await self.active_page.url()
            self.add_navigation_event(url)

            return f"Recording started: {result}"
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return f"Failed to start recording: {str(e)}"

    async def stop_recording(self):
        """Stop recording browser interactions"""
        if not self.recording:
            return "Not recording"

        try:
            if self.active_page:
                # Get all events from the browser
                events = await workflow_recorder.get_recorded_events(self.active_page)

                # Merge events with any we've captured
                if events:
                    # Keep navigation events we added and append new events
                    nav_events = [
                        e for e in self.current_workflow if e["type"] == "navigation"
                    ]
                    self.current_workflow = nav_events + events

                # Stop recording in the browser
                await workflow_recorder.stop_recording(self.active_page)

            self.recording = False
            self.active_page = None
            return "Recording stopped"
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            self.recording = False
            self.active_page = None
            return f"Failed to stop recording: {str(e)}"

    def add_navigation_event(self, url: str):
        """Add a navigation event to the workflow"""
        event = {
            "type": "navigation",
            "timestamp": int(time.time() * 1000),
            "tabId": 1,  # Simplified - in real usage we would track actual tab IDs
            "url": url,
        }
        self.current_workflow.append(event)
        return self.current_workflow

    def add_click_event(self, selector: str, url: str, frame_url: Optional[str] = None):
        """Add a click event to the workflow"""
        if not frame_url:
            frame_url = url

        event = {
            "type": "click",
            "timestamp": int(time.time() * 1000),
            "tabId": 1,  # Simplified
            "url": url,
            "frameUrl": frame_url,
            "cssSelector": selector,
            "elementTag": "ELEMENT",  # Simplified
        }
        self.current_workflow.append(event)
        return self.current_workflow

    def add_input_event(self, selector: str, value: str, url: str):
        """Add an input event to the workflow"""
        event = {
            "type": "input",
            "timestamp": int(time.time() * 1000),
            "tabId": 1,  # Simplified
            "url": url,
            "cssSelector": selector,
            "value": value,
        }
        self.current_workflow.append(event)
        return self.current_workflow

    def add_wait_event(self, duration_ms: int):
        """Add a wait event to the workflow"""
        event = {
            "type": "wait",
            "timestamp": int(time.time() * 1000),
            "duration": duration_ms,
        }
        self.current_workflow.append(event)
        return self.current_workflow

    def edit_workflow(self, workflow_json: str):
        """Edit the workflow from a JSON string"""
        try:
            self.current_workflow = json.loads(workflow_json)
            return "Workflow updated", self.format_workflow_display()
        except json.JSONDecodeError:
            return "Invalid JSON format", self.format_workflow_display()

    def delete_event(self, event_index: int):
        """Delete an event from the workflow by index"""
        if event_index < 0 or event_index >= len(self.current_workflow):
            return "Invalid event index"

        self.current_workflow.pop(event_index)
        return "Event deleted"

    def format_workflow_display(self):
        """Format the workflow for display in the UI"""
        if not self.current_workflow:
            return "No events recorded yet"

        formatted = []
        for i, event in enumerate(self.current_workflow):
            event_type = event.get("type", "unknown")
            timestamp = event.get("timestamp", 0)
            time_str = datetime.fromtimestamp(timestamp / 1000).strftime("%H:%M:%S.%f")[
                :-3
            ]

            if event_type == "navigation":
                formatted.append(
                    f"[{i}] {time_str} - Navigate to: {event.get('url', 'unknown')}"
                )
            elif event_type == "click":
                formatted.append(
                    f"[{i}] {time_str} - Click on: {event.get('cssSelector', 'unknown')}"
                )
            elif event_type == "input":
                formatted.append(
                    f"[{i}] {time_str} - Input '{event.get('value', '')}' to: {event.get('cssSelector', 'unknown')}"
                )
            elif event_type == "wait":
                formatted.append(
                    f"[{i}] {time_str} - Wait for: {event.get('duration', 0)}ms"
                )
            elif event_type == "select":
                formatted.append(
                    f"[{i}] {time_str} - Select '{event.get('selectedValue', '')}' from: {event.get('cssSelector', 'unknown')}"
                )
            elif event_type == "keypress":
                formatted.append(
                    f"[{i}] {time_str} - Press key: {event.get('key', 'unknown')}"
                )
            else:
                formatted.append(
                    f"[{i}] {time_str} - {event_type}: {json.dumps(event)}"
                )

        return "\n".join(formatted)

    def save_workflow(self, name: Optional[str] = None):
        """Save the workflow to a file"""
        if not self.current_workflow:
            return "No workflow to save"

        if name:
            self.workflow_name = name

        filename = f"{self.workflow_name}.json"
        if not filename.endswith(".json"):
            filename += ".json"

        filepath = os.path.join(self.workflows_path, filename)

        with open(filepath, "w") as f:
            json.dump(self.current_workflow, f, indent=2)

        return f"Workflow saved to {filepath}"

    def load_workflow(self, filepath: str):
        """Load a workflow from a file"""
        try:
            with open(filepath, "r") as f:
                self.current_workflow = json.load(f)

            # Extract workflow name from filename
            self.workflow_name = os.path.splitext(os.path.basename(filepath))[0]

            return "Workflow loaded successfully", self.format_workflow_display()
        except Exception as e:
            return f"Error loading workflow: {str(e)}", self.format_workflow_display()


def create_record_workflow_tab(webui_manager: WebuiManager):
    """Creates a workflow recording tab."""

    input_components = set(webui_manager.get_components())
    tab_components = {}

    # Create recorder instance and attach to webui_manager
    recorder = WorkflowRecorder(webui_manager)
    # Store the recorder on the webui_manager (we'll use setattr to avoid linter errors)
    setattr(webui_manager, "workflow_recorder", recorder)

    with gr.Group():
        with gr.Row():
            gr.Markdown(
                """
                ## Browser Workflow Recorder
                Record, edit, and replay browser actions as automated workflows
                """
            )

    with gr.Group():
        with gr.Row():
            workflow_name = gr.Textbox(
                label="Workflow Name",
                value="my_workflow",
                info="Name for your workflow (will be used for saving)",
                interactive=True,
            )
            workflows_dir = gr.Textbox(
                label="Workflows Directory",
                value=DEFAULT_WORKFLOWS_PATH,
                info="Directory to save and load workflows",
                interactive=True,
            )

    with gr.Group():
        with gr.Row():
            record_btn = gr.Button("▶️ Start Recording", variant="primary")
            stop_btn = gr.Button("⏹️ Stop Recording", variant="stop")

    with gr.Group():
        with gr.Row():
            workflow_display = gr.Textbox(
                label="Current Workflow",
                value="No workflow recorded yet",
                lines=15,
                interactive=False,
            )

    with gr.Group():
        with gr.Row():
            workflow_json = gr.Code(
                label="Workflow JSON", language="json", value="[]", interactive=True
            )

    with gr.Group():
        with gr.Row():
            add_navigation_btn = gr.Button("Add Navigation")
            add_click_btn = gr.Button("Add Click")
            add_input_btn = gr.Button("Add Input")
            add_wait_btn = gr.Button("Add Wait")
            delete_event_btn = gr.Button("Delete Event")

    with gr.Group():
        with gr.Row(visible=False) as navigation_row:
            nav_url = gr.Textbox(
                label="URL", placeholder="https://example.com", interactive=True
            )
            nav_add_btn = gr.Button("Add")

    with gr.Group():
        with gr.Row(visible=False) as click_row:
            click_selector = gr.Textbox(
                label="CSS Selector", placeholder="#submit-button", interactive=True
            )
            click_url = gr.Textbox(
                label="URL", placeholder="https://example.com", interactive=True
            )
            click_add_btn = gr.Button("Add")

    with gr.Group():
        with gr.Row(visible=False) as input_row:
            input_selector = gr.Textbox(
                label="CSS Selector", placeholder="#username", interactive=True
            )
            input_value = gr.Textbox(
                label="Value", placeholder="user@example.com", interactive=True
            )
            input_url = gr.Textbox(
                label="URL", placeholder="https://example.com", interactive=True
            )
            input_add_btn = gr.Button("Add")

    with gr.Group():
        with gr.Row(visible=False) as wait_row:
            wait_duration = gr.Number(
                label="Duration (ms)", value=1000, interactive=True
            )
            wait_add_btn = gr.Button("Add")

    with gr.Group():
        with gr.Row(visible=False) as delete_row:
            event_index = gr.Number(
                label="Event Index", value=0, precision=0, interactive=True
            )
            delete_confirm_btn = gr.Button("Confirm Delete")

    with gr.Group():
        with gr.Row():
            save_btn = gr.Button("💾 Save Workflow", variant="primary")
            load_file = gr.File(
                label="Load Workflow File", file_types=[".json"], interactive=True
            )

    with gr.Group():
        with gr.Row():
            status_display = gr.Textbox(
                label="Status", value="Ready to record", interactive=False
            )

    # Event handlers
    async def start_recording_click(*args):
        logger.info("Starting recording workflow...")
        components_dict = dict(zip(webui_manager.get_components(), args))

        try:
            # Get extension path
            extension_path = extension_loader.get_extension_path()
            if not extension_path:
                logger.error("Workflow recorder extension not found")
                return "Error: Workflow recorder extension not found. Please check the extension path."

            # Create temporary copy of extension
            ext_path = extension_loader.create_temp_extension_dir()
            if not ext_path:
                logger.error("Failed to create temporary extension directory")
                return "Error: Failed to create temporary extension directory"

            # Get browser settings
            headless = _get_config_value(
                webui_manager, components_dict, "headless", False
            )
            window_w = int(
                _get_config_value(webui_manager, components_dict, "window_w", 1280)
            )
            window_h = int(
                _get_config_value(webui_manager, components_dict, "window_h", 1100)
            )

            # Launch browser with extension
            from playwright.async_api import async_playwright

            playwright = await async_playwright().start()

            # Configure browser with extension
            browser = await playwright.chromium.launch_persistent_context(
                user_data_dir="./tmp/browser_data",
                headless=headless,
                args=[
                    f"--load-extension={ext_path}",
                    f"--window-size={window_w},{window_h}",
                    "--disable-extensions-except=" + ext_path,
                ],
            )

            # Store browser in webui_manager
            webui_manager.bu_browser = browser
            webui_manager.bu_browser_context = browser

            # Get the first page
            page = browser.pages[0] if browser.pages else await browser.new_page()

            # Navigate to extension page
            await page.goto("chrome://extensions")

            # Start recording
            result = await workflow_recorder.start_recording(page)
            logger.info(f"Recording started: {result}")
            return result

        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            return f"Error starting recording: {str(e)}"

    async def stop_recording_click():
        result = await recorder.stop_recording()
        workflow_text = recorder.format_workflow_display()
        workflow_json_text = json.dumps(recorder.current_workflow, indent=2)
        return result, workflow_text, workflow_json_text

    def update_from_json(json_text):
        result, display = recorder.edit_workflow(json_text)
        return result, display

    def add_navigation():
        return (
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    def add_click():
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    def add_input():
        return (
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
        )

    def add_wait():
        return (
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
        )

    def delete_event():
        return (
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=True),
        )

    def confirm_navigation(url):
        recorder.add_navigation_event(url)
        return (
            "Navigation added",
            recorder.format_workflow_display(),
            json.dumps(recorder.current_workflow, indent=2),
            gr.update(visible=False),
        )

    def confirm_click(selector, url):
        recorder.add_click_event(selector, url)
        return (
            "Click added",
            recorder.format_workflow_display(),
            json.dumps(recorder.current_workflow, indent=2),
            gr.update(visible=False),
        )

    def confirm_input(selector, value, url):
        recorder.add_input_event(selector, value, url)
        return (
            "Input added",
            recorder.format_workflow_display(),
            json.dumps(recorder.current_workflow, indent=2),
            gr.update(visible=False),
        )

    def confirm_wait(duration):
        recorder.add_wait_event(int(duration))
        return (
            "Wait added",
            recorder.format_workflow_display(),
            json.dumps(recorder.current_workflow, indent=2),
            gr.update(visible=False),
        )

    def confirm_delete(index):
        recorder.delete_event(int(index))
        return (
            "Event deleted",
            recorder.format_workflow_display(),
            json.dumps(recorder.current_workflow, indent=2),
            gr.update(visible=False),
        )

    def save_workflow_click(name):
        recorder.workflow_name = name
        result = recorder.save_workflow()
        return result

    def load_workflow_file(file):
        if file is None:
            return (
                "No file selected",
                recorder.format_workflow_display(),
                json.dumps(recorder.current_workflow, indent=2),
            )

        result, display = recorder.load_workflow(file.name)
        return result, display, json.dumps(recorder.current_workflow, indent=2)

    # Connect event handlers
    record_btn.click(
        start_recording_click,
        inputs=webui_manager.get_components(),
        outputs=[status_display],
    )
    stop_btn.click(
        stop_recording_click, outputs=[status_display, workflow_display, workflow_json]
    )
    workflow_json.change(
        update_from_json,
        inputs=[workflow_json],
        outputs=[status_display, workflow_display],
    )

    # Action button connections
    add_navigation_btn.click(
        add_navigation,
        outputs=[navigation_row, click_row, input_row, wait_row, delete_row],
    )
    add_click_btn.click(
        add_click, outputs=[navigation_row, click_row, input_row, wait_row, delete_row]
    )
    add_input_btn.click(
        add_input, outputs=[navigation_row, click_row, input_row, wait_row, delete_row]
    )
    add_wait_btn.click(
        add_wait, outputs=[navigation_row, click_row, input_row, wait_row, delete_row]
    )
    delete_event_btn.click(
        delete_event,
        outputs=[navigation_row, click_row, input_row, wait_row, delete_row],
    )

    # Confirm action button connections
    nav_add_btn.click(
        confirm_navigation,
        inputs=[nav_url],
        outputs=[status_display, workflow_display, workflow_json, navigation_row],
    )

    click_add_btn.click(
        confirm_click,
        inputs=[click_selector, click_url],
        outputs=[status_display, workflow_display, workflow_json, click_row],
    )

    input_add_btn.click(
        confirm_input,
        inputs=[input_selector, input_value, input_url],
        outputs=[status_display, workflow_display, workflow_json, input_row],
    )

    wait_add_btn.click(
        confirm_wait,
        inputs=[wait_duration],
        outputs=[status_display, workflow_display, workflow_json, wait_row],
    )

    delete_confirm_btn.click(
        confirm_delete,
        inputs=[event_index],
        outputs=[status_display, workflow_display, workflow_json, delete_row],
    )

    # Save/Load connections
    save_btn.click(
        save_workflow_click, inputs=[workflow_name], outputs=[status_display]
    )
    load_file.change(
        load_workflow_file,
        inputs=[load_file],
        outputs=[status_display, workflow_display, workflow_json],
    )

    # Update workflows directory
    def update_workflows_dir(dir_path):
        recorder.workflows_path = dir_path
        os.makedirs(dir_path, exist_ok=True)
        return f"Workflows directory updated to {dir_path}"

    workflows_dir.change(
        update_workflows_dir, inputs=[workflows_dir], outputs=[status_display]
    )

    # Register components with the webui manager
    tab_components.update(
        dict(
            workflow_name=workflow_name,
            workflows_dir=workflows_dir,
            record_btn=record_btn,
            stop_btn=stop_btn,
            workflow_display=workflow_display,
            workflow_json=workflow_json,
            add_navigation_btn=add_navigation_btn,
            add_click_btn=add_click_btn,
            add_input_btn=add_input_btn,
            add_wait_btn=add_wait_btn,
            delete_event_btn=delete_event_btn,
            nav_url=nav_url,
            click_selector=click_selector,
            click_url=click_url,
            input_selector=input_selector,
            input_value=input_value,
            input_url=input_url,
            wait_duration=wait_duration,
            event_index=event_index,
            save_btn=save_btn,
            load_file=load_file,
            status_display=status_display,
        )
    )
    webui_manager.add_components("record_workflow", tab_components)
