from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional, Literal

import pandas as pd
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# Public Interface Models


class EnrichedDatabaseContext(BaseModel):
    """
    A structured, pre-built context object containing all information
    needed for an agent to generate a query.
    """

    raw_schema: str = Field(..., description="The original, unmodified DDL schema.")
    augmented_schema: str = Field(
        ..., description="The schema augmented with distinct values and annotations."
    )
    schema_key: str = Field(
        ..., description="The hash of the raw schema, used for caching."
    )
    business_context: Optional[str] = Field(
        None, description="User-provided business rules and definitions."
    )


class SQLPlan(BaseModel):
    """
    Represents the output of the planning phase (SQL generation).
    This model does not contain a DataFrame, as no query has been executed.
    """

    status: Literal["success", "clarification_needed", "error"] = Field(
        ..., description="The outcome of the SQL generation attempt."
    )
    sql_query: Optional[str] = Field(
        None, description="The generated SQL query, if generation was successful."
    )
    reasoning: Optional[str] = Field(
        None, description="The LLM's reasoning for generating the query."
    )
    is_validated: bool = Field(
        False, description="True if the SQL passed a database dry-run validation."
    )
    clarification_question: Optional[str] = Field(
        None, description="A question to the user if the request was ambiguous."
    )
    error_message: Optional[str] = Field(
        None, description="Details of the error if the generation failed."
    )


class SQLResult(BaseModel):
    """
    Represents the final result after a full run (generation and execution).
    """

    status: Literal["success", "clarification_needed", "error"] = Field(
        ..., description="The final outcome of the entire process."
    )
    dataframe: Optional[pd.DataFrame] = Field(
        None, description="The resulting pandas DataFrame if execution was successful."
    )
    sql_query: Optional[str] = Field(
        None, description="The final, successfully executed SQL query."
    )
    clarification_question: Optional[str] = Field(
        None, description="A question to the user if the initial request was ambiguous."
    )
    error_message: Optional[str] = Field(
        None, description="Details of the error if any step in the process failed."
    )

    class Config:
        arbitrary_types_allowed = True


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
        None, description="A brief explanation of how the query was constructed."
    )
    clarification_question: Optional[str] = Field(
        None,
        description="A question to ask the user if the original request is ambiguous. This question must be on target and not ambiguous.",
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


class SQLAgentState(TypedDict):
    """
    Represents the internal, temporary state of the SQL Agent's workflow.
    This is now simpler, as the complex context is pre-built.
    """

    # Inputs
    natural_language_question: str
    chat_history: List[Tuple[str, str]]
    db_context: Dict[str, Any]  # This will now hold the pre-built augmented context

    # Internal loop state
    history: List[str]
    max_attempts: int
    current_attempt: int

    # The structured result from the generation LLM
    generation_result: Optional[LLM_SQLResponse]

    # Outputs
    final_dataframe: Optional[pd.DataFrame]
    generated_sql: str
    error: Optional[str]
