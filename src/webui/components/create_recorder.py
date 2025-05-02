import gradio as gr
from gradio.components import Component
import asyncio

from src.webui.webui_manager import WebuiManager
from src.utils import config
from src.recorder.recorder import WorkflowRecorder


def create_recorder(webui_manager: WebuiManager):
    """
    Creates a load and save config tab.
    """
    input_components = set(webui_manager.get_components())
    tab_components = {}
    with gr.Column():
        url_input = gr.Textbox(label="Website URL to Record", placeholder="example.com")
        run_recorder = gr.Button("Run recorder", variant="primary")

    tab_components.update(dict(
        run_recorder=run_recorder,
        url_input=url_input
    ))

    webui_manager.add_components("create_recorder", tab_components)

    async def run_recorder_with_url(url):
        if not url:
            url = 'current_url'
        if not url.startswith('http://www.') and not url.startswith('https://www.') and url != 'current_url':
            url = 'https://' + url
        await WorkflowRecorder().record_workflow(url)

    def run_recorder_with_url_sync(url):
        asyncio.run(run_recorder_with_url(url))

    run_recorder.click(
        fn=run_recorder_with_url_sync,
        inputs=[url_input],
        outputs=[]
    )
