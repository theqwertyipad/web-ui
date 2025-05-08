# flake8: noqa
import json
import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import gradio as gr
import pandas as pd
from browser_use.browser.browser import Browser, BrowserConfig
from src.recorder.recorder import WorkflowRecorder
from gradio.components import Component

from src.utils import llm_provider
from src.webui.webui_manager import WebuiManager
from src.workflows.workflow import Workflow
from src.workflows.workflow_builder import parse_session

# Directory to store user workflows
WORKFLOW_STORAGE_DIR = Path("./saved_workflows")
WORKFLOW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
# Directory to store user recordings
RECORD_STORAGE_DIR = Path("./saved_recordings")
RECORD_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Set chrome path
def get_executable_path() -> str:
    """Get the path to the executable for the current OS."""
    if sys.platform == "darwin":
        # macOS path
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif sys.platform.startswith("linux"):
        # Linux path
        return "/usr/bin/google-chrome"
    elif sys.platform == "win32":
        # Windows path
        return "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    else:
        raise ValueError(f"Unsupported platform: {sys.platform}")


CHROME_PATH = get_executable_path()


def _list_saved_workflows() -> list[str]:
    """Return a sorted list of saved workflow filenames (relative)."""
    return sorted([p.name for p in WORKFLOW_STORAGE_DIR.glob("*.json")])

def _list_saved_recordings() -> list[str]:
    """Return a sorted list of saved recording filenames (relative)."""
    return sorted([p.name for p in RECORD_STORAGE_DIR.glob("*.json")])


