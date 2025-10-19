"""
Main Streamlit application file for the IntelliQuery demo.

This file orchestrates the entire user interface, manages application state,
and integrates the various services (chat, database, LLM) to provide
the interactive text-to-SQL experience.

The application is structured as a single-page app with different "pages"
rendered based on the application's state.
"""

# --- Core Imports ---
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# --- Library Imports ---
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from nexus_llm import load_settings
from sqlalchemy import create_engine
import plotly.express as px


# --- Internal Imports ---
from intelliquery import (
    DBContextAnalyzer,
    DatabaseService,
    FileSystemCacheProvider,
    BIOrchestrator,
    BIResult,
)
from services import chat_service, connection_service, llm_service
from state import AppState, get_state
from ui_components import chat_renderer, sidebar

# --- Initial Setup ---
load_dotenv()

st.set_page_config(
    page_title="IntelliQuery",
    page_icon="🧠",
    layout="wide",
)


# -----------------------------------------------------------------------------
# Page Rendering Functions
# -----------------------------------------------------------------------------


def render_home_page():
    """Renders the main welcome page."""
    state = get_state()
    st.title("Welcome to IntelliQuery 🧠")
    st.markdown(
        """
        **Your intelligent BI assistant for talking to your databases.**

        Select a database connection from the sidebar to begin. If you haven't configured
        any, click **Manage Connections** to add your first one.
        """
    )

    if state.selected_connection:
        st.success(f"Connection **'{state.selected_connection['name']}'** is active.")
        if st.button("Start Chatting →", type="primary"):
            state.set_page("chat")
            st.rerun()
    else:
        st.warning("Please select an active connection from the sidebar.")


def render_connection_manager_page():
    """Renders the page for managing database connections."""
    state = get_state()
    st.title("🗄️ Connection Manager")
    st.markdown(
        "Manage your database connections here. The enriched context for each connection will be cached for faster performance."
    )

    # Initialize confirmation state for deletions
    if "confirming_delete_index" not in st.session_state:
        st.session_state.confirming_delete_index = None

    col1, col2 = st.columns([1, 1.5])

    # --- Column 1: Existing Connections ---
    with col1:
        st.subheader("Existing Connections")
        if not state.connections:
            st.info("No connections added yet. Use the form on the right to add one.")
        else:
            for i, conn in enumerate(state.connections):
                is_active = (
                    state.selected_connection
                    and conn["name"] == state.selected_connection["name"]
                )
                schema_display = conn.get("schema") or "DB default"
                expander_label = f"**{conn['name']}** (Schema: `{schema_display}`)"
                if is_active:
                    expander_label += " 🟢 Active"

                with st.expander(expander_label, expanded=True):
                    st.text_input(
                        "URL", value=conn["url"], disabled=True, key=f"url_{i}"
                    )

                    # --- Deletion Logic ---
                    if st.session_state.confirming_delete_index == i:
                        st.warning(f"Are you sure you want to delete **{conn['name']}**?")
                        c1, c2, _ = st.columns([1, 1, 2])
                        if c1.button("✅ Confirm Delete", key=f"confirm_delete_{i}"):
                            state.connections.pop(i)
                            state.save_and_reload_connections()
                            st.session_state.confirming_delete_index = None
                            st.rerun()
                        if c2.button("❌ Cancel", key=f"cancel_delete_{i}"):
                            st.session_state.confirming_delete_index = None
                            st.rerun()
                    else:
                        c1, c2, _ = st.columns([1, 1, 3])
                        if c1.button("Edit", key=f"edit_{i}"):
                            state.selected_connection = conn
                            st.rerun()
                        if c2.button("Delete", key=f"delete_{i}", type="primary"):
                            st.session_state.confirming_delete_index = i
                            st.rerun()

    # --- Column 2: Add/Edit Connection Form ---
    with col2:
        is_editing = state.selected_connection is not None
        form_title = "Edit Connection" if is_editing else "Add New Connection"
        st.subheader(form_title)

        with st.form(key="connection_form", clear_on_submit=False):
            default_conn = state.selected_connection or {}
            name = st.text_input(
                "Connection Name*",
                value=default_conn.get("name", ""),
                help="A unique, friendly name for this connection.",
            )
            url = st.text_input(
                "Database URL*",
                value=default_conn.get("url", ""),
                help="SQLAlchemy connection string. Use ${SECRET_NAME} for secrets.",
            )
            schema = st.text_input(
                "Schema",
                value=default_conn.get("schema", ""),
                help="The schema to use. Leave blank for default.",
            )
            tables = st.text_input(
                "Include Tables (Optional)",
                value=",".join(default_conn.get("tables", [])),
                help="Comma-separated list of tables. Leave blank for all.",
            )
            business_context = st.text_area(
                "Default Business Context (Optional)",
                value=default_conn.get("business_context", ""),
                height=150,
            )

            submitted = st.form_submit_button("Save & Analyze Connection")

            if submitted:
                if not all([name, url]):
                    st.error("Connection Name and URL are required.")
                else:
                    handle_connection_form_submission(
                        state,
                        name,
                        url,
                        schema,
                        tables,
                        business_context,
                        is_editing,
                        default_conn.get("name"),
                    )

        if is_editing:
            if st.button("Cancel Edit"):
                state.selected_connection = None
                st.rerun()


