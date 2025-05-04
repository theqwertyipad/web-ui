import asyncio
import sys

from browser_use.browser.browser import Browser, BrowserConfig
from langchain_openai import ChatOpenAI

from src.workflows.workflow import Workflow
from src.workflows.workflow_builder import save_clean_recording


async def main(input_str: str):
    recording_path = "linkedin.json"
    workflow_path = recording_path.replace(".json", "_workflow.json")

    save_clean_recording(recording_path, workflow_path)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    browser_config = BrowserConfig(
        headless=False,
        extra_browser_args=[
            "--remote-debugging-port=9222",
            "--load-extension ~/rrweb-recorder/dist/",
        ],
        browser_binary_path="/usr/bin/google-chrome",
    )
    browser = Browser(config=browser_config)

    workflow = Workflow(
        json_path=workflow_path,
        browser=browser,
        llm=llm,
        fallback_to_agent=False,
    )
    await workflow.run_as_tool(input_str)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please provide an input string as argument")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
