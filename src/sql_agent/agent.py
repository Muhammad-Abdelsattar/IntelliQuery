from __future__ import annotations
import logging
import importlib.resources
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import pandas as pd
from langgraph.graph import StateGraph, END
from simple_llm import LLMInterface, FileSystemPromptProvider

from .database import DatabaseService
from .models import LLM_SQLResponse, SQLAgentState, SQLPlan, SQLResult
from .exceptions import SQLGenerationError

logger = logging.getLogger(__name__)


class SQLAgent:
    """
    A self-contained agent that generates and optionally executes SQL queries.

    This agent uses an internal workflow to attempt SQL generation, execute it,
    and retry upon failure. Its public interface provides two entry points:
    - `plan`: Generates the SQL query without executing it.
    - `run`: Generates and executes the query, returning a DataFrame.
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

        # Use pkg_resources to find the prompts within the installed package
        prompts_base_path = importlib.resources.files("sql_agent") / "prompts"

        self.prompt_provider = FileSystemPromptProvider(base_path=prompts_base_path)

        self.workflow = self._build_graph()
        self.app = self.workflow.compile()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(SQLAgentState)
        graph.add_node("generate_sql", self.generate_sql_node)
        graph.add_node("execute_sql", self.execute_sql_node)
        graph.set_entry_point("generate_sql")
        graph.add_edge("generate_sql", "execute_sql")
        graph.add_conditional_edges(
            "execute_sql", self.should_retry_node, {"retry": "generate_sql", "end": END}
        )
        return graph

    # Nodes

    def generate_sql_node(self, state: SQLAgentState) -> Dict[str, Any]:
        """Node that generates an SQL query."""
        logger.info(
            f"--- Attempt {state['current_attempt'] + 1}/{self.max_attempts}: Generating SQL ---"
        )
        chat_history_str = "\n".join(
            [f"Human: {q}\nAI: {a}" for q, a in state["chat_history"]]
        ).strip()
        system_prompt = self.prompt_provider.get_template("system.prompt")

        business_context_str = (
            state.get("business_context") or "No additional context provided."
        )

        llm_variables = {
            "database_dialect": self.db_service.dialect,
            "schema_definition": state["db_context"]["table_info"],
            "user_question": state["natural_language_question"],
            "history": "\n".join(state["history"]),
            "chat_history": (
                chat_history_str
                if chat_history_str
                else "No previous conversation history."
            ),
            "business_context": business_context_str,  # NEW: Add to variables
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
        if state["current_attempt"] >= self.max_attempts:
            logger.warning("--- Max attempts reached, ending workflow ---")
            return "end"
        logger.info("--- Database error detected, retrying generation ---")
        return "retry"

    # Public Interface

    def run(
        self,
        question: str,
        chat_history: Optional[List[Tuple[str, str]]] = None,
        business_context: Optional[str] = None,
        auto_execute: bool = True,
    ) -> Union[SQLPlan, SQLResult]:
        """
        Generates and optionally executes an SQL query.

        Args:
            question: The natural language question to answer.
            chat_history: A list of previous user/AI message tuples.
            business_context: Optional string containing business rules or definitions.
            auto_execute: If True, executes the query and returns an SQLResult
                          with a DataFrame. If False, generates and validates
                          the query, returning an SQLPlan without execution.

        Returns:
            An SQLResult if auto_execute is True and successful.
            An SQLPlan if auto_execute is False or if execution fails at the
            planning stage (e.g., for clarification).
        """
        if not auto_execute:
            return self._plan_and_validate(question, chat_history, business_context)
        else:
            return self._execute_full_workflow(question, chat_history, business_context)

    def _plan_and_validate(
        self,
        question: str,
        chat_history: Optional[List[Tuple[str, str]]],
        business_context: Optional[str],
    ) -> SQLPlan:
        """
        Internal method for the "plan-only" logic. Generates and validates SQL.
        """
        initial_state: SQLAgentState = {
            "natural_language_question": question,
            "chat_history": chat_history or [],
            "business_context": business_context,
            "db_context": self.db_service.get_context_for_agent(),
            "history": [],
            "max_attempts": 1,
            "current_attempt": 0,
            "generation_result": None,
            "final_dataframe": None,
            "generated_sql": "",
            "error": None,
        }
        # Run only the generation node
        gen_state = self.workflow.get_node("generate_sql").invoke(initial_state)
        gen_result = gen_state["generation_result"]

        if gen_result.status == "clarification":
            return SQLPlan(
                status="clarification_needed",
                clarification_question=gen_result.clarification_question,
            )
        if gen_result.status == "error":
            return SQLPlan(status="error", error_message=gen_result.reason)

        # We have a successful generation, now let's validate it
        sql_query = gen_result.query
        try:
            self.db_service.validate_sql(sql_query)
            # If we reach here, validation was successful
            return SQLPlan(
                status="success",
                sql_query=sql_query,
                reasoning=gen_result.reason,
                is_validated=True,
            )
        except ValueError as e:
            # Validation failed
            return SQLPlan(
                status="error",
                sql_query=sql_query,
                reasoning="The generated SQL was syntactically invalid.",
                error_message=str(e),
                is_validated=False,
            )

    def _execute_full_workflow(
        self,
        question: str,
        chat_history: Optional[List[Tuple[str, str]]],
        business_context: Optional[str],
    ) -> SQLResult:
        """
        Internal method to run the full LangGraph workflow with retries.
        """
        initial_state: SQLAgentState = {
            "natural_language_question": question,
            "chat_history": chat_history or [],
            "business_context": business_context,
            "db_context": self.db_service.get_context_for_agent(),
            "history": [],
            "max_attempts": self.max_attempts,
            "current_attempt": 0,
            "generation_result": None,
            "final_dataframe": None,
            "generated_sql": "",
            "error": None,
        }

        final_state = self.app.invoke(initial_state)
        gen_result = final_state["generation_result"]

        if gen_result.status == "clarification":
            return SQLResult(
                status="clarification_needed",
                clarification_question=gen_result.clarification_question,
            )
        if gen_result.status == "error" and final_state.get("error") is None:
            return SQLResult(status="error", error_message=gen_result.reason)

        db_error = final_state.get("error")
        if db_error:
            return SQLResult(
                status="error",
                error_message=f"SQL execution failed after {self.max_attempts} attempts: {db_error}",
                sql_query=gen_result.query,
            )
        else:
            return SQLResult(
                status="success",
                dataframe=final_state.get("final_dataframe"),
                sql_query=final_state.get("generated_sql"),
            )
