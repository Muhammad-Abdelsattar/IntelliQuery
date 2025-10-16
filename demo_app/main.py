import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import time
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, Any

from state import get_state, AppState
from services import connection_service, chat_service, llm_service
from ui_components import sidebar, chat_renderer

from intelliquery import (
    QueryOrchestrator,
    DatabaseService,
    DBContextAnalyzer,
    SQLPlan,
    SQLResult,
    FileSystemCacheProvider,
)
from nexus_llm import load_settings

load_dotenv()


st.set_page_config(
    page_title="IntelliQuery",
    page_icon="🧠",
    layout="wide",
)


def render_home_page():
    """Renders the main welcome page."""
    state = get_state()
    st.title("Welcome to IntelliQuery 🧠")
    st.markdown(
        """
        **Your intelligent assistant for talking to your databases.**

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

    # Initialize confirmation state
    if "confirming_delete_index" not in st.session_state:
        st.session_state.confirming_delete_index = None

    col1, col2 = st.columns([1, 1.5])

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

                    # Deletion confirmation logic
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


def handle_connection_form_submission(
    state, name, url, schema, tables, business_context, is_editing, original_name
):
    """Logic to handle the submission of the connection form."""
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


def render_chat_page():
    """Renders the main chat interface."""
    state = get_state()

    if not state.selected_connection:
        st.info("Please select a database connection from the sidebar to start chatting.")
        st.stop()

    if not state.services_initialized:
        initialize_chat_services(state)

    st.title("💬 IntelliQuery Chat")

    for message in state.chat_history:
        chat_renderer.render_message(message, run_query_and_display_results)

    if prompt := st.chat_input("Ask a question about your data..."):
        handle_user_prompt(state, prompt)


def run_query_and_display_results(sql_query: str):
    """Executes a SQL query and displays the results or an error."""
    state = get_state()
    if not state.db_service:
        st.error("Database service not initialized.")
        return

    with st.spinner("Executing query..."):
        try:
            df = state.db_service.execute_for_dataframe(sql_query)
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to execute query: {e}")


def initialize_chat_services(state: AppState):
    """Initializes all backend services required for the chat page."""
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
        orchestrator = QueryOrchestrator(
            llm_interface=llm_interface,
            db_service=db_service,
            workflow_type=state.workflow_mode,
        )

        state.db_service = db_service
        state.context_analyzer = context_analyzer
        state.query_orchestrator = orchestrator
        state.enriched_context = enriched_context
        state.services_initialized = True


def handle_user_prompt(state: AppState, prompt: str):
    """Handles the logic for processing a user's chat input."""
    user_message = {"role": "user", "content": prompt, "timestamp": time.time()}
    state.chat_history.append(user_message)
    chat_renderer.render_message(user_message, run_query_and_display_results)

    conversation_history = chat_service.get_conversation_history(state.chat_history)

    with st.chat_message("assistant"):
        with st.status("Agent is thinking...", expanded=True) as status:
            status.write("Generating SQL plan...")
            time.sleep(1)  # Simulate thought

            result = state.query_orchestrator.run(
                question=prompt,
                context=state.enriched_context,
                chat_history=conversation_history,
                auto_execute=state.agent_mode == "execute",
            )

            assistant_response = process_agent_result(result, status)
            assistant_response["timestamp"] = time.time()

    chat_renderer.render_message(assistant_response, run_query_and_display_results)
    state.chat_history.append(assistant_response)

    chat_service.save_chat_history(
        state.current_chat_id,
        state.selected_connection["name"],
        state.chat_history,
    )


def process_agent_result(result, status) -> Dict[str, Any]:
    """Processes the result from the QueryOrchestrator and returns a message dict."""
    if result.status == "success":
        if isinstance(result, SQLPlan):
            status.update(label="Plan generated successfully!", state="complete")
            return {
                "role": "assistant",
                "content_type": "plan",
                "data": {
                    "sql_query": result.sql_query,
                    "reasoning": result.reasoning,
                    "is_validated": result.is_validated,
                },
            }
        elif isinstance(result, SQLResult):
            status.update(label="Query executed successfully!", state="complete")
            return {
                "role": "assistant",
                "content_type": "result",
                "data": {
                    "dataframe": result.dataframe if result.dataframe is not None else pd.DataFrame(),
                    "sql_query": result.sql_query,
                    "reasoning": result.reasoning,
                },
            }
    elif result.status == "clarification_needed":
        status.update(label="Agent needs more information.", state="complete")
        return {
            "role": "assistant",
            "content_type": "text",
            "content": result.clarification_question,
        }
    else:  # Error
        status.update(label="An error occurred.", state="error")
        return {
            "role": "assistant",
            "content_type": "error",
            "content": result.error_message,
        }


def main():
    """Main function to run the Streamlit application."""
    state = get_state()

    # Initialize connections and LLM providers once
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

    # The sidebar is the main navigation hub
    sidebar.build_sidebar()

    # URL Sync Logic - to allow sharing and bookmarking chats
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

    # Page routing
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