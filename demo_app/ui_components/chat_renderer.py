import streamlit as st
from typing import Dict, Any, Callable
import sqlparse


def render_message(message: Dict[str, Any], regenerate_func: Callable):
    """Renders a single chat message."""
    role = message.get("role")
    if role == "user":
        avatar_icon = "./assets/user_avatar.png"
    else:
        avatar_icon = "./assets/icon.png"
    with st.chat_message(role, avatar=avatar_icon):
        content_type = message.get("content_type", "text")

        if role == "user":
            st.markdown(message.get("content"))
        elif content_type == "text":
            st.markdown(message.get("content"))
        elif content_type == "error":
            st.error(message.get("content"))
        elif content_type == "bi_result":
            render_bi_result(message, regenerate_func)


def render_bi_result(message: Dict[str, Any], regenerate_func: Callable):
    """Renders the BI result with a default-expanded container for data."""
    message_data = message.get("data", {})
    answer = message_data.get("answer", "No answer provided.")
    sql_query = message_data.get("sql_query")
    reasoning = message_data.get("reasoning")
    vis_params = message_data.get("visualization_params")
    timestamp = message.get("timestamp")

    # Check for live data (from the initial turn) vs. refreshed data (from state)
    live_dataframe = message_data.get("dataframe")
    live_visualization = message_data.get("visualization")
    refreshed_results = st.session_state.get("refreshed_results", {}).get(timestamp)

    st.markdown(answer)

    if sql_query:
        with st.expander("Show Details"):
            st.markdown("**Generated SQL Query:**")
            st.code(
                sqlparse.format(sql_query, reindent=True, keyword_case="upper"),
                language="sql",
            )
            if reasoning:
                st.markdown("**Agent's Reasoning:**")
                st.markdown(reasoning)

        button_label = (
            "🔄 Refresh Data"
            if live_dataframe is not None or refreshed_results
            else "▶️ Execute Step"
        )
        st.button(
            button_label,
            key=f"run_{timestamp}",
            on_click=regenerate_func,
            args=(timestamp, sql_query, vis_params),
        )

    visualization_to_show = (
        refreshed_results["visualization"] if refreshed_results else live_visualization
    )
    dataframe_to_show = (
        refreshed_results["dataframe"] if refreshed_results else live_dataframe
    )

    # Determine if the expander should be open by default
    has_results_to_show = (
        dataframe_to_show is not None or visualization_to_show is not None
    )
    is_expanded_by_default = has_results_to_show and (
        live_dataframe is not None or refreshed_results is not None
    )

    if has_results_to_show:
        with st.expander("View Results", expanded=is_expanded_by_default):
            if visualization_to_show:
                st.plotly_chart(visualization_to_show, use_container_width=True)

            if dataframe_to_show is not None:
                st.dataframe(dataframe_to_show, use_container_width=True)
                if dataframe_to_show.empty:
                    st.info("The query executed successfully but returned no results.")
                else:
                    st.download_button(
                        label="Download as CSV",
                        data=dataframe_to_show.to_csv(index=False).encode("utf-8"),
                        file_name="query_results.csv",
                        mime="text/csv",
                        key=f"download_{timestamp}",
                    )
