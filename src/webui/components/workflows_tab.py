import json
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict

import gradio as gr  # type: ignore
import yaml
from browser_use.browser.browser import Browser, BrowserConfig
from gradio.components import Component  # type: ignore

from src.utils import llm_provider
from src.webui.webui_manager import WebuiManager
from src.workflows.workflow import Workflow
from src.workflows.workflow_builder import parse_session

# Directory to store user workflows
WORKFLOW_STORAGE_DIR = Path("./saved_workflows")
WORKFLOW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _list_saved_workflows() -> list[str]:
    """Return a sorted list of saved workflow filenames (relative)."""
    return sorted([p.name for p in WORKFLOW_STORAGE_DIR.glob("*.y*ml")])


def create_workflows_tab(webui_manager: WebuiManager):
    """
    Creates a Workflows tab for uploading a workflow YAML file, specifying optional
    JSON inputs and executing the workflow.  The execution result (or errors) is
    rendered in a read-only textbox.
    """
    # Gather already-registered components so that we can later pass the full
    # component set into WebuiManager.save_config if needed.
    tab_components: dict[str, Component] = {}

    # ------------------------------------------------------------------
    #      UI LAYOUT
    # ------------------------------------------------------------------

    with gr.Tabs():
        # ===============================================================
        # 1. GENERATE WORKFLOW TAB
        # ===============================================================
        with gr.TabItem("⏺️ Record"):
            with gr.Group():
                with gr.Row():
                    session_json_file = gr.File(
                        label="Session JSON",
                        file_types=[".json"],
                        interactive=True,
                    )
                    user_goal_tb = gr.Textbox(
                        label="Task Description (Goal)",
                        placeholder="Describe the task / goal for the workflow",
                        lines=3,
                        interactive=True,
                    )
            with gr.Row():
                generate_button = gr.Button("✨ Generate Workflow", variant="primary")

            generate_workflow_output = gr.Textbox(
                label="Generated Workflow Output / Status",
                lines=2,
                interactive=False,
            )
            # Keep a separate reference to this status box before `record_workflow_output` is re-assigned later.
            generate_status_output = generate_workflow_output

            generated_yaml = gr.Code(
                language="yaml", label="Generated Workflow YAML", interactive=False
            )

            # --- Display parsed input schema ---
            generated_workflow_schema = gr.Code(
                language="json", label="Input Schema (from YAML)", interactive=False
            )
            # --- Save generated workflow UI ---
            with gr.Row():
                generated_filename_tb = gr.Textbox(
                    label="Save As Filename (.yaml)",
                    placeholder="my_workflow.yaml",
                    lines=1,
                    interactive=True,
                )
                generated_save_status = gr.Textbox(
                    label="Save Status",
                    lines=1,
                    interactive=False,
                )
                save_generated_button = gr.Button(
                    "💾 Save Workflow", variant="secondary"
                )
            with gr.Row():
                # --- Run generated workflow UI ---
                generated_workflow_inputs_json = gr.Textbox(
                    label="Workflow Inputs (JSON)",
                    placeholder="{}",
                    lines=4,
                    interactive=True,
                    info="Optional JSON dictionary with inputs required by the workflow",
                )
                generated_tool_input = gr.Textbox(
                    label="Natural Language Prompt (Run as Tool)",
                    placeholder="Describe what you want to achieve with this workflow",
                    lines=2,
                    interactive=True,
                    elem_id="record_tool_input",
                )

            with gr.Row():
                generated_run_button = gr.Button("🏃 Run Generated", variant="primary")
                generated_run_tool_button = gr.Button(
                    "🧰 Run Generated as Tool", variant="secondary"
                )

            record_workflow_output = gr.Textbox(
                label="Workflow Output / Status",
                lines=10,
                interactive=False,
            )

        # ===============================================================
        # 2. RUN WORKFLOW TAB
        # ===============================================================
        with gr.TabItem("📥 Upload Workflow"):
            with gr.Group():
                with gr.Row():
                    workflow_file = gr.File(
                        label="Workflow YAML",
                        file_types=[".yaml", ".yml"],
                        interactive=True,
                        elem_id="uploaded_workflow_file",
                    )
                # -- Saved workflows section --
                with gr.Row():
                    saved_workflows_dd = gr.Dropdown(
                        label="Saved Workflows",
                        choices=_list_saved_workflows(),
                        value=None,
                        interactive=True,
                    )
                    refresh_saved_button = gr.Button("🔄 Refresh", variant="secondary")

            # Display the uploaded workflow
            upload_yaml = gr.Code(language="yaml", label="Workflow", interactive=False)

            # --- Display parsed input schema ---
            uploaded_yaml_schema = gr.Code(
                language="json", label="Input Schema ", interactive=False
            )
            with gr.Row():
                # --- Run generated workflow UI ---
                uploaded_workflow_inputs_json = gr.Textbox(
                    label="Workflow Inputs (JSON)",
                    placeholder="{}",
                    lines=4,
                    interactive=True,
                    info="JSON dictionary with inputs required by the workflow",
                )
                uploaded_tool_input = gr.Textbox(
                    label="Natural Language Prompt",
                    placeholder="",
                    lines=4,
                    interactive=True,
                    info="Give the workflow input via natura language.",
                    elem_id="upload_tool_input",
                )

            with gr.Row():
                run_uploaded_button = gr.Button("🏃 Run from JSON", variant="secondary")
                run_uploaded_tool_button = gr.Button(
                    "🧰 Run from Prompt", variant="primary"
                )

            upload_workflow_output = gr.Textbox(
                label="Generated Workflow Output / Status",
                lines=10,
                interactive=False,
            )
    # ------------------------------------------------------------------
    # Register components so they can be saved via WebuiManager
    # ------------------------------------------------------------------

    tab_components.update(
        dict(
            # Generate
            session_json_file=session_json_file,
            user_goal_tb=user_goal_tb,
            generate_button=generate_button,
            generated_filename_tb=generated_filename_tb,
            save_generated_button=save_generated_button,
            generated_yaml=generated_yaml,
            generated_save_status=generated_save_status,
            generated_workflow_inputs_json=generated_workflow_inputs_json,
            # Run
            workflow_file=workflow_file,
            saved_workflows_dd=saved_workflows_dd,
            refresh_saved_button=refresh_saved_button,
            record_workflow_output=record_workflow_output,
            # Generated
            generated_workflow_schema=generated_workflow_schema,
            generated_run_button=generated_run_button,
            generated_tool_input=generated_tool_input,
            generated_run_tool_button=generated_run_tool_button,
            generate_status_output=generate_status_output,
            # Uploaded
            upload_yaml=upload_yaml,
            uploaded_yaml_schema=uploaded_yaml_schema,
            uploaded_workflow_inputs_json=uploaded_workflow_inputs_json,
            uploaded_tool_input=uploaded_tool_input,
            run_uploaded_button=run_uploaded_button,
            run_uploaded_tool_button=run_uploaded_tool_button,
            upload_workflow_output=upload_workflow_output,
        )
    )
    webui_manager.add_components("workflows", tab_components)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _sanitize_filename(name: str) -> str | None:
        """Return sanitized filename ensuring `.yaml` extension or None if invalid."""
        if not name:
            return None
        name = name.strip()
        # default extension
        if not name.lower().endswith((".yaml", ".yml")):
            name += ".yaml"

        # Prevent directory traversal
        if any(part in ("..", "/") for part in name.split(os.sep)):
            return None
        return name

    # ------------------------------------------------------------------
    # Callback helpers
    # ------------------------------------------------------------------

    def _initialize_llm(
        provider: str | None,
        model_name: str | None,
        temperature: float,
        base_url: str | None,
        api_key: str | None,
        num_ctx: int | None = None,
    ):
        """Create an LLM instance from the given settings (returns None on failure)."""
        if not provider or not model_name:
            return None

        try:
            llm = llm_provider.get_llm_model(
                provider=provider,
                model_name=model_name,
                temperature=temperature,
                base_url=base_url or None,
                api_key=api_key or None,
                num_ctx=num_ctx if provider == "ollama" else None,
            )
            return llm
        except Exception as e:
            print(f"Failed to initialise LLM: {e}")
            return None

    def _load_yaml_file(file_obj):
        """Load YAML file content from uploaded file or path string."""
        if file_obj is None:
            return None, None

        # file_obj can be Gradio File object or a path string
        file_path_str = getattr(file_obj, "name", str(file_obj))
        if not file_path_str:
            return None, None

        file_path = Path(file_path_str)
        if not file_path.exists():
            print(f"File not found during load: {file_path}")
            return None, None

        try:
            yaml_content = file_path.read_text(encoding="utf-8")
            schema_text = _extract_schema(yaml_content)
            return yaml_content, schema_text
        except Exception as e:
            print(f"Error loading YAML file {file_path}: {e}")
            return None, None

    async def _generate_workflow(components: Dict[Component, Any]):
        """Generate YAML workflow from a simplified session JSON + goal."""

        # Helper to fetch value by id suffix from the components dict
        def _val(tab: str, name: str, default: Any = None):
            comp = webui_manager.id_to_component.get(f"{tab}.{name}")
            return components.get(comp, default) if comp else default

        session_file_obj = components.get(session_json_file)
        session_path_str = None
        if session_file_obj:
            session_path_str = str(getattr(session_file_obj, "name", session_file_obj))

        user_goal_val = components.get(user_goal_tb, "")

        if not session_path_str:
            # Update the status output, not the yaml display directly
            return {
                generate_status_output: gr.update(
                    value="⚠️ Please upload a session JSON file."
                ),
                generated_yaml: gr.update(value=""),
                generated_workflow_schema: gr.update(value="{}"),
            }

        # ------------------------------------------------------------------
        # Build LLM instance from Agent Settings tab
        # ------------------------------------------------------------------

        provider = _val("agent_settings", "llm_provider")
        model_name = _val("agent_settings", "llm_model_name")
        temperature = float(_val("agent_settings", "llm_temperature", 0.6))
        base_url = _val("agent_settings", "llm_base_url")
        api_key = _val("agent_settings", "llm_api_key")
        ollama_ctx = _val("agent_settings", "ollama_num_ctx")
        use_screenshots = _val("agent_settings", "use_vision")

        llm = _initialize_llm(
            provider, model_name, temperature, base_url, api_key, ollama_ctx
        )

        if llm is None:
            return {
                generate_status_output: gr.update(
                    value="❌ Failed to initialise LLM. Check Agent Settings."
                ),
                generated_yaml: gr.update(value=""),
                generated_workflow_schema: gr.update(value="{}"),
            }

        try:
            workflow_obj = parse_session(
                session_path_str,
                user_goal_val,
                llm=llm,
                use_screenshots=use_screenshots,
            )
            yaml_path = Path(workflow_obj.yaml_path)
            yaml_content = yaml_path.read_text(encoding="utf-8")

            # Extract schema
            schema_text = _extract_schema(yaml_content)

            return {
                generated_yaml: gr.update(value=yaml_content),
                generated_workflow_schema: gr.update(value=schema_text),
            }
        except Exception as e:
            tb = traceback.format_exc()
            # Update status output on error
            return {
                generate_status_output: gr.update(
                    value=f"❌ Error generating workflow: {e}\n\n{tb}"
                ),
                generated_yaml: gr.update(value=""),
                generated_workflow_schema: gr.update(value="{}"),
            }

    async def _execute_workflow_from_json(yaml_file: Any, inputs_json: str | None):
        """Execute the selected workflow and return a gradio update for the output box."""
        if yaml_file is None:
            return gr.update(
                value="⚠️ Please upload/select a workflow YAML file before running."
            )

        yaml_path = Path(getattr(yaml_file, "name", str(yaml_file)))
        if not yaml_path.exists():
            # Check if it's a relative path within WORKFLOW_STORAGE_DIR
            potential_path = WORKFLOW_STORAGE_DIR / yaml_path.name
            if potential_path.exists():
                yaml_path = potential_path
            else:
                return gr.update(value=f"⚠️ YAML file not found: {yaml_path}")

        # Parse optional JSON inputs
        inputs_dict = {}
        if inputs_json and inputs_json.strip():
            try:
                inputs_dict = json.loads(inputs_json)
                if not isinstance(inputs_dict, dict):
                    raise ValueError("Inputs JSON must decode to a JSON object/dict.")
            except Exception as e:
                return gr.update(value=f"⚠️ Invalid inputs JSON – {e}")

        try:
            config = BrowserConfig(
                browser_binary_path="/usr/bin/google-chrome",
                headless=False,
            )
            browser = Browser(config=config)
            workflow = Workflow(yaml_path=str(yaml_path), browser=browser)
            results = await workflow.run_async(inputs=inputs_dict or None)
            pretty = json.dumps(results, indent=2, ensure_ascii=False)
            return gr.update(value=f"✅ Workflow finished successfully\n\n{pretty}")
        except Exception as e:
            tb = traceback.format_exc()
            return gr.update(value=f"❌ Error running workflow: {e}\n\n{tb}")

    async def _execute_workflow_from_prompt(yaml_file: Any, nl_input: str, llm: Any):
        """
        Core function to execute a workflow as a tool.
        Assumes LLM is already initialized.
        """
        if yaml_file is None:
            return {
                record_workflow_output: gr.update(
                    value="⚠️ Please upload/select a workflow YAML file before running as tool."
                ),
            }

        if not nl_input or not str(nl_input).strip():
            return {
                record_workflow_output: gr.update(
                    value="⚠️ Please enter a natural language prompt for the tool run."
                )
            }

        yaml_path = Path(getattr(yaml_file, "name", str(yaml_file)))
        if not yaml_path.exists():
            # Check if it's a relative path within WORKFLOW_STORAGE_DIR
            potential_path = WORKFLOW_STORAGE_DIR / yaml_path.name
            if potential_path.exists():
                yaml_path = potential_path
            else:
                return gr.update(value=f"⚠️ YAML file not found: {yaml_path}")

        if llm is None:
            # This check should ideally happen before calling this function,
            # but added here as a safeguard.
            return {
                record_workflow_output: gr.update(
                    value="❌ Failed to initialise LLM. Check Agent Settings."
                )
            }

        try:
            config = BrowserConfig(
                browser_binary_path="/usr/bin/google-chrome",
                headless=False,
            )
            browser = Browser(config=config)
            workflow = Workflow(yaml_path=str(yaml_path), llm=llm, browser=browser)
            result = await workflow.run_as_tool(nl_input)
            return {
                record_workflow_output: gr.update(
                    value=f"✅ Tool run completed:\n\n{result}"
                )
            }
        except Exception as e:
            tb = traceback.format_exc()
            return {
                record_workflow_output: gr.update(
                    value=f"❌ Error running as tool: {e}\n\n{tb}"
                )
            }

    # ------------------------------------------------------------------
    # Persistence Callbacks
    # ------------------------------------------------------------------

    def _save_generated_workflow(yaml_content: str | None, filename: str | None):
        """Save generated YAML content to storage directory."""
        if not yaml_content or not yaml_content.strip():
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
            save_path.write_text(yaml_content, encoding="utf-8")
            status_msg = f"✅ Saved workflow to {save_path}"
        except Exception as e:
            status_msg = f"❌ Failed to save workflow: {e}"

        return {
            generated_save_status: gr.update(value=status_msg),
            saved_workflows_dd: gr.update(
                choices=_list_saved_workflows(), value=sanitized
            ),
        }

    def _refresh_saved_dropdown():
        """Refresh list of saved workflows for dropdown."""
        return gr.update(choices=_list_saved_workflows())

    async def _run_yaml_text(yaml_text: str | None, inputs_json: str | None):
        """Run a workflow from YAML text content using JSON inputs."""
        if not yaml_text or not yaml_text.strip():
            return gr.update(value="⚠️ No workflow YAML available.")

        # Write to temporary file
        tmp_path = WORKFLOW_STORAGE_DIR / f"_tmp_{uuid.uuid4().hex}.yaml"
        try:
            tmp_path.write_text(yaml_text, encoding="utf-8")
            # Use the refactored core execution function
            return await _execute_workflow_from_json(str(tmp_path), inputs_json)
        except Exception as e:
            return gr.update(value=f"❌ Error processing workflow YAML: {e}")
        finally:
            # Clean up temp file
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except:
                    pass

    async def _run_yaml_text_as_tool(components_dict: Dict[Component, Any]):
        """Wrapper to run a workflow as a tool from generated YAML text content."""
        yaml_text = components_dict.get(generated_yaml)
        nl_input = components_dict.get(generated_tool_input)

        if not yaml_text or not yaml_text.strip():
            return {
                record_workflow_output: gr.update(value="⚠️ No workflow YAML available.")
            }

        if not nl_input or not str(nl_input).strip():
            return {
                record_workflow_output: gr.update(
                    value="⚠️ Please enter a natural language prompt for the tool run."
                )
            }

        # --- Initialize LLM ---
        def _val(tab: str, name: str, default: Any = None):
            comp = webui_manager.id_to_component.get(f"{tab}.{name}")
            return components_dict.get(comp, default) if comp else default

        provider = _val("agent_settings", "llm_provider")
        model_name = _val("agent_settings", "llm_model_name")
        temperature = float(_val("agent_settings", "llm_temperature", 0.6))
        base_url = _val("agent_settings", "llm_base_url")
        api_key = _val("agent_settings", "llm_api_key")
        ollama_ctx = _val("agent_settings", "ollama_num_ctx")
        llm = _initialize_llm(
            provider, model_name, temperature, base_url, api_key, ollama_ctx
        )
        # --- End LLM Initialization ---

        if llm is None:
            return {
                record_workflow_output: gr.update(
                    value="❌ Failed to initialise LLM. Check Agent Settings."
                )
            }

        try:
            config = BrowserConfig(
                browser_binary_path="/usr/bin/google-chrome",
                headless=False,
            )
            browser = Browser(config=config)
            workflow = Workflow(yaml_path=str(yaml_text), llm=llm, browser=browser)
            result = await workflow.run_as_tool(nl_input)
            return {
                record_workflow_output: gr.update(
                    value=f"✅ Tool run completed:\n\n{result}"
                )
            }
        except Exception as e:
            tb = traceback.format_exc()
            return {
                record_workflow_output: gr.update(
                    value=f"❌ Error running as tool: {e}\n\n{tb}"
                )
            }

    # --- New Helper for Running Uploaded Workflow as Tool ---
    async def _run_uploaded_workflow_as_tool(components_dict: Dict[Component, Any]):
        """Wrapper to run an uploaded/selected workflow as a tool."""

        # Extract inputs
        yaml_file = components_dict.get(workflow_file)
        nl_input = components_dict.get(uploaded_tool_input)

        # --- Validate nl_input ---
        if not nl_input or not str(nl_input).strip():
            return {
                upload_workflow_output: gr.update(
                    value="⚠️ Please enter a natural language prompt for the tool run."
                )
            }
        # Ensure nl_input is a string for the core function
        nl_input_str = str(nl_input)

        # Helper to get LLM settings
        def _val(tab: str, name: str, default: Any = None):
            comp = webui_manager.id_to_component.get(f"{tab}.{name}")
            return components_dict.get(comp, default) if comp else default

        # Initialize LLM
        provider = _val("agent_settings", "llm_provider")
        model_name = _val("agent_settings", "llm_model_name")
        temperature = float(_val("agent_settings", "llm_temperature", 0.6))
        base_url = _val("agent_settings", "llm_base_url")
        api_key = _val("agent_settings", "llm_api_key")
        ollama_ctx = _val("agent_settings", "ollama_num_ctx")
        llm = _initialize_llm(
            provider, model_name, temperature, base_url, api_key, ollama_ctx
        )

        if llm is None:
            return {
                upload_workflow_output: gr.update(
                    value="❌ Failed to initialise LLM. Check Agent Settings."
                )
            }

        # Call the core execution function
        result_update = await _execute_workflow_from_prompt(
            yaml_file, nl_input_str, llm
        )

        # Adapt result for the correct output component
        if isinstance(result_update, dict):
            # If error dictionary returned, update the upload output
            output_key = list(result_update.keys())[
                0
            ]  # Should be record_workflow_output
            return {upload_workflow_output: result_update[output_key]}
        else:
            # If direct gr.update returned
            return {upload_workflow_output: result_update}

    def _extract_schema(yaml_text: str | None):
        """Extract and format input schema from YAML content."""
        if not yaml_text or not yaml_text.strip():
            return "{}"
        try:
            data = yaml.safe_load(yaml_text)
            if not data:
                return "{}"
            schema = data.get("inputs", {})
            return json.dumps(schema, indent=2)
        except Exception:
            return "{}"

    # ------------------------------------------------------------------
    # Bind callbacks
    # ------------------------------------------------------------------

    def show_generating_status():
        """Show that workflow generation is in progress with a clear loading indicator."""
        loading_message = "⏳ GENERATING WORKFLOW... PLEASE WAIT ⏳"
        # Update both the schema and YAML areas to show loading status
        return (
            gr.update(value=loading_message),
            gr.update(value=""),
            gr.update(value=""),
        )

    def show_generation_complete(yaml_result, schema_result):
        """Update status based on generation result."""
        if (
            yaml_result
            and not yaml_result.startswith("❌")
            and not yaml_result.startswith("⚠️")
        ):
            return "✅ WORKFLOW GENERATION COMPLETED ✅"
        elif yaml_result and yaml_result.startswith("❌"):
            return yaml_result
        elif yaml_result and yaml_result.startswith("⚠️"):
            return yaml_result
        return "⚠️ WORKFLOW GENERATION FAILED WITH UNKNOWN ERROR ⚠️"

    # Replace the existing generate_button binding with the one that shows status
    generate_button.click(
        fn=show_generating_status,
        inputs=None,
        outputs=[
            generate_status_output,
            generated_yaml,
            generated_workflow_schema,
        ],
        queue=False,
    )

    # After showing the loading message, invoke the asynchronous generation function.
    generate_button.click(
        fn=_generate_workflow,
        inputs=set(webui_manager.get_components()),
        outputs=[generated_yaml, generated_workflow_schema],
    ).then(
        fn=show_generation_complete,
        inputs=[generated_yaml, generated_workflow_schema],
        outputs=generate_status_output,
    )

    # Bind save, refresh, run saved
    save_generated_button.click(
        fn=lambda: gr.update(value="💾 Saving workflow..."),
        inputs=None,
        outputs=[generated_save_status],
        queue=False,
    )

    save_generated_button.click(
        fn=_save_generated_workflow,
        inputs=[generated_yaml, generated_filename_tb],
        outputs=[generated_save_status, saved_workflows_dd],
    )

    refresh_saved_button.click(
        fn=_refresh_saved_dropdown,
        inputs=[],
        outputs=[saved_workflows_dd],
    )

    # Add loading status functions for running workflows
    def show_running_workflow_status():
        """Show that workflow is running."""
        return gr.update(value="⏳ RUNNING WORKFLOW... PLEASE WAIT ⏳")

    # Update run buttons to show loading status
    generated_run_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=record_workflow_output,
        queue=False,
    )

    generated_run_tool_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=record_workflow_output,
        queue=False,
    )

    # Add callbacks to display uploaded YAML content in Code component
    def update_yaml_display(file_obj):
        yaml_content, schema_text = _load_yaml_file(file_obj)
        if yaml_content:
            return {
                upload_yaml: gr.update(value=yaml_content),
                uploaded_yaml_schema: gr.update(value=schema_text),
            }
        return {
            upload_yaml: gr.update(value=""),
            uploaded_yaml_schema: gr.update(value="{}"),
        }

    # Update YAML display when file is uploaded
    workflow_file.change(
        fn=update_yaml_display,
        inputs=[workflow_file],
        outputs=[upload_yaml, uploaded_yaml_schema],
    )

    # Update YAML display when selecting from dropdown (through workflow_file update)
    saved_workflows_dd.change(
        fn=lambda x: gr.update(value=str(WORKFLOW_STORAGE_DIR / x) if x else None),
        inputs=[saved_workflows_dd],
        outputs=[workflow_file],
    )

    # Add loading status to run buttons
    generated_run_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=record_workflow_output,
        queue=False,
    )
    generated_run_button.click(
        fn=_run_yaml_text,
        inputs=[generated_yaml, generated_workflow_inputs_json],
        outputs=[record_workflow_output],
    )

    generated_run_tool_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=record_workflow_output,
        queue=False,
    )
    generated_run_tool_button.click(
        fn=_run_yaml_text_as_tool,
        inputs=set(webui_manager.get_components()),
        outputs=[record_workflow_output],
    )

    # Add bindings for the Upload Workflow tab buttons
    run_uploaded_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=upload_workflow_output,
        queue=False,
    )
    run_uploaded_button.click(
        fn=_execute_workflow_from_json,
        inputs=[workflow_file, uploaded_workflow_inputs_json],
        outputs=[upload_workflow_output],
    )

    run_uploaded_tool_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=upload_workflow_output,
        queue=False,
    )
    run_uploaded_tool_button.click(
        fn=_run_uploaded_workflow_as_tool,
        inputs=set(webui_manager.get_components()),
        outputs=[upload_workflow_output],
    )

    # Also add binding for loaded workflows from dropdown
    saved_workflows_dd.change(
        fn=lambda x: gr.update(value=str(WORKFLOW_STORAGE_DIR / x) if x else None),
        inputs=[saved_workflows_dd],
        outputs=[workflow_file],
    )
