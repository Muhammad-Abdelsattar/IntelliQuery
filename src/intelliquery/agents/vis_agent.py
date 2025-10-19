from __future__ import annotations
import logging
import yaml
from typing import Dict, Any
import importlib.resources

from pathlib import Path

from nexus_llm import LLMInterface

from ..models.sql_agent.public import SQLResult
from ..models.vis_agent.public import VisualizationResult
from ..models.vis_agent.state import VisAgentState
from ..core.data_analyzer import generate_dataframe_metadata
from ..workflows.vis_agent.react import ReactWorkflow

logger = logging.getLogger(__name__)


class VisualizationAgent:
    """
    A high-level orchestrator for the visualization agent.
    It initializes and runs the ReAct workflow to generate a visualization
    from a given SQL result.
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
    ):
        self.llm_interface = llm_interface
        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        vis_framework_path = (
            Path(prompts_base_path) / "vis_agent" / "react_agent.prompt"
        )
        self.vis_framework = vis_framework_path.read_text()
        self.app = ReactWorkflow(llm_interface).compile()

    def _prepare_initial_state(
        self,
        user_question: str,
        sql_result: SQLResult,
    ) -> VisAgentState:
        """Encapsulates the creation of the initial state for the graph."""
        metadata = generate_dataframe_metadata(sql_result.dataframe)
        return {
            "user_question": user_question,
            "sql_query": sql_result.sql_query,
            "dataframe": sql_result.dataframe,
            "metadata": metadata,
            "visualization_agent_framework": self.vis_framework,
            "agent_scratchpad": [],
            "current_step": 1,
            "final_visualization": None,
            "error": None,
        }

    def _format_output(self, final_state: VisAgentState) -> VisualizationResult:
        """Interprets the final state and formats the public-facing response."""
        final_visualization = final_state.get("final_visualization")
        if final_visualization:
            # Extract the toolset used from the last step in the scratchpad
            last_reasoning, last_toolset, last_observation = final_state[
                "agent_scratchpad"
            ][-1]
            return VisualizationResult(
                status="success",
                visualization=final_visualization,
                vis_params=last_toolset,
            )
        else:
            error_message = final_state.get("error") or "Unknown error occurred."
            return VisualizationResult(status="error", error_message=error_message)

    def run(
        self,
        user_question: str,
        sql_result: SQLResult,
    ) -> VisualizationResult:
        """
        Runs the visualization agent workflow.
        """
        if sql_result.dataframe is None or sql_result.dataframe.empty:
            return VisualizationResult(
                status="error",
                error_message="Cannot generate visualization from an empty or missing DataFrame.",
            )

        initial_state = self._prepare_initial_state(user_question, sql_result)

        # The config here adds recursion limit and thread pool for the graph
        final_state = self.app.invoke(initial_state, config={"recursion_limit": 10})

        return self._format_output(final_state)
