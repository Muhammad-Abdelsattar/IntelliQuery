import streamlit as st
from services import connection_service
from state import AppState
from ui_components import sidebar

st.set_page_config(page_title="IntelliQuery Home", page_icon="🏠", layout="centered")

st.session_state["active_page"] = "home"


def initialize_state():
    if AppState.CONNECTIONS not in st.session_state:
        st.session_state[AppState.CONNECTIONS] = connection_service.load_connections()


initialize_state()
sidebar.build_sidebar()

st.title("Welcome to IntelliQuery 🧠")
st.markdown(
    """
    **Your intelligent assistant for talking to your databases.**

    Select a database connection from the sidebar to begin. If you haven't configured
    any, click **Manage Connections** to add your first one.
    """
)

# Check if a connection has been selected in the sidebar
if st.session_state.get(AppState.SELECTED_CONNECTION):
    st.success(
        f"Connection **'{st.session_state[AppState.SELECTED_CONNECTION]['name']}'** is active."
    )
    if st.button("Start Chatting →", type="primary"):
        st.switch_page("pages/chat.py")
else:
    st.warning("Please select an active connection from the sidebar.")
