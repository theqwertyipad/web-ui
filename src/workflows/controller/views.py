from pydantic import BaseModel


class ClickElementByCssSelectorAction(BaseModel):
    """Parameters for clicking an element identified by CSS selector."""
    selector: str


class InputTextActionCssSelector(BaseModel):
    """Parameters for entering text into an input field identified by CSS selector."""
    selector: str
    text: str


class SelectDropdownOptionBySelectorAndText(BaseModel):
    """Parameters for selecting a dropdown option identified by *selector* and *text*."""
    selector: str
    text: str
