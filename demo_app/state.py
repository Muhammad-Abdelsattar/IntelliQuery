import streamlit as st
from typing import List, Dict, Any, Optional
from services import connection_service, chat_service


class AppState:
    """A class to manage the application's session state in a structured way."""

    def __init__(self):
        # Page navigation
        self.page: str = "home"

        # Connection management
        self.connections: List[Dict[str, Any]] = []
        self.selected_connection: Optional[Dict[str, Any]] = None

        # Chat management
        self.chat_history: List[Dict[str, Any]] = []
        self.current_chat_id: Optional[str] = None
        self.business_context: str = ""

        # Agent & Core Services (placeholders, to be initialized)
        self.db_service: Optional[Any] = None
        self.context_analyzer: Optional[Any] = None
        self.query_orchestrator: Optional[Any] = None
        self.enriched_context: Optional[Any] = None
        self.services_initialized: bool = False

        # LLM Management
        self.all_llm_providers: Optional[Dict] = None
        self.selected_llm_provider: Optional[str] = None

        # UI control
        self.active_page: str = "home"
        self.workflow_mode: str = "simple"
        self.agent_mode: str = "execute"

    def initialize_connections(self):
        """Loads connections from the service layer into the state."""
        if not self.connections:
            self.connections = connection_service.load_connections()

    def set_page(self, page_name: str):
        """Sets the current page and handles chat session loading if needed."""
        self.page = page_name
        self.active_page = page_name

        # If navigating to a new chat, ensure a chat ID is set
        if page_name == "chat" and not self.current_chat_id:
            self.start_new_chat()

    def start_new_chat(self):
        """Initializes a new chat session."""
        self.current_chat_id = chat_service.get_new_chat_id()
        self.chat_history = []
        # Reset services so they re-initialize for the potentially new connection context
        self.services_initialized = False
        # Update URL to reflect the new chat
        st.query_params["chat_id"] = self.current_chat_id

    def select_connection(self, connection_name: str):
        """
        Selects a connection by name, resets dependent state, and returns True
        if the connection was found and selected.
        """
        conn_to_select = next(
            (c for c in self.connections if c["name"] == connection_name), None
        )
        if conn_to_select:
            self.selected_connection = conn_to_select
            # Reset chat and services when connection changes
            self.start_new_chat()
            return True
        return False

    def save_and_reload_connections(self):
        """Saves the current list of connections and reloads them."""
        connection_service.save_connections(self.connections)
        self.connections = connection_service.load_connections()


# The key to our new state management: a single function to get the state
_STATE_KEY = "app_state"


def get_state() -> AppState:
    """
    Retrieves the AppState instance from the session state, creating it if it
    doesn't exist.
    """
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = AppState()
    return st.session_state[_STATE_KEY]