from __future__ import annotations
from typing import Optional, Any, Literal, Dict

from pydantic import BaseModel, Field, ConfigDict


class VisualizationResult(BaseModel):
    """
    Represents the final result after a full visualization agent run.
    """

    status: Literal["success", "error"] = Field(
        ..., description="The final outcome of the visualization process."
    )
    visualization: Optional[Any] = Field(
        None, description="The visualization object (e.g., a Plotly figure)."
    )
    vis_params: Optional[Dict[str, Any]] = Field(
        None, description="The parameters used to generate the visualization."
    )
    error_message: Optional[str] = Field(
        None, description="Details of the error if the process failed."
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)
