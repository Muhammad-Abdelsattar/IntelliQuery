from __future__ import annotations
import os
import logging
from typing import Dict, Any, List
import importlib.resources

from langgraph.graph import StateGraph, END
from nexus_llm import LLMInterface, FileSystemPromptProvider

from ...models.vis_agent.state import VisAgentState
from ...models.vis_agent.agent_io import VisualizationToolset
from ...core.vis_provider import VisualizationProvider

logger = logging.getLogger(__name__)


class ReactWorkflow:
    """
    Implements the ReAct (Reason, Act) workflow for the visualization agent.
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
        provider: VisualizationProvider,
    ):
        self.llm_interface = llm_interface
        self.provider = provider  # Store the injected provider
        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        self.prompt_provider = FileSystemPromptProvider(base_path=prompts_base_path)
        # The mapping file is no longer loaded here

    def build_graph(self) -> StateGraph:
        """Builds the LangGraph workflow for the ReAct loop."""
        graph = StateGraph(VisAgentState)
        graph.add_node("think", self.think_node)
        graph.add_node("execute_tool", self.tool_execution_node)

        graph.set_entry_point("think")

        graph.add_conditional_edges(
            "execute_tool",
            self.should_continue_node,
            {"continue": "think", "end": END},
        )
        graph.add_edge("think", "execute_tool")

        return graph

    def compile(self):
        """Builds and compiles the graph, returning the runnable app."""
        graph = self.build_graph()
        return graph.compile()

    def _format_scratchpad(self, intermediate_steps: List[tuple]) -> str:
        """Formats the intermediate steps into a string for the LLM prompt."""
        if not intermediate_steps:
            return "No previous attempts."
        log = []
        for reasoning, toolset, observation in intermediate_steps:
            log.append(f"Reasoning: {reasoning}")
            log.append(f"Visualization Toolset: {toolset}")
            log.append(f"Observation: {observation}")
        return "\n".join(log)

    def think_node(self, state: VisAgentState) -> Dict[str, Any]:
        """
        The "think" step. It calls the LLM to decide the visualization strategy.
        """
        logger.info(
            f"--- Step {state['current_step']}: Thinking about Visualization ---"
        )

        scratchpad = self._format_scratchpad(state["agent_scratchpad"])

        prompt_variables = {
            "user_question": state["user_question"],
            "sql_query": state["sql_query"],
            "metadata": state["metadata"],
            "visualization_agent_framework": state["visualization_agent_framework"],
            "agent_scratchpad": scratchpad,
        }

        system_prompt = self.prompt_provider.get_template(
            os.path.join("vis_agent", "react_agent.prompt")
        )

        response = self.llm_interface.generate_structured(
            system_prompt=system_prompt,
            user_input=state["user_question"],
            variables=prompt_variables,
            response_model=VisualizationToolset,
        )

        logger.info(f"\t|>Reasoning: {response.reasoning}")
        logger.info(f"\t|>Toolset: {response.visualization_toolset}")

        return {
            "agent_scratchpad": state["agent_scratchpad"]
            + [(response.reasoning, response.visualization_toolset, "")]
        }

    def tool_execution_node(self, state: VisAgentState) -> Dict[str, Any]:
        """
        The "act" step. It delegates the visualization creation to the
        configured provider.
        """
        reasoning, toolset, _ = state["agent_scratchpad"][-1]

        tool_name, args = next(iter(toolset.items()))

        logger.info(f"--- Delegating to Provider for Tool: {tool_name} ---")

        observation = ""
        final_visualization = None
        error = None

        try:
            # Delegate chart creation to the provider. This is the key change.
            final_visualization = self.provider.create_chart(
                chart_type=tool_name,
                dataframe=state["dataframe"],
                **args["arguments"],
            )

            observation = f"Successfully generated '{tool_name}' via provider."
            logger.info(f"--- {observation} ---")

        except (NotImplementedError, ValueError, AttributeError, TypeError, KeyError) as e:
            error = f"Error during visualization generation: {e}"
            observation = error
            logger.error(f"--- {error} ---")
        except Exception as e:
            error = f"An unexpected error occurred: {e}"
            observation = error
            logger.error(f"--- {error} ---")


        return {
            "final_visualization": final_visualization,
            "error": error,
            "agent_scratchpad": state["agent_scratchpad"][:-1]
            + [(reasoning, toolset, observation)],
        }

    def should_continue_node(self, state: VisAgentState) -> str:
        """Determines if the ReAct loop should continue or end."""
        if state.get("final_visualization"):
            logger.info("--- Visualization generated, ending workflow ---")
            return "end"

        if state["current_step"] >= 3:  # Max 3 attempts
            logger.warning("--- Max steps reached, ending workflow ---")
            if not state.get("error"):
                state["error"] = (
                    "Failed to generate a visualization after multiple attempts."
                )
            return "end"

        logger.info("--- Retrying visualization generation ---")
        return "continue"
