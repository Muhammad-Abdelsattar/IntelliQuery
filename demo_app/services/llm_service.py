import streamlit as st
from state import AppState
from nexus_llm import LLMInterface, load_settings
from dotenv import load_dotenv


def get_llm_interface(state: AppState) -> LLMInterface:
    """
    Initializes and returns an LLMInterface based on the current app state.
    """
    load_dotenv()

    if not state.all_llm_providers:
        st.error("LLM providers not loaded.")
        st.stop()

    if not state.selected_llm_provider:
        st.warning("No LLM provider selected.")
        st.stop()

    try:
        return LLMInterface(state.all_llm_providers, state.selected_llm_provider)
    except Exception as e:
        st.error(f"Failed to initialize LLM provider '{state.selected_llm_provider}': {e}")
        st.stop()
