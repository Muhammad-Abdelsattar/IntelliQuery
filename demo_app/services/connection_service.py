import json
import os
from typing import List, Dict, Any, Optional
import streamlit as st

# The path to our simple JSON database for connections
CONNECTIONS_FILE = ".connections.json"

def load_connections() -> List[Dict[str, Any]]:
    """Loads the list of connection configurations from the JSON file."""
    if not os.path.exists(CONNECTIONS_FILE):
        return []
    try:
        with open(CONNECTIONS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If the file is corrupted or unreadable, return an empty list
        return []

def save_connections(connections: List[Dict[str, Any]]):
    """Saves the list of connection configurations to the JSON file."""
    try:
        with open(CONNECTIONS_FILE, "w") as f:
            json.dump(connections, f, indent=2)
    except IOError as e:
        st.error(f"Failed to save connections: {e}")

def resolve_secrets_in_url(url: str) -> str:
    """
    Replaces placeholders like ${DB_PASSWORD} in the URL with Streamlit secrets.
    """
    # Find all placeholders like ${VAR_NAME}
    placeholders = [p[2:-1] for p in url.split() if p.startswith("${") and p.endswith("}")]
    
    resolved_url = url
    for placeholder in placeholders:
        if placeholder in st.secrets:
            resolved_url = resolved_url.replace(f"${{{placeholder}}}", st.secrets[placeholder])
        else:
            raise ValueError(f"Secret '{placeholder}' not found in secrets.toml")
            
    return resolved_url
