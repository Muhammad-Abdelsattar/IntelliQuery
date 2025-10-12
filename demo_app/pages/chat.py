import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import time

from state import AppState
from services import connection_service, chat_service
from ui_components import sidebar, chat_renderer

from intelliquery import (
    QueryOrchestrator,
    DatabaseService,
    DBContextAnalyzer,
    SQLPlan,
    SQLResult,
)
from intelliquery import FileSystemCacheProvider
from nexus_llm import LLMInterface, load_settings

st.set_page_config(page_title="IntelliQuery Chat", page_icon="💬", layout="wide")

st.session_state["active_page"] = "chat"


def sync_url_and_state():
    url_id = st.query_params.get("chat_id")
    state_id = st.session_state.get(AppState.CURRENT_CHAT_ID)

    if state_id and state_id != url_id:
        st.query_params["chat_id"] = state_id

    elif not state_id and url_id:
        conn_name, history = chat_service.load_chat_history(url_id)
        if conn_name:
            connections = st.session_state.get(AppState.CONNECTIONS, [])
            conn_to_load = next(
                (c for c in connections if c["name"] == conn_name), None
            )
            if conn_to_load:
                st.session_state[AppState.SELECTED_CONNECTION] = conn_to_load
                st.session_state[AppState.CURRENT_CHAT_ID] = url_id
                st.session_state[AppState.CHAT_HISTORY] = history
                # Ensure services are re-initialized
                st.session_state[AppState.SERVICES_INITIALIZED] = False
            else:
                st.error(
                    f"The connection '{conn_name}' associated with this chat was not found."
                )
                # Clear the bad chat_id from the URL
                st.query_params.clear()
        else:
            # The chat file is old or corrupted, clear the bad chat_id
            st.query_params.clear()


