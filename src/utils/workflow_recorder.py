import json
import logging
import os

logger = logging.getLogger(__name__)

# Directory containing the extension code
DEFAULT_EXTENSION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "src",
    "workflow",
    "recorder_extension",
    "dist",
)


def is_extension_available() -> bool:
    """
    Check if the Chrome extension is available

    Returns:
        bool: True if the extension is available, False otherwise
    """
    return os.path.exists(DEFAULT_EXTENSION_DIR)


async def check_for_extension(page):
    """
    Check if the extension is loaded in the page

    Args:
        page: The browser page to check

    Returns:
        bool: True if the extension is loaded, False otherwise
    """
    try:
        # Try to detect if the extension is loaded by checking for its namespace
        result = await page.evaluate("""
            () => {
                return window.BrowserUseRecorder !== undefined || 
                       window.chrome?.extension?.BrowserUseRecorder !== undefined;
            }
        """)
        return bool(result)
    except Exception as e:
        logger.error(f"Error checking for extension: {e}")
        return False


# The extension code as a JavaScript string
RECORDER_EXTENSION_CODE = """
// Workflow recorder extension for browser-use
// This code will be injected into the browser to record user interactions

// Wrapper for compatibility with different browser environments
(function() {
    // Store events
    let events = [];
    let isRecording = false;
    let startTime = 0;

    // Element selectors
    function getXPath(element) {
        if (!element) return "";
        if (element.id) return `id("${element.id}")`;
        if (element === document.body) return element.tagName.toLowerCase();

        let ix = 0;
        const siblings = element.parentNode?.children;
        if (siblings) {
            for (let i = 0; i < siblings.length; i++) {
                const sibling = siblings[i];
                if (sibling === element) {
                    return `${getXPath(element.parentElement)}/${element.tagName.toLowerCase()}[${ix + 1}]`;
                }
                if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                    ix++;
                }
            }
        }
        return element.tagName.toLowerCase();
    }

    function getCssSelector(element) {
        if (!element) return "";
        if (element.id) return `#${element.id}`;
        
        // Create a selector with class names - similar to the provided rrweb extension
        if (element.classList && element.classList.length > 0) {
            const validClassPattern = /^[a-zA-Z_][a-zA-Z0-9_-]*$/;
            let selector = element.tagName.toLowerCase();
            element.classList.forEach((className) => {
                if (className && validClassPattern.test(className)) {
                    selector += `.${CSS.escape(className)}`;
                }
            });
            return selector;
        }
        
        // Try with attributes - expanded set from the rrweb extension
        const safeAttributes = [
            'name', 'type', 'placeholder', 'role', 'data-testid', 'data-id', 
            'data-qa', 'data-cy', 'aria-label', 'aria-labelledby', 'aria-describedby',
            'for', 'autocomplete', 'required', 'readonly', 'alt', 'title'
        ];
        
        for (const attr of safeAttributes) {
            const value = element.getAttribute(attr);
            if (value) {
                return `${element.tagName.toLowerCase()}[${attr}="${value}"]`;
            }
        }
        
        // Fallback to positioning
        const parent = element.parentNode;
        if (parent && parent !== document) {
            const children = Array.from(parent.children);
            const index = children.indexOf(element) + 1;
            return `${getCssSelector(parent)} > ${element.tagName.toLowerCase()}:nth-child(${index})`;
        }
        
        return element.tagName.toLowerCase();
    }

    // Event handlers
    function handleClick(event) {
        if (!isRecording) return;
        
        const target = event.target;
        if (!target || target.nodeType !== 1) return;
        
        events.push({
            type: "click",
            timestamp: Date.now(),
            tabId: 1, // Simplified
            url: document.location.href,
            frameUrl: window.location.href,
            xpath: getXPath(target),
            cssSelector: getCssSelector(target),
            elementTag: target.tagName,
            elementText: target.textContent?.trim().slice(0, 200) || ""
        });
        
        console.log("[WorkflowRecorder] Click recorded:", getCssSelector(target));
    }

    function handleInput(event) {
        if (!isRecording) return;
        
        const target = event.target;
        if (!target || !('value' in target)) return;
        
        const isPassword = target.type === 'password';
        
        events.push({
            type: "input",
            timestamp: Date.now(),
            tabId: 1, // Simplified
            url: document.location.href,
            frameUrl: window.location.href,
            xpath: getXPath(target),
            cssSelector: getCssSelector(target),
            elementTag: target.tagName,
            value: isPassword ? "********" : target.value
        });
        
        console.log("[WorkflowRecorder] Input recorded:", getCssSelector(target));
    }

    // Handle select changes - similar to rrweb extension
    function handleSelectChange(event) {
        if (!isRecording) return;
        
        const target = event.target;
        if (!target || target.tagName !== "SELECT") return;
        
        try {
            const selectedOption = target.options[target.selectedIndex];
            events.push({
                type: "select",
                timestamp: Date.now(),
                tabId: 1,
                url: document.location.href,
                frameUrl: window.location.href,
                xpath: getXPath(target),
                cssSelector: getCssSelector(target),
                elementTag: target.tagName,
                selectedValue: target.value,
                selectedText: selectedOption ? selectedOption.text : ""
            });
            
            console.log("[WorkflowRecorder] Select change recorded:", getCssSelector(target));
        } catch (error) {
            console.error("Error capturing select change:", error);
        }
    }

    // Handle keypress events - similar to rrweb extension
    const CAPTURED_KEYS = new Set([
        "Enter", "Tab", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
        "Home", "End", "PageUp", "PageDown", "Backspace", "Delete"
    ]);
    
    function handleKeydown(event) {
        if (!isRecording) return;
        
        const key = event.key;
        let keyToLog = "";
        
        // Check if it's a key we explicitly capture
        if (CAPTURED_KEYS.has(key)) {
            keyToLog = key;
        }
        // Check for common modifier combinations (Ctrl/Cmd + key)
        else if ((event.ctrlKey || event.metaKey) && key.length === 1 && /[a-zA-Z0-9]/.test(key)) {
            keyToLog = `CmdOrCtrl+${key.toUpperCase()}`;
        }
        
        // If we have a key we want to log, send the event
        if (keyToLog) {
            const target = event.target;
            let xpath = "";
            let cssSelector = "";
            let elementTag = "document"; // Default if target is not an element
            
            if (target && typeof target.tagName === "string") {
                try {
                    xpath = getXPath(target);
                    cssSelector = getCssSelector(target);
                    elementTag = target.tagName;
                } catch (e) {
                    console.error("Error getting selector for keydown target:", e);
                }
            }
            
            events.push({
                type: "keypress",
                timestamp: Date.now(),
                tabId: 1,
                url: document.location.href,
                frameUrl: window.location.href,
                key: keyToLog,
                xpath: xpath,
                cssSelector: cssSelector,
                elementTag: elementTag
            });
            
            console.log("[WorkflowRecorder] Key press recorded:", keyToLog);
        }
    }

    function handleNavigation() {
        if (!isRecording) return;
        
        events.push({
            type: "navigation",
            timestamp: Date.now(),
            tabId: 1, // Simplified
            url: document.location.href
        });
        
        console.log("[WorkflowRecorder] Navigation recorded:", document.location.href);
    }

    // API for browser-use to interact with the recorder
    window.BrowserUseRecorder = {
        startRecording: function() {
            if (isRecording) return "Already recording";
            
            console.log("[WorkflowRecorder] Recording started");
            isRecording = true;
            startTime = Date.now();
            events = [];
            
            // Record initial page
            handleNavigation();
            
            // Add event listeners
            document.addEventListener('click', handleClick, true);
            document.addEventListener('input', handleInput, true);
            document.addEventListener('change', handleSelectChange, true);
            document.addEventListener('keydown', handleKeydown, true);
            
            // Listen for navigation events
            window.addEventListener('popstate', handleNavigation);
            
            // Track page unload - useful for tab navigation
            window.addEventListener('beforeunload', handleNavigation);
            
            // Return success message
            return "Recording started";
        },
        
        stopRecording: function() {
            if (!isRecording) return "Not recording";
            
            console.log("[WorkflowRecorder] Recording stopped");
            isRecording = false;
            
            // Remove event listeners
            document.removeEventListener('click', handleClick, true);
            document.removeEventListener('input', handleInput, true);
            document.removeEventListener('change', handleSelectChange, true);
            document.removeEventListener('keydown', handleKeydown, true);
            window.removeEventListener('popstate', handleNavigation);
            window.removeEventListener('beforeunload', handleNavigation);
            
            return "Recording stopped";
        },
        
        getEvents: function() {
            return JSON.stringify(events);
        },
        
        clearEvents: function() {
            events = [];
            return "Events cleared";
        },
        
        getStatus: function() {
            return isRecording ? "recording" : "stopped";
        },
        
        // Helper to add a custom event (useful for non-standard interactions)
        addCustomEvent: function(eventType, data) {
            if (!isRecording) return "Not recording";
            
            events.push({
                type: eventType,
                timestamp: Date.now(),
                tabId: 1,
                url: document.location.href,
                ...data
            });
            
            return "Custom event added";
        }
    };
    
    console.log("[WorkflowRecorder] Extension loaded and ready to record");
})();
"""


