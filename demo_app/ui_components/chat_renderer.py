"""
UI component for rendering chat messages in the Streamlit application.

This module is responsible for the visual representation of the conversation
between the user and the AI agent. It handles different message types (user,
assistant, error, plan, result) and formats them appropriately.

By encapsulating the rendering logic here, the main application file is kept
cleaner and more focused on orchestration rather than UI details.
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, Callable
import sqlparse


def render_message(message: Dict[str, Any], run_query_func: Callable[[str], None]):
    """
    Renders a single chat message based on its content and type.

    This function uses `st.chat_message` and then inspects the message's
    `role` and `content_type` to determine how to display it.

    Args:
        message: A dictionary representing a single chat message. It should
                 contain at least a 'role' and often a 'content_type'.
        run_query_func: A callback function that is executed when the user
                        clicks the "Run Query" button on a plan or result message.
    """
    role = message.get("role")

    with st.chat_message(role):
        # --- User Messages ---
        if role == "user":
            st.markdown(message.get("content"))
            return

        # --- Assistant Messages ---
        content_type = message.get("content_type", "text")

        if content_type == "text":
            # Simple text response from the assistant (e.g., a clarification question)
            st.markdown(message.get("content"))

        elif content_type == "error":
            # An error message from the agent or system
            st.error(message.get("content"))

        elif content_type in ["plan", "result"]:
            # A message containing a generated SQL query
            data = message.get("data", {})
            sql_query = data.get("sql_query", "No SQL available.")
            reasoning = data.get("reasoning", "No reasoning provided.")

            # Display the formatted SQL query
            st.markdown("Here is the generated query:")
            formatted_sql = sqlparse.format(
                sql_query, reindent=True, keyword_case="upper"
            )
            st.code(formatted_sql, language="sql")

            # Provide a button to execute the query manually
            # The key is made unique using the message timestamp to avoid conflicts
            if st.button("▶️ Run Query", key=f"run_{message['timestamp']}"):
                run_query_func(sql_query)

            # Show the agent's reasoning in an expander
            with st.expander("Show Agent's Reasoning"):
                st.markdown(reasoning or "_The agent did not provide specific reasoning._")

            # --- Displaying Query Results ---
            # If it's a result message, also show the dataframe
            if content_type == "result":
                df = data.get("dataframe")
                if df is not None and not df.empty:
                    st.markdown("--- ")
                    st.markdown("**Query Results:**")
                    st.dataframe(df, use_container_width=True)
                    # Allow downloading the results as a CSV
                    st.download_button(
                        label="Download as CSV",
                        data=df.to_csv(index=False).encode("utf-8"),
                        file_name="query_results.csv",
                        mime="text/csv",
                        key=f"download_{message['timestamp']}",
                    )
                else:
                    st.info("The query executed successfully but returned no results.")