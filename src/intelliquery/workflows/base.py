import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
import importlib.resources

from langgraph.graph import StateGraph
from nexus_llm import LLMInterface, FileSystemPromptProvider

from ..core.database import DatabaseService
from ..models.state import SQLAgentState
from ..models.agent_io import LLM_SQLResponse

logger = logging.getLogger(__name__)


class BaseWorkflow(ABC):
    """
    An abstract base class for creating SQL generation workflows.
    It provides common nodes and structure that can be shared across different
    workflow implementations.
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
        db_service: DatabaseService,
    ):
        self.llm_interface = llm_interface
        self.db_service = db_service
        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        self.prompt_provider = FileSystemPromptProvider(base_path=prompts_base_path)

    @abstractmethod
    def _build_graph(self) -> StateGraph:
        """Subclasses must implement this method to define the workflow graph."""
        pass

    def compile(self):
        """Builds and compiles the graph, returning the runnable app."""
        graph = self._build_graph()
        return graph.compile()

    def generate_sql_node(self, state: SQLAgentState) -> Dict[str, Any]:
        """Node that generates an SQL query using the pre-built context."""
        logger.info(
            f"\t\t > Attempt {state['current_attempt'] + 1}/{state['max_attempts']}: Generating SQL..."
        )
        chat_history_str = "\n".join(
            [f"Human: {q}\nAI: {a}" for q, a in state["chat_history"]]
        ).strip()
        system_prompt = self.prompt_provider.get_template(
            os.path.join("direct_workflow", "direct_generation.prompt")
        )

        # Append reflection review if it exists
        history = state["history"]
        if state.get("review"):
            history = history + [f"REVIEWER SUGGESTIONS:\n{state['review']}"]

        llm_variables = {
            "database_dialect": self.db_service.dialect,
            "schema_definition": state["db_context"]["augmented_schema"],
            "business_context": state["db_context"]["business_context"],
            "user_question": state["natural_language_question"],
            "history": "\n".join(history),
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
            "review": None,  # Clear previous review
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
        logger.info(f"\t\t > Executing SQL: {sql_query}")
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
        """Decides whether to retry SQL generation after an execution error."""
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
