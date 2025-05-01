from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Selector(BaseModel):
	"""Represents a selector for locating a DOM element."""

	type: Literal['css', 'xpath']
	value: str


class BaseAction(BaseModel):
	"""Base model for any action performed in the browser."""

	action_type: str
	timestamp: float  # Or perhaps datetime? Using float for now based on common replay formats.


class ClickAction(BaseAction):
	action_type: Literal['click'] = 'click'
	selector: Selector
	button: Literal['left', 'right', 'middle'] = 'left'
	click_count: int = 1
	# coordinates? relative position?


class TypeAction(BaseAction):
	action_type: Literal['type'] = 'type'
	selector: Selector
	text: str
	delay_ms: Optional[float] = None  # Delay between keystrokes


class NavigateAction(BaseAction):
	action_type: Literal['navigate'] = 'navigate'
	url: str


class ScrollAction(BaseAction):
	action_type: Literal['scroll'] = 'scroll'
	delta_x: int
	delta_y: int
	# Optional selector if scrolling a specific element?


# We need a way to unionize these actions. Pydantic v2 handles discriminated unions well.
# For older versions or simplicity, a container with optional fields might be used,
# but discriminated unions based on 'action_type' are cleaner.
# Assuming Pydantic v2 style usage here. Consider compatibility if needed.
Action = ClickAction | TypeAction | NavigateAction | ScrollAction


class WorkflowStep(BaseModel):
	"""Represents a single step or event in the workflow."""

	id: str  # Unique identifier for the step
	action: Action
	# Optional metadata like screenshot path, DOM snapshot, etc.
	metadata: Optional[Dict[str, Any]] = None


class BrowserWorkflow(BaseModel):
	"""Represents a complete browser interaction workflow."""

	workflow_id: str
	description: Optional[str] = None
	start_url: Optional[str] = None
	steps: List[WorkflowStep] = Field(default_factory=list)
	# Other global metadata? viewport size? user agent?
	metadata: Optional[Dict[str, Any]] = None
