import streamlit as st
import pandas as pd
from typing import Dict, Any
import sqlparse


def _render_details_expander(sql_query: str, reasoning: str):
    """Helper function to render the details expander for both plans and results."""
    with st.expander("Show Details"):
        tab1, tab2 = st.tabs(["Agent's Reasoning", "SQL Query"])
        with tab1:
            st.markdown(reasoning or "_The agent did not provide specific reasoning._")
        with tab2:
            formatted_sql = sqlparse.format(
                sql_query, reindent=True, keyword_case="upper"
            )
            st.code(formatted_sql, language="sql")


def render_message(message: Dict[str, Any]):
    """Renders a single chat message based on its content and type."""
    role = message.get("role")

    with st.chat_message(role):
        if role == "user":
            st.markdown(message.get("content"))
            return

        content_type = message.get("content_type", "text")

        if content_type == "text":
            st.markdown(message.get("content"))

        elif content_type == "error":
            st.error(message.get("content"))

        elif content_type == "plan":
            data = message.get("data", {})
            sql_query = data.get("sql_query", "No SQL available.")
            reasoning = data.get("reasoning", "No reasoning provided.")
            is_validated = data.get("is_validated", False)

            st.markdown("Here is the generated query plan:")
            if is_validated:
                st.success(
                    "✅ **Query is valid.** The agent has confirmed this query can run against the database."
                )
            else:
                st.warning(
                    "⚠️ **Query not validated.** The generated SQL may have syntax errors."
                )

            # Use our refactored helper to show the details
            _render_details_expander(sql_query, reasoning)

        elif content_type == "result":
            data = message.get("data", {})
            df = data.get("dataframe")
            sql_query = data.get("sql_query", "No SQL available.")
            reasoning = data.get("reasoning", "No reasoning provided.")

            st.markdown("Here are the results from your query:")

            if df is not None and not df.empty:
                st.dataframe(df, use_container_width=True)
                st.download_button(
                    label="Download as CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="query_results.csv",
                    mime="text/csv",
                    key=f"download_{hash(sql_query)}",
                )
            else:
                st.info("The query executed successfully but returned no results.")

            # Use our refactored helper to show the details
            _render_details_expander(sql_query, reasoning)
