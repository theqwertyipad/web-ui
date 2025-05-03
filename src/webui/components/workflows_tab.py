import json
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import gradio as gr
import yaml
from browser_use.browser.browser import Browser, BrowserConfig
from gradio.components import Component

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
            # Add instructions markdown
            gr.Markdown("""
            ### Recording a Workflow
            
            **Step 1:** Install the browser extension from the Agent Settings tab
            
            **Step 2:** Open a new tab and turn on recording (click the extension icon)
            
            **Step 3:** Complete the task you want to automate
            
            **Step 4:** Stop recording and download the session JSON file
            
            **Step 5:** Upload the JSON file below and describe what you want to achieve
            """)

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

            generate_status_output = gr.Textbox(
                label="Generated Workflow Output / Status",
                lines=2,
                interactive=False,
            )

            generated_yaml = gr.Code(
                language="yaml", label="Generated Workflow YAML", interactive=False
            )

            # --- Display parsed input schema ---
            generated_workflow_schema = gr.Code(
                language="json", label="Input Schema (from YAML)", interactive=False
            )

            # Add save instructions
            gr.Markdown("""
            ### Saving Your Workflow
            
            Save your workflow with a descriptive name. Saved workflows will be available in the "Run Workflows" tab for future use.
            """)

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
            
            # Add run instructions for generated workflow
            gr.Markdown("""
            ### Testing Your Generated Workflow
            
            You can test your workflow immediately after generation:
            
            **Option 1: Run with JSON** - Provide specific inputs in JSON format
            
            **Option 2: Run as Tool** - Use natural language to describe what you want the workflow to do
            
            """)

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
        with gr.TabItem("📥 Run Workflows"):
            # Add instructions markdown
            gr.Markdown("""
            ### Running Saved Workflows
            
            You can run workflows you've created or upload workflow files created by others.
            
            **Option 1:** Select from your saved workflows in the dropdown below
            
            **Option 2:** Upload a workflow YAML file
            """)

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

            # Add run instructions
            gr.Markdown("""
            ### Executing Your Workflow
            
            There are two ways to run your workflow:
            
            **1. JSON Input:** Provide inputs as a JSON object matching the schema above
            
            **2. Natural Language:** Describe what you want the workflow to do in plain English
            
            If your inputs don't work or the workflow doesn't behave as expected, you can always modify and try again!
            """)

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
                    info="Give the workflow input via natural language.",
                    elem_id="upload_tool_input",
                )

            with gr.Row():
                run_uploaded_button = gr.Button("🏃 Run from JSON", variant="secondary")
                run_uploaded_tool_button = gr.Button(
                    "🧰 Run from Prompt", variant="primary"
                )

            upload_workflow_output = gr.Textbox(
                label="Workflow Output / Status",
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
    # Helper functions
    # ------------------------------------------------------------------

    def _sanitize_filename(name: str) -> Optional[str]:
        """Return sanitized filename ensuring `.yaml` extension or None if invalid."""
        if not name:
            return None
        name = name.strip()
        # Default extension
        if not name.lower().endswith((".yaml", ".yml")):
            name += ".yaml"

        # Prevent directory traversal
        if any(part in ("..", "/") for part in name.split(os.sep)):
            return None
        return name

    def _initialize_llm(
        provider: Optional[str],
        model_name: Optional[str],
        temperature: float,
        base_url: Optional[str],
        api_key: Optional[str],
        num_ctx: Optional[int] = None,
    ):
        """Create an LLM instance from the given settings (returns None on failure)."""
        if not provider or not model_name:
            return None

        try:
            llm = llm_provider.get_llm_model(
                provider=provider,
                model_name="gpt-4o",
                temperature=temperature,
                base_url=base_url or None,
                api_key=api_key or None,
                num_ctx=num_ctx if provider == "ollama" else None,
            )
            return llm
        except Exception as e:
            print(f"Failed to initialize LLM: {e}")
            return None

    def _extract_schema(yaml_text: Optional[str]) -> str:
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

    def _get_agent_settings(components_dict):
        """Helper to get LLM settings from Agent Settings tab."""

        def _val(tab: str, name: str, default: Any = None):
            comp = webui_manager.id_to_component.get(f"{tab}.{name}")
            return components_dict.get(comp, default) if comp else default

        provider = _val("agent_settings", "llm_provider")
        model_name = _val("agent_settings", "llm_model_name")
        temperature = float(_val("agent_settings", "llm_temperature", 0.6))
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

    def _resolve_yaml_path(yaml_file) -> Optional[Path]:
        """Resolve YAML file path, checking if it exists in WORKFLOW_STORAGE_DIR."""
        if yaml_file is None:
            return None

        yaml_path = Path(getattr(yaml_file, "name", str(yaml_file)))
        if yaml_path.exists():
            return yaml_path

        # Check if it's a relative path within WORKFLOW_STORAGE_DIR
        potential_path = WORKFLOW_STORAGE_DIR / yaml_path.name
        if potential_path.exists():
            return potential_path

        return None

    # ------------------------------------------------------------------
    # Main workflow functions
    # ------------------------------------------------------------------

    async def _generate_workflow(components: Dict[Component, Any]):
        """Generate YAML workflow from a simplified session JSON + goal."""
        session_file_obj = components.get(session_json_file)
        session_path_str = None

        if session_file_obj:
            session_path_str = str(getattr(session_file_obj, "name", session_file_obj))

        user_goal_val = components.get(user_goal_tb, "")

        if not session_path_str:
            return {
                generate_status_output: gr.update(
                    value="⚠️ Please upload a session JSON file."
                ),
                generated_yaml: gr.update(value=""),
                generated_workflow_schema: gr.update(value="{}"),
            }

        # Build LLM instance from Agent Settings tab
        settings = _get_agent_settings(components)
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
                generate_status_output: gr.update(
                    value="❌ Failed to initialize LLM. Check Agent Settings."
                ),
                generated_yaml: gr.update(value=""),
                generated_workflow_schema: gr.update(value="{}"),
            }

        try:
            workflow_obj = parse_session(
                session_path_str,
                user_goal_val,
                llm=llm,
                use_screenshots=settings["use_screenshots"],
            )
            yaml_path = Path(workflow_obj.yaml_path)
            yaml_content = yaml_path.read_text(encoding="utf-8")

            # Extract schema
            schema_text = _extract_schema(yaml_content)

            return {
                generate_status_output: gr.update(
                    value="✅ WORKFLOW GENERATION COMPLETED ✅"
                ),
                generated_yaml: gr.update(value=yaml_content),
                generated_workflow_schema: gr.update(value=schema_text),
            }
        except Exception as e:
            tb = traceback.format_exc()
            return {
                generate_status_output: gr.update(
                    value=f"❌ Error generating workflow: {e}\n\n{tb}"
                ),
                generated_yaml: gr.update(value=""),
                generated_workflow_schema: gr.update(value="{}"),
            }

    async def _execute_workflow_from_json(yaml_file: Any, inputs_json: Optional[str]):
        """Execute the workflow using JSON inputs."""
        # Validate YAML file
        if yaml_file is None:
            return gr.update(
                value="⚠️ Please upload/select a workflow YAML file before running."
            )

        yaml_path = _resolve_yaml_path(yaml_file)
        if yaml_path is None:
            return gr.update(
                value=f"⚠️ YAML file not found: {getattr(yaml_file, 'name', str(yaml_file))}"
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

    async def _execute_workflow_as_tool(
        yaml_path: Path, nl_input: str, llm: Any, output_component: Component
    ):
        """
        Core function to execute a workflow as a tool.
        Returns a dictionary with the output component as the key.
        """
        # Validate inputs
        if yaml_path is None:
            return {
                output_component: gr.update(
                    value="⚠️ Please upload/select a workflow YAML file before running as tool."
                )
            }

        if not nl_input or not str(nl_input).strip():
            return {
                output_component: gr.update(
                    value="⚠️ Please enter a natural language prompt for the tool run."
                )
            }

        if llm is None:
            return {
                output_component: gr.update(
                    value="❌ Failed to initialize LLM. Check Agent Settings."
                )
            }

        # Execute workflow
        try:
            config = BrowserConfig(
                browser_binary_path="/usr/bin/google-chrome",
                headless=False,
            )
            browser = Browser(config=config)
            workflow = Workflow(yaml_path=str(yaml_path), llm=llm, browser=browser)
            result = await workflow.run_as_tool(nl_input)
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

    async def _run_generated_workflow_as_tool(components_dict: Dict[Component, Any]):
        """Run workflow as a tool from generated YAML."""
        yaml_text = components_dict.get(generated_yaml)
        nl_input = components_dict.get(generated_tool_input)

        if not yaml_text or not yaml_text.strip():
            return {
                record_workflow_output: gr.update(value="⚠️ No workflow YAML available.")
            }

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
                record_workflow_output: gr.update(
                    value="❌ Failed to initialize LLM. Check Agent Settings."
                )
            }

        # Write yaml to temporary file
        tmp_path = WORKFLOW_STORAGE_DIR / f"_tmp_{uuid.uuid4().hex}.yaml"
        try:
            tmp_path.write_text(yaml_text, encoding="utf-8")
            return await _execute_workflow_as_tool(
                tmp_path, nl_input, llm, record_workflow_output
            )
        except Exception as e:
            tb = traceback.format_exc()
            return {
                record_workflow_output: gr.update(
                    value=f"❌ Error running as tool: {e}\n\n{tb}"
                )
            }
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except:
                    pass

    async def _run_uploaded_workflow_as_tool(components_dict: Dict[Component, Any]):
        """Run an uploaded workflow as a tool."""
        yaml_file = components_dict.get(workflow_file)
        nl_input = components_dict.get(uploaded_tool_input)

        # Resolve YAML path
        yaml_path = _resolve_yaml_path(yaml_file)
        if yaml_path is None:
            return {
                upload_workflow_output: gr.update(
                    value=f"⚠️ YAML file not found: {getattr(yaml_file, 'name', str(yaml_file))}"
                )
            }

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
            yaml_path, nl_input, llm, upload_workflow_output
        )

    # ------------------------------------------------------------------
    # Persistence functions
    # ------------------------------------------------------------------

    def _save_generated_workflow(yaml_content: Optional[str], filename: Optional[str]):
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

    async def _run_yaml_text(yaml_text: Optional[str], inputs_json: Optional[str]):
        """Run a workflow from YAML text content using JSON inputs."""
        if not yaml_text or not yaml_text.strip():
            return gr.update(value="⚠️ No workflow YAML available.")

        # Write to temporary file
        tmp_path = WORKFLOW_STORAGE_DIR / f"_tmp_{uuid.uuid4().hex}.yaml"
        try:
            tmp_path.write_text(yaml_text, encoding="utf-8")
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

    def update_yaml_display(file_obj):
        """Update the YAML display when a file is uploaded or selected."""
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

    # ------------------------------------------------------------------
    # Bind callbacks - Generate tab
    # ------------------------------------------------------------------

    # Generate workflow button with loading status
    generate_button.click(
        fn=show_generating_status,
        inputs=None,
        outputs=[generate_status_output, generated_yaml, generated_workflow_schema],
        queue=False,
    ).then(
        fn=_generate_workflow,
        inputs=set(webui_manager.get_components()),
        outputs=[generate_status_output, generated_yaml, generated_workflow_schema],
    )

    # Save generated workflow
    save_generated_button.click(
        fn=lambda: gr.update(value="💾 Saving workflow..."),
        inputs=None,
        outputs=[generated_save_status],
        queue=False,
    ).then(
        fn=_save_generated_workflow,
        inputs=[generated_yaml, generated_filename_tb],
        outputs=[generated_save_status, saved_workflows_dd],
    )

    # Run generated workflow with JSON inputs
    generated_run_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=record_workflow_output,
        queue=False,
    ).then(
        fn=_run_yaml_text,
        inputs=[generated_yaml, generated_workflow_inputs_json],
        outputs=[record_workflow_output],
    )

    # Run generated workflow as tool
    generated_run_tool_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=record_workflow_output,
        queue=False,
    ).then(
        fn=_run_generated_workflow_as_tool,
        inputs=set(webui_manager.get_components()),
        outputs=[record_workflow_output],
    )

    # ------------------------------------------------------------------
    # Bind callbacks - Upload/Run tab
    # ------------------------------------------------------------------

    # Refresh saved workflows dropdown
    refresh_saved_button.click(
        fn=_refresh_saved_dropdown,
        inputs=[],
        outputs=[saved_workflows_dd],
    )

    # Update YAML display when file is uploaded
    workflow_file.change(
        fn=update_yaml_display,
        inputs=[workflow_file],
        outputs=[upload_yaml, uploaded_yaml_schema],
    )

    # Update workflow file when dropdown selection changes
    saved_workflows_dd.change(
        fn=lambda x: gr.update(value=str(WORKFLOW_STORAGE_DIR / x) if x else None),
        inputs=[saved_workflows_dd],
        outputs=[workflow_file],
    )

    # Run uploaded workflow with JSON inputs
    run_uploaded_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=upload_workflow_output,
        queue=False,
    ).then(
        fn=_execute_workflow_from_json,
        inputs=[workflow_file, uploaded_workflow_inputs_json],
        outputs=[upload_workflow_output],
    )

    # Run uploaded workflow as tool
    run_uploaded_tool_button.click(
        fn=show_running_workflow_status,
        inputs=None,
        outputs=upload_workflow_output,
        queue=False,
    ).then(
        fn=_run_uploaded_workflow_as_tool,
        inputs=set(webui_manager.get_components()),
        outputs=[upload_workflow_output],
    )