def render_chat_page():
    """Renders the main chat interface."""
    state = get_state()

    if not state.selected_connection:
        st.info("Please select a database connection from the sidebar to start chatting.")
        st.stop()

    if not state.services_initialized:
        initialize_chat_services(state)

    st.title("💬 IntelliQuery BI Chat")

    # Render the existing chat history
    for message in state.chat_history:
        chat_renderer.render_message(message, handle_regeneration)

    # Handle new user input
    if prompt := st.chat_input("Ask a question about your data..."):
        handle_user_prompt(state, prompt)


# -----------------------------------------------------------------------------
# Service Initialization and Handling
# -----------------------------------------------------------------------------


def initialize_chat_services(state: AppState):
    """
    Initializes all backend services (LLM, DB, Orchestrator) required for the
    chat page.
    """
    with st.spinner("Initializing services, please wait..."):
        llm_interface = llm_service.get_llm_interface(state)
        if not llm_interface:
            st.error("LLM interface could not be initialized. Check settings.")
            st.stop()

        try:
            resolved_url = connection_service.resolve_secrets_in_url(
                state.selected_connection["url"]
            )
            engine = create_engine(resolved_url)
            db_service = DatabaseService(
                engine=engine, cache_provider=FileSystemCacheProvider()
            )
            context_analyzer = DBContextAnalyzer(
                llm_interface=llm_interface, db_service=db_service
            )
        except Exception as e:
            st.error(f"Failed to connect to the database: {e}")
            st.stop()

        enriched_context = context_analyzer.build_context(
            business_context=state.business_context
        )

        orchestrator = BIOrchestrator(
            llm_interface=llm_interface,
            db_service=db_service,
        )

        state.db_service = db_service
        state.context_analyzer = context_analyzer
        state.bi_orchestrator = orchestrator
        state.enriched_context = enriched_context
        state.services_initialized = True


def handle_connection_form_submission(
    state, name, url, schema, tables, business_context, is_editing, original_name
):
    """
    Handles the logic for saving and analyzing a new or edited database connection.
    """
    llm_interface = llm_service.get_llm_interface(state)
    if not llm_interface:
        st.error("Could not initialize AI model. Check configurations.")
        return

    try:
        resolved_url = connection_service.resolve_secrets_in_url(url)
        engine = create_engine(resolved_url)
        with st.spinner("1/3 - Testing database connection..."):
            with engine.connect():
                pass

        with st.spinner("2/3 - Analyzing database and building context..."):
            db_service = DatabaseService(
                engine=engine,
                cache_provider=FileSystemCacheProvider(
                    cache_dir=Path(".cache/context_cache")
                ),
                schema=schema if schema else None,
            )
            context_analyzer = DBContextAnalyzer(
                llm_interface=llm_interface, db_service=db_service
            )
            context_analyzer.build_context(business_context=business_context)

        with st.spinner("3/3 - Saving connection..."):
            table_list = [t.strip() for t in tables.split(",") if t.strip()]
            new_conn = {
                "name": name,
                "url": url,
                "schema": schema,
                "tables": table_list,
                "business_context": business_context,
            }

            if is_editing:
                for i, c in enumerate(state.connections):
                    if c["name"] == original_name:
                        state.connections[i] = new_conn
                        break
            else:
                state.connections.append(new_conn)

            state.save_and_reload_connections()
            state.selected_connection = None

        st.success(f"Connection '{name}' saved and analyzed successfully!")
        st.rerun()

    except Exception as e:
        st.error(f"An error occurred: {e}")
        with st.expander("View Full Error Traceback"):
            st.exception(e)


# -----------------------------------------------------------------------------
# Chat and Agent Interaction
# -----------------------------------------------------------------------------


