import json
import traceback
from pathlib import Path
from typing import Any

import gradio as gr  # type: ignore
from gradio.components import Component  # type: ignore

from src.webui.webui_manager import WebuiManager
from src.workflows.workflow import Workflow


def create_workflows_tab(webui_manager: WebuiManager):
    """
    Creates a Workflows tab for uploading a workflow YAML file, specifying optional
    JSON inputs and executing the workflow.  The execution result (or errors) is
    rendered in a read-only textbox.
    """
    # Gather already-registered components so that we can later pass the full
    # component set into WebuiManager.save_config if needed.
    tab_components: dict[str, Component] = {}

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
            run_workflow_button = gr.Button("▶️ Run Workflow", variant="primary")

    workflow_output = gr.Textbox(
        label="Workflow Output / Status",
        lines=10,
        interactive=False,
    )

    # Register components so their state can be saved via WebuiManager
    tab_components.update(
        dict(
            workflow_file=workflow_file,
            workflow_inputs_json=workflow_inputs_json,
            run_workflow_button=run_workflow_button,
            workflow_output=workflow_output,
        )
    )
    webui_manager.add_components("workflows", tab_components)

    # ------------------------------------------------------------------
    # Callback helpers
    # ------------------------------------------------------------------

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

    run_workflow_button.click(
        fn=_run_workflow,
        inputs=[workflow_file, workflow_inputs_json],
        outputs=[workflow_output],
    )
