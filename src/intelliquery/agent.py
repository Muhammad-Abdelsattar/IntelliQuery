from __future__ import annotations
import logging
from typing import List, Tuple, Dict, Any, Optional, Union
import importlib.resources

from langgraph.graph import StateGraph, END
from simple_llm import LLMInterface, FileSystemPromptProvider

from .database import DatabaseService
from .models import (
    LLM_SQLResponse,
    SQLAgentState,
    SQLPlan,
    SQLResult,
    EnrichedDatabaseContext,
)

logger = logging.getLogger(__name__)


class SQLAgent:
    """
    A self-contained agent that generates and optionally executes SQL queries.
    It operates on a pre-built, enriched context and is unaware of caching. Its
    primary responsibility is to solve the text-to-SQL task.
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
        db_service: DatabaseService,
        max_attempts: int = 3,
    ):
        self.llm_interface = llm_interface
        self.db_service = db_service
        self.max_attempts = max_attempts

        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        self.prompt_provider = FileSystemPromptProvider(base_path=prompts_base_path)

        self.workflow = self._build_graph()
        self.app = self.workflow.compile()

    def _build_graph(self) -> StateGraph:
        """Builds the internal LangGraph workflow for the agent."""
        graph = StateGraph(SQLAgentState)
        graph.add_node("generate_sql", self.generate_sql_node)
        graph.add_node("execute_sql", self.execute_sql_node)
        graph.set_entry_point("generate_sql")
        graph.add_edge("generate_sql", "execute_sql")
        graph.add_conditional_edges(
            "execute_sql", self.should_retry_node, {"retry": "generate_sql", "end": END}
        )
        return graph

    def generate_sql_node(self, state: SQLAgentState) -> Dict[str, Any]:
        """Node that generates an SQL query using the pre-built context."""
        logger.info(
            f"--- Attempt {state['current_attempt'] + 1}/{state['max_attempts']}: Generating SQL ---"
        )
        chat_history_str = "\n".join(
            [f"Human: {q}\nAI: {a}" for q, a in state["chat_history"]]
        ).strip()
        system_prompt = self.prompt_provider.get_template("system.prompt")

        pre_built_context = state["db_context"]

        llm_variables = {
            "database_dialect": self.db_service.dialect,
            "schema_definition": pre_built_context["augmented_schema"],
            "business_context": pre_built_context["business_context"],
            "user_question": state["natural_language_question"],
            "history": "\n".join(state["history"]),
            "chat_history": (
                chat_history_str
                if chat_history_str
                else "No previous conversation history."
            ),
        }

        response = self.llm_interface.generate_structured(
            system_prompt=system_prompt,
            user_input=state["natural_language_question"],
            variables=llm_variables,
            response_model=LLM_SQLResponse,
        )

        history_entry = (
            f"ATTEMPT {state['current_attempt'] + 1} - Status: {response.status}"
        )
        if response.query:
            history_entry += f"\nSQL:\n{response.query}"
        if response.reason:
            history_entry += f"\nReason:\n{response.reason}"

        return {
            "generation_result": response,
            "current_attempt": state["current_attempt"] + 1,
            "history": state["history"] + [history_entry],
        }

    def execute_sql_node(self, state: SQLAgentState) -> Dict[str, Any]:
        """Node that executes the SQL only if the generation was successful."""
        gen_result = state["generation_result"]
        if gen_result.status != "success":
            logger.warning(
                f"Skipping SQL execution. Generation status: '{gen_result.status}'."
            )
            return {}

        sql_query = gen_result.query.strip()
        logger.info("--- Executing SQL ---")
        try:
            results_df = self.db_service.execute_for_dataframe(sql_query)
            logger.info("Successfully executed SQL.")
            return {
                "final_dataframe": results_df,
                "generated_sql": sql_query,
                "error": None,
            }
        except (ValueError, RuntimeError) as e:
            error_message = f"Error executing SQL: {e}"
            logger.error(f"Execution failed: {error_message}")
            history_update = state["history"] + [f"EXECUTION FAILED: {error_message}"]
            return {
                "error": error_message,
                "final_dataframe": None,
                "history": history_update,
            }

    def should_retry_node(self, state: SQLAgentState) -> str:
        """Decides whether to retry SQL generation or end the workflow."""
        if state["generation_result"].status != "success":
            return "end"
        if state.get("error") is None:
            logger.info("--- Workflow successful ---")
            return "end"
        if state["current_attempt"] >= state["max_attempts"]:
            logger.warning("--- Max attempts reached, ending workflow ---")
            return "end"
        logger.info("--- Database error detected, retrying generation ---")
        return "retry"

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
            "final_dataframe": None,
            "generated_sql": "",
            "error": None,
        }

        if not auto_execute:
            gen_state = self.workflow.get_node("generate_sql").invoke(initial_state)
            gen_result = gen_state["generation_result"]

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
        else:
            final_state = self.app.invoke(initial_state)
            gen_result = final_state["generation_result"]

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

            # This handles the case where the LLM itself reports an error on its first try
            if gen_result.status == "error":
                return SQLResult(status="error", error_message=gen_result.reason)

            return SQLResult(
                status="success",
                dataframe=final_state.get("final_dataframe"),
                sql_query=final_state.get("generated_sql"),
            )
