import streamlit as st
import time
from sqlalchemy import create_engine
from dotenv import load_dotenv
from typing import Dict, Any

from state import get_state, AppState
from services import connection_service, chat_service
from ui_components import sidebar, chat_renderer

from intelliquery import create_intelliquery_system, BIResult
from nexus_llm import load_settings

load_dotenv()

st.set_page_config(page_title="IntelliQuery", page_icon="🧠", layout="wide")


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
    st.markdown("Manage your database connections here.")

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
                expander_label = f"**{conn['name']}** (Schema: `{conn.get('schema') or 'DB default'}`)"
                if is_active:
                    expander_label += " 🟢 Active"

                with st.expander(expander_label, expanded=True):
                    st.text_input(
                        "URL", value=conn["url"], disabled=True, key=f"url_{i}"
                    )
                    if st.session_state.confirming_delete_index == i:
                        st.warning(
                            f"Are you sure you want to delete **{conn['name']}**?"
                        )
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
            name = st.text_input("Connection Name*", value=default_conn.get("name", ""))
            url = st.text_input("Database URL*", value=default_conn.get("url", ""))
            schema = st.text_input("Schema", value=default_conn.get("schema", ""))
            tables = st.text_input(
                "Include Tables (Optional)",
                value=",".join(default_conn.get("tables", [])),
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
        if is_editing and st.button("Cancel Edit"):
            state.selected_connection = None
            st.rerun()


def handle_connection_form_submission(
    state, name, url, schema, tables, business_context, is_editing, original_name
):
    try:
        engine = create_engine(connection_service.resolve_secrets_in_url(url))
        with st.spinner("1/3 - Testing database connection..."):
            with engine.connect():
                pass
        with st.spinner("2/3 - Analyzing database and building context..."):
            temp_system = create_intelliquery_system(
                database_engine=engine,
                llm_settings=state.all_llm_providers.model_dump(),
            )
            temp_system._get_or_build_context(business_context=business_context)
        with st.spinner("3/3 - Saving connection..."):
            new_conn = {
                "name": name,
                "url": url,
                "schema": schema,
                "tables": [t.strip() for t in tables.split(",") if t.strip()],
                "business_context": business_context,
            }
            if is_editing:
                state.connections = [
                    new_conn if c["name"] == original_name else c
                    for c in state.connections
                ]
            else:
                state.connections.append(new_conn)
            state.save_and_reload_connections()
            state.selected_connection = None
            st.success(f"Connection '{name}' saved successfully!")
            st.rerun()
    except Exception as e:
        st.error(f"An error occurred: {e}")
        with st.expander("View Full Error Traceback"):
            st.exception(e)


def render_chat_page():
    """Renders the main chat interface."""
    state = get_state()
    if not state.selected_connection:
        st.info(
            "Please select a database connection from the sidebar to start chatting."
        )
        st.stop()
    if not state.services_initialized:
        initialize_chat_services(state)
    st.title("💬 IntelliQuery Chat")
    for message in state.chat_history:
        chat_renderer.render_message(message, regenerate_bi_output)
    if prompt := st.chat_input("Ask a question about your data..."):
        handle_user_prompt(state, prompt)


def initialize_chat_services(state: AppState):
    """Initializes the IntelliQuery system for the chat page."""
    with st.spinner("Initializing AI services, please wait..."):
        try:
            resolved_url = connection_service.resolve_secrets_in_url(
                state.selected_connection["url"]
            )
            engine = create_engine(resolved_url)
            state.intelliquery_system = create_intelliquery_system(
                database_engine=engine,
                llm_settings=state.all_llm_providers.model_dump(),
                sql_workflow_type=state.workflow_mode,
                default_agent_llm_key=state.selected_llm_provider,
            )
            state.services_initialized = True
        except Exception as e:
            st.error(f"Failed to initialize IntelliQuery system: {e}")
            with st.expander("View Error"):
                st.exception(e)
            st.stop()


def regenerate_bi_output(message_timestamp: float, sql_query: str, vis_params: Dict):
    """Callback to re-run the BI logic and store results in session_state."""
    state = get_state()
    system = state.intelliquery_system
    if not (system and system.db_service):
        return

    df = system.db_service.execute_for_dataframe(sql_query)
    fig = None
    if vis_params and system.vis_provider:
        try:
            tool_name, tool_args = next(iter(vis_params.items()))
            fig = system.vis_provider.create_chart(
                tool_name, df, **tool_args.get("arguments", {})
            )
        except Exception as e:
            print(f"Error regenerating visualization: {e}")

    if "refreshed_results" not in st.session_state:
        st.session_state.refreshed_results = {}
    st.session_state.refreshed_results[message_timestamp] = {
        "dataframe": df,
        "visualization": fig,
    }
    # CRITICAL FIX: Do NOT call st.rerun() here. Modifying session_state is enough.
    # st.rerun() # This line is removed.


def handle_user_prompt(state: AppState, prompt: str):
    """Handles the logic for processing a user's chat input."""
    user_message = {"role": "user", "content": prompt, "timestamp": time.time()}
    state.chat_history.append(user_message)
    chat_renderer.render_message(user_message, regenerate_bi_output)

    with st.chat_message("assistant"):
        with st.status("Agent is thinking...", expanded=True) as status:
            result = state.intelliquery_system.ask(
                question=prompt,
                chat_history=chat_service.get_conversation_history(state.chat_history),
                business_context=state.business_context,
                llm_key=state.selected_llm_provider,
            )
            response_for_storage = process_agent_result_for_storage(result, status)
            response_for_storage["timestamp"] = time.time()
            response_for_display = response_for_storage.copy()
            if result.status == "success":
                response_for_display["data"]["dataframe"] = result.dataframe
                response_for_display["data"]["visualization"] = result.visualization

    chat_renderer.render_message(response_for_display, regenerate_bi_output)
    state.chat_history.append(response_for_storage)
    chat_service.save_chat_history(
        state.current_chat_id, state.selected_connection["name"], state.chat_history
    )


def process_agent_result_for_storage(result: BIResult, status) -> Dict[str, Any]:
    """Returns a message dict suitable for saving (no live objects)."""
    if result.status == "success":
        status.update(label="Agent answered successfully!", state="complete")
        return {
            "role": "assistant",
            "content_type": "bi_result",
            "data": {
                "answer": result.final_answer,
                "sql_query": result.sql_query,
                "reasoning": result.reasoning,
                "visualization_params": result.visualization_params,
            },
        }
    elif result.status == "clarification_needed":
        status.update(label="Agent needs more information.", state="complete")
        return {
            "role": "assistant",
            "content_type": "text",
            "content": result.final_answer,
        }
    else:
        status.update(label="An error occurred.", state="error")
        return {
            "role": "assistant",
            "content_type": "error",
            "content": result.error_message,
        }


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
            if "refreshed_results" in st.session_state:
                del st.session_state.refreshed_results
            st.rerun()
        else:
            st.query_params.clear()

    page_map = {
        "home": render_home_page,
        "connection_manager": render_connection_manager_page,
        "chat": render_chat_page,
    }
    page_map.get(state.page, lambda: st.error("Page not found!"))()


if __name__ == "__main__":
    main()
