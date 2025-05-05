import os
import gradio as gr


from src.webui.webui_manager import WebuiManager
from src.recorder.recorder import WorkflowRecorder
from browser_use.browser.browser import BrowserConfig


def create_recorder(webui_manager: WebuiManager):
    """
    Creates a recorder instance
    """
    tab_components = {}
    with gr.Column():
        url_input = gr.Textbox(label="Website URL to Record (default to browser-use.com)", placeholder="example.com")
        run_recorder = gr.Button("Run recorder", variant="primary")

    tab_components.update(dict(
        run_recorder=run_recorder,
        url_input=url_input
    ))

    webui_manager.add_components("create_recorder", tab_components)

    async def run_recorder_with_url(url):
        browser_binary_path = (
            os.getenv("CHROME_PATH", None)
        )
        config=BrowserConfig(
            browser_binary_path=browser_binary_path,
        )
        recorder = WorkflowRecorder(config)
        url = url.strip()
        if not url:
            url = 'https://www.browser-use.com/'
        elif not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            await recorder.record_workflow(url)
        except Exception as e:
            print(f"An error occurred while recording the workflow: {e}")

    run_recorder.click(
        fn=run_recorder_with_url,
        inputs=[url_input],
        outputs=[]
    )
