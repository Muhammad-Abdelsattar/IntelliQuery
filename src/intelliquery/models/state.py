from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional
import pandas as pd
from typing_extensions import TypedDict
from .agent_io import LLM_SQLResponse

class SQLAgentState(TypedDict):
    """
    Represents the internal state of the SQL Agent's workflow.
    It's designed to be comprehensive for both simple and reflection workflows.
    """
    # Inputs
    natural_language_question: str
    chat_history: List[Tuple[str, str]]
    db_context: Dict[str, Any]

    # Generation loop state
    history: List[str]
    max_attempts: int
    current_attempt: int
    generation_result: Optional[LLM_SQLResponse]

    # Reflection loop state
    max_reflection_attempts: int
    current_reflection_attempt: int
    review: Optional[str] # To store reviewer feedback

    # Outputs
    final_dataframe: Optional[pd.DataFrame]
    generated_sql: str
    error: Optional[str]
