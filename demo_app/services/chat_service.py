import json
import os
import uuid
from typing import List, Dict, Any, Tuple
import pandas as pd
import copy

CHAT_HISTORY_DIR = ".chat_history"

def ensure_chat_history_dir():
    os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

def save_chat_history(chat_id: str, connection_name: str, history: List[Dict[str, Any]]):
    """
    Saves a chat history to a JSON file, now including the connection name.
    """
    ensure_chat_history_dir()
    
    serializable_history = copy.deepcopy(history)
    for message in serializable_history:
        if message.get("content_type") == "result":
            data = message.get("data", {})
            if "dataframe" in data and isinstance(data["dataframe"], pd.DataFrame):
                data["dataframe_json"] = data["dataframe"].to_json(orient='split')
                del data["dataframe"]

    # Create a new structure that includes the connection name
    payload = {
        "connection_name": connection_name,
        "messages": serializable_history
    }

    file_path = os.path.join(CHAT_HISTORY_DIR, f"{chat_id}.json")
    with open(file_path, "w") as f:
        json.dump(payload, f, indent=2)

def load_chat_history(chat_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Loads a chat history, now returning both the connection name and the messages.
    """
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{chat_id}.json")
    if not os.path.exists(file_path):
        return None, []
    
    with open(file_path, "r") as f:
        payload = json.load(f)
    
    connection_name = payload.get("connection_name")
    history = payload.get("messages", [])
    
    # Convert JSON strings back to DataFrame objects
    for message in history:
        if message.get("content_type") == "result":
            data = message.get("data", {})
            if "dataframe_json" in data:
                try:
                    data["dataframe"] = pd.read_json(data["dataframe_json"], orient='split')
                    del data["dataframe_json"]
                except Exception:
                    data["dataframe"] = pd.DataFrame()
                    
    return connection_name, history

def get_new_chat_id() -> str:
    """Generates a new unique ID for a chat session."""
    return str(uuid.uuid4())


def list_chat_sessions() -> List[Dict[str, str]]:
    """Lists all saved chat sessions."""
    ensure_chat_history_dir()
    sessions = []
    for filename in os.listdir(CHAT_HISTORY_DIR):
        if filename.endswith(".json"):
            chat_id = filename.replace(".json", "")
            try:
                # Load just to get the first message for the name
                _, history = load_chat_history(chat_id)
                first_message = history[0]['content'] if history and history[0]['role'] == 'user' else 'Chat Session'
                sessions.append({"id": chat_id, "name": first_message[:50]})
            except (IndexError, KeyError):
                continue
    return sessions
