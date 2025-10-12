import streamlit as st
from state import AppState
from services import connection_service, chat_service


def build_sidebar():
    """
    Builds the main sidebar for the application, making it consistent across all pages.
    This sidebar is now the central hub for connection and chat management.
    """
    with st.sidebar:
        st.header("IntelliQuery")
        st.markdown("Your AI Database Assistant")

        # Connection Selection
        st.subheader("Database Connection")
        connections = st.session_state.get(AppState.CONNECTIONS, [])
        connection_options = {conn["name"]: conn for conn in connections}

        current_conn_name = None
        if st.session_state.get(AppState.SELECTED_CONNECTION):
            current_conn_name = st.session_state[AppState.SELECTED_CONNECTION]["name"]

        selected_name = st.selectbox(
            "Active Connection",
            options=connection_options.keys(),
            index=(
                list(connection_options.keys()).index(current_conn_name)
                if current_conn_name in connection_options
                else None
            ),
            placeholder="Select a connection...",
            label_visibility="collapsed",
        )

        # If the user selects a different connection, update the state and rerun
        if selected_name and selected_name != current_conn_name:
            st.session_state[AppState.SELECTED_CONNECTION] = connection_options[
                selected_name
            ]
            # When connection changes, we need to reset dependent services
            st.session_state[AppState.SERVICES_INITIALIZED] = False
            st.rerun()

        if st.button("Manage Connections", use_container_width=True):
            st.switch_page("pages/connection_manager.py")

        st.divider()

        st.subheader("Chat History")
        if st.button("➕ New Chat", use_container_width=True):
            if not st.session_state.get(AppState.SELECTED_CONNECTION):
                st.warning("Please select a connection first.")
            else:
                st.session_state[AppState.CURRENT_CHAT_ID] = (
                    chat_service.get_new_chat_id()
                )
                st.session_state[AppState.CHAT_HISTORY] = []
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

                    # Find the full connection object from the name
                    connections = st.session_state.get(AppState.CONNECTIONS, [])
                    conn_to_load = next(
                        (c for c in connections if c["name"] == conn_name), None
                    )

                    if conn_to_load:
                        st.session_state[AppState.SELECTED_CONNECTION] = conn_to_load
                        st.session_state[AppState.CURRENT_CHAT_ID] = session["id"]
                        st.session_state[AppState.CHAT_HISTORY] = history
                        # We need to re-initialize services with the new connection
                        st.session_state[AppState.SERVICES_INITIALIZED] = False
                        st.rerun()
                    else:
                        st.error(
                            f"Connection '{conn_name}' for this chat could not be found."
                        )

        # We can detect the current page to decide whether to show these
        if st.session_state.get("active_page") == "chat":
            st.divider()
            st.subheader("Session Controls")

            agent_mode = st.radio(
                "Agent Mode", ["execute", "plan"], index=0, horizontal=True
            )
            workflow_mode = st.radio(
                "Workflow", ["simple", "reflection"], index=0, horizontal=True
            )

            with st.expander("**Current Chat's Business Context**", expanded=False):
                st.info("Define business rules for this session only.", icon="ℹ️")
                if AppState.BUSINESS_CONTEXT not in st.session_state:
                    default_context = ""
                    if st.session_state.get(AppState.SELECTED_CONNECTION):
                        default_context = st.session_state[
                            AppState.SELECTED_CONNECTION
                        ].get("business_context", "")
                    st.session_state[AppState.BUSINESS_CONTEXT] = default_context

                st.session_state[AppState.BUSINESS_CONTEXT] = st.text_area(
                    "Context",
                    value=st.session_state[AppState.BUSINESS_CONTEXT],
                    height=200,
                    label_visibility="collapsed",
                )

            return agent_mode == "execute", workflow_mode

    # Return default values if not on the chat page
    return True, "simple"
