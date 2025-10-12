class AppState:
    """Keys for storing and accessing session state."""

    # Connection Management
    CONNECTIONS = "connections"
    SELECTED_CONNECTION = "selected_connection"

    # Chat Management 
    CHAT_HISTORY = "chat_history"
    CURRENT_CHAT_ID = "current_chat_id"
    BUSINESS_CONTEXT = (
        "business_context"
    )

    # Agent & Core Services 
    DB_SERVICE = "db_service"
    CONTEXT_ANALYZER = "context_analyzer"
    QUERY_ORCHESTRATOR = "query_orchestrator"
    ENRICHED_CONTEXT = "enriched_context"

    # Flag to indicate if services are initialized
    SERVICES_INITIALIZED = "services_initialized"
