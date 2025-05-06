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

logger = logging.getLogger(__name__)


EXAMPLE_WORKFLOW_PATH = Path(__file__).parent / "example.workflow.json"


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


def parse_session(
    session_path: str,
    user_goal: str | None = None,
    use_screenshots: bool = False,
    llm: BaseChatModel | None = None,
) -> Workflow:
    """Generate a Workflow JSON from a *simplified session* JSON file using an LLM.

    The resulting JSON is saved next to *session_path* with suffix `.workflow.json` and a
    :class:`Workflow` instance is returned for immediate use.
    """

    assert llm is not None, (
        "A ``BaseChatModel`` instance must be supplied to ``parse_session``"
    )

    session_file = Path(session_path)
    with session_file.open("r", encoding="utf-8") as fp:
        raw_workflow: dict = json.load(fp)

    session_events = raw_workflow["steps"]

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

    prompt = PromptTemplate.from_template(workflow_builder_template)

    # Instead of inlining the entire event log in the main prompt we will stream
    # each event (and its nearby screenshot) as *separate* messages.  This keeps
    # related visual context tightly coupled to the structured data and avoids
    # the pathological "events first, screenshots last" ordering.
    prompt_str = prompt.format(
        actions=_available_actions_markdown(),
        events="Events will follow one-by-one in subsequent messages.",
        example_workflow=EXAMPLE_WORKFLOW_PATH.read_text(),
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

    # Invoke the LLM to get the workflow as text
    llm_response = llm.invoke([HumanMessage(content=cast(Any, vision_messages))])
    llm_content: str = str(llm_response.content).strip()

    # TODO: Use structured output to make this better.
    # Extract the JSON content from the markdown code block
    json_content = llm_content  # Default to full content if extraction fails
    if "```json" in llm_content:
        # Find the start and end of the json block
        start_index = llm_content.find("```json") + len("```json\n")
        end_index = llm_content.rfind("```")
        if start_index != -1 and end_index != -1 and start_index < end_index:
            json_content = llm_content[start_index:end_index].strip()
    elif llm_content.startswith("```"):
        # Fallback for generic code blocks if ```json is missing
        parts = llm_content.split("\n", 1)
        if len(parts) > 1:
            content_after_fence = parts[1]
            if content_after_fence.endswith("```"):
                json_content = content_after_fence[:-3].strip()

    print("Extracted Workflow JSON:")
    print(json_content)

    # Persist JSON next to original JSON file
    json_path = session_file.with_suffix(".workflow.json")
    json_path.write_text(json_content, encoding="utf-8")

    # Return a ready-to-use Workflow instance
    return Workflow(json_path=str(json_path))
