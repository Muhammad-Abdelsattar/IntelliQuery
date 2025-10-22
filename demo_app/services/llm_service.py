"""
Service layer for initializing and providing the Large Language Model (LLM) interface.

This module acts as a bridge between the Streamlit application and the underlying
`nexus_llm` library. It is responsible for creating an `LLMInterface` instance
based on the application's current state, such as the selected LLM provider.

This abstraction allows the main application logic to remain agnostic about the
specifics of the LLM provider being used.
"""

import streamlit as st
from state import AppState
from nexus_llm import LLMInterface, load_settings
from dotenv import load_dotenv


def get_llm_interface(state: AppState) -> LLMInterface:
    """
    Initializes and returns an LLMInterface based on the current app state.

    This function reads the selected LLM provider from the app state and
    instantiates the `LLMInterface`, which is the gateway for making calls
    to the language model.

    Args:
        state: The current application state, which contains the LLM provider
               settings and the user's selection.

    Returns:
        An initialized LLMInterface instance ready to be used.

    Side Effects:
        - Displays Streamlit errors and stops the app if the configuration is
          missing or invalid.
        - Loads environment variables from a .env file.
    """
    load_dotenv()

    if not state.all_llm_providers:
        st.error("LLM providers not loaded. Please check your llm_providers.yaml file.")
        st.stop()

    if not state.selected_llm_provider:
        st.warning("No LLM provider selected. Please select one from the sidebar.")
        st.stop()

    try:
        # The LLMInterface handles the logic of selecting the provider and its parameters.
        return LLMInterface(state.all_llm_providers, state.selected_llm_provider)
    except Exception as e:
        st.error(f"Failed to initialize LLM provider '{state.selected_llm_provider}': {e}")
        st.stop()
