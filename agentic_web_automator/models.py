from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, model_validator


class ActionType(str, Enum):
    GOTO = "GOTO"
    CLICK = "CLICK"
    TYPE = "TYPE"
    SCROLL = "SCROLL"
    WAIT = "WAIT"
    EXTRACT = "EXTRACT"
    DONE = "DONE"


class Action(BaseModel):
    thought: str
    action_type: ActionType
    url: Optional[str] = None
    element_id: Optional[str] = None
    text: Optional[str] = None
    scroll_x: int = 0
    scroll_y: int = 500
    wait_ms: int = 1000
    result: Optional[str] = None

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "Action":
        if self.action_type == ActionType.GOTO and not self.url:
            raise ValueError("GOTO requires 'url'")
        if self.action_type in (ActionType.CLICK, ActionType.TYPE) and not self.element_id:
            raise ValueError(f"{self.action_type.value} requires 'element_id'")
        if self.action_type == ActionType.TYPE and self.text is None:
            raise ValueError("TYPE requires 'text'")
        return self


class AgentStep(BaseModel):
    step_number: int
    thought: str
    action: Action
    observation: str = ""
