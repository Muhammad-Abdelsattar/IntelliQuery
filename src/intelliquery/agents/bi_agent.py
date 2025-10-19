from __future__ import annotations
import logging
from typing import List, Tuple, Optional

from nexus_llm import LLMInterface

from ..core.database import DatabaseService
from ..models.sql_agent.public import EnrichedDatabaseContext
from ..models.bi_agent.public import BIResult
from ..models.bi_agent.state import BIAgentState
from ..workflows.bi_agent.react import ReactWorkflow
from .sql_agent import SQLAgent
from .vis_agent import VisualizationAgent

logger = logging.getLogger(__name__)


class BIOrchestrator:
    """
    A high-level orchestrator for the conversational BI agent.
    It initializes and runs the ReAct workflow to interpret user questions,
    delegate to specialized agents (SQL, Visualization), and return a structured result.
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
        sql_agent: SQLAgent,
        vis_agent: VisualizationAgent,
    ):
        self.llm_interface = llm_interface
        
        workflow = ReactWorkflow(llm_interface, sql_agent, vis_agent)
        self.app = workflow.compile()

    def _prepare_initial_state(
        self,
        question: str,
        context: EnrichedDatabaseContext,
        chat_history: Optional[List[Tuple[str, str]]],
    ) -> BIAgentState:
        """Encapsulates the creation of the initial state for the graph."""
        return {
            "natural_language_question": question,
            "chat_history": chat_history or [],
            "db_context": context, # Pass the full context object
            "agent_scratchpad": [],
            "intermediate_steps": [],
            "current_step": 1,
            "sql_result": None,
            "visualization_result": None,
            "final_answer": None,
            "error": None,
        }

    def _format_output(self, final_state: BIAgentState) -> BIResult:
        """Interprets the final state and formats the public-facing response."""
        final_answer = final_state.get("final_answer") or ""
        sql_result = final_state.get("sql_result")
        vis_result = final_state.get("visualization_result")
        error = final_state.get("error")

        # Consolidate reasoning from all steps
        reasoning_steps = [step[0] for step in final_state.get("intermediate_steps", [])]
        consolidated_reasoning = "\n".join(reasoning_steps)

        # Extract SQL query and visualization params
        sql_query = sql_result.sql_query if sql_result else None
        vis_params = vis_result.vis_params if vis_result and hasattr(vis_result, 'vis_params') else None

        # Handle clarification from the SQL agent
        if sql_result and sql_result.status == "clarification_needed":
            return BIResult(
                status="clarification_needed",
                final_answer=sql_result.clarification_question,
                reasoning=consolidated_reasoning,
            )

        # Handle clarification from the BI agent itself
        if "?" in final_answer and len(final_answer) < 200:
            return BIResult(
                status="clarification_needed",
                final_answer=final_answer,
                reasoning=consolidated_reasoning,
            )

        # Handle errors
        if error:
            return BIResult(
                status="error",
                final_answer=final_answer or "An error occurred.",
                error_message=error,
                reasoning=consolidated_reasoning,
            )
        if sql_result and sql_result.status == "error":
            return BIResult(
                status="error",
                final_answer=final_answer
                or "An error occurred during SQL generation or execution.",
                error_message=sql_result.error_message,
                reasoning=consolidated_reasoning,
            )

        # Success case
        return BIResult(
            status="success",
            final_answer=final_answer or "Request processed successfully.",
            dataframe=sql_result.dataframe if sql_result else None,
            visualization=vis_result.visualization if vis_result else None,
            sql_query=sql_query,
            reasoning=consolidated_reasoning,
            visualization_params=vis_params,
        )

    def run(
        self,
        question: str,
        context: EnrichedDatabaseContext,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> BIResult:
        """
        Runs the BI agent workflow for a given question and context.
        """
        initial_state = self._prepare_initial_state(question, context, chat_history)
        
        # The config here adds recursion limit and thread pool for the graph
        final_state = self.app.invoke(initial_state, config={"recursion_limit": 15})
        
        return self._format_output(final_state)
