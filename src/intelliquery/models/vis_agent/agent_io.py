import json
from typing import Any
from pydantic import BaseModel, Field, field_validator


class VisualizationToolset(BaseModel):
    """The structured response from the visualization agent's think step."""

    reasoning: str = Field(
        ..., description="The detailed reasoning for choosing a specific visualization."
    )
    visualization_toolset: dict = Field(
        ...,
        description="The selected visualization tool and its arguments, conforming to the framework.",
    )

    @field_validator('visualization_toolset', mode='before')
    def parse_json_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError('visualization_toolset contains a malformed JSON string')
        return v
