import streamlit as st
import pandas as pd
from typing import Dict, Any, Callable
import sqlparse


def render_message(message: Dict[str, Any], run_query_func: Callable[[str], None]):
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

        elif content_type in ["plan", "result"]:
            data = message.get("data", {})
            sql_query = data.get("sql_query", "No SQL available.")
            reasoning = data.get("reasoning", "No reasoning provided.")

            # For both plans and historical results, show the query and run button
            st.markdown("Here is the generated query:")
            formatted_sql = sqlparse.format(
                sql_query, reindent=True, keyword_case="upper"
            )
            st.code(formatted_sql, language="sql")

            if st.button("▶️ Run Query", key=f"run_{message['timestamp']}"):
                run_query_func(sql_query)

            with st.expander("Show Agent's Reasoning"):
                st.markdown(reasoning or "_The agent did not provide specific reasoning._")

            # If it's a result from the current turn, also show the dataframe
            if content_type == "result":
                df = data.get("dataframe")
                if df is not None and not df.empty:
                    st.markdown("--- ")
                    st.markdown("**Query Results:**")
                    st.dataframe(df, use_container_width=True)
                    st.download_button(
                        label="Download as CSV",
                        data=df.to_csv(index=False).encode("utf-8"),
                        file_name="query_results.csv",
                        mime="text/csv",
                        key=f"download_{message['timestamp']}",
                    )
                else:
                    st.info("The query executed successfully but returned no results.")