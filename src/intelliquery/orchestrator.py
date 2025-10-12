from __future__ import annotations
import logging
from typing import List, Tuple, Optional, Union, Literal

from nexus_llm import LLMInterface

from .core.database import DatabaseService
from .models.public import SQLPlan, SQLResult, EnrichedDatabaseContext
from .models.state import SQLAgentState
from .workflows.simple import SimpleWorkflow
from .workflows.reflection import ReflectionWorkflow

logger = logging.getLogger(__name__)


class QueryOrchestrator:
    """
    A high-level orchestrator for text-to-SQL workflows.
    It initializes and runs a selected workflow (e.g., simple, reflection)
    to convert a natural language question into an SQL query and optionally
    execute it, handling the full lifecycle of the request.
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
        db_service: DatabaseService,
        workflow_type: Literal["simple", "reflection"] = "simple",
        max_attempts: int = 3,
        max_reflection_attempts: int = 2,
    ):
        self.llm_interface = llm_interface
        self.db_service = db_service
        self.max_attempts = max_attempts
        self.max_reflection_attempts = max_reflection_attempts

        if workflow_type == "simple":
            workflow = SimpleWorkflow(llm_interface, db_service)
        elif workflow_type == "reflection":
            workflow = ReflectionWorkflow(llm_interface, db_service)
        else:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        self.app = workflow.compile()

    def _prepare_initial_state(
        self,
        question: str,
        context: EnrichedDatabaseContext,
        chat_history: Optional[List[Tuple[str, str]]],
        auto_execute: bool,
    ) -> SQLAgentState:
        """Encapsulates the creation of the initial state dictionary for the graph."""
        db_context_for_graph = {
            "augmented_schema": context.augmented_schema,
            "business_context": context.business_context
            or "No additional context provided.",
        }
        return {
            "natural_language_question": question,
            "chat_history": chat_history or [],
            "db_context": db_context_for_graph,
            "history": [],
            "max_attempts": self.max_attempts if auto_execute else 1,
            "current_attempt": 0,
            "generation_result": None,
            "max_reflection_attempts": self.max_reflection_attempts,
            "current_reflection_attempt": 0,
            "review": None,
            "final_dataframe": None,
            "generated_sql": "",
            "error": None,
        }

    def _format_output(
        self, final_state: SQLAgentState, auto_execute: bool
    ) -> Union[SQLPlan, SQLResult]:
        """Interprets the final state from the workflow and formats the appropriate public-facing response."""
        gen_result = final_state["generation_result"]

        # Handle clarification case (applies to both modes)
        if gen_result.status == "clarification":
            response_model = SQLResult if auto_execute else SQLPlan
            return response_model(
                status="clarification_needed",
                clarification_question=gen_result.clarification_question,
            )

        # Handle general error from the LLM
        if gen_result.status == "error":
            response_model = SQLResult if auto_execute else SQLPlan
            return response_model(status="error", error_message=gen_result.reason)

        # Handle database execution errors (only in execute mode)
        db_error = final_state.get("error")
        if auto_execute and db_error:
            return SQLResult(
                status="error",
                error_message=f"SQL execution failed after {final_state['current_attempt']} attempts: {db_error}",
                sql_query=gen_result.query,
                reasoning=gen_result.reason,
            )

        # Handle successful plan-only mode
        if not auto_execute:
            sql_query = gen_result.query
            try:
                self.db_service.validate_sql(sql_query)
                return SQLPlan(
                    status="success",
                    sql_query=sql_query,
                    reasoning=gen_result.reason,
                    is_validated=True,
                )
            except ValueError as e:
                return SQLPlan(
                    status="error",
                    sql_query=sql_query,
                    error_message=str(e),
                    is_validated=False,
                )

        # Handle successful execution mode
        return SQLResult(
            status="success",
            dataframe=final_state.get("final_dataframe"),
            sql_query=final_state.get("generated_sql"),
            reasoning=gen_result.reason,
        )

    def run(
        self,
        question: str,
        context: EnrichedDatabaseContext,
        chat_history: Optional[List[Tuple[str, str]]] = None,
        auto_execute: bool = True,
    ) -> Union[SQLPlan, SQLResult]:
        """
        Generates and optionally executes an SQL query using the provided context.
        """
        # Prepare the initial state for the workflow
        initial_state = self._prepare_initial_state(
            question, context, chat_history, auto_execute
        )

        # Invoke the compiled LangGraph application
        final_state = self.app.invoke(initial_state)

        # Format the output into a clean, public-facing model
        return self._format_output(final_state, auto_execute)
