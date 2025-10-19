from __future__ import annotations
from typing import Optional, Any, Literal, Dict

import pandas as pd
from pydantic import BaseModel, Field, ConfigDict


class BIResult(BaseModel):
    """
    Represents the final result after a full BI agent run.
    It can contain a textual answer, a DataFrame, a visualization, or a mix.
    """

    status: Literal["success", "clarification_needed", "error"] = Field(
        ..., description="The final outcome of the entire process."
    )
    final_answer: str = Field(
        ..., description="The final summary answer or clarification question from the agent."
    )
    dataframe: Optional[pd.DataFrame] = Field(
        None, description="The resulting pandas DataFrame if data was retrieved."
    )
    visualization: Optional[Any] = Field(
        None, description="The visualization object, if one was created."
    )
    sql_query: Optional[str] = Field(
        None, description="The SQL query generated during the process."
    )
    reasoning: Optional[str] = Field(
        None, description="The consolidated reasoning from the agent's steps."
    )
    visualization_params: Optional[Dict[str, Any]] = Field(
        None, description="The parameters needed to regenerate the visualization."
    )
    error_message: Optional[str] = Field(
        None, description="Details of the error if any step in the process failed."
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)
