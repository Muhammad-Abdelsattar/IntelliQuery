from __future__ import annotations
from typing import Any, Dict, List, Tuple
import hashlib
import logging

import pandas as pd
import sqlparse
from langchain_community.utilities.sql_database import SQLDatabase
from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import text

logger = logging.getLogger(__name__)


class DatabaseService(SQLDatabase):
    """
    A specialized database service that provides core database interactions.
    
    This class handles schema extraction, query execution, and validation.
    It no longer manages caching, which is now handled by the DBContextAnalyzer.
    """

    CARDINALITY_LIMIT = 25

    # --- MODIFICATION: Simplified __init__ ---
    def __init__(
        self,
        engine: Engine,
        **kwargs: Any,
    ):
        """
        Initializes the service.

        Args:
            engine: The SQLAlchemy engine to connect to the database.
            **kwargs: All other arguments are passed directly to the SQLDatabase parent class.
        """
        super().__init__(engine=engine, **kwargs)
        # The cache provider is no longer part of this service.
        self._metadata = MetaData()

    def get_raw_schema_and_key(self) -> Tuple[str, str]:
        """
        Gets the raw schema DDL and computes a stable SHA256 hash to use as a key.
        """
        raw_schema = self.get_table_info()
        schema_key = hashlib.sha256(raw_schema.encode()).hexdigest()
        return raw_schema, schema_key

    def fetch_distinct_values(
        self, tables_and_columns: List[Dict[str, str]]
    ) -> Dict[str, List[Any]]:
        """
        Safely and portably fetches distinct values for a list of columns.
        """
        distinct_values = {}
        limit = self.CARDINALITY_LIMIT + 1

        with self._engine.connect() as connection:
            for item in tables_and_columns:
                table_name = item["table"]
                column_name = item["column"]
                key = f"{table_name}.{column_name}"

                try:
                    table = Table(table_name, self._metadata, autoload_with=connection)
                    column = table.c[column_name]
                    query = select(column).distinct().limit(limit)
                    result = connection.execute(query).fetchall()

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
            raise ValueError(f"SQL Validation Error: {e}") from e

    def execute_for_dataframe(self, sql_query: str) -> pd.DataFrame:
        """
        Executes a read-only SQL query and returns results as a pandas DataFrame.
        """
        try:
            with self._engine.connect() as connection:
                return pd.read_sql_query(sql_query, connection)
        except SQLAlchemyError as e:
            raise RuntimeError(f"Database execution failed: {e}") from e
