import json
import traceback
from pathlib import Path
from typing import Any, Dict

import gradio as gr  # type: ignore
from gradio.components import Component  # type: ignore

from src.utils import llm_provider
from src.webui.webui_manager import WebuiManager
from src.workflows.workflow import Workflow
from src.workflows.workflow_builder import parse_session


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
        with gr.TabItem("🛠️ Generate from Session JSON"):
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

            generated_yaml = gr.Code(
                language="yaml", label="Generated Workflow YAML", interactive=False
            )

        # ===============================================================
        # 2. RUN WORKFLOW TAB
        # ===============================================================
        with gr.TabItem("▶️ Run Workflow"):
            with gr.Group():
                with gr.Row():
                    workflow_file = gr.File(
                        label="Workflow YAML",
                        file_types=[".yaml", ".yml"],
                        interactive=True,
                    )
                    workflow_inputs_json = gr.Textbox(
                        label="Workflow Inputs (JSON)",
                        placeholder='{"example_key": "value"}',
                        lines=4,
                        interactive=True,
                        info="Optional JSON dictionary with inputs required by the workflow",
                    )
                with gr.Row():
                    run_workflow_button = gr.Button("🏃 Run", variant="primary")

                workflow_output = gr.Textbox(
                    label="Workflow Output / Status",
                    lines=10,
                    interactive=False,
                )

                # --- Run as Tool UI ---
                tool_input = gr.Textbox(
                    label="Natural Language Prompt (Run as Tool)",
                    placeholder="Describe what you want to achieve with this workflow",
                    lines=2,
                    interactive=True,
                )
                run_tool_button = gr.Button("🧰 Run as Tool", variant="secondary")

    # ------------------------------------------------------------------
    # Register components so they can be saved via WebuiManager
    # ------------------------------------------------------------------

    tab_components.update(
        dict(
            # Generate
            session_json_file=session_json_file,
            user_goal_tb=user_goal_tb,
            generate_button=generate_button,
            generated_yaml=generated_yaml,
            # Run
            workflow_file=workflow_file,
            workflow_inputs_json=workflow_inputs_json,
            run_workflow_button=run_workflow_button,
            workflow_output=workflow_output,
            tool_input=tool_input,
            run_tool_button=run_tool_button,
        )
    )
    webui_manager.add_components("workflows", tab_components)

    # ------------------------------------------------------------------
    # Callback helpers
    # ------------------------------------------------------------------

    async def _initialize_llm(
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
            return {
                generated_yaml: gr.update(value="⚠️ Please upload a session JSON file.")
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

        llm = await _initialize_llm(
            provider, model_name, temperature, base_url, api_key, ollama_ctx
        )

        if llm is None:
            return {
                generated_yaml: gr.update(
                    value="❌ Failed to initialise LLM. Check Agent Settings."
                )
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
            return {generated_yaml: gr.update(value=yaml_content)}
        except Exception as e:
            tb = traceback.format_exc()
            return {
                generated_yaml: gr.update(
                    value=f"❌ Error generating workflow: {e}\n\n{tb}"
                )
            }

    async def _run_workflow(yaml_file: Any, inputs_json: str | None):
        """Execute the selected workflow and return a gradio update for the output box."""
        if yaml_file is None:
            return gr.update(
                value="⚠️ Please upload a workflow YAML file before running."
            )

        yaml_path = Path(getattr(yaml_file, "name", yaml_file))
        if not yaml_path.exists():
            # If the file was uploaded through gr.File, it may already reside on disk.
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
            workflow = Workflow(yaml_path=str(yaml_path))
            results = await workflow.run_async(inputs=inputs_dict or None)
            pretty = json.dumps(results, indent=2, ensure_ascii=False)
            return gr.update(value=f"✅ Workflow finished successfully\n\n{pretty}")
        except Exception as e:
            tb = traceback.format_exc()
            return gr.update(value=f"❌ Error running workflow: {e}\n\n{tb}")

    async def _run_workflow_tool(components_dict: Dict[Component, Any]):
        """Run the workflow as a structured tool given a natural language prompt."""
        yaml_comp = webui_manager.get_component_by_id("workflows.workflow_file")
        nl_comp = webui_manager.get_component_by_id("workflows.tool_input")

        yaml_file = components_dict.get(yaml_comp)
        nl_input = components_dict.get(nl_comp, "")

        if yaml_file is None:
            return {
                nl_comp: gr.update(interactive=True),
                workflow_output: gr.update(
                    value="⚠️ Please upload a workflow YAML file before running as tool."
                ),
            }

        if not nl_input or not str(nl_input).strip():
            return {
                workflow_output: gr.update(
                    value="⚠️ Please enter a natural language prompt for the tool run."
                )
            }

        yaml_path = Path(getattr(yaml_file, "name", yaml_file))
        if not yaml_path.exists():
            return {
                workflow_output: gr.update(value=f"⚠️ YAML file not found: {yaml_path}")
            }

        # Build LLM instance from Agent Settings tab (reuse helper)
        def _val(tab: str, name: str, default: Any = None):
            comp = webui_manager.id_to_component.get(f"{tab}.{name}")
            return components_dict.get(comp, default) if comp else default

        provider = _val("agent_settings", "llm_provider")
        model_name = _val("agent_settings", "llm_model_name")
        temperature = float(_val("agent_settings", "llm_temperature", 0.6))
        base_url = _val("agent_settings", "llm_base_url")
        api_key = _val("agent_settings", "llm_api_key")
        ollama_ctx = _val("agent_settings", "ollama_num_ctx")

        llm = await _initialize_llm(
            provider, model_name, temperature, base_url, api_key, ollama_ctx
        )

        if llm is None:
            return {
                workflow_output: gr.update(
                    value="❌ Failed to initialise LLM. Check Agent Settings."
                )
            }

        try:
            workflow = Workflow(yaml_path=str(yaml_path), llm=llm)
            result = await workflow.run_as_tool(nl_input)
            return {
                workflow_output: gr.update(value=f"✅ Tool run completed:\n\n{result}")
            }
        except Exception as e:
            tb = traceback.format_exc()
            return {
                workflow_output: gr.update(
                    value=f"❌ Error running as tool: {e}\n\n{tb}"
                )
            }

    # ------------------------------------------------------------------
    # Bind callbacks
    # ------------------------------------------------------------------

    generate_button.click(
        fn=_generate_workflow,
        inputs=set(webui_manager.get_components()),
        outputs=[generated_yaml],
    )

    run_workflow_button.click(
        fn=_run_workflow,
        inputs=[workflow_file, workflow_inputs_json],
        outputs=[workflow_output],
    )

    run_tool_button.click(
        fn=_run_workflow_tool,
        inputs=set(webui_manager.get_components()),
        outputs=[workflow_output],
    )
