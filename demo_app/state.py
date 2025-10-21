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

        # IntelliQuery System (replaces individual services)
        self.intelliquery_system: Optional[Any] = None
        self.services_initialized: bool = False

        # LLM Management
        self.all_llm_providers: Optional[Dict] = None
        self.selected_llm_provider: Optional[str] = None

        # UI control
        self.active_page: str = "home"
        self.workflow_mode: str = "simple"

    def initialize_connections(self):
        """Loads connections from the service layer into the state."""
        if not self.connections:
            self.connections = connection_service.load_connections()

    def set_page(self, page_name: str):
        """Sets the current page and handles chat session loading if needed."""
        self.page = page_name
        self.active_page = page_name

        if page_name == "chat" and not self.current_chat_id:
            self.start_new_chat()

    def start_new_chat(self):
        """Initializes a new chat session."""
        self.current_chat_id = chat_service.get_new_chat_id()
        self.chat_history = []
        self.services_initialized = False
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
            self.start_new_chat()
            return True
        return False

    def save_and_reload_connections(self):
        """Saves the current list of connections and reloads them."""
        connection_service.save_connections(self.connections)
        self.connections = connection_service.load_connections()


_STATE_KEY = "app_state"


def get_state() -> AppState:
    """
    Retrieves the AppState instance from the session state, creating it if it
    doesn't exist.
    """
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = AppState()
    return st.session_state[_STATE_KEY]
