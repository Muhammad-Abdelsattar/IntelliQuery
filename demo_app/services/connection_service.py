"""
Service layer for managing database connection configurations.

This module handles the persistence of database connection details, storing them
in a simple JSON file. It provides functions for loading and saving these
connections.

It also includes a utility function to resolve secrets (like passwords) in
connection URLs using Streamlit's secrets management, which is a security
best practice.
"""

import json
import os
from typing import List, Dict, Any, Optional
import streamlit as st

# The path to our simple JSON file used as a database for connections.
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
        # to prevent the app from crashing.
        return []


def save_connections(connections: List[Dict[str, Any]]):
    """Saves the list of connection configurations to the JSON file."""
    try:
        with open(CONNECTIONS_FILE, "w") as f:
            json.dump(connections, f, indent=2)
    except IOError as e:
        # Display an error in the Streamlit UI if saving fails.
        st.error(f"Failed to save connections: {e}")


def resolve_secrets_in_url(url: str) -> str:
    """
    Replaces placeholders like ${DB_PASSWORD} in a URL with their corresponding
    values from Streamlit's secrets.

    Args:
        url: The URL string which may contain secret placeholders.

    Returns:
        The URL with placeholders substituted with actual secrets.

    Raises:
        ValueError: If a placeholder is found in the URL but the corresponding
                    secret is not defined in Streamlit's secrets.toml.
    """
    # A simple regex could also work, but this is robust enough for the format.
    placeholders = [p[2:-1] for p in url.split() if p.startswith("${") and p.endswith("}")]

    resolved_url = url
    for placeholder in placeholders:
        if placeholder in st.secrets:
            resolved_url = resolved_url.replace(f"${{{placeholder}}}", st.secrets[placeholder])
        else:
            raise ValueError(f"Secret '{placeholder}' not found in secrets.toml. Please add it to your .streamlit/secrets.toml file.")

    return resolved_url
