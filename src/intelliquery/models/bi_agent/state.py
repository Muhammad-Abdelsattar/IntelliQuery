from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional

import pandas as pd
from typing_extensions import TypedDict

from ..sql_agent.public import SQLResult
from .agent_io import BIAction


class BIAgentState(TypedDict):
    """
    Represents the internal state of the BI Agent's workflow.
    """

    # Inputs
    natural_language_question: str
    chat_history: List[Tuple[str, str]]
    db_context: Dict[str, Any]

    # Agent loop state
    agent_scratchpad: List[str]  # Stores the ReAct formatted history
    intermediate_steps: List[
        Tuple[str, Tuple[str, dict[str, Any]], str]
    ]  # Stores actions and observations
    current_step: int

    # Outputs
    sql_result: Optional[SQLResult]
    visualization_result: Optional[Any]
    final_answer: Optional[str]
    error: Optional[str]
