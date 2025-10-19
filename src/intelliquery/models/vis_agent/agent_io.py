from pydantic import BaseModel, Field


class VisualizationToolset(BaseModel):
    """The structured response from the visualization agent's think step."""

    reasoning: str = Field(
        ..., description="The detailed reasoning for choosing a specific visualization."
    )
    visualization_toolset: dict = Field(
        ...,
        description="The selected visualization tool and its arguments, conforming to the framework.",
    )
