from typing import Optional

from pydantic import BaseModel

# Shared config allowing extra fields so recorder payloads pass through


class _BaseExtra(BaseModel):
    class Config:
        extra = "ignore"


# Common optional fields present in recorder events


class RecorderBase(_BaseExtra):
    xpath: Optional[str] = None
    elementTag: Optional[str] = None
    elementText: Optional[str] = None
    frameUrl: Optional[str] = None
    screenshot: Optional[str] = None


class ClickElementDeterministicAction(RecorderBase):
    """Parameters for clicking an element identified by CSS selector."""

    cssSelector: str


class InputTextDeterministicAction(RecorderBase):
    """Parameters for entering text into an input field identified by CSS selector."""

    cssSelector: str
    value: str


class SelectDropdownOptionDeterministicAction(RecorderBase):
    """Parameters for selecting a dropdown option identified by *selector* and *text*."""

    cssSelector: str
    selectedValue: str
    selectedText: str


class KeyPressDeterministicAction(RecorderBase):
    """Parameters for pressing a key on an element identified by CSS selector."""

    cssSelector: str
    key: str


class NavigationAction(_BaseExtra):
    """Parameters for navigating to a URL."""

    url: str


class ScrollDeterministicAction(_BaseExtra):
    """Parameters for scrolling the page by x/y offsets (pixels)."""

    scrollX: int = 0
    scrollY: int = 0
    targetId: Optional[int] = None
