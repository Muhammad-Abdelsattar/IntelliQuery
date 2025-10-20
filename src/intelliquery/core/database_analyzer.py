import os
import re
import json
import logging
from typing import Optional, Dict, List, Any
import importlib.resources

from nexus_llm import LLMInterface, FileSystemPromptProvider

from .database import DatabaseService
from .caching import CacheProvider
from ..models.sql_agent.agent_io import InspectionPlan
from ..models.sql_agent.public import EnrichedDatabaseContext

logger = logging.getLogger(__name__)


class DBContextAnalyzer:
    """
    A class responsible for building an enriched, cached context from a database.
    It orchestrates the database service and cache provider. If an LLM interface
    is not provided, it falls back to providing only the raw schema.
    """

    def __init__(
        self,
        db_service: DatabaseService,
        cache_provider: CacheProvider,
        llm_interface: Optional[LLMInterface] = None,
        max_values: int = 25,
    ):
        self.llm_interface = llm_interface
        self.db_service = db_service
        self.cache_provider = cache_provider
        self.max_values = max_values

        if self.llm_interface:
            prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
            self.prompt_provider = FileSystemPromptProvider(base_path=prompts_base_path)

    def _synthesize_augmented_schema(
        self, raw_schema: str, fetched_values: Dict[str, List[Any]]
    ) -> str:
        """
        Augments the DDL schema with inline comments showing possible values for categorical columns.
        Handles multiple SQL identifier quoting styles: "table", `table`, [table], and unquoted.
        """
        lines = raw_schema.strip().split("\n")
        augmented_lines = []

        # Simple regex pattern to match any SQL identifier
        IDENTIFIER = r'(?:"([^"]+)"|`([^`]+)`|$$([^$$]+)\]|(\w+))'

        # Pattern to detect CREATE TABLE statements
        table_pattern = re.compile(
            rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            rf"(?:{IDENTIFIER}\.)?"  # Optional schema prefix
            rf"{IDENTIFIER}",  # Table name
            re.IGNORECASE,
        )

        # Pattern to detect column definitions (indented lines with identifier + data type)
        column_pattern = re.compile(
            rf"^\s+"  # Leading whitespace
            rf"{IDENTIFIER}"  # Column name
            rf"\s+"
            rf"[A-Z][\w()]*",  # Data type
            re.IGNORECASE,
        )

        # Keywords that indicate constraint lines (not column definitions)
        CONSTRAINT_KEYWORDS = {
            "PRIMARY",
            "FOREIGN",
            "UNIQUE",
            "CHECK",
            "CONSTRAINT",
            "KEY",
        }

        def extract_identifier(groups: tuple) -> Optional[str]:
            """Extract identifier from regex groups (handles all quote styles)."""
            return next((g for g in groups if g), None)

        def is_constraint_line(line: str) -> bool:
            """Check if this is a constraint line rather than a column definition."""
            stripped = line.strip().upper()
            return any(stripped.startswith(kw) for kw in CONSTRAINT_KEYWORDS)

        def format_values(values: Any) -> str:
            """Format values into a readable comment string."""
            if isinstance(values, list):
                if len(values) <= self.max_values:
                    formatted = [
                        f"'{v}'" if isinstance(v, str) else str(v) for v in values
                    ]
                    return f"Possible values: {', '.join(formatted)}"
                else:
                    formatted = [
                        f"'{v}'" if isinstance(v, str) else str(v) for v in values[:8]
                    ]
                    return f"Possible values: {', '.join(formatted)} ... (+{len(values) - 8} more)"
            elif values == "TOO_MANY_VALUES":
                return "Too many distinct values"
            else:
                return str(values)

        # Track current table context
        current_table: Optional[str] = None

        # Process each line
        for line in lines:
            # Check if this is a CREATE TABLE line
            table_match = table_pattern.search(line)
            if table_match:
                # Extract table name (last 4 groups are the table identifier)
                current_table = extract_identifier(table_match.groups()[-4:])
                augmented_lines.append(line)
                logger.debug(f"Entered table context: {current_table}")
                continue

            # If we're in a table and this looks like a column definition
            if current_table and not is_constraint_line(line):
                col_match = column_pattern.match(line)

                if col_match:
                    # Extract column name (first 4 groups)
                    col_name = extract_identifier(col_match.groups()[:4])

                    if col_name:
                        # Check if we have metadata for this column
                        key = f"{current_table}.{col_name}"

                        if key in fetched_values:
                            # Add comment with values
                            comment = f" -- {format_values(fetched_values[key])}"
                            augmented_lines.append(line.rstrip() + comment)
                            logger.debug(f"Added comment for {key}")
                            continue

            # Default: add line as-is
            augmented_lines.append(line)

        return "\n".join(augmented_lines)


def build_context(
    self, business_context: Optional[str] = None
) -> EnrichedDatabaseContext:
    """
    Main orchestration method for the context enrichment.
    If no LLM is provided, it returns a basic context with only the raw schema.
    """
    raw_schema, schema_key = self.db_service.get_raw_schema_and_key()

    if not self.llm_interface:
        logger.warning("No LLM interface provided. Falling back to raw schema context.")
        return EnrichedDatabaseContext(
            raw_schema=raw_schema,
            augmented_schema=raw_schema,  # Augmented is same as raw
            schema_key=schema_key,
            business_context=business_context,
        )

    full_key = f"{schema_key}-{hash(business_context)}"

    # Check the cache (using the injected cache_provider)
    cached_context_str = self.cache_provider.get(full_key)
    if cached_context_str:
        logger.info(f"CACHE HIT for context key: {full_key[:10]}...")
        return EnrichedDatabaseContext(**json.loads(cached_context_str))

    logger.info(f"CACHE MISS for key: {full_key[:10]}... Building new context.")

    analyzer_prompt = self.prompt_provider.get_template(
        os.path.join("sql_agent", "schema_analyzer.prompt")
    )
    try:
        plan = self.llm_interface.generate_structured(
            system_prompt=analyzer_prompt,
            user_input=f"Analyze this schema: {raw_schema}",
            variables={"schema_ddl": raw_schema},
            response_model=InspectionPlan,
        )

        columns_to_check = [item.model_dump() for item in plan.columns_to_inspect]
    except Exception as e:
        # raise e
        logger.error(f"Failed to generate a valid inspection plan: {e}")
        columns_to_check = []

    # Fetch the distinct values
    fetched_values = self.db_service.fetch_distinct_values(columns_to_check)

    augmented_schema = self._synthesize_augmented_schema(raw_schema, fetched_values)

    context = EnrichedDatabaseContext(
        raw_schema=raw_schema,
        augmented_schema=augmented_schema,
        schema_key=schema_key,
        business_context=business_context,
    )

    # Save to cache
    self.cache_provider.set(full_key, context.model_dump_json())
    logger.info(f"Saved new context to cache for key: {full_key[:10]}...")

    return context
