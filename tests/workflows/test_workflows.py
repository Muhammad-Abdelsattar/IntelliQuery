from unittest.mock import MagicMock
from intelliquery.workflows.reflection import ReflectionWorkflow
from intelliquery.models.agent_io import LLM_SQLResponse, ReflectionReview

# A sample state dictionary to be used across multiple tests
SAMPLE_STATE = {
    "natural_language_question": "How many users?",
    "chat_history": [],
    "db_context": {
        "augmented_schema": "CREATE TABLE users...",
        "business_context": "None",
    },
    "history": [],
    "max_attempts": 3,
    "current_attempt": 0,
    "max_reflection_attempts": 2,
    "current_reflection_attempt": 0,
    "generation_result": None,
    "review": None,
}


def test_generate_sql_node(mocker):
    """Verify the generate_sql_node calls the LLM with the correct context."""
    mock_llm = MagicMock()
    mock_db = MagicMock()
    mock_db.dialect = "postgresql"

    # Mock the LLM response
    llm_response = LLM_SQLResponse(status="success", query="SELECT 1;")
    mock_llm.generate_structured.return_value = llm_response

    workflow = ReflectionWorkflow(llm_interface=mock_llm, db_service=mock_db)

    # Create a state with some history and a review
    state = SAMPLE_STATE.copy()
    state["history"] = ["ATTEMPT 1 - FAILED"]
    state["review"] = "You made a mistake."

    result = workflow.generate_sql_node(state)

    # Assertions
    mock_llm.generate_structured.assert_called_once()
    call_args, call_kwargs = mock_llm.generate_structured.call_args

    # Check that the review and history were included in the prompt variables
    prompt_vars = call_kwargs["variables"]
    assert "ATTEMPT 1 - FAILED" in prompt_vars["history"]
    assert "REVIEWER SUGGESTIONS:\nYou made a mistake." in prompt_vars["history"]
    assert prompt_vars["schema_definition"] == "CREATE TABLE users..."

    assert result["generation_result"] == llm_response
    assert result["review"] is None  # Ensure the review is cleared after use


def test_reflection_node(mocker):
    """Verify the reflection_node calls the LLM with the correct review prompt."""
    mock_llm = MagicMock()
    mock_db = MagicMock()

    # Mock the reviewer's decision
    review = ReflectionReview(decision="revise", suggestions="Use a JOIN.")
    mock_llm.generate_structured.return_value = review

    workflow = ReflectionWorkflow(llm_interface=mock_llm, db_service=mock_db)

    # Create a state where a query has just been generated
    state = SAMPLE_STATE.copy()
    state["generation_result"] = LLM_SQLResponse(
        status="success", query="SELECT * FROM users;"
    )

    result = workflow.reflection_node(state)

    # Assertions
    mock_llm.generate_structured.assert_called_once()
    call_args, call_kwargs = mock_llm.generate_structured.call_args

    prompt_vars = call_kwargs["variables"]
    assert prompt_vars["sql_query"] == "SELECT * FROM users;"
    assert prompt_vars["user_question"] == "How many users?"

    assert result["review"] == "Use a JOIN."
    assert result["current_reflection_attempt"] == 1


def test_should_retry_node():
    """Test the logic for retrying after a database execution error."""
    workflow = ReflectionWorkflow(llm_interface=None, db_service=None)

    # Case 1: No error, should end
    state_success = {
        "generation_result": LLM_SQLResponse(status="success"),
        "error": None,
    }
    assert workflow.should_retry_node(state_success) == "end"

    # Case 2: Generation failed, should end
    state_gen_fail = {
        "generation_result": LLM_SQLResponse(status="error"),
        "error": None,
    }
    assert workflow.should_retry_node(state_gen_fail) == "end"

    # Case 3: DB error and attempts remaining, should retry
    state_retry = {
        "generation_result": LLM_SQLResponse(status="success"),
        "error": "DB error",
        "current_attempt": 1,
        "max_attempts": 3,
    }
    assert workflow.should_retry_node(state_retry) == "retry"

    # Case 4: DB error but max attempts reached, should end
    state_max_attempts = {
        "generation_result": LLM_SQLResponse(status="success"),
        "error": "DB error",
        "current_attempt": 3,
        "max_attempts": 3,
    }
    assert workflow.should_retry_node(state_max_attempts) == "end"


def test_decide_after_reflection_node():
    """Test the logic for proceeding or regenerating after a review."""
    workflow = ReflectionWorkflow(llm_interface=None, db_service=None)

    # Case 1: Reviewer approved (review is None), should execute
    state_proceed = {"review": None}
    assert workflow.decide_after_reflection_node(state_proceed) == "execute"

    # Case 2: Reviewer suggested changes, attempts remaining, should regenerate
    state_revise = {
        "review": "Change it",
        "current_reflection_attempt": 1,
        "max_reflection_attempts": 2,
    }
    assert workflow.decide_after_reflection_node(state_revise) == "regenerate"

    # Case 3: Reviewer suggested changes, but max attempts reached, should execute anyway
    state_max_reflection = {
        "review": "Change it",
        "current_reflection_attempt": 2,
        "max_reflection_attempts": 2,
    }
    assert workflow.decide_after_reflection_node(state_max_reflection) == "execute"