async def inject_recorder_extension(page):
    """
    Inject the workflow recorder extension into the browser page

    Args:
        page: The browser page to inject the extension into

    Returns:
        str: Status message
    """
    try:
        # First check if the extension is already available (Chrome extension)
        extension_available = await check_for_extension(page)

        if extension_available:
            logger.info("Recorder extension is already available in the browser")
            return "Recorder extension is already loaded"

        # Inject the recorder extension if not available
        await page.evaluate(RECORDER_EXTENSION_CODE)
        logger.info("Workflow recorder extension injected via JavaScript")
        return "Workflow recorder extension injected successfully"
    except Exception as e:
        logger.error(f"Failed to inject workflow recorder extension: {e}")
        return f"Failed to inject extension: {str(e)}"


async def start_recording(page):
    """
    Start recording browser interactions

    Args:
        page: The browser page where recording should start

    Returns:
        str: Status message
    """
    try:
        # First check if we need to inject the extension
        extension_available = await check_for_extension(page)

        if not extension_available:
            inject_result = await inject_recorder_extension(page)
            if (
                "successfully" not in inject_result.lower()
                and "already loaded" not in inject_result.lower()
            ):
                return f"Failed to set up recording: {inject_result}"

        # Call the startRecording function in the injected extension or Chrome extension
        result = await page.evaluate("window.BrowserUseRecorder.startRecording()")
        logger.info("Started workflow recording")
        return result
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        return f"Failed to start recording: {str(e)}"


