class SQLToolkitError(Exception):
    """Base exception for the SQL Agent Toolkit library."""
    pass

class SQLGenerationError(SQLToolkitError):
    """Raised for errors during the SQL generation process."""
    pass

class DatabaseConnectionError(SQLToolkitError):
    """Raised for issues related to database connectivity."""
    pass
