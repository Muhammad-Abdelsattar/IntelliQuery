from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import logging
import hashlib

import pandas as pd
import sqlparse
from langchain_community.utilities.sql_database import SQLDatabase

from sqlalchemy import create_engine, inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .exceptions import DatabaseConnectionError
from .caching import CacheProvider, InMemoryCacheProvider

logger = logging.getLogger(__name__)


class DatabaseConnectionStrategy(ABC):
    """Abstract base class for a database connection strategy."""

    @abstractmethod
    def get_uri(self) -> str:
        """Constructs the SQLAlchemy database URI."""
        pass


@dataclass
class PostgresConnectionStrategy(DatabaseConnectionStrategy):
    host: str
    port: int
    user: str
    password: str
    dbname: str

    def get_uri(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"


@dataclass
class SqliteConnectionStrategy(DatabaseConnectionStrategy):
    db_path: str

    def get_uri(self) -> str:
        return f"sqlite:///{self.db_path}"


# A generic connection strategy for any SQLAlchemy-supported database
@dataclass
class TemplatedConnectionStrategy(DatabaseConnectionStrategy):
    """
    A generic strategy for connecting to any SQLAlchemy-supported database
    using a URI template.
    """

    uri_template: str
    substitutions: Dict[str, Any]

    def get_uri(self) -> str:
        """Constructs the URI by formatting the template with substitutions."""
        try:
            return self.uri_template.format(**self.substitutions)
        except KeyError as e:
            raise ValueError(
                f"Missing key in 'substitutions' for URI template: {e}. "
                f"Required keys: {self._get_required_keys()}"
            ) from e

    def _get_required_keys(self) -> List[str]:
        """Helper to parse required keys from the template string."""
        import re

        return re.findall(r"\{(\w+)\}", self.uri_template)


# Main Service Class
class DatabaseService:
    """
    A self-contained database service providing context for agents
    and robust query execution for internal use.
    """

    CARDINALITY_LIMIT = 25  # The safety limit for fetching distinct values

    def __init__(
        self,
        strategy: DatabaseConnectionStrategy,
        include_tables: Optional[List[str]] = None,
        sample_rows_in_table_info: int = 3,
        cache_provider: Optional[CacheProvider] = None,  # NEW: Accept a cache provider
    ):
        try:
            self._engine: Engine = create_engine(strategy.get_uri())
            self._langchain_db = SQLDatabase(
                engine=self._engine,
                sample_rows_in_table_info=sample_rows_in_table_info,
                include_tables=include_tables,
            )
            self.dialect = self._langchain_db.dialect
            # NEW: Default to in-memory cache if none is provided
            self.cache = (
                cache_provider
                if cache_provider is not None
                else InMemoryCacheProvider()
            )
        except Exception as e:
            raise DatabaseConnectionError(
                f"Failed to connect to the database: {e}"
            ) from e

    @classmethod
    def from_config(
        cls, db_type: str, params: Dict[str, Any], **kwargs: Any
    ) -> DatabaseService:
        """
        Factory method to create a DatabaseService from configuration parameters.
        """
        strategy: DatabaseConnectionStrategy
        if db_type == "postgres":
            strategy = PostgresConnectionStrategy(**params)
        elif db_type == "sqlite":
            strategy = SqliteConnectionStrategy(**params)
        elif db_type == "templated":
            try:
                strategy = TemplatedConnectionStrategy(**params)
            except TypeError as e:
                raise ValueError(
                    "For 'templated' db_type, 'params' must contain "
                    "'uri_template' and 'substitutions'."
                ) from e
        else:
            raise NotImplementedError(
                f"Database type '{db_type}' is not supported. "
                f"For custom databases, use the 'templated' type."
            )
        return cls(strategy, **kwargs)

    def get_context_for_agent(self) -> Dict[str, Any]:
        """Gets all necessary context (schema, tables) for a prompt template."""
        return {**self._langchain_db.get_context(), "database_dialect": self.dialect}

    def get_raw_schema_and_key(self) -> Tuple[str, str]:
        """
        Gets the raw schema DDL and computes a stable SHA256 hash to use as a cache key.
        """
        raw_schema = self._langchain_db.get_table_info()
        schema_key = hashlib.sha256(raw_schema.encode()).hexdigest()
        return raw_schema, schema_key

    def fetch_distinct_values(
        self, tables_and_columns: List[Dict[str, str]]
    ) -> Dict[str, List[Any]]:
        """
        Safely fetches distinct values for a list of user-specified columns.
        """
        distinct_values = {}
        limit = self.CARDINALITY_LIMIT + 1

        with self._engine.connect() as connection:
            for item in tables_and_columns:
                table = item["table"]
                column = item["column"]
                key = f"{table}.{column}"

                try:
                    # Note: Identifier quoting is important for different SQL dialects
                    query = f'SELECT DISTINCT "{column}" FROM "{table}" LIMIT {limit}'
                    result = connection.execute(text(query)).fetchall()

                    if len(result) >= limit:
                        distinct_values[key] = "TOO_MANY_VALUES"
                    else:
                        distinct_values[key] = [row[0] for row in result]
                except Exception as e:
                    logger.warning(f"Could not fetch distinct values for {key}: {e}")
                    distinct_values[key] = "ERROR_FETCHING"

        return distinct_values

    def validate_sql(self, sql_query: str) -> None:
        """
        Validates an SQL query using the EXPLAIN command without executing it.
        Raises ValueError for syntax errors or semantic errors (e.g., table not found).
        """
        try:
            statement_type = sqlparse.parse(sql_query)[0].get_type()
            if statement_type != "SELECT":
                raise ValueError(
                    f"Only SELECT statements can be validated. Found: {statement_type}"
                )
        except IndexError:
            raise ValueError("The SQL query is empty or invalid.")

        try:
            with self._engine.connect() as connection:
                connection.execute(text(f"EXPLAIN {sql_query}"))
        except SQLAlchemyError as e:
            raise ValueError(f"SQL Validation Error: {e.original}") from e

    def execute_for_dataframe(self, sql_query: str) -> pd.DataFrame:
        """
        Executes a read-only SQL query and returns results as a pandas DataFrame.
        """

        try:
            with self._engine.connect() as connection:
                return pd.read_sql_query(text(sql_query), connection)
        except SQLAlchemyError as e:
            raise RuntimeError(f"Database execution failed: {e.original}") from e
