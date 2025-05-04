import base64
import json
import logging
from pathlib import Path
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate

from .controller.service import WorkflowController
from .prompts import workflow_builder_template
from .workflow import Workflow
from . import WORKFLOW_VERSION

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Prompt helpers
# -----------------------------------------------------------------------------

def _available_actions_markdown() -> str:
    """Return a bullet list with available deterministic actions and their descriptions."""
    controller = WorkflowController()
    lines: list[str] = []
    for action in controller.registry.registry.actions.values():
        lines.append(f"- **{action.name}**: {action.description}")
        lines.append(f"  - params: {action.param_model.model_json_schema()}")
    return "\n".join(lines)


def _prune_event(event: dict) -> dict:
    """Return a shallow copy of *event* with any screenshot payload removed.

    Some recorders store the base-64 screenshot on the top-level ``screenshot`` key,
    or inside a nested ``data`` mapping.  Because the raw payload can be very large
    (and thus very expensive to send to the LLM in text form) we strip it out
    before serialising the event JSON for the prompt.  We keep the *original* event
    object untouched so that the binary data can still be attached to the prompt
    as an *image_url* when screenshots are enabled.
    """
    event = event.copy()
    event.pop("screenshot", None)
    if isinstance(event.get("data"), dict):
        event["data"] = event["data"].copy()
        event["data"].pop("screenshot", None)
    return event


def _event_to_messages(event: dict, include_screenshot: bool) -> list[dict[str, Any]]:
    """Convert a *single* session *event* into a list of OpenAI vision messages.

    The first message is always a ``text`` chunk containing the pruned JSON of the
    event.  If *include_screenshot* is ``True`` **and** the event contains a valid
    Base-64 screenshot, two additional messages are appended: a short textual
    caption followed by the binary image payload encoded as a ``data:` URI.  Doing
    it this way keeps the screenshot *adjacent* to its corresponding event, which
    greatly helps the model associate the visual context with the structured log
    entry.
    """
    messages: list[dict[str, Any]] = []

    # 1) textual representation of the event without the bulky screenshot field
    pruned = _prune_event(event)
    messages.append({"type": "text", "text": json.dumps(pruned, indent=2)})

    # 2-3) optional screenshot if requested and available
    if not include_screenshot or event.get("type") == "input":
        return messages

    # Accept both top-level and nested variants
    screenshot: str | None = event.get("screenshot") or event.get("data", {}).get(
        "screenshot"
    )
    if screenshot and screenshot.startswith("data:"):
        # The recorder may have stored a full data-URI.  Strip the scheme/prefix so
        # that we are left with *just* the raw Base-64 payload that
        # ``base64.b64decode`` expects.
        screenshot = screenshot.split(",", 1)[-1]

    # Validate base-64 payload – discard if invalid to avoid API errors
    try:
        base64.b64decode(cast(str, screenshot), validate=True)
    except Exception:
        logger.warning(
            f"Invalid screenshot for event {event.get('type', 'unknown')} @ {event.get('timestamp', '')}"
        )
        return messages

    meta = f"Screenshot for event {event.get('type', 'unknown')} @ {event.get('timestamp', '')}"
    messages.append({"type": "text", "text": meta})
    messages.append(
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{screenshot}"},
        }
    )

    return messages


def _prepare_event_messages(
    events: list[dict], include_screenshots: bool, max_images: int = 100
) -> list[dict[str, Any]]:
    """Return a flattened list of vision messages for *events*.

    The function walks over the events in chronological order, emitting the text
    record (and optional screenshot) for each.  To stay within the token and
    cost budget we cap the *total* number of screenshots that will be attached
    via the *max_images* parameter (default: 8).
    """
    messages: list[dict[str, Any]] = []
    images_used = 0

    for evt in events:
        # Decide whether we can still attach screenshots for this event
        attach_image = include_screenshots and images_used < max_images

        chunk = _event_to_messages(evt, attach_image)
        messages.extend(chunk)

        # Update image counter – each _event_to_messages attaches at most *one*
        # image so a simple increment is sufficient.
        if attach_image and len(chunk) > 1:
            images_used += 1

    return messages


def _debounce_input_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse successive *input* events on the same element.

    Many recorders emit a new *input* event on every keystroke so typing
    "hello" becomes five events with values "h", "he", "hel", … We keep only
    the *last* event of each consecutive run on the same element.
    """
    debounced: list[dict[str, Any]] = []
    pending_input: dict[str, Any] | None = None

    def _flush_pending():
        nonlocal pending_input
        if pending_input is not None:
            debounced.append(pending_input)
            pending_input = None

    for evt in events:
        if evt.get("type") == "input":
            selector_key = evt.get("cssSelector") or evt.get("xpath") or ""
            if (
                pending_input
                and (pending_input.get("cssSelector") or pending_input.get("xpath"))
                == selector_key
            ):
                # Same element – keep the newer (more complete) value
                pending_input = evt
            else:
                # New element – flush previous and start new pending
                _flush_pending()
                pending_input = evt
        else:
            _flush_pending()
            debounced.append(evt)

    _flush_pending()
    return debounced

def prune_screenshots(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prune screenshots from the events."""
    for evt in events:
        if evt.get("screenshot"):
            evt["screenshot"] = ""
    return events


