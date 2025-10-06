import json
import logging
from typing import Optional, Dict, List, Any
import importlib.resources

from simple_llm import LLMInterface, FileSystemPromptProvider

from .database import DatabaseService
from .models import EnrichedDatabaseContext, InspectionPlan

logger = logging.getLogger(__name__)


class DBContextAnalyzer:
    """
    A class responsible for building an enriched, cached context from a database.
    This encapsulates the logic of analyzing, fetching, and synthesizing context.
    """

    def __init__(self, llm_interface: LLMInterface, db_service: DatabaseService):
        self.llm_interface = llm_interface
        self.db_service = db_service

        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        self.prompt_provider = FileSystemPromptProvider(base_path=prompts_base_path)

    def _synthesize_augmented_schema(
        self, raw_schema: str, fetched_values: Dict[str, List[Any]]
    ) -> str:
        """Combines the raw DDL with fetched distinct values into an augmented schema."""
        lines = raw_schema.split("\n")
        augmented_lines = []
        current_table = ""

        for line in lines:
            augmented_lines.append(line)
            if "CREATE TABLE" in line and '"' in line:
                current_table = line.split('"')[1]

            for key, values in fetched_values.items():
                table, column = key.split(".")
                if table == current_table and f'"{column}"' in line:
                    comment = ""
                    if isinstance(values, list):
                        comment = f" -- Possible values: {values}"
                    elif values == "TOO_MANY_VALUES":
                        comment = " -- (Too many distinct values to display)"

                    if comment:
                        augmented_lines[-1] = line.rstrip() + comment

        return "\n".join(augmented_lines)

    def build_context(
        self, business_context: Optional[str] = None
    ) -> EnrichedDatabaseContext:
        """
        Main orchestration method for the context enrichment and caching workflow.
        """
        raw_schema, schema_key = self.db_service.get_raw_schema_and_key()
        full_key = f"{schema_key}-{hash(business_context)}"

        # Check the cache
        cached_context_str = self.db_service.cache.get(full_key)
        if cached_context_str:
            logger.info(f"CACHE HIT for context key: {full_key[:10]}...")
            return EnrichedDatabaseContext(**json.loads(cached_context_str))

        logger.info(
            f"CACHE MISS for context key: {full_key[:10]}... Building new context."
        )

        # Cache Miss: Analyze the schema with an LLM
        analyzer_prompt = self.prompt_provider.get_template("schema_analyzer.prompt")
        try:
            plan = self.llm_interface.generate_structured(
                system_prompt=analyzer_prompt,
                user_input=f"Analyze this schema: {raw_schema}",
                variables={"schema_ddl": raw_schema},
                response_model=InspectionPlan,
            )

            columns_to_check = [item.dict() for item in plan.columns_to_inspect]
        except Exception as e:
            # raise e
            logger.error(f"Failed to generate a valid inspection plan: {e}")
            columns_to_check = []

        # Fetch the distinct values
        fetched_values = self.db_service.fetch_distinct_values(columns_to_check)

        # Synthesize the final augmented schema
        augmented_schema = self._synthesize_augmented_schema(raw_schema, fetched_values)

        # Create the context object
        context = EnrichedDatabaseContext(
            raw_schema=raw_schema,
            augmented_schema=augmented_schema,
            schema_key=schema_key,
            business_context=business_context,
        )

        # Save to cache before returning
        self.db_service.cache.set(full_key, context.json())
        logger.info(f"Saved new context to cache for key: {full_key[:10]}...")

        return context
