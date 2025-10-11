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


class SQLAgent:
    """
    A high-level agent that orchestrates text-to-SQL workflows.
    It can operate in different modes (e.g., simple, reflection) by delegating
    the graph-building and execution to specialized workflow classes.
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
        db_context_for_graph = {
            "augmented_schema": context.augmented_schema,
            "business_context": context.business_context
            or "No additional context provided.",
        }

        max_attempts_for_run = self.max_attempts if auto_execute else 1

        initial_state: SQLAgentState = {
            "natural_language_question": question,
            "chat_history": chat_history or [],
            "db_context": db_context_for_graph,
            "history": [],
            "max_attempts": max_attempts_for_run,
            "current_attempt": 0,
            "generation_result": None,
            "max_reflection_attempts": self.max_reflection_attempts,
            "current_reflection_attempt": 0,
            "review": None,
            "final_dataframe": None,
            "generated_sql": "",
            "error": None,
        }

        final_state = self.app.invoke(initial_state)
        gen_result = final_state["generation_result"]

        # Handle non-execution path (planning only)
        if not auto_execute:
            if gen_result.status == "clarification":
                return SQLPlan(
                    status="clarification_needed",
                    clarification_question=gen_result.clarification_question,
                )
            if gen_result.status == "error":
                return SQLPlan(status="error", error_message=gen_result.reason)

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
                    reasoning="The generated SQL was syntactically invalid.",
                    error_message=str(e),
                    is_validated=False,
                )

        # Handle execution path
        if gen_result.status == "clarification":
            return SQLResult(
                status="clarification_needed",
                clarification_question=gen_result.clarification_question,
            )

        db_error = final_state.get("error")
        if db_error:
            return SQLResult(
                status="error",
                error_message=f"SQL execution failed after {self.max_attempts} attempts: {db_error}",
                sql_query=gen_result.query,
            )

        if gen_result.status == "error":
            return SQLResult(status="error", error_message=gen_result.reason)

        return SQLResult(
            status="success",
            dataframe=final_state.get("final_dataframe"),
            sql_query=final_state.get("generated_sql"),
        )