def find_first_user_interaction_url(events: list[dict[str, Any]]) -> str | None:
    """Find the first user interaction in the events."""
    return next(
        (
            evt.get("frameUrl")
            for evt in events
            if evt.get("type") in ["input", "click", "scroll"]
        ),
        None,
    )



# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

# NOTE: Screenshots can significantly increase token usage (and cost). They are
# therefore disabled by default and can be enabled explicitly via the
# *use_screenshots* parameter or the CLI flag ``--use-screenshots``.

def save_clean_recording(recording_path:str, out_path:str) -> None:
    """This function clean up the recording by making it nicer to work with by the workflow."""
    with open(recording_path, "r") as f:
        recording = json.load(f)

    # Remove screenshots
    recording = prune_screenshots(recording)

    # Debounce input events
    recording = _debounce_input_events(recording)

    # Find the first user interaction url
    first_user_interaction_url = find_first_user_interaction_url(recording)
    print(f"first_user_interaction_url: {first_user_interaction_url}")  
    # We remove all the initial navigation until the first user interaction
    for idx, evt in enumerate(recording):
        if evt.get("frameUrl") == first_user_interaction_url:
            break
        print(f"popping {idx, evt} {evt.get('frameUrl')}")
        recording.pop(idx)
    print(f"recording: {recording}")
        
    # We append a navigaton event to the url at the beginning of the recording
    recording.insert(0, {
        "type": "navigation",
        "url": first_user_interaction_url,
        "timestamp": recording[0].get("timestamp"),
        "tabId": recording[0].get("tabId"),
    })

    # Wrap events in a steps array
    recording_dict = {
        "steps": recording,
        "name": recording_path.split(".")[0],
        "description": "",
        "version": WORKFLOW_VERSION,
        "input_schema": {
            "type": "object", 
            "properties": {}
        }
    }
    recording = recording_dict
    # Return the cleaned recording
    with open(out_path, "w") as f:
        json.dump(recording, f)

def parse_session(
    session_path: str,
    user_goal: str | None = None,
    use_screenshots: bool = True,
    llm: BaseChatModel | None = None,
) -> Workflow:
    """Generate a Workflow YAML from a *simplified session* JSON file using an LLM.

    The resulting YAML is saved next to *session_path* with suffix ``.yaml`` and a
    :class:`Workflow` instance is returned for immediate use.
    """

    assert llm is not None, (
        "A ``BaseChatModel`` instance must be supplied to ``parse_session``"
    )

    session_file = Path(session_path)
    with session_file.open("r", encoding="utf-8") as fp:
        session_events: list[dict] = json.load(fp)

    # Ask user for goal description if not supplied
    if user_goal is None:
        try:
            user_goal = input(
                "Please describe the high-level task you want the workflow to accomplish (press Enter to skip): "
            ).strip()
        except EOFError:
            # In non-interactive environments just fall back to empty string
            user_goal = ""
    user_goal = user_goal or ""

    # Read example YAML (truncate if very large)

    prompt = PromptTemplate.from_template(workflow_builder_template)

    # Instead of inlining the entire event log in the main prompt we will stream
    # each event (and its nearby screenshot) as *separate* messages.  This keeps
    # related visual context tightly coupled to the structured data and avoids
    # the pathological "events first, screenshots last" ordering.
    prompt_str = prompt.format(
        actions=_available_actions_markdown(),
        events="Events will follow one-by-one in subsequent messages.",
        goal=user_goal,
    )

    vision_messages: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": prompt_str,
        }
    ]

    # Always append the chronological event stream – with or without images – so
    # that the model can rely on a consistent structure.
    vision_messages.extend(
        _prepare_event_messages(session_events, include_screenshots=use_screenshots)
    )

    yaml_response = llm.invoke([HumanMessage(content=cast(Any, vision_messages))])

    yaml_content: str = str(yaml_response.content).strip()

    # Validate that action types match the model
    prompt_str = (
        prompt_str
        + "\n\nIMPORTANT: Please ensure that all parameter types in the generated YAML strictly conform to the input models defined for each action. For example, if an action expects a 'url' parameter of type string, the YAML must provide a string value, not a number or boolean. Check each parameter against its corresponding model definition."
    )

    # Ask model to validate types
    validation_messages: list[dict[str, Any]] = [
        {"type": "text", "text": prompt_str + "\n\nGenerated YAML:\n" + yaml_content}
    ]
    validation_response = llm.invoke(
        [HumanMessage(content=cast(Any, validation_messages))]
    )
    yaml_content = str(validation_response.content).strip()

    # Persist YAML next to original JSON file
    yaml_path = session_file.with_suffix(".workflow.yaml")
    yaml_path.write_text(yaml_content, encoding="utf-8")

    # Return a ready-to-use Workflow instance
    return Workflow(json_path=str(yaml_path))


if __name__ == "__main__":
    from langchain_openai import ChatOpenAI

    workflow = parse_session(
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        session_path="linkedin.json",
        user_goal="I want to send messages automatically on linkedin",
        use_screenshots=True,
    )
    print(workflow.json_path)
