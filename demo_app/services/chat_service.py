import json
import os
import uuid
from typing import List, Dict, Any, Tuple
import copy

CHAT_HISTORY_DIR = ".chat_history"

def ensure_chat_history_dir():
    os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


def save_chat_history(
    chat_id: str, connection_name: str, history: List[Dict[str, Any]]
):
    """
    Saves a chat history to a JSON file, ensuring no live Python objects are saved.
    """
    ensure_chat_history_dir()

    serializable_history = copy.deepcopy(history)
    for message in serializable_history:
        if message.get("role") == "assistant":
            data = message.get("data", {})
            # CRITICAL: Strip all non-serializable objects before saving.
            data.pop("dataframe", None)
            data.pop("visualization", None)

    payload = {"connection_name": connection_name, "messages": serializable_history}
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{chat_id}.json")
    with open(file_path, "w") as f:
        json.dump(payload, f, indent=2)


def load_chat_history(chat_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Loads a chat history, returning both the connection name and the messages.
    """
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{chat_id}.json")
    if not os.path.exists(file_path):
        return None, []
    with open(file_path, "r") as f:
        payload = json.load(f)
    return payload.get("connection_name"), payload.get("messages", [])


def get_new_chat_id() -> str:
    """Generates a new unique ID for a chat session."""
    return str(uuid.uuid4())


def list_chat_sessions() -> List[Dict[str, str]]:
    """Lists all saved chat sessions, safely skipping corrupted files."""
    ensure_chat_history_dir()
    sessions = []
    for filename in sorted(os.listdir(CHAT_HISTORY_DIR), reverse=True):
        if filename.endswith(".json"):
            chat_id = filename.replace(".json", "")
            try:
                _, history = load_chat_history(chat_id)
                if history and history[0].get("role") == "user":
                    first_message = history[0]["content"]
                    sessions.append({"id": chat_id, "name": first_message[:50]})
                else:
                    sessions.append({"id": chat_id, "name": f"Chat {chat_id[:8]}"})
            except (IndexError, KeyError, json.JSONDecodeError) as e:
                print(
                    f"Warning: Skipping corrupted chat history file: {filename}. Error: {e}"
                )
                continue
    return sessions


def get_conversation_history(
    chat_history: list[dict[str, any]],
) -> list[tuple[str, str]]:
    """
    Extracts a clean (user, assistant) conversational history for the LLM.
    """
    conversation_history = []
    for i in range(0, len(chat_history) - 1, 2):
        user_msg = chat_history[i]
        asst_msg = chat_history[i + 1]
        if user_msg.get("role") == "user" and asst_msg.get("role") == "assistant":
            user_question = user_msg.get("content", "")
            ai_answer = ""
            content_type = asst_msg.get("content_type", "text")
            if content_type == "bi_result":
                ai_answer = asst_msg.get("data", {}).get("answer", "")
            elif content_type in ["text", "error"]:
                ai_answer = asst_msg.get("content", "")
            if user_question and ai_answer:
                conversation_history.append((user_question, ai_answer))
    return conversation_history