def create_workflows_tab(webui_manager: WebuiManager):
    """
    Creates three tabs: one for recording a session, one for creating a workflow from that session, and one for running saved workflows.
    """
    # expose module-level helper functions for callbacks
    global \
        _save_generated_workflow, \
        update_json_display, \
        show_running_workflow_status, \
        _execute_workflow, \
        _run_selected_workflow_as_tool

    # Initialize empty tab_components dictionary to collect all components
    tab_components: dict[str, Component] = {}

    # Collect agent_settings components using id_to_component attribute
    agent_settings_prefix = "agent_settings."
    for component_id, component in webui_manager.id_to_component.items():
        if component_id.startswith(agent_settings_prefix):
            # Add the component to tab_components with its ID
            tab_components[component] = component

    # Two main tabs: Create Workflow and Run Workflow
    with gr.Tabs():
        # Recording Tab
        with gr.TabItem("🔴 Run Recorder"):
            gr.Markdown("""
                    ##### When the recording is finished or imported, it will be saved to the "🛠️ Workflow Builder" page!
                    """)
            with gr.Row():
                # Column 1: Browser-based in-built recorder
                with gr.Column():
                    gr.Markdown("""
                    #### Option 1: Use In-Built Browser Recorder
                    Record your session directly in the browser using the in-built recorder:
                    - Navigate to the website you want to record.
                    - Use the in-built recorder to capture your actions.
                    """)
                    url_input = gr.Textbox(
                        label="Website URL to begin the recording (default: browser-use.com)",
                        placeholder="example.com"
                    )
                    run_recorder = gr.Button("Launch recorder", variant="primary")

                # Column 2: Browser extension method (original content)
                with gr.Column():
                    gr.Markdown("""
                    #### Option 2: Use Browser Extension
                    Record your session using the browser extension:
                    1. Install the browser extension (chrome://extensions/ → Developer mode → Load unpacked)
                    2. Click the extension, record your session, and download the JSON file
                    3. The JSON will be saved to your recordings
                    """)
                    session_json_file = gr.File(
                        label="Session JSON (.json)",
                        file_types=[".json"],
                        interactive=True
                    )
                    session_save_status = gr.Textbox(
                        label="Upload Status",
                        lines=1,
                        interactive=False
                    )


        # Create Workflow Tab
        with gr.TabItem("🛠️ Workflow Builder"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Choose the recording from here:")
                    session_dropdown = gr.Dropdown(
                        label="Select Recorded Session JSON",
                        choices=_list_saved_recordings(),
                        interactive=True
                    )
                    refresh_sessions_button = gr.Button("Refresh Recordings", variant="secondary")
            with gr.Row():
                gr.Markdown("### Create an Executable Workflow from the chosen Recording")
            with gr.Row():
                # Column 1: AI-Driven Option (Existing Logic)
                with gr.Column():
                    gr.Markdown("#### Step 1: Let AI Build the Workflow")
                    gr.Markdown(
                        """
                        Let the AI process the recording and generate the workflow based on your prompt:
                        - Provide a goal or prompt for the AI.
                        - The AI will automatically select relevant actions.
                        - It will decide what type of information goes where in future runs.
                        """
                    )
                    workflow_chat = gr.Chatbot(label="Workflow Chat")
                    chat_input = gr.Textbox(
                        placeholder="Type a prompt to generate (e.g., 'Create a login workflow')",
                        lines=1,
                        interactive=True
                    )
                    use_vision_cb = gr.Checkbox(
                        label="Use Vision (Screenshots)",
                        value=False,
                        interactive=True
                    )
                    chat_button = gr.Button("Send", variant="primary")
                with gr.Column():
                    gr.Markdown("#### Step 2: Select the Right Inputs")
                    gr.Markdown(
                        """
                        Review and modify the input schema generated by the AI:
                        - Edit property names, types, or delete rows as needed.
                        - Add new rows for additional inputs.
                        - Click 'Update Inputs' to apply changes to the workflow.
                        """
                    )
                    input_schema_df = gr.Dataframe(
                        label="Input Schema Properties",
                        headers=["Property Name", "Type"],
                        datatype=["str", "str"],
                        interactive=True,
                        wrap=True,
                        value=[]  # Initially empty
                    )
                    update_inputs_button = gr.Button("Update Inputs", variant="primary")

            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### You can still edit the recording here before saving.")
                    generated_json = gr.Code(
                        language="json",
                        label="Generated Workflow JSON",
                        interactive=True,
                        max_lines=50,
                    )
            with gr.Row():
                with gr.Column():
                    gr.Markdown(
                        "### Give your generated workflow a name and save it. To run it, switch to the **🚀 Run Workflow** tab."
                    )
                    generated_filename_tb = gr.Textbox(
                        label="Filename (.json)",
                        placeholder="ai_workflow.json",
                        lines=1,
                        interactive=True
                    )
                    generated_save_status = gr.Textbox(
                        label="Save Status",
                        lines=1,
                        interactive=False
                    )
                    save_generated_button = gr.Button("Save Workflow", variant="secondary")
        # Run Workflow Tab
        with gr.TabItem("🚀 Run Workflows"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Upload a workflow and select it from the dropdown...")
                    workflow_file = gr.File(
                        label="Upload Workflow JSON", file_types=[".json"], interactive=True
                    )
                with gr.Column():
                    gr.Markdown("### Or run a saved workflow")
                    saved_workflows_dd = gr.Dropdown(
                        label="Select from list",
                        choices=_list_saved_workflows(),
                        interactive=True,
                        value=_list_saved_workflows()[0] if _list_saved_workflows() else None,
                    )
                    refresh_saved_button = gr.Button("Refresh", variant="secondary")
            upload_workflow = gr.Code(
                language="json", label="Workflow JSON", interactive=False, max_lines=30
            )
            uploaded_json_schema = gr.Code(
                language="json", label="Input Schema", interactive=False, max_lines=30
            )
            gr.Markdown("#### Run Options")
            with gr.Row():
                with gr.Column():
                    uploaded_workflow_inputs_json = gr.Textbox(
                        label="Run with pre-determined inputs (JSON)", placeholder="{}", lines=3, interactive=True
                    )
                    run_uploaded_button = gr.Button("Run with JSON", variant="primary")
                with gr.Column():
                    uploaded_tool_input = gr.Textbox(
                        label="Let AI decide based on your prompt what to put in the input schema (NLP)",
                        placeholder="Describe what to do",
                        lines=1,
                        interactive=True,
                    )
                    run_uploaded_tool_button = gr.Button("Run as Tool", variant="primary")
            upload_workflow_output = gr.Textbox(
                label="Output / Status", lines=10, interactive=False
            )

    # Register components for this tab
    workflow_tab_components = {
        "run_recorder": run_recorder,
        "url_input": url_input,
        "session_json_file": session_json_file,
        "session_save_status": session_save_status,
        "session_dropdown": session_dropdown,
        "refresh_sessions_button": refresh_sessions_button,
        "use_vision_cb": use_vision_cb,
        "workflow_chat": workflow_chat,
        "chat_input": chat_input,
        "chat_button": chat_button,
        "generated_json": generated_json,
        "generated_filename_tb": generated_filename_tb,
        "input_schema_df": input_schema_df,
        "update_inputs_button": update_inputs_button,
        "generated_save_status": generated_save_status,
        "save_generated_button": save_generated_button,
        "workflow_file": workflow_file,
        "saved_workflows_dd": saved_workflows_dd,
        "refresh_saved_button": refresh_saved_button,
        "upload_workflow": upload_workflow,
        "uploaded_json_schema": uploaded_json_schema,
        "uploaded_workflow_inputs_json": uploaded_workflow_inputs_json,
        "uploaded_tool_input": uploaded_tool_input,
        "run_uploaded_button": run_uploaded_button,
        "run_uploaded_tool_button": run_uploaded_tool_button,
        "upload_workflow_output": upload_workflow_output,
    }

    # Update tab_components with workflow components
    tab_components.update(workflow_tab_components)

    # Add all components to webui_manager
    webui_manager.add_components("workflows", tab_components)

    # Callbacks will be registered after helper definitions

    # ------------------------------------------------------------------
    # Helper functions
    # ------------------------------------------------------------------

    def _sanitize_filename(name: str) -> Optional[str]:
        """Return sanitized filename ensuring `.json` extension or None if invalid."""
        if not name:
            return None
        name = name.strip()
        # Default extension
        if not name.lower().endswith((".json",)):
            name += ".json"

        # Prevent directory traversal
        if any(part in ("..", "/") for part in name.split(os.sep)):
            return None
        return name
    
    def _save_session_json(file_obj):
        """Save uploaded session JSON to RECORD_STORAGE_DIR."""
        if not file_obj:
            return gr.update(value="⚠️ No file uploaded.")
        
        file_path = Path(getattr(file_obj, "name", file_obj))
        if not file_path.exists():
            return gr.update(value=f"⚠️ File not found: {file_path}")
        
        try:
            sanitized = _sanitize_filename(file_path.name)
            if not sanitized:
                return gr.update(value="⚠️ Invalid filename.")
            
            save_path = RECORD_STORAGE_DIR / sanitized
            save_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
            return gr.update(value=f"✅ Saved session to {save_path}")
        except Exception as e:
            return gr.update(value=f"❌ Failed to save session: {e}")
        
    def _save_uploaded_workflow(file_obj):
        """Save uploaded workflow JSON to WORKFLOW_STORAGE_DIR and update dropdown."""
        if not file_obj:
            return {
                upload_workflow_output: gr.update(value="⚠️ No file uploaded."),
                saved_workflows_dd: gr.update(),
                upload_workflow: gr.update(value=""),
                uploaded_json_schema: gr.update(value="{}"),
            }

        file_path = Path(getattr(file_obj, "name", file_obj))
        if not file_path.exists():
            return {
                upload_workflow_output: gr.update(value=f"⚠️ File not found: {file_path}"),
                saved_workflows_dd: gr.update(),
                upload_workflow: gr.update(value=""),
                uploaded_json_schema: gr.update(value="{}"),
            }

        try:
            sanitized = _sanitize_filename(file_path.name)
            if not sanitized:
                return {
                    upload_workflow_output: gr.update(value="⚠️ Invalid filename."),
                    saved_workflows_dd: gr.update(),
                    upload_workflow: gr.update(value=""),
                    uploaded_json_schema: gr.update(value="{}"),
                }

            save_path = WORKFLOW_STORAGE_DIR / sanitized
            save_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
            wf_content, schema_text = _load_workflow_file(sanitized)
            return {
                    upload_workflow_output: gr.update(value=f"✅ Workflow saved to {save_path}. Select it from the dropdown to run."),
                    saved_workflows_dd: gr.update(choices=_list_saved_workflows(), value=sanitized),
                    upload_workflow: gr.update(value=wf_content if wf_content else ""),
                    uploaded_json_schema: gr.update(value=schema_text if schema_text else "{}"),
                }
        except Exception as e:
            return {
                upload_workflow_output: gr.update(value=f"❌ Failed to save workflow: {e}"),
                saved_workflows_dd: gr.update(),
                upload_workflow: gr.update(value=""),
                uploaded_json_schema: gr.update(value="{}"),
            }

    def _initialize_llm(
        provider: Optional[str],
        model_name: Optional[str],
        temperature: float,
        base_url: Optional[str],
        api_key: Optional[str],
        num_ctx: Optional[int] = None,
    ):
        """Create an LLM instance from the given settings (returns None on failure)."""
        print("--- Initializing LLM ---")
        print(f"  Provider: {provider}, Model: {model_name}, Temperature: {temperature}, Base URL: {base_url}")
        if not provider or not model_name:
            print("  ❌ LLM Init Failed: Missing provider or model name.")
            return None

        try:
            llm = llm_provider.get_llm_model(
                provider=provider,
                model_name="deepseek-chat", # TODO Hardcoded modelname! Something wrong with the Agent Setting tab in retrieving the llm_model_name.
                temperature=temperature,
                base_url=base_url or None,
                api_key=api_key or None,
                num_ctx=num_ctx if provider == "ollama" else None,
            )
            return llm
        except Exception as e:
            print(f"  ❌ LLM Init Failed: Exception during get_llm_model: {e}")
            print(f"Failed to initialize LLM: {e}")
            return None

    def _extract_schema(workflow_text: Optional[str]) -> str:
        """Extract and pretty-print the `input_schema` schema from a workflow JSON string."""
        if not workflow_text or not workflow_text.strip():
            return "{}"
        try:
            data = json.loads(workflow_text)
            schema = data.get("input_schema", {}) if data else {}
            return json.dumps(schema, indent=2)
        except Exception:
            return "{}"
    
    def _schema_to_dataframe(workflow_text: Optional[str]) -> pd.DataFrame:
        """Convert the input_schema.properties to a DataFrame for editing."""
        if not workflow_text or not workflow_text.strip():
            return pd.DataFrame(columns=["Property Name", "Type"])
        try:
            data = json.loads(workflow_text)
            schema = data.get("input_schema", {}).get("properties", {})
            rows = []
            for prop_name, prop_details in schema.items():
                rows.append({
                    "Property Name": prop_name,
                    "Type": prop_details.get("type", "string")
                })
            return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Property Name", "Type"])
        except Exception as e:
            print(f"Error converting schema to DataFrame: {e}")
            return pd.DataFrame(columns=["Property Name", "Type"])
    
    def _dataframe_to_schema(df: pd.DataFrame, original_json: str) -> str:
        """Convert the DataFrame back to an input_schema and update the original JSON."""
        try:
            data = json.loads(original_json) if original_json.strip() else {}
            if "name" not in data or not data["name"].strip():
                raise ValueError("JSON must contain a non-empty 'name' field")
            if "description" not in data or not data["description"].strip():
                raise ValueError("JSON must contain a non-empty 'description' field")
            if "version" not in data:
                data["version"] = "1.0"
            properties = {}
            for _, row in df.iterrows():
                prop_name = row["Property Name"].strip()
                prop_type = row["Type"].strip()
                if prop_name:
                    properties[prop_name] = {"type": prop_type if prop_type else "string"}
            original_required = data.get("input_schema", {}).get("required", [])
            print(original_required)
            new_required = [prop_name for prop_name in properties.keys() if prop_name in original_required]
            print(new_required)
            data["input_schema"] = {
                "type": "object",
                "properties": properties,
                "required": new_required
            }
            return json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON format")
        except ValueError as e:
            raise ValueError(str(e))

    def _load_workflow_file(file_obj_or_filename: Any) -> tuple[Optional[str], Optional[str]]:
        """Load workflow JSON file content from uploaded file, path string, or filename."""
        if file_obj_or_filename is None:
            return None, None

        # Handle both file objects and filenames
        if isinstance(file_obj_or_filename, str):
            # If it's a filename, construct the full path in WORKFLOW_STORAGE_DIR
            file_path = WORKFLOW_STORAGE_DIR / file_obj_or_filename
        else:
            # If it's a file object, get the path from the 'name' attribute
            file_path_str = getattr(file_obj_or_filename, "name", str(file_obj_or_filename))
            if not file_path_str:
                return None, None
            file_path = Path(file_path_str)

        if not file_path.exists():
            print(f"File not found during load: {file_path}")
            return None, None

        try:
            workflow_content = file_path.read_text(encoding="utf-8")
            schema_text = _extract_schema(workflow_content)
            return workflow_content, schema_text
        except Exception as e:
            print(f"Error loading workflow file {file_path}: {e}")
            return None, None

    def _get_agent_settings(components_dict):
        """Helper to get LLM settings from Agent Settings tab."""

        def _val(tab: str, name: str, default: Any = None):
            comp = webui_manager.id_to_component.get(f"{tab}.{name}")
            return comp.value
        
        provider = _val("agent_settings", "llm_provider")
        model_name = _val("agent_settings", "llm_model_name")
        temperature = _val("agent_settings", "llm_temperature", 0.6)
        base_url = _val("agent_settings", "llm_base_url")
        api_key = _val("agent_settings", "llm_api_key")
        ollama_ctx = _val("agent_settings", "ollama_num_ctx")
        use_screenshots = _val("agent_settings", "use_vision")

        return {
            "provider": provider,
            "model_name": model_name,
            "temperature": temperature,
            "base_url": base_url,
            "api_key": api_key,
            "ollama_ctx": ollama_ctx,
            "use_screenshots": use_screenshots,
        }

    def _resolve_workflow_path(wf_file) -> Optional[Path]:
        """Resolve workflow JSON path, checking saved directory as fallback."""
        if wf_file is None:
            return None

        wf_path = Path(getattr(wf_file, "name", str(wf_file)))
        if wf_path.exists():
            return wf_path

        # Fallback to saved directory
        potential_path = WORKFLOW_STORAGE_DIR / wf_path.name
        if potential_path.exists():
            return potential_path

        return None

    # ------------------------------------------------------------------
    # The two main workflow functions
    # ------------------------------------------------------------------

    async def _execute_workflow(wf_file: Any, inputs_json: Optional[str]):
        """Execute the workflow using JSON inputs."""
        # Validate workflow file
        if wf_file is None:
            return gr.update(
                value="⚠️ Please upload/select a workflow JSON file before running."
            )

        wf_path = _resolve_workflow_path(wf_file)
        if wf_path is None:
            return gr.update(
                value=f"⚠️ JSON file not found: {getattr(wf_file, 'name', str(wf_file))}"
            )

        # Parse optional JSON inputs
        inputs_dict = {}
        if inputs_json and inputs_json.strip():
            try:
                inputs_dict = json.loads(inputs_json)
                if not isinstance(inputs_dict, dict):
                    raise ValueError("Inputs JSON must decode to a JSON object/dict.")
            except Exception as e:
                return gr.update(value=f"⚠️ Invalid inputs JSON – {e}")

        # Execute workflow
        try:
            config = BrowserConfig(
                # browser_binary_path=CHROME_PATH,
                headless=False,
            )
            browser = Browser(config=config)
            workflow = Workflow(json_path=str(wf_path), browser=browser)
            results = await workflow.run_async(inputs=inputs_dict or None)
            pretty = json.dumps(results, indent=2, ensure_ascii=False)
            return gr.update(value=f"✅ Workflow finished successfully\n\n{pretty}")
        except Exception as e:
            tb = traceback.format_exc()
            return gr.update(value=f"❌ Error running workflow: {e}\n\n{tb}")

    async def _execute_workflow_as_tool(
        wf_path: Path, nl_input: Optional[str], llm: Any, output_component: Component
    ):
        """
        Core function to execute a workflow as a tool.
        Returns a dictionary with the output component as the key.
        """
        # Validate inputs
        if wf_path is None:
            return {
                output_component: gr.update(
                    value="⚠️ Please upload/select a workflow JSON file before running as tool."
                )
            }

        if not nl_input or not str(nl_input).strip():
            return {
                output_component: gr.update(
                    value="⚠️ Please enter a natural language prompt for the tool run."
                )
            }

        # Ensure nl_input is a string
        nl_input_str = str(nl_input) if nl_input is not None else ""

        if llm is None:
            return {
                output_component: gr.update(
                    value="❌ Failed to initialize LLM. Check Agent Settings."
                )
            }

        # Execute workflow
        try:
            config = BrowserConfig(
                # browser_binary_path=CHROME_PATH,
                headless=False,
            )
            browser = Browser(config=config)
            workflow = Workflow(json_path=str(wf_path), llm=llm, browser=browser)
            result = await workflow.run_as_tool(nl_input_str)
            return {
                output_component: gr.update(value=f"✅ Tool run completed:\n\n{result}")
            }
        except Exception as e:
            tb = traceback.format_exc()
            return {
                output_component: gr.update(
                    value=f"❌ Error running as tool: {e}\n\n{tb}"
                )
            }

    # ------------------------------------------------------------------
    # Tab-specific wrapper functions
    # ------------------------------------------------------------------

    # Launch recorder
    async def run_recorder_with_url(url):
        yield gr.update(value="Launching recorder...")
        browser_binary_path = (
            os.getenv("CHROME_PATH", None)
        )
        config=BrowserConfig(
            # browser_binary_path=browser_binary_path,
        )
        recorder = WorkflowRecorder(RECORD_STORAGE_DIR, config)
        url = url.strip()
        if not url:
            url = 'https://www.browser-use.com/'
        elif not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            await recorder.record_workflow(url)
        except Exception as e:
            print(f"An error occurred while recording the workflow: {e}")
        finally:
            yield gr.update(value="Run recorder")

    # Wrapper for _execute_workflow_as_tool
    async def _run_selected_workflow_as_tool(components_dict: Dict[Component, Any]):
        """Run an selected workflow as a tool."""
        wf_file = components_dict.get(saved_workflows_dd)
        nl_input = components_dict.get(uploaded_tool_input)

        # Resolve JSON path
        wf_path = _resolve_workflow_path(wf_file)
        if wf_path is None:
            return {
                upload_workflow_output: gr.update(
                    value=f"⚠️ JSON file not found: {getattr(wf_file, 'name', str(wf_file))}"
                )
            }

        if not nl_input or not str(nl_input).strip():
            return {
                upload_workflow_output: gr.update(
                    value="⚠️ Please enter a prompt for the tool run."
                )
            }

        # Ensure nl_input is a string
        nl_input_str = str(nl_input) if nl_input is not None else ""

        # Initialize LLM
        settings = _get_agent_settings(components_dict)
        llm = _initialize_llm(
            settings["provider"],
            settings["model_name"],
            settings["temperature"],
            settings["base_url"],
            settings["api_key"],
            settings["ollama_ctx"],
        )

        if llm is None:
            return {
                upload_workflow_output: gr.update(
                    value="❌ Failed to initialize LLM. Check Agent Settings."
                )
            }

        # Execute workflow
        return await _execute_workflow_as_tool(
            wf_path, nl_input_str, llm, upload_workflow_output
        )

    # ------------------------------------------------------------------
    # Persistence functions
    # ------------------------------------------------------------------

    def _save_generated_workflow(wf_content: Optional[str], filename: Optional[str]):
        """Save generated workflow JSON content to storage directory."""
        if not wf_content or not wf_content.strip():
            return {
                generated_save_status: gr.update(
                    value="⚠️ No workflow generated to save."
                ),
                saved_workflows_dd: gr.update(),
            }

        sanitized = _sanitize_filename(filename or "")
        if sanitized is None:
            return {
                generated_save_status: gr.update(value="⚠️ Invalid filename."),
                saved_workflows_dd: gr.update(),
            }

        save_path = WORKFLOW_STORAGE_DIR / sanitized
        try:
            save_path.write_text(wf_content, encoding="utf-8")
            status_msg = f"✅ Saved workflow!"
        except Exception as e:
            status_msg = f"❌ Failed to save workflow: {e}"

        return {
            generated_save_status: gr.update(value=status_msg),
            saved_workflows_dd: gr.update(
                choices=_list_saved_workflows(), value=sanitized
            ),
        }

    # ------------------------------------------------------------------
    # UI event functions
    # ------------------------------------------------------------------

    def show_generating_status():
        """Show that workflow generation is in progress."""
        loading_message = "⏳ GENERATING WORKFLOW... PLEASE WAIT ⏳"
        return (
            gr.update(value=loading_message),
            gr.update(value=""),
            gr.update(value=""),
        )

    def show_running_workflow_status():
        """Show that workflow is running."""
        return gr.update(value="⏳ RUNNING WORKFLOW... PLEASE WAIT ⏳")

    def update_json_display(file_obj):
        """Update the JSON display when a file is uploaded or selected."""
        wf_content, schema_text = _load_workflow_file(file_obj)
        if wf_content:
            return {
                upload_workflow: gr.update(value=wf_content),
                uploaded_json_schema: gr.update(value=schema_text),
            }
        return {
            upload_workflow: gr.update(value=""),
            uploaded_json_schema: gr.update(value="{}"),
        }

    # Define the chat generation function here, before it's used in the callback
    def _generate_via_chat(session_file, user_msg, chat_history, use_vision):
        print("--- Generating via Chat ---")
        chat_history = chat_history or []
        chat_history.append(("user", user_msg))
        # Ensure session_path is always a string
        session_path = RECORD_STORAGE_DIR / session_file
        print(f"  Session Path: {session_path}")
        if not session_path:
            print("  ⚠️ No session file uploaded.")
            chat_history.append(("bot", "⚠️ Please upload a session JSON file."))
            return chat_history, gr.update(value="")

        # We need to create a components_dict from known components to pass to _get_agent_settings
        components_dict = set(webui_manager.get_components())

        # Use the already defined _get_agent_settings and _initialize_llm
        settings = _get_agent_settings(components_dict)
        llm = _initialize_llm(
            settings["provider"],
            settings["model_name"],
            settings["temperature"],
            settings["base_url"],
            settings["api_key"],
            settings["ollama_ctx"],
        )
        print(f"  LLM Initialized: {llm is not None}")
        if llm is None:
            print("  ❌ LLM is None, returning error to chat.")
            chat_history.append(
                ("bot", "❌ Failed to initialize LLM. Check Agent Settings. ")
            )
            return chat_history, gr.update(value="")
        try:
            print("  Attempting parse_session...")
            workflow_obj = parse_session(
                session_path, user_goal=user_msg, llm=llm, use_screenshots=use_vision
            )
            print(
                f"  Parse session successful. Workflow path: {workflow_obj.json_path}"
            )
            text = Path(workflow_obj.json_path).read_text(encoding="utf-8")
            schema_df = _schema_to_dataframe(text)
            chat_history.append(("bot", text))
            print("  Added workflow JSON to chat history.")
            return chat_history, gr.update(value=text), gr.update(value=schema_df)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"  ❌ Exception during parse_session: {e}\n{tb}")
            chat_history.append(("bot", f"❌ Error generating workflow: {e}\n\n{tb}"))
            return chat_history, gr.update(value=""), gr.update(value=pd.DataFrame(columns=["Property Name", "Type"]))

    # --- ALL CALLBACKS MOVED HERE --- #
    # Recording Tab Callbacks
    run_recorder.click(
        fn=run_recorder_with_url,
        inputs=[url_input],
        outputs=[run_recorder]
    )

    session_json_file.upload(
        fn=_save_session_json,
        inputs=[session_json_file],
        outputs=[session_save_status]
    )

    # Create Workflow Tab Callbacks
    chat_button.click(
        fn=_generate_via_chat,
        inputs=[session_dropdown, chat_input, workflow_chat, use_vision_cb],
        outputs=[workflow_chat, generated_json, input_schema_df],
    )

    update_inputs_button.click(
        fn=_dataframe_to_schema,
        inputs=[input_schema_df, generated_json],
        outputs=[generated_json]
    )
    save_generated_button.click(
        fn=_save_generated_workflow,
        inputs=[generated_json, generated_filename_tb],
        outputs=[generated_save_status, saved_workflows_dd],
    )
    refresh_sessions_button.click(
        fn=lambda: gr.update(choices=_list_saved_recordings()),
        inputs=None,
        outputs=[session_dropdown]
    )

    # Run Workflow Tab Callbacks
    refresh_saved_button.click(
        fn=lambda: gr.update(choices=_list_saved_workflows()),
        inputs=None,
        outputs=[saved_workflows_dd],
    )
    # Add this to the "Run Workflow Tab Callbacks" section
    saved_workflows_dd.change(
        fn=lambda x: _load_workflow_file(x) if x else (None, None),
        inputs=[saved_workflows_dd],
        outputs=[upload_workflow, uploaded_json_schema],
    )
    workflow_file.upload(
        fn=_save_uploaded_workflow,
        inputs=[workflow_file],
        outputs=[upload_workflow_output, saved_workflows_dd, upload_workflow, uploaded_json_schema],
    )
    run_uploaded_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=[upload_workflow_output],
        queue=False,
    ).then(
        fn=_execute_workflow,
        inputs=[saved_workflows_dd, uploaded_workflow_inputs_json],
        outputs=[upload_workflow_output],
    )
    run_uploaded_tool_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=[upload_workflow_output],
        queue=False,
    ).then(
        fn=_run_selected_workflow_as_tool,
        inputs=set(webui_manager.get_components()),
        outputs=[upload_workflow_output],
    )
