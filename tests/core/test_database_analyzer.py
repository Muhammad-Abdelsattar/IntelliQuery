import json
from unittest.mock import MagicMock, patch

from src.intelliquery.core.database_analyzer import DBContextAnalyzer
from src.intelliquery.models.public import EnrichedDatabaseContext
from src.intelliquery.models.agent_io import InspectionPlan, ColumnToInspect


def test_synthesize_schema_standard_augmentation():
    """Test basic augmentation with double-quoted identifiers."""
    analyzer = DBContextAnalyzer(llm_interface=None, db_service=None)
    raw_schema = 'CREATE TABLE "users" (\n\t"id" INTEGER,\n\t"status" VARCHAR(50)\n);'
    fetched_values = {"users.status": ["active", "inactive"]}

    augmented = analyzer._synthesize_augmented_schema(raw_schema, fetched_values)

    assert "VARCHAR(50) -- Possible values: 'active', 'inactive'" in augmented


def test_synthesize_schema_handles_too_many_values():
    """Test the 'TOO_MANY_VALUES' special case."""
    analyzer = DBContextAnalyzer(llm_interface=None, db_service=None)
    raw_schema = "CREATE TABLE `products` (\n\t`category` VARCHAR(50)\n);"
    fetched_values = {"products.category": "TOO_MANY_VALUES"}

    augmented = analyzer._synthesize_augmented_schema(raw_schema, fetched_values)

    assert "VARCHAR(50) -- Too many distinct values" in augmented


def test_synthesize_schema_handles_no_quotes():
    """Test augmentation with unquoted identifiers."""
    analyzer = DBContextAnalyzer(llm_interface=None, db_service=None)
    raw_schema = "CREATE TABLE sales (\n\tregion TEXT\n);"
    fetched_values = {"sales.region": ["NA", "EU", "APAC"]}

    augmented = analyzer._synthesize_augmented_schema(raw_schema, fetched_values)

    assert "TEXT -- Possible values: 'NA', 'EU', 'APAC'" in augmented


def test_synthesize_schema_ignores_unmatched_columns():
    """Test that it doesn't augment columns not in the fetched_values dict."""
    analyzer = DBContextAnalyzer(llm_interface=None, db_service=None)
    raw_schema = 'CREATE TABLE "users" (\n\t"id" INTEGER,\n\t"name" VARCHAR(100)\n);'
    fetched_values = {"users.status": ["active", "inactive"]}  # No 'name' column

    augmented = analyzer._synthesize_augmented_schema(raw_schema, fetched_values)

    assert "--" not in augmented  # No comments should have been added


def test_build_context_cache_hit(mocker):
    """Verify that if the context is cached, LLM and DB are not called."""
    mock_llm = MagicMock()
    mock_db = MagicMock()

    # Setup the mock cache to return a value
    cached_context = EnrichedDatabaseContext(
        raw_schema="schema", augmented_schema="augmented", schema_key="key"
    )
    mock_db.cache.get.return_value = cached_context.model_dump_json()
    mock_db.get_raw_schema_and_key.return_value = ("schema", "key")

    analyzer = DBContextAnalyzer(llm_interface=mock_llm, db_service=mock_db)
    result = analyzer.build_context(business_context="biz")

    # Assertions
    mock_db.cache.get.assert_called_once()
    mock_llm.generate_structured.assert_not_called()
    mock_db.fetch_distinct_values.assert_not_called()
    assert result.augmented_schema == "augmented"


def test_build_context_cache_miss(mocker):
    """Verify that on a cache miss, the full analysis and caching pipeline runs."""
    mock_llm = MagicMock()
    mock_db = MagicMock()

    # Setup a cache miss
    mock_db.cache.get.return_value = None
    mock_db.get_raw_schema_and_key.return_value = ("raw_schema", "key")

    # Mock the LLM's inspection plan
    inspection_plan = InspectionPlan(
        columns_to_inspect=[ColumnToInspect(table="users", column="status")]
    )
    mock_llm.generate_structured.return_value = inspection_plan

    # Mock the DB's fetched values
    mock_db.fetch_distinct_values.return_value = {"users.status": ["active"]}

    # Mock the synthesizer so we don't re-test it
    mocker.patch(
        "src.intelliquery.core.database_analyzer.DBContextAnalyzer._synthesize_augmented_schema",
        return_value="final_augmented_schema",
    )

    analyzer = DBContextAnalyzer(llm_interface=mock_llm, db_service=mock_db)
    result = analyzer.build_context(business_context="biz")

    # Assertions
    mock_db.cache.get.assert_called_once()
    mock_llm.generate_structured.assert_called_once()
    mock_db.fetch_distinct_values.assert_called_once_with(
        [{"table": "users", "column": "status"}]
    )
    mock_db.cache.set.assert_called_once()
    assert result.augmented_schema == "final_augmented_schema"