def handle_user_prompt(state: AppState, prompt: str):
    """
    Handles the logic for processing a user's chat input, running the agent,
    and displaying the results.
    """
    user_message = {"role": "user", "content": prompt, "timestamp": time.time()}
    state.chat_history.append(user_message)
    chat_renderer.render_message(user_message, handle_regeneration)

    conversation_history = chat_service.get_conversation_history(state.chat_history)

    with st.chat_message("assistant"):
        with st.status("Agent is thinking...", expanded=True) as status:
            status.write("Analyzing request and planning execution...")
            time.sleep(1)

            result = state.bi_orchestrator.run(
                question=prompt,
                context=state.enriched_context,
                chat_history=conversation_history,
            )

            assistant_response = process_agent_result(result, status)
            assistant_response["timestamp"] = time.time()

    chat_renderer.render_message(assistant_response, handle_regeneration)
    state.chat_history.append(assistant_response)

    chat_service.save_chat_history(
        state.current_chat_id,
        state.selected_connection["name"],
        state.chat_history,
    )


def process_agent_result(result: BIResult, status) -> Dict[str, Any]:
    """
    Processes the result from the BIOrchestrator and returns a message
    dictionary suitable for rendering.
    """
    if result.status == "clarification_needed":
        status.update(label="Agent needs more information.", state="complete")
        return {
            "role": "assistant",
            "content_type": "text",
            "content": result.final_answer,
        }
    elif result.status == "error":
        status.update(label="An error occurred.", state="error")
        return {
            "role": "assistant",
            "content_type": "error",
            "content": result.error_message,
        }
    elif result.status == "success":
        status.update(label="Request processed successfully!", state="complete")
        # If the successful result has no data or viz, treat it as a simple text response
        if result.dataframe is None and result.visualization is None:
            return {
                "role": "assistant",
                "content_type": "text",
                "content": result.final_answer,
            }
        
        # Otherwise, it's a full BI result
        return {
            "role": "assistant",
            "content_type": "bi_result",
            "data": {
                "final_answer": result.final_answer,
                "sql_query": result.sql_query,
                "reasoning": result.reasoning,
                "visualization_params": result.visualization_params,
            },
        }
    else: # Fallback for unknown status
        status.update(label="An unknown error occurred.", state="error")
        return {
            "role": "assistant",
            "content_type": "error",
            "content": "An unknown error occurred.",
        }


def handle_regeneration(message_data: Dict[str, Any]) -> Tuple[Optional[pd.DataFrame], Optional[Any]]:
    """
    Callback function to deterministically regenerate results (data + viz)
    from saved parameters in the chat history.
    Returns the dataframe and the figure object.
    """
    state = get_state()
    if not state.db_service:
        st.error("Database service not initialized.")
        return None, None

    sql_query = message_data.get("sql_query")
    vis_params = message_data.get("visualization_params")

    if not sql_query:
        st.warning("No SQL query found to regenerate results.")
        return None, None

    try:
        df = state.db_service.execute_for_dataframe(sql_query)
        fig = None

        if vis_params and not df.empty:
            tool_name = next(iter(vis_params))
            args_copy = vis_params[tool_name]["arguments"].copy()
            args_copy["data_frame"] = df  # Inject the fresh dataframe

            vis_func_name = tool_name.replace("_chart", "")
            
            if hasattr(px, vis_func_name):
                vis_func = getattr(px, vis_func_name)
                fig = vis_func(**args_copy)
                fig.update_layout(template="plotly_white")
            else:
                st.error(f"Visualization function '{vis_func_name}' not found in Plotly Express.")
        
        return df, fig

    except Exception as e:
        st.error(f"Failed to regenerate results: {e}")
        return None, None


# -----------------------------------------------------------------------------
# Main Application Logic
# -----------------------------------------------------------------------------


def main():
    """Main function to run the Streamlit application."""
    state = get_state()

    state.initialize_connections()
    if state.all_llm_providers is None:
        try:
            settings = load_settings("llm_providers.yaml")
            state.all_llm_providers = settings
            if not state.selected_llm_provider:
                state.selected_llm_provider = list(settings.llm_providers.keys())[0]
        except FileNotFoundError:
            st.error("Fatal: llm_providers.yaml not found.")
            st.stop()

    sidebar.build_sidebar()

    url_chat_id = st.query_params.get("chat_id")
    if url_chat_id and url_chat_id != state.current_chat_id:
        conn_name, history = chat_service.load_chat_history(url_chat_id)
        if conn_name and state.select_connection(conn_name):
            state.chat_history = history
            state.current_chat_id = url_chat_id
            state.set_page("chat")
            st.rerun()
        else:
            st.query_params.clear()

    if state.page == "home":
        render_home_page()
    elif state.page == "connection_manager":
        render_connection_manager_page()
    elif state.page == "chat":
        render_chat_page()
    else:
        st.error("Page not found!")


if __name__ == "__main__":
    main()
