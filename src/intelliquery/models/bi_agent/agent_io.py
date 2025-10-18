from dataclasses import field
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


class BIAction(BaseModel):
    """The action to take."""

    action: Literal["sql_agent", "visualization_agent", "FinalAnswer"]

    args: Dict[str, Any] = Field(description="The arguments for the action.")
    # sql_question: Optional[str] = Field(
    #     description="The complete context and history aware question to ask the SQL agent. Only if the action is 'sql_agent'."
    # )
    # instruction: Optional[str] = Field(
    #     description="The instruction to follow for the visualization agent. Only if the action is 'visualization_agent'."
    # )
    # answer: Optional[str] = Field(
    #     description="A summary for the answer generation to the user to the user's question. That shouldn't be very detailed. Only if the action is 'FinalAnswer'."
    # )


class Reflection(BaseModel):
    """The reflection on the action."""

    reasoning: str
    action: BIAction
