"""
UI component for rendering chat messages in the Streamlit application.

This module is responsible for the visual representation of the conversation
between the user and the AI agent. It handles different message types and
formats them appropriately, including the new BI result format which can
contain text, data, and visualizations.
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, Callable, Optional, Tuple
import sqlparse


def render_message(message: Dict[str, Any], regenerate_func: Callable[[Dict[str, Any]], Tuple[Optional[pd.DataFrame], Optional[Any]]]):
    """
    Renders a single chat message based on its content and type.

    Args:
        message: A dictionary representing a single chat message.
        regenerate_func: A callback function that returns a dataframe and a figure.
    """
    role = message.get("role")
    message_key = f"regen_{message.get('timestamp', 0)}"

    # Initialize the results cache in the session state if it doesn't exist
    if "results_cache" not in st.session_state:
        st.session_state.results_cache = {}

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

            st.markdown(final_answer)

            with st.expander("Show Details"):
                st.markdown("**Agent's Reasoning:**")
                st.markdown(reasoning or "_No reasoning provided._")
                st.markdown("**Generated SQL Query:**")
                st.code(sqlparse.format(sql_query, reindent=True, keyword_case="upper"), language="sql")

            # The button's click is the trigger for regeneration.
            if st.button("🔄 Regenerate & View Results", key=message_key):
                with st.spinner("Executing query and regenerating results..."):
                    df, fig = regenerate_func(data)
                    # Store the results in our cache, keyed by the message's unique ID.
                    st.session_state.results_cache[message_key] = (df, fig)
                # No st.rerun() needed, the button click handles it.

            # On every script run, check if results for this message exist in the cache.
            if message_key in st.session_state.results_cache:
                df, fig = st.session_state.results_cache[message_key]

                # Display data in an expander
                if df is not None and not df.empty:
                    with st.expander("View Data", expanded=True):
                        st.dataframe(df, use_container_width=True)
                elif df is not None:  # Handles empty dataframe case
                    with st.expander("View Data", expanded=True):
                        st.info("The query executed successfully but returned no results.")
                
                # Display visualization in an expander
                if fig is not None:
                    with st.expander("View Visualization", expanded=True):
                        st.plotly_chart(fig, use_container_width=True)

