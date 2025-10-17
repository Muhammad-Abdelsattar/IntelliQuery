"""
Manages the Streamlit session state for the IntelliQuery demo application.

This file defines the `AppState` class, which centralizes all the application's
session-specific data. Using a single, structured class for state management
prevents the pollution of the Streamlit session state with numerous individual
keys and makes the state easier to debug and maintain.

The `get_state()` function is the designated accessor for the `AppState` instance,
ensuring a singleton-like pattern within a single user session.
"""

import streamlit as st
from typing import List, Dict, Any, Optional
from services import connection_service, chat_service


class AppState:
    """
    A class to manage the application's session state in a structured way.

    This object holds all the data that needs to persist across reruns of the
    Streamlit application for a single user session. It includes UI state,
    connection details, chat history, and initialized backend services.
    """

    def __init__(self):
        # --- Page Navigation ---
        # The current page being displayed (e.g., "home", "chat", "connection_manager")
        self.page: str = "home"

        # --- Connection Management ---
        # The list of all configured database connections
        self.connections: List[Dict[str, Any]] = []
        # The currently active database connection
        self.selected_connection: Optional[Dict[str, Any]] = None

        # --- Chat Management ---
        # The list of messages in the current chat session
        self.chat_history: List[Dict[str, Any]] = []
        # The unique identifier for the current chat session
        self.current_chat_id: Optional[str] = None
        # Business context specific to the current chat session
        self.business_context: str = ""

        # --- Agent & Core Services ---
        # These are placeholders for the heavy services that are initialized on demand
        self.db_service: Optional[Any] = None
        self.context_analyzer: Optional[Any] = None
        self.query_orchestrator: Optional[Any] = None
        self.enriched_context: Optional[Any] = None
        # A flag to indicate if the services have been initialized for the current connection
        self.services_initialized: bool = False

        # --- LLM Management ---
        # The full configuration for all available LLM providers
        self.all_llm_providers: Optional[Dict] = None
        # The key of the currently selected LLM provider for the session
        self.selected_llm_provider: Optional[str] = None

        # --- UI Control ---
        # The mode of the agent ("execute" or "plan")
        self.agent_mode: str = "execute"
        # The workflow to use for the agent ("simple" or "reflection")
        self.workflow_mode: str = "simple"

    def initialize_connections(self):
        """Loads connections from the persistent storage into the state."""
        if not self.connections:
            self.connections = connection_service.load_connections()

    def set_page(self, page_name: str):
        """Sets the current page and ensures a chat session is started if needed."""
        self.page = page_name

        # If the user navigates to the chat page, ensure there is an active chat session.
        if page_name == "chat" and not self.current_chat_id:
            self.start_new_chat()

    def start_new_chat(self):
        """
        Initializes a new chat session by generating a new ID, clearing the
        history, and resetting the services.
        """
        self.current_chat_id = chat_service.get_new_chat_id()
        self.chat_history = []
        # Services must be re-initialized to use the correct context for the new chat
        self.services_initialized = False
        # Update the URL to reflect the new chat session ID for bookmarking/sharing
        st.query_params["chat_id"] = self.current_chat_id

    def select_connection(self, connection_name: str) -> bool:
        """
        Selects a connection by name, resets dependent state (like chat),
        and returns True if the connection was found and selected.
        """
        conn_to_select = next(
            (c for c in self.connections if c["name"] == connection_name), None
        )
        if conn_to_select:
            self.selected_connection = conn_to_select
            # A new connection requires a new chat session and re-initialization of services
            self.start_new_chat()
            return True
        return False

    def save_and_reload_connections(self):
        """Saves the current list of connections to persistent storage and reloads them."""
        connection_service.save_connections(self.connections)
        self.connections = connection_service.load_connections()


# The key used to store the AppState object in Streamlit's session state.
_STATE_KEY = "app_state"


def get_state() -> AppState:
    """
    Retrieves the AppState instance from the session state, creating it if it
    doesn't exist. This is the single entry point for accessing the app state.
    """
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = AppState()
    return st.session_state[_STATE_KEY]