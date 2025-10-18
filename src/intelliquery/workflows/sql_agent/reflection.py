import os
import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from .base import BaseWorkflow
from ..models.sql_agent.state import SQLAgentState
from ..models.sql_agent.agent_io import ReflectionReview

logger = logging.getLogger(__name__)


class ReflectionWorkflow(BaseWorkflow):
    """
    Implements a reflection-based workflow. An intermediate reviewer agent
    examines the generated SQL for improvements before execution.
    """

    def build_graph(self) -> StateGraph:
        """Builds the LangGraph workflow with a reflection loop."""
        graph = StateGraph(SQLAgentState)
        graph.add_node("generate_sql", self.generate_sql_node)
        graph.add_node("reflection_node", self.reflection_node)
        graph.add_node("execute_sql", self.execute_sql_node)

        graph.set_entry_point("generate_sql")

        graph.add_conditional_edges(
            "generate_sql",
            self.should_reflect_node,
            {"reflect": "reflection_node", "execute": "execute_sql"},
        )
        graph.add_conditional_edges(
            "reflection_node",
            self.decide_after_reflection_node,
            {"regenerate": "generate_sql", "execute": "execute_sql"},
        )
        graph.add_conditional_edges(
            "execute_sql", self.should_retry_node, {"retry": "generate_sql", "end": END}
        )
        return graph

    def _prepare_reflection_prompt_variables(
        self, state: SQLAgentState
    ) -> Dict[str, Any]:
        """Prepares the variables for the reflection/review prompt."""
        return {
            "user_question": state["natural_language_question"],
            "schema_definition": state["db_context"]["augmented_schema"],
            "sql_query": state["generation_result"].query,
        }

    def reflection_node(self, state: SQLAgentState) -> Dict[str, Any]:
        """Node that reviews the generated SQL for correctness and performance."""
        logger.info("--- Reviewing generated SQL ---")

        prompt = self.prompt_provider.get_template(
            os.path.join("sql_agent", "reflection.prompt")
        )
        variables = self._prepare_reflection_prompt_variables(state)

        review = self.llm_interface.generate_structured(
            system_prompt=prompt,
            user_input="Please review the provided SQL query.",
            variables=variables,
            response_model=ReflectionReview,
        )

        logger.info(f"--- Reviewer decision: {review.decision} ---")
        if review.suggestions:
            logger.info(f"--- Reviewer suggestions: {review.suggestions} ---")

        return {
            "review": review.suggestions if review.decision == "revise" else None,
            "current_reflection_attempt": state["current_reflection_attempt"] + 1,
        }

    def should_reflect_node(self, state: SQLAgentState) -> str:
        """Determines if the reflection step should be triggered."""
        if state["generation_result"].status == "success":
            return "reflect"
        # For clarification or error, skip reflection and go to the end
        return "execute"

    def decide_after_reflection_node(self, state: SQLAgentState) -> str:
        """Decides the next step based on the reviewer's feedback."""
        if state["review"] is None:
            logger.info("--- Reviewer approved. Proceeding to execution. ---")
            return "execute"

        if state["current_reflection_attempt"] >= state["max_reflection_attempts"]:
            logger.warning(
                "--- Max reflection attempts reached. Proceeding to execution with last query. ---"
            )
            return "execute"

        logger.info("--- Reviewer suggested revisions. Regenerating SQL. ---")
        return "regenerate"
