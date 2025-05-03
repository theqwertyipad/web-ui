from pydantic import BaseModel


class ClickElementDeterministicAction(BaseModel):
    """Parameters for clicking an element identified by CSS selector."""

    selector: str


class InputTextDeterministicAction(BaseModel):
    """Parameters for entering text into an input field identified by CSS selector."""

    selector: str
    text: str


class SelectDropdownOptionDeterministicAction(BaseModel):
    """Parameters for selecting a dropdown option identified by *selector* and *text*."""

    selector: str
    text: str


class KeyPressDeterministicAction(BaseModel):
    """Parameters for pressing a key on an element identified by CSS selector."""

    selector: str
    key: str


class NavigateAction(BaseModel):
    """Parameters for navigating to a URL."""

    url: str


class ScrollDeterministicAction(BaseModel):
    """Parameters for scrolling the page by x/y offsets (pixels)."""

    scrollX: int = 0
    scrollY: int = 0