def initialize_services(connection_config: dict):
    """
    Initializes all backend services (LLM, DB, Orchestrator) and caches them
    in the session state. This function is designed to run only once per session
    or when the connection changes.
    """
    st.session_state[AppState.SERVICES_INITIALIZED] = True

    with st.spinner("Initializing services, please wait..."):
        if "GOOGLE_API_KEY" not in st.secrets:
            st.error("GOOGLE_API_KEY not found in Streamlit secrets.")
            st.stop()

        llm_settings_dict = {
            "llm_providers": {
                "google_gemini": {
                    "type": "google",
                    "params": {
                        "model": "gemini-2.5-flash",
                        "google_api_key": st.secrets["GOOGLE_API_KEY"],
                        "temperature": 0.1,
                    },
                }
            }
        }
        settings = load_settings(llm_settings_dict)
        llm_interface = LLMInterface(settings=settings, provider_key="google_gemini")

        try:
            resolved_url = connection_service.resolve_secrets_in_url(
                connection_config["url"]
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

        # Build/Load Enriched Context
        # This will use caching and will be fast on subsequent runs
        business_context = st.session_state.get(
            AppState.BUSINESS_CONTEXT, connection_config.get("business_context", "")
        )
        enriched_context = context_analyzer.build_context(
            business_context=business_context
        )

        # Initialize the Query Orchestrator
        workflow_type = st.session_state.get(
            "workflow_mode", "simple"
        )  # Get from sidebar state
        orchestrator = QueryOrchestrator(
            llm_interface=llm_interface,
            db_service=db_service,
            workflow_type=workflow_type,
        )

        # Store all initialized services in session state
        st.session_state[AppState.DB_SERVICE] = db_service
        st.session_state[AppState.CONTEXT_ANALYZER] = context_analyzer
        st.session_state[AppState.QUERY_ORCHESTRATOR] = orchestrator
        st.session_state[AppState.ENRICHED_CONTEXT] = enriched_context


# Main App Logic
if AppState.CONNECTIONS not in st.session_state:
    st.session_state[AppState.CONNECTIONS] = connection_service.load_connections()

# This is a key change: call sidebar BEFORE sync, but get returns AFTER sync
# This allows the sidebar to set the state first
sidebar_returns = {}

sync_url_and_state()

auto_execute, workflow_mode = sidebar.build_sidebar()
st.session_state["workflow_mode"] = workflow_mode

if not st.session_state.get(AppState.SELECTED_CONNECTION):
    st.info("Please select a database connection from the sidebar to start chatting.")
    st.stop()

# Initialize services if they haven't been for this session
if not st.session_state.get(AppState.SERVICES_INITIALIZED, False):
    initialize_services(st.session_state[AppState.SELECTED_CONNECTION])

# Set up or load chat session
if AppState.CURRENT_CHAT_ID not in st.session_state:
    new_id = chat_service.get_new_chat_id()
    st.session_state[AppState.CURRENT_CHAT_ID] = new_id
    st.query_params["chat_id"] = new_id  # Set URL for new chat

if AppState.CHAT_HISTORY not in st.session_state:
    st.session_state[AppState.CHAT_HISTORY] = []

if not st.session_state.get(AppState.SELECTED_CONNECTION):
    st.info("Please select a database connection from the sidebar to start chatting.")
    st.stop()

# Initialize services if they haven't been for this session
if not st.session_state.get(AppState.SERVICES_INITIALIZED, False):
    initialize_services(st.session_state[AppState.SELECTED_CONNECTION])

# Set up or load chat session
if AppState.CURRENT_CHAT_ID not in st.session_state:
    new_id = chat_service.get_new_chat_id()
    st.session_state[AppState.CURRENT_CHAT_ID] = new_id
    # After creating a new chat, sync to update the URL
    sync_url_and_state()
if AppState.CHAT_HISTORY not in st.session_state:
    st.session_state[AppState.CHAT_HISTORY] = []

st.title("💬 IntelliQuery Chat")

# Display existing chat messages
for message in st.session_state[AppState.CHAT_HISTORY]:
    chat_renderer.render_message(message)

# Handle user input
if prompt := st.chat_input("Ask a question about your data..."):
    # Add user message to history and display it
    user_message = {"role": "user", "content": prompt}
    st.session_state[AppState.CHAT_HISTORY].append(user_message)
    chat_renderer.render_message(user_message)

    # Get the latest conversational history for the agent
    # We only need the (user, ai_response) pairs for the LLM context
    conversation_history = []
    history = st.session_state[AppState.CHAT_HISTORY]

    # Iterate up to the second-to-last message to form pairs
    for i in range(len(history) - 1):
        current_msg = history[i]
        next_msg = history[i + 1]

        # We are looking for a (user, assistant) pair
        if current_msg.get("role") == "user" and next_msg.get("role") == "assistant":
            user_question = current_msg.get("content", "")
            ai_answer = ""  # Default answer

            # Intelligently extract the AI's response string based on its type
            content_type = next_msg.get("content_type", "text")

            if content_type in ["text", "error"]:
                ai_answer = next_msg.get("content", "")
            elif content_type == "result":
                # For results, the SQL query is the most useful context for follow-ups
                ai_answer = next_msg.get("data", {}).get("sql_query", "")

            # Only add to history if we have a valid, non-empty pair
            if user_question and ai_answer:
                conversation_history.append((user_question, ai_answer))

    # Get the initialized orchestrator and context
    orchestrator = st.session_state[AppState.QUERY_ORCHESTRATOR]
    enriched_context = st.session_state[AppState.ENRICHED_CONTEXT]

    assistant_response = {}
    with st.chat_message("assistant"):
        with st.status("Agent is thinking...", expanded=True) as status:
            status.write("Generating SQL plan...")
            time.sleep(1)

            result = orchestrator.run(
                question=prompt,
                context=enriched_context,
                chat_history=conversation_history,
                auto_execute=auto_execute,
            )

            if result.status == "success":
                if isinstance(result, SQLPlan):
                    status.update(
                        label="Plan generated successfully!", state="complete"
                    )
                    assistant_response = {
                        "role": "assistant",
                        "content_type": "plan",  # New, specific content type
                        "data": {
                            "sql_query": result.sql_query,
                            "reasoning": result.reasoning,
                            "is_validated": result.is_validated,
                        },
                    }
                elif isinstance(result, SQLResult):
                    status.update(
                        label="Query executed successfully!", state="complete"
                    )
                    assistant_response = {
                        "role": "assistant",
                        "content_type": "result",
                        "data": {
                            "dataframe": (
                                result.dataframe
                                if result.dataframe is not None
                                else pd.DataFrame()
                            ),
                            "sql_query": result.sql_query,
                            "reasoning": result.reasoning,
                        },
                    }

            elif result.status == "clarification_needed":
                status.update(label="Agent needs more information.", state="complete")
                assistant_response = {
                    "role": "assistant",
                    "content_type": "text",
                    "content": result.clarification_question,
                }
            else:  # Error
                status.update(label="An error occurred.", state="error")
                assistant_response = {
                    "role": "assistant",
                    "content_type": "error",
                    "content": result.error_message,
                }

    # Display the final response
    chat_renderer.render_message(assistant_response)
    st.session_state[AppState.CHAT_HISTORY].append(assistant_response)

    # Save the history after every turn
    chat_service.save_chat_history(
        st.session_state[AppState.CURRENT_CHAT_ID],
        st.session_state[AppState.SELECTED_CONNECTION]["name"],
        st.session_state[AppState.CHAT_HISTORY],
    )
