#!/usr/bin/env python
"""
Test script to verify workflow recorder functionality
"""

import asyncio
import logging
import os

from playwright.async_api import async_playwright

from src.utils import workflow_recorder

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Test the workflow recorder with Playwright"""
    logger.info("Starting workflow recorder test")

    # Create a directory for the workflow recordings
    os.makedirs("./tmp/workflows", exist_ok=True)

    # Launch a browser with Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Navigate to a test page
        await page.goto("https://www.google.com")
        logger.info("Page loaded")

        # Inject the recorder extension
        result = await workflow_recorder.inject_recorder_extension(page)
        logger.info(f"Extension injection result: {result}")

        # Start recording
        start_result = await workflow_recorder.start_recording(page)
        logger.info(f"Recording started: {start_result}")

        # Perform some actions
        await page.fill('input[name="q"]', "workflow automation test")
        await page.press('input[name="q"]', "Enter")
        await page.wait_for_load_state("networkidle")

        # Wait a moment to get some recording data
        await asyncio.sleep(3)

        # Stop recording
        stop_result = await workflow_recorder.stop_recording(page)
        logger.info(f"Recording stopped: {stop_result}")

        # Get the recorded events
        events = await workflow_recorder.get_recorded_events(page)
        logger.info(f"Retrieved {len(events)} events")
        for event in events:
            logger.info(f"Event: {event.get('type')} - {event.get('timestamp')}")

        # Save the events to a file
        with open("./tmp/workflows/test_workflow.json", "w") as f:
            import json

            json.dump(events, f, indent=2)
        logger.info("Saved workflow to ./tmp/workflows/test_workflow.json")

        # Close browser
        await browser.close()

    logger.info("Test completed")


if __name__ == "__main__":
    asyncio.run(main())
