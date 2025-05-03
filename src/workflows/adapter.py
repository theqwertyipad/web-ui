from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

###############################################################################
# Event model definitions
###############################################################################


@dataclass
class RRWebEvent(ABC):
    """Base RRWeb-like event.

    Only the fields we actually need for conversion are declared – everything
    else is passed through **kwargs to keep the constructor flexible.
    """

    type: str
    timestamp: int | None = None
    tabId: int | None = None
    url: str | None = None

    @abstractmethod
    def to_workflow_step(self) -> Optional[Dict[str, Any]]:
        """Convert the event into a deterministic workflow *step*.

        Returns ``None`` if the event does not translate to a supported action.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Individual event variants
# ---------------------------------------------------------------------------


@dataclass
class RRWebNavigationEvent(RRWebEvent):
    """Navigating the browser to a new URL."""

    type: str = "navigation"

    def to_workflow_step(self) -> Optional[Dict[str, Any]]:  # noqa: D401
        if not self.url:
            return None
        return {
            "type": "deterministic",
            "description": f"Open URL {self.url}",
            "action": "navigate",
            "params": {"url": self.url},
        }


@dataclass
class RRWebClickEvent(RRWebEvent):
    frameUrl: str | None = None
    xpath: str | None = None
    cssSelector: str | None = None
    elementTag: str | None = None
    elementText: str | None = None
    screenshot: str | None = None
    type: str = "click"

    def to_workflow_step(self) -> Optional[Dict[str, Any]]:
        selector: str | None = self.cssSelector or self.xpath
        if not selector:
            return None
        return {
            "type": "deterministic",
            "description": f"Click element {selector}",
            "action": "click_element",
            "params": {
                "selector": self.cssSelector,
                "xpath": self.xpath,
                "elementTag": self.elementTag,
                "elementText": self.elementText,
                "frameUrl": self.frameUrl,
            },
        }


@dataclass
class RRWebInputEvent(RRWebEvent):
    frameUrl: str | None = None
    xpath: str | None = None
    cssSelector: str | None = None
    elementTag: str | None = None
    elementText: str | None = None
    screenshot: str | None = None
    value: str | None = None
    type: str = "input"

    def to_workflow_step(self) -> Optional[Dict[str, Any]]:
        selector: str | None = self.cssSelector or self.xpath
        if not selector or self.value is None:
            return None
        return {
            "type": "deterministic",
            "description": f"Input text into {selector}",
            "action": "input",
            "params": {
                "selector": self.cssSelector,
                "xpath": self.xpath,
                "elementTag": self.elementTag,
                "elementText": self.elementText,
                "frameUrl": self.frameUrl,
                "text": self.value,
            },
        }


@dataclass
class RRWebSelectEvent(RRWebEvent):
    frameUrl: str | None = None
    xpath: str | None = None
    cssSelector: str | None = None
    elementTag: str | None = None
    selectedValue: str | None = None
    selectedText: str | None = None
    screenshot: str | None = None
    type: str = "select_change"

    def to_workflow_step(self) -> Optional[Dict[str, Any]]:
        selector: str | None = self.cssSelector or self.xpath
        text_to_select = self.selectedText or self.selectedValue
        if not selector or text_to_select is None:
            return None

        return {
            "type": "deterministic",
            "description": f"Select option '{text_to_select}' in dropdown {selector}",
            "action": "select_change",
            "params": {"selector": selector, "text": text_to_select},
        }


@dataclass
class RRWebTabUpdatedEvent(RRWebEvent):
    url: str | None = None
    changeInfo: Dict[str, Any] | None = None
    type: str = "tabUpdated"

    def to_workflow_step(self) -> Optional[Dict[str, Any]]:  # noqa: D401
        # ``tabUpdated`` contains no deterministic action, return None
        return None


# ---------------------------------------------------------------------------
# Key press event
# ---------------------------------------------------------------------------


@dataclass
class RRWebKeyPressEvent(RRWebEvent):
    frameUrl: str | None = None
    xpath: str | None = None
    cssSelector: str | None = None
    elementTag: str | None = None
    elementText: str | None = None
    screenshot: str | None = None
    key: str | None = None
    type: str = "key_press"

    def to_workflow_step(self) -> Optional[Dict[str, Any]]:
        selector: str | None = self.cssSelector or self.xpath
        if not selector or self.key is None:
            return None
        return {
            "type": "deterministic",
            "description": f"Press key '{self.key}' on element {selector}",
            "action": "key_press",
            "params": {
                "selector": selector,
                "key": self.key,
            },
        }


# ---------------------------------------------------------------------------
# Scroll update event
# ---------------------------------------------------------------------------


@dataclass
class RRWebScrollEvent(RRWebEvent):
    targetId: int | None = None
    scrollX: int | None = 0
    scrollY: int | None = 0
    type: str = "scroll_update"

    def to_workflow_step(self) -> Optional[Dict[str, Any]]:
        if self.scrollX is None or self.scrollY is None:
            return None
        return {
            "type": "deterministic",
            "description": f"Scroll page by (x={self.scrollX}, y={self.scrollY})",
            "action": "scroll",
            "params": {"scrollX": self.scrollX, "scrollY": self.scrollY},
        }


###############################################################################
# Parsing helpers
###############################################################################


def _parse_rrweb_event(evt: Dict[str, Any]) -> RRWebEvent:
    """Instantiate an RRWebEvent subclass based on *evt['type']*."""

    etype = evt.get("type")
    if etype in {"navigation", "navigate"}:
        return RRWebNavigationEvent(**evt)
    if etype == "click":
        return RRWebClickEvent(**evt)
    if etype == "input":
        return RRWebInputEvent(**evt)
    if etype == "key_press":
        return RRWebKeyPressEvent(**evt)
    if etype == "scroll_update":
        return RRWebScrollEvent(**evt)
    if etype == "select_change":
        return RRWebSelectEvent(**evt)
    if etype in {"tabUpdated", "tab_updated"}:
        return RRWebTabUpdatedEvent(**evt)
    print(f"Unknown event type: {etype}")
    return RRWebEvent(**evt)  # type: ignore[arg-type]


def parse_json_session(data: Any) -> List[RRWebEvent]:
    """Parse *data* coming from a RECORDER.

    The recorder may store the session as either a *list* of events or inside a
    top-level ``{"events": [...]}`` mapping.
    """

    if isinstance(data, dict) and "events" in data:
        events_raw = data["events"]
    else:
        events_raw = data  # assume already a list

    events: List[RRWebEvent] = []
    for evt in events_raw:
        try:
            events.append(_parse_rrweb_event(evt))
        except Exception as exc:
            print(f"Error parsing event: {evt['type']}")
            # Log / skip invalid events quietly – they cannot be mapped anyway
            print(f"[adapter] Skipping event due to parse error: {exc}")
    return events


###############################################################################
# Workflow construction helpers
###############################################################################


def events_to_workflow_steps(events: List[RRWebEvent]) -> List[Dict[str, Any]]:
    """Convert a list of RRWebEvent objects to deterministic workflow *steps*."""

    steps: List[Dict[str, Any]] = []
    for i, ev in enumerate(events):
        step = ev.to_workflow_step()
        if step:
            # Debugging: Check types within the step dictionary
            for key, value in step.items():
                # print(f"Step {i}, Key '{key}', Value Type: {type(value)}") # Temporarily disable noisy print
                if not isinstance(
                    value, (str, int, float, bool, list, dict, type(None))
                ):
                    print(
                        f"!!! Non-standard type found: Step {i}, Key '{key}', Type: {type(value)}, Value: {value!r}"
                    )
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        # print(f"  Step {i}, Param Key '{sub_key}', Param Value Type: {type(sub_value)}") # Temporarily disable noisy print
                        if not isinstance(
                            sub_value, (str, int, float, bool, list, dict, type(None))
                        ):
                            print(
                                f"!!! Non-standard type found in params: Step {i}, Key '{sub_key}', Type: {type(sub_value)}, Value: {sub_value!r}"
                            )
            # End Debugging
            steps.append(step)
    return steps


def build_deterministic_workflow_yaml(
    events: List[RRWebEvent],
    *,
    name: str = "Deterministic Workflow from Recording",
    description: str = "Workflow generated directly from session recording – no input parameters.",
) -> str:
    """Return YAML string representing a fully deterministic workflow."""

    workflow_dict = OrderedDict(
        [
            ("name", name),
            ("description", description),
            (
                "inputs",
                {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            ("steps", events_to_workflow_steps(events)),
        ]
    )

    # Convert OrderedDict to regular dict before dumping
    regular_dict = dict(workflow_dict)

    return yaml.safe_dump(regular_dict, sort_keys=False)


###############################################################################
# Convenience loader from JSON file path
###############################################################################


def json_file_to_workflow_yaml(path: str | os.PathLike[str] | str, **kwargs) -> str:
    """Read *path*, parse events and return deterministic workflow YAML string."""

    import json
    import sys
    from pathlib import Path

    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Error: File not found at {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file {path}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file {path}: {e}", file=sys.stderr)
        sys.exit(1)

    events = parse_json_session(data)
    return build_deterministic_workflow_yaml(events, **kwargs)


if __name__ == "__main__":
    # Generate the workflow YAML from the JSON file
    workflow_yaml = json_file_to_workflow_yaml(
        "/home/pietro/Downloads/scroll.json"
    )

    # Define the output file path
    output_path = "output_workflow.yaml"

    # Write the YAML string to the output file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(workflow_yaml)

    print(f"Workflow saved to {output_path}")
