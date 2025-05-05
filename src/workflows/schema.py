from typing import List, Literal, Optional, Union

from browser_use.controller.views import (
    ClickElementAction,
    CloseTabAction,
    DoneAction,
    DragDropAction,
    GoToUrlAction,
    InputTextAction,
    NoParamsAction,
    OpenTabAction,
    Position,
    ScrollAction,
    SearchGoogleAction,
    SendKeysAction,
    SwitchTabAction,
)
from pydantic import BaseModel, ConfigDict, Field

from .controller.views import (
    ClickElementDeterministicAction,
    InputTextDeterministicAction,
    KeyPressDeterministicAction,
    NavigationAction,
    ScrollDeterministicAction,
    SelectDropdownOptionDeterministicAction,
)


class JSONSchemaProperty(BaseModel):
    type: Literal["string", "number", "boolean"] = Field(
        ..., description="The type of the property."
    )
    description: Optional[str] = Field(
        default=None, description="Optional description for the property."
    )

    model_config = ConfigDict(extra="forbid") 


class WorkflowInputSchema(BaseModel):
    type: Literal["object"] = Field(
        "object", description="Defines the type of the input schema, must be 'object'."
    )

    properties: dict[str, JSONSchemaProperty] = Field(
        ...,
        description="Dictionary mapping property names to their JSONSchemaProperty definitions.",
        json_schema_extra={"additionalProperties": False},
    )
    additionalProperties: bool = Field(
        False,
        description="Indicates if additional properties not defined in 'properties' are allowed. Must be False.",
    )
    required: list[str] = Field(
        default=[], description="List of property names that are mandatory."
    )


class WorkflowSchema(BaseModel):
    name: str = Field(..., description="Unique name identifying the workflow.")
    description: str = Field(
        ..., description="Detailed description of what the workflow does."
    )
    version: str = Field(
        ...,
        description="Version string for the workflow definition (e.g., semantic versioning).",
    )
    input_schema: WorkflowInputSchema = Field(
        ..., description="The schema defining the inputs required by the workflow."
    )
    steps: List[
        Union[
            ClickElementDeterministicAction,
            InputTextDeterministicAction,
            SelectDropdownOptionDeterministicAction,
            KeyPressDeterministicAction,
            NavigationAction,
            ScrollDeterministicAction,
            DoneAction,
            ClickElementAction,
            CloseTabAction,
            DoneAction,
            DragDropAction,
            GoToUrlAction,
            InputTextAction,
            NoParamsAction,
            OpenTabAction,
            Position,
            ScrollAction,
            SearchGoogleAction,
            SendKeysAction,
            SwitchTabAction,
        ]
    ] = Field(..., description="List of workflow steps")
