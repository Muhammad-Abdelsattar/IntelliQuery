from langgraph.graph import StateGraph, END

from ..models.state import SQLAgentState
from .base import BaseWorkflow


class SimpleWorkflow(BaseWorkflow):
    """
    Implements the direct, non-reflection-based workflow for SQL generation.
    It follows a simple generate -> execute -> retry loop.
    """

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
