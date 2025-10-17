"""
Service layer for managing chat history.

This module provides functions for handling the persistence of chat sessions.
It includes saving, loading, and listing chat histories, which are stored
as JSON files on the local filesystem.

This approach decouples the chat persistence logic from the main application
and state management, making it easier to maintain and potentially replace
with a different storage backend in the future.
"""

import json
import os
import uuid
from typing import List, Dict, Any, Tuple
import pandas as pd
import copy

# The directory where chat history files are stored.
CHAT_HISTORY_DIR = ".chat_history"


def ensure_chat_history_dir():
    """Creates the chat history directory if it doesn't already exist."""
    os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


def save_chat_history(chat_id: str, connection_name: str, history: List[Dict[str, Any]]):
    """
    Saves a chat history to a JSON file.

    Args:
        chat_id: The unique identifier for the chat session.
        connection_name: The name of the database connection used for the chat.
        history: The list of chat messages to save.
    """
    ensure_chat_history_dir()

    # Deepcopy to avoid modifying the original history object in memory
    serializable_history = copy.deepcopy(history)

    # Remove non-serializable data (like DataFrames) before saving
    for message in serializable_history:
        if message.get("content_type") == "result":
            data = message.get("data", {})
            if "dataframe" in data:
                del data["dataframe"]

    # The payload includes the connection name to restore the session context
    payload = {
        "connection_name": connection_name,
        "messages": serializable_history
    }

    file_path = os.path.join(CHAT_HISTORY_DIR, f"{chat_id}.json")
    with open(file_path, "w") as f:
        json.dump(payload, f, indent=2)


def load_chat_history(chat_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Loads a chat history from a JSON file.

    Args:
        chat_id: The unique identifier for the chat session.

    Returns:
        A tuple containing the connection name and the list of chat messages.
        Returns (None, []) if the chat history is not found.
    """
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{chat_id}.json")
    if not os.path.exists(file_path):
        return None, []

    with open(file_path, "r") as f:
        payload = json.load(f)

    connection_name = payload.get("connection_name")
    history = payload.get("messages", [])

    return connection_name, history


def get_new_chat_id() -> str:
    """Generates a new unique ID for a chat session."""
    return str(uuid.uuid4())


def list_chat_sessions() -> List[Dict[str, str]]:
    """Lists all saved chat sessions, creating a display name from the first message."""
    ensure_chat_history_dir()
    sessions = []
    for filename in os.listdir(CHAT_HISTORY_DIR):
        if filename.endswith(".json"):
            chat_id = filename.replace(".json", "")
            try:
                # Load the history to get the first user message for a display name
                _, history = load_chat_history(chat_id)
                first_message = history[0]['content'] if history and history[0]['role'] == 'user' else 'Chat Session'
                sessions.append({"id": chat_id, "name": first_message[:50]})
            except (IndexError, KeyError):
                # Handle cases where the history is empty or malformed
                continue
    return sessions


def get_conversation_history(
    chat_history: list[dict[str, any]]
) -> list[tuple[str, str]]:
    """
    Extracts a clean (user, assistant) conversational history from the full
    chat history. This is used to provide context to the LLM.

    Args:
        chat_history: The full list of message dictionaries.

    Returns:
        A list of (user_question, ai_answer) tuples.
    """
    conversation_history = []
    for i in range(len(chat_history) - 1):
        current_msg = chat_history[i]
        next_msg = chat_history[i + 1]

        # We are looking for a user message followed by an assistant message
        if current_msg.get("role") == "user" and next_msg.get("role") == "assistant":
            user_question = current_msg.get("content", "")
            ai_answer = ""
            content_type = next_msg.get("content_type", "text")

            # Extract the relevant part of the assistant's response for the history
            if content_type in ["text", "error"]:
                ai_answer = next_msg.get("content", "")
            elif content_type == "result":
                # For results, the SQL query is the most important part of the answer
                ai_answer = next_msg.get("data", {}).get("sql_query", "")

            if user_question and ai_answer:
                conversation_history.append((user_question, ai_answer))
    return conversation_history
