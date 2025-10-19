from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional

import pandas as pd
from typing_extensions import TypedDict


class VisAgentState(TypedDict):
    """
    Represents the internal state of the Visualization Agent's workflow.
    """

    # Inputs
    user_question: str
    sql_query: str
    dataframe: pd.DataFrame
    metadata: Dict[str, Any]
    visualization_agent_framework: str

    # Agent loop state
    agent_scratchpad: List[str]
    current_step: int

    # Outputs
    final_visualization: Optional[Any]
    error: Optional[str]
