from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class LLM_SQLResponse(BaseModel):
    """
    The expected structured response from the LLM after a generation call.
    This is an internal model used for parsing the LLM's output.
    """

    status: Literal["success", "clarification", "error"] = Field(
        ...,
        description="Indicator of whether the query was generated, needs clarification, or an error occurred.",
    )
    query: Optional[str] = Field(
        None, description="The complete, syntactically correct SQL query."
    )
    reason: Optional[str] = Field(
        None,
        description="A brief explanation of how the query was constructed or why an error occurred.",
    )
    clarification_question: Optional[str] = Field(
        None,
        description="A question to ask the user if the original request is ambiguous and the state is 'clarification'.",
    )


class ReflectionReview(BaseModel):
    """
    The structured response from the reflection/reviewer agent.
    """

    decision: Literal["proceed", "revise"] = Field(
        ..., description="Decision to either proceed with the SQL or revise it."
    )
    suggestions: Optional[str] = Field(
        None,
        description="Constructive feedback and suggestions for improving the SQL if the decision is 'revise'.",
    )


class ColumnToInspect(BaseModel):
    """A Pydantic model for a single column identified for enrichment."""

    table: str = Field(..., description="The name of the table.")
    column: str = Field(
        ..., description="The name of the column to inspect for unique values."
    )


class InspectionPlan(BaseModel):
    """The structured plan produced by the schema analyzer LLM call."""

    columns_to_inspect: List[ColumnToInspect]
