"""
UI component for rendering chat messages in the Streamlit application.

This module is responsible for the visual representation of the conversation
between the user and the AI agent. It handles different message types and
formats them appropriately, including the new BI result format which can
contain text, data, and visualizations.
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, Callable
import sqlparse


def render_message(message: Dict[str, Any], regenerate_func: Callable[[Dict[str, Any]], None]):
    """
    Renders a single chat message based on its content and type.

    Args:
        message: A dictionary representing a single chat message.
        regenerate_func: A callback function executed when the user clicks
                         the "Regenerate" button.
    """
    role = message.get("role")

    with st.chat_message(role):
        content_type = message.get("content_type", "text")

        # --- User Messages ---
        if role == "user":
            st.markdown(message.get("content"))
            return

        # --- Assistant Messages: Simple Text or Error ---
        if content_type in ["text", "error"]:
            st.markdown(message.get("content"))
            return

        # --- Assistant Messages: BI Result (Text + Regeneratable Data/Viz) ---
        if content_type == "bi_result":
            data = message.get("data", {})
            final_answer = data.get("final_answer", "No answer provided.")
            sql_query = data.get("sql_query", "No SQL available.")
            reasoning = data.get("reasoning", "No reasoning provided.")

            # 1. Display the agent's textual answer
            st.markdown(final_answer)

            # 2. Display the details in an expander
            with st.expander("Show Details"):
                st.markdown("**Agent's Reasoning:**")
                st.markdown(reasoning or "_No reasoning provided._")
                st.markdown("**Generated SQL Query:**")
                formatted_sql = sqlparse.format(
                    sql_query, reindent=True, keyword_case="upper"
                )
                st.code(formatted_sql, language="sql")

            # 3. The button to trigger regeneration
            if st.button("🔄 Regenerate", key=f"regen_{message['timestamp']}"):
                # We store the key of the message being regenerated in session state
                st.session_state.regenerating_key = f"regen_{message['timestamp']}"

            # 4. The container where results will appear after regeneration
            results_container = st.container()

            # Check if this specific message is the one being regenerated
            if st.session_state.get("regenerating_key") == f"regen_{message['timestamp']}":
                with results_container:
                    # Call the regeneration function from main.py
                    regenerate_func(data)
                # Clear the flag after regeneration to prevent re-triggering
                st.session_state.regenerating_key = None