from __future__ import annotations
from typing import Optional, Literal
import pandas as pd
from pydantic import BaseModel, Field

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