async def stop_recording(page):
    """
    Stop recording browser interactions

    Args:
        page: The browser page where recording should stop

    Returns:
        str: Status message
    """
    try:
        # Check if the extension is available
        extension_available = await check_for_extension(page)

        if not extension_available:
            return "Recorder not active in this page"

        # Call the stopRecording function in the injected extension
        result = await page.evaluate("window.BrowserUseRecorder.stopRecording()")
        logger.info("Stopped workflow recording")
        return result
    except Exception as e:
        logger.error(f"Failed to stop recording: {e}")
        return f"Failed to stop recording: {str(e)}"


async def get_recorded_events(page):
    """
    Get all recorded events from the browser

    Args:
        page: The browser page where events were recorded

    Returns:
        list: List of recorded events
    """
    try:
        # Check if the extension is available
        extension_available = await check_for_extension(page)

        if not extension_available:
            return []

        # Get the events from the injected extension
        events_json = await page.evaluate("window.BrowserUseRecorder.getEvents()")
        events = json.loads(events_json)
        return events
    except Exception as e:
        logger.error(f"Failed to get recorded events: {e}")
        return []


async def clear_recorded_events(page):
    """
    Clear all recorded events in the browser

    Args:
        page: The browser page where events should be cleared

    Returns:
        str: Status message
    """
    try:
        # Check if the extension is available
        extension_available = await check_for_extension(page)

        if not extension_available:
            return "Recorder not active in this page"

        # Clear the events in the injected extension
        result = await page.evaluate("window.BrowserUseRecorder.clearEvents()")
        return result
    except Exception as e:
        logger.error(f"Failed to clear recorded events: {e}")
        return f"Failed to clear events: {str(e)}"


async def get_recording_status(page):
    """
    Get the current recording status

    Args:
        page: The browser page to check

    Returns:
        str: Recording status ('recording' or 'stopped')
    """
    try:
        # Check if the extension is available
        extension_available = await check_for_extension(page)

        if not extension_available:
            return "not_available"

        # Get the status from the injected extension
        status = await page.evaluate("window.BrowserUseRecorder.getStatus()")
        return status
    except Exception as e:
        logger.error(f"Failed to get recording status: {e}")
        return "unknown"
