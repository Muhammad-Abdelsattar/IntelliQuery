import streamlit as st
from state import AppState, get_state
from services import chat_service


def build_sidebar():
    """
    Builds the main sidebar, now driving the state of the single-page app.
    """
    state = get_state()

    with st.sidebar:
        st.header("IntelliQuery")
        st.markdown("Your AI Database Assistant")

        # Page Navigation
        # Use buttons to set the page state, which the main app will use to render
        if st.button("🏠 Home", use_container_width=True):
            state.set_page("home")
            st.rerun()
        if st.button("🗄️ Manage Connections", use_container_width=True):
            state.set_page("connection_manager")
            st.rerun()

        st.divider()

        # Connection Selection
        st.subheader("Database Connection")
        connections = state.connections
        connection_options = {conn["name"]: conn for conn in connections}

        # Initialize confirmation state
        if "pending_connection_change" not in st.session_state:
            st.session_state.pending_connection_change = None

        # Handle pending connection change confirmation
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
            # If chat is active, ask for confirmation. Otherwise, switch directly.
            if state.chat_history:
                st.session_state.pending_connection_change = selected_name
                st.rerun()
            else:
                if state.select_connection(selected_name):
                    state.set_page("chat")
                    st.rerun()

        st.divider()

        # Chat History Management
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
                    if state.select_connection(conn_name):
                        state.chat_history = history
                        state.current_chat_id = session["id"]
                        state.set_page("chat")
                        st.rerun()
                    else:
                        st.error(
                            f"Connection '{conn_name}' for this chat could not be found."
                        )

        # Session controls are now part of the main sidebar, shown only on the chat page
        if state.page == "chat":
            st.divider()
            st.subheader("Session Controls")

            st.markdown("**AI Model**")
            if state.all_llm_providers:
                provider_keys = list(state.all_llm_providers.llm_providers.keys())
                current_provider = state.selected_llm_provider or (provider_keys[0] if provider_keys else None)

                selected_provider_key = st.selectbox(
                    "Select the AI model for this session:",
                    options=provider_keys,
                    index=(
                        provider_keys.index(current_provider)
                        if current_provider in provider_keys
                        else 0
                    ),
                    label_visibility="collapsed",
                )

                if selected_provider_key != state.selected_llm_provider:
                    state.selected_llm_provider = selected_provider_key
                    state.services_initialized = False
                    st.rerun()

            state.workflow_mode = st.radio(
                "Workflow", ["simple", "reflection"], index=0, horizontal=True
            )

            # Map internal agent mode values to user-friendly labels
            agent_mode_options = {"Automatic": "execute", "Manual Approval": "plan"}
            # Get current index based on state
            current_agent_mode_label = [k for k, v in agent_mode_options.items() if v == state.agent_mode][0]
            available_labels = list(agent_mode_options.keys())

            selected_label = st.radio(
                "Execution Mode",
                options=available_labels,
                index=available_labels.index(current_agent_mode_label),
                horizontal=True,
                help="**Automatic**: The AI will run queries instantly. **Manual Approval**: The AI will generate a query and wait for you to run it.",
            )
            # Update state with the internal value
            state.agent_mode = agent_mode_options[selected_label]

            with st.expander("**Current Chat's Business Context**", expanded=False):
                st.info("Define business rules for this session only.", icon="ℹ️")
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