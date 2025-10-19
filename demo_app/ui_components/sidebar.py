"""
UI component for the main sidebar of the Streamlit application.

This module is responsible for building the primary navigation and control center
of the application. The sidebar allows users to:
- Navigate between the main pages (Home, Manage Connections).
- Select the active database connection.
- Start new chat sessions.
- Load past chat sessions.
- Control session-specific settings like the AI model, workflow, and execution mode.

All actions taken in the sidebar modify the central `AppState` object, making it
the single source of truth for the application's state.
"""

import streamlit as st
from state import AppState, get_state
from services import chat_service


def build_sidebar():
    """
    Builds the main sidebar, which acts as the primary navigation and
    control panel for the application.
    """
    state = get_state()

    with st.sidebar:
        st.header("IntelliQuery")
        st.markdown("Your AI Database & BI Assistant")

        # --- Page Navigation ---
        # These buttons update the `page` attribute in the app state, which the
        # main app file uses for routing.
        if st.button("🏠 Home", use_container_width=True):
            state.set_page("home")
            st.rerun()
        if st.button("🗄️ Manage Connections", use_container_width=True):
            state.set_page("connection_manager")
            st.rerun()

        st.divider()

        # --- Database Connection Selection ---
        st.subheader("Database Connection")
        connections = state.connections
        connection_options = {conn["name"]: conn for conn in connections}

        # --- Connection Change Confirmation Logic ---
        # This prevents accidental loss of an active chat session.
        if "pending_connection_change" not in st.session_state:
            st.session_state.pending_connection_change = None

        if st.session_state.pending_connection_change:
            st.warning(
                "Changing connections will start a new chat session. Your current chat will be lost. Proceed?"
            )
            c1, c2 = st.columns(2)
            if c1.button("✅ Proceed", use_container_width=True):
                new_conn_name = st.session_state.pending_connection_change
                st.session_state.pending_connection_change = None
                if state.select_connection(new_conn_name):
                    state.set_page("chat")
                    st.rerun()
            if c2.button("❌ Cancel", use_container_width=True):
                st.session_state.pending_connection_change = None
                st.rerun()

        current_conn_name = (
            state.selected_connection["name"] if state.selected_connection else None
        )
        selected_name = st.selectbox(
            "Active Connection",
            options=list(connection_options.keys()),
            index=(
                list(connection_options.keys()).index(current_conn_name)
                if current_conn_name in connection_options
                else None
            ),
            placeholder="Select a connection...",
            label_visibility="collapsed",
        )

        if selected_name and selected_name != current_conn_name:
            # If a chat is already active, ask for confirmation before switching.
            # Otherwise, switch the connection directly.
            if state.chat_history:
                st.session_state.pending_connection_change = selected_name
                st.rerun()
            else:
                if state.select_connection(selected_name):
                    state.set_page("chat")
                    st.rerun()

        st.divider()

        # --- Chat History Management ---
        st.subheader("Chat History")
        if st.button("➕ New Chat", use_container_width=True):
            if not state.selected_connection:
                st.warning("Please select a connection first.")
            else:
                state.start_new_chat()
                state.set_page("chat")
                st.rerun()

        with st.expander("Load Past Chat"):
            past_sessions = chat_service.list_chat_sessions()
            if not past_sessions:
                st.caption("No past chats found.")
            for session in past_sessions:
                if st.button(
                    session["name"], key=session["id"], use_container_width=True
                ):
                    conn_name, history = chat_service.load_chat_history(session["id"])
                    # When loading a chat, we also need to switch to its associated connection.
                    if state.select_connection(conn_name):
                        state.chat_history = history
                        state.current_chat_id = session["id"]
                        state.set_page("chat")
                        st.rerun()
                    else:
                        st.error(
                            f"Connection '{conn_name}' for this chat could not be found."
                        )

            # --- Business Context Override ---
            with st.expander("**Current Chat's Business Context**", expanded=False):
                st.info(
                    "Define business rules, acronyms, or jargon for this session only.",
                    icon="ℹ️",
                )
                default_context = (
                    state.selected_connection.get("business_context", "")
                    if state.selected_connection
                    else ""
                )
                state.business_context = st.text_area(
                    "Context",
                    value=state.business_context or default_context,
                    height=200,
                    label_visibility="collapsed",
                )

