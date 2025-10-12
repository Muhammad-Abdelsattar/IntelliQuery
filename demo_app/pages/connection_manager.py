import os
from pathlib import Path
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from typing import Dict, Any

from services import connection_service
from state import AppState

# Import from your core library
from intelliquery import DatabaseService, DBContextAnalyzer
from intelliquery import FileSystemCacheProvider
from nexus_llm import LLMInterface, load_settings

st.set_page_config(page_title="Connection Manager", page_icon="🗄️", layout="wide")

# Helper Functions
def initialize_llm_interface():
    """Initializes the LLM interface from secrets."""
    # This is an example setup. Adjust as needed for your LLM provider.
    if "GOOGLE_API_KEY" in st.secrets:
        llm_settings_dict = {
            "llm_providers": {
                "google_gemini": {
                    "class_path": "langchain_google_genai.ChatGoogleGenerativeAI",
                    "params": {
                        "model": "gemini-2.5-flash",
                        "google_api_key": st.secrets["GOOGLE_API_KEY"],
                        "temperature": 0.1,
                    },
                }
            }
        }
        settings = load_settings(llm_settings_dict)
        return LLMInterface(settings=settings, provider_key="google_gemini")
    else:
        st.error("GOOGLE_API_KEY not found in Streamlit secrets.")
        return None


def get_default_value(key: str) -> Any:
    """Gets a default value from the currently selected connection for the form."""
    if st.session_state.get(AppState.SELECTED_CONNECTION):
        return st.session_state[AppState.SELECTED_CONNECTION].get(key, "")
    return ""


# Main Page UI

st.title("🗄️ Connection Manager")
st.markdown(
    "Manage your database connections here. The enriched context for each connection will be cached for faster performance."
)

# Initialize session state if not already done
if AppState.CONNECTIONS not in st.session_state:
    st.session_state[AppState.CONNECTIONS] = connection_service.load_connections()
if AppState.SELECTED_CONNECTION not in st.session_state:
    st.session_state[AppState.SELECTED_CONNECTION] = None

llm_interface = initialize_llm_interface()

col1, col2 = st.columns([1, 1.5])

# Column 1: List and Manage Existing Connections
with col1:
    st.subheader("Existing Connections")
    connections = st.session_state[AppState.CONNECTIONS]

    if not connections:
        st.info("No connections added yet. Use the form on the right to add one.")
    else:
        for i, conn in enumerate(connections):
            with st.expander(
                f"**{conn['name']}** (`{conn['dialect']}`)", expanded=True
            ):
                st.text_input("URL", value=conn["url"], disabled=True, key=f"url_{i}")

                c1, c2, _ = st.columns([1, 1, 3])
                if c1.button("Edit", key=f"edit_{i}"):
                    st.session_state[AppState.SELECTED_CONNECTION] = conn
                    st.rerun()
                if c2.button("Delete", key=f"delete_{i}", type="primary"):
                    st.session_state[AppState.CONNECTIONS].pop(i)
                    connection_service.save_connections(
                        st.session_state[AppState.CONNECTIONS]
                    )
                    st.rerun()

# Column 2: Add/Edit Connection Form
with col2:
    is_editing = st.session_state[AppState.SELECTED_CONNECTION] is not None
    form_title = "Edit Connection" if is_editing else "Add New Connection"
    st.subheader(form_title)

    with st.form(key="connection_form", clear_on_submit=False):
        name = st.text_input(
            "Connection Name*",
            value=get_default_value("name"),
            help="A unique, friendly name for this connection.",
        )
        dialect = st.selectbox(
            "Database Dialect*",
            options=["postgresql", "mysql", "sqlite"],
            index=0,
            help="The type of database you are connecting to.",
        )
        url = st.text_input(
            "Database URL*",
            value=get_default_value("url"),
            help="SQLAlchemy connection string. Use ${SECRET_NAME} for secrets (e.g., ${DB_PASSWORD}).",
        )
        tables = st.text_input(
            "Include Tables (Optional)",
            value=get_default_value("tables"),
            help="Comma-separated list of tables to include. Leave blank to include all.",
        )
        business_context = st.text_area(
            "Default Business Context (Optional)",
            value=get_default_value("business_context"),
            height=150,
            help="Provide default business rules or definitions for this data source.",
        )

        submitted = st.form_submit_button("Save & Analyze Connection")

        if submitted:
            if not all([name, dialect, url]):
                st.error("Please fill in all required fields (*).")
            elif llm_interface is None:
                st.error("LLM Interface is not initialized. Check your secrets.")
            else:
                try:
                    resolved_url = connection_service.resolve_secrets_in_url(url)
                    engine = create_engine(resolved_url)

                    with st.spinner("1/3 - Testing database connection..."):
                        with engine.connect() as connection:
                            pass  # This is enough to test the connection

                    with st.spinner(
                        "2/3 - Analyzing database and building context... This may take a moment."
                    ):
                        db_service = DatabaseService(
                            engine=engine,
                            cache_provider=FileSystemCacheProvider(
                                cache_dir=Path(".cache/context_cache")
                            ),
                        )
                        context_analyzer = DBContextAnalyzer(
                            llm_interface=llm_interface, db_service=db_service
                        )
                        context_analyzer.build_context(
                            business_context=business_context
                        )

                    with st.spinner("3/3 - Saving connection..."):
                        new_conn = {
                            "name": name,
                            "dialect": dialect,
                            "url": url,  # Save the unresolved URL for display
                            "tables": tables,
                            "business_context": business_context,
                        }

                        connections = st.session_state[AppState.CONNECTIONS]
                        if is_editing:
                            # Find and update the existing connection
                            original_name = st.session_state[
                                AppState.SELECTED_CONNECTION
                            ]["name"]
                            for i, c in enumerate(connections):
                                if c["name"] == original_name:
                                    connections[i] = new_conn
                                    break
                        else:
                            # Add a new one
                            connections.append(new_conn)

                        connection_service.save_connections(connections)
                        st.session_state[AppState.CONNECTIONS] = connections
                        st.session_state[AppState.SELECTED_CONNECTION] = None

                    st.success(f"Connection '{name}' saved and analyzed successfully!")
                    st.rerun()

                except Exception as e:
                    st.error("An error occurred:")
                    with st.expander("View Full Error Traceback"):
                        st.exception(e)

    if is_editing:
        if st.button("Cancel Edit"):
            st.session_state[AppState.SELECTED_CONNECTION] = None
            st.rerun()
