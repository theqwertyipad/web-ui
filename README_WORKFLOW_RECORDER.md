# Browser Workflow Recorder

A component for Browser-Use that allows recording, editing, and replaying browser workflows.

## Features

- Record browser interactions in real-time
- View and edit recorded workflows in the UI
- Save workflows as JSON files
- Load and replay saved workflows
- Manually add or modify workflow steps

## Installation

Ensure you have all required dependencies installed:

```bash
# Install Python dependencies
pip install gradio playwright

# Install Playwright browsers
python -m playwright install
```

## Setup

1. The workflow recorder is integrated with the Browser-Use WebUI.
2. Start the WebUI using the following command:
   ```bash
   python webui.py --ip 127.0.0.1 --port 7788
   ```
3. Navigate to the "🔍 Record Workflow" tab in the WebUI.

## Usage

### Recording a Workflow

1. Before recording, you need to have the browser running:
   - Go to the "🤖 Run Agent" tab first
   - Run a simple task to start the browser (e.g., "Navigate to google.com")
   - Once the browser is running, switch to the "🔍 Record Workflow" tab

2. Start recording:
   - Enter a name for your workflow in the "Workflow Name" field
   - Click "▶️ Start Recording"
   - Perform the actions you want to record in the browser window
   - Click "⏹️ Stop Recording" when finished

3. Review and save:
   - Review the recorded workflow in the "Current Workflow" panel
   - You can edit the workflow using the JSON editor if needed
   - Click "💾 Save Workflow" to save the workflow as a JSON file

### Editing a Workflow

- You can manually add actions using the buttons:
  - "Add Navigation" - Navigate to a URL
  - "Add Click" - Click on an element
  - "Add Input" - Enter text into a field
  - "Add Wait" - Add a waiting period

- You can also delete steps:
  - Click "Delete Event"
  - Enter the index of the event to delete
  - Click "Confirm Delete"

### Working with the Main WebUI

The workflow recorder is designed to work with the main Browser-Use WebUI started with:

```bash
python webui.py --ip 127.0.0.1 --port 7788
```

When using this startup method:

1. Always start a browser first using the "🤖 Run Agent" tab
2. Then switch to the "🔍 Record Workflow" tab to record your workflow
3. The recorder will use the same browser instance that's already running

## Troubleshooting

If you encounter issues:

1. **Browser not starting:** Make sure you've started a browser in the "🤖 Run Agent" tab first

2. **Recording not working:**
   - Check the browser console for errors (Press F12 in the browser, then look at the Console tab)
   - Look for messages starting with "[WorkflowRecorder]"
   - Refresh the page and try again

3. **Cannot save workflow:**
   - Ensure the tmp/workflows directory exists
   - Make sure you have write permissions to that directory

## Example Workflow

Here's what a recorded workflow looks like:

```json
[
  {
    "type": "navigation",
    "timestamp": 1745983750345,
    "tabId": 1,
    "url": "https://www.google.com"
  },
  {
    "type": "click",
    "timestamp": 1745983755500,
    "tabId": 1,
    "url": "https://www.google.com",
    "cssSelector": "input[name=\"q\"]",
    "elementTag": "INPUT"
  },
  {
    "type": "input",
    "timestamp": 1745983756000,
    "tabId": 1,
    "url": "https://www.google.com",
    "cssSelector": "input[name=\"q\"]",
    "value": "browser automation workflow"
  },
  {
    "type": "keypress",
    "timestamp": 1745983756500,
    "tabId": 1,
    "url": "https://www.google.com",
    "key": "Enter"
  }
]
``` 