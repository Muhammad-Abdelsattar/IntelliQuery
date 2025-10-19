from __future__ import annotations
import os
import logging
from typing import Dict, Any, List

from langgraph.graph import StateGraph, END
from nexus_llm import LLMInterface, FileSystemPromptProvider
import importlib.resources

from ...models.bi_agent.state import BIAgentState
from ...models.bi_agent.agent_io import Reflection
from ...models.sql_agent.public import SQLResult
from ...agents.sql_agent import SQLAgent
from ...agents.vis_agent import VisualizationAgent


logger = logging.getLogger(__name__)

class ReactWorkflow:
    """
    Implements the ReAct (Reason, Act) workflow for the conversational BI agent.
    """

    def __init__(
        self,
        llm_interface: LLMInterface,
        sql_agent: SQLAgent,
        vis_agent: VisualizationAgent,
    ):
        self.llm_interface = llm_interface
        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        self.prompt_provider = FileSystemPromptProvider(base_path=prompts_base_path)
        self.sql_agent = sql_agent
        self.vis_agent = vis_agent

    def build_graph(self) -> StateGraph:
        """Builds the LangGraph workflow for the ReAct loop."""
        graph = StateGraph(BIAgentState)
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
        log = []
        for reasonging, (action, action_args), observation in intermediate_steps:
            log.append(f"Reasoning: {reasonging}")
            log.append(f"Action: {action}\nArgs: {action_args}")
            log.append(f"Observation: {observation}")
        return "\n".join(log)

    def think_node(self, state: BIAgentState) -> Dict[str, Any]:
        """
        The "think" step in the ReAct loop. It calls the LLM to decide the next action.
        """
        logger.info(f"--- Step {state['current_step']}: Thinking ---")

        chat_history_str = "\n".join(
            [f"Human: {q}\nAI: {a}" for q, a in state["chat_history"]]
        ).strip()

        scratchpad = self._format_scratchpad(state["intermediate_steps"])

        prompt_variables = {
            "user_question": state["natural_language_question"],
            "chat_history": chat_history_str or "No previous conversation history.",
            "agent_scratchpad": scratchpad,
        }

        system_prompt = self.prompt_provider.get_template(
            os.path.join("bi_agent", "react_agent.prompt")
        )

        response = self.llm_interface.generate_structured(
            system_prompt=system_prompt,
            user_input=state["natural_language_question"],
            variables=prompt_variables,
            response_model=Reflection,
        )

        if response.action == "FinalAnswer":
            action_args = response.answer
        elif response.action == "sql_agent":
            action_args = response.sql_question
        elif response.action == "visualization_agent":
            action_args = {
                "sql_query": response.sql_query,
                "instruction": response.instruction,
            }

        else:
            action_args = "No action args provided."

        logger.info(f"\t|>Reasoning: {response.reasoning}")
        logger.info(f"\t|>Action: {response.action}")
        logger.info(f"\t|>Args: {action_args}")

        return {
            "intermediate_steps": state["intermediate_steps"]
            + [(response.reasoning, (response.action, action_args), "")]
        }

    def tool_execution_node(self, state: BIAgentState) -> Dict[str, Any]:
        """
        The "act" step in the ReAct loop. It executes the action chosen by the LLM.
        """
        reasoning, (action, action_args), _ = state["intermediate_steps"][-1]
        logger.info(f"--- Executing Tool: {action} ---")

        observation = ""
        sql_result_state = state.get("sql_result")
        vis_result_state = state.get("visualization_result")

        try:
            if action == "sql_agent":
                question = action_args
                if not question:
                    raise ValueError("Missing 'question' argument for sql_agent.")

                # The context is passed when the BI Orchestrator is run
                db_context = state["db_context"]

                result = self.sql_agent.run(
                    question=question,
                    context=db_context,
                    auto_execute=True,
                )

                sql_result_state = result

                if result.status == "success":
                    observation = (
                        f"Successfully executed SQL query: {result.sql_query}.\n"
                        f"Result has {len(result.dataframe)} rows and {len(result.dataframe.columns)} columns."
                    )
                elif result.status == "clarification_needed":
                    observation = f"The SQL agent requires clarification: {result.clarification_question}"
                else:
                    observation = f"SQL agent returned an error: {result.error_message}"

            elif action == "visualization_agent":
                if not sql_result_state or sql_result_state.status != "success":
                    raise ValueError(
                        "Cannot run visualization agent without a successful SQL result."
                    )

                vis_result = self.vis_agent.run(
                    user_question=state["natural_language_question"],
                    sql_result=sql_result_state,
                )

                if vis_result.status == "success":
                    observation = "Successfully generated visualization."
                else:
                    observation = f"Visualization agent returned an error: {vis_result.error_message}"
                
                return {
                    "visualization_result": vis_result, # Store the whole object
                    "intermediate_steps": state["intermediate_steps"][:-1]
                    + [(reasoning, (action, action_args), observation)],
                }

            elif action == "FinalAnswer":
                answer = action_args
                if not answer:
                    raise ValueError("Missing 'answer' argument for FinalAnswer.")
                observation = "Final answer provided."
                return {
                    "final_answer": answer,
                    "intermediate_steps": state["intermediate_steps"][:-1]
                    + [(reasoning, (action, action_args), observation)],
                }

            else:
                observation = f"Unknown action: {action}"

        except Exception as e:
            logger.error(f"Error executing tool {action}: {e}")
            observation = f"Error: {e}"

        return {
            "sql_result": sql_result_state,
            "intermediate_steps": state["intermediate_steps"][:-1]
            + [(reasoning, (action, action_args), observation)],
        }

    def should_continue_node(self, state: BIAgentState) -> str:
        """Determines if the ReAct loop should continue or end."""
        _, (last_action, _), _ = state["intermediate_steps"][-1]
        if last_action == "FinalAnswer":
            logger.info("--- FinalAnswer received, ending workflow ---")
            return "end"

        # Add a max steps condition to prevent infinite loops
        if state["current_step"] >= 10:
            logger.warning("--- Max steps reached, ending workflow ---")
            return "end"

        return "continue"
