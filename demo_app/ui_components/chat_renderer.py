import streamlit as st
import pandas as pd
from typing import Dict, Any, Callable, Optional, Tuple
import sqlparse


def render_message(
    message: Dict[str, Any],
    regenerate_func: Callable[
        [Dict[str, Any]], Tuple[Optional[pd.DataFrame], Optional[Any]]
    ],
):
    """
    Renders a single chat message based on its content and type, with new logic
    for eager display of live results vs. button for historical results.
    """
    role = message.get("role")

    # Use the unique message key if it exists, otherwise fallback to timestamp
    message_key = message.get("message_key", f"regen_{message.get('timestamp', 0)}")

    if "results_cache" not in st.session_state:
        st.session_state.results_cache = {}

    with st.chat_message(role):
        content_type = message.get("content_type", "text")

        if role == "user":
            st.markdown(message.get("content"))
            return

        if content_type in ["text", "error"]:
            st.markdown(message.get("content"))
            return

        if content_type == "bi_result":
            data = message.get("data", {})
            final_answer = data.get("final_answer", "No answer provided.")
            sql_query = data.get("sql_query", "No SQL available.")
            reasoning = data.get("reasoning", "No reasoning provided.")

            is_live_generation = message.get("is_live_generation", False)
            results_are_visible = message_key in st.session_state.results_cache

            st.markdown(final_answer)

            button_label = (
                "🔄 Refresh Data"
                if results_are_visible
                else "▶️ Run Query & View Results"
            )
            if st.button(button_label, key=message_key):
                with st.spinner("Executing query and regenerating results..."):
                    df, fig = regenerate_func(data)
                    st.session_state.results_cache[message_key] = (df, fig)
                st.rerun()

            if is_live_generation or results_are_visible:
                if message_key in st.session_state.results_cache:
                    df, fig = st.session_state.results_cache[message_key]

                    if df is not None and not df.empty:
                        with st.expander("View Data", expanded=True):
                            st.dataframe(df, use_container_width=True)
                            st.download_button(
                                "Download CSV",
                                df.to_csv(index=False).encode("utf-8"),
                                f"data_{message_key}.csv",
                                "text/csv",
                            )
                    elif df is not None:
                        with st.expander("View Data", expanded=True):
                            st.info(
                                "The query executed successfully but returned no data."
                            )

                    if fig is not None:
                        with st.expander("View Visualization", expanded=True):
                            st.plotly_chart(fig, use_container_width=True)

            # Details are always available in an expander
            with st.expander("Show Details"):
                st.markdown("**Agent's Reasoning:**")
                st.markdown(reasoning or "_No reasoning provided._")
                st.markdown("**Generated SQL Query:**")
                st.code(
                    sqlparse.format(sql_query, reindent=True, keyword_case="upper"),
                    language="sql",
                )

