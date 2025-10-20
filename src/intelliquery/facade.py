from __future__ import annotations
import logging
from typing import List, Tuple, Optional, Literal, Dict, Any

from sqlalchemy import Engine
from nexus_llm import LLMInterface, Settings, load_settings

from .agents.bi_agent import BIOrchestrator
from .agents.sql_agent import SQLAgent
from .agents.vis_agent import VisualizationAgent
from .core.database import DatabaseService
from .core.database_analyzer import DBContextAnalyzer
from .core.caching import CacheProvider, FileSystemCacheProvider
from .core.vis_provider import VisualizationProvider, PlotlyProvider
from .models.bi_agent.public import BIResult
from .models.sql_agent.public import EnrichedDatabaseContext
from .workflows.sql_agent.simple import SimpleWorkflow
from .workflows.sql_agent.reflection import ReflectionWorkflow

logger = logging.getLogger(__name__)


class IntelliQuery:
    """
    The main interaction handle for the IntelliQuery system.

    This class is a lightweight container for the fully configured components
    of the BI system. It is not meant to be instantiated directly, but rather
    through the `create_intelliquery_system` factory function.
    """

    def __init__(
        self,
        context_analyzer: DBContextAnalyzer,
        orchestrators: Dict[str, BIOrchestrator],
        default_llm_key: str,
    ):
        self._context_analyzer = context_analyzer
        self._orchestrators = orchestrators
        self._default_llm_key = default_llm_key
        self._enriched_context: Optional[EnrichedDatabaseContext] = None
        self._last_business_context: Optional[str] = None

    def _get_or_build_context(
        self, business_context: Optional[str] = None
    ) -> EnrichedDatabaseContext:
        """Lazily builds and caches the database context."""
        if self._enriched_context and self._last_business_context == business_context:
            return self._enriched_context

        logger.info("Building new enriched database context...")
        self._enriched_context = self._context_analyzer.build_context(
            business_context=business_context
        )
        self._last_business_context = business_context
        logger.info("Enriched database context is ready.")
        return self._enriched_context

    def ask(
        self,
        question: str,
        chat_history: Optional[List[Tuple[str, str]]] = None,
        business_context: Optional[str] = None,
        llm_key: Optional[str] = None,
    ) -> BIResult:
        """
        Asks a question to the BI agent.

        Args:
            question: The natural language question from the user.
            chat_history: Conversational context.
            business_context: Business rules to enrich the schema.
            llm_key: (Optional) The key of the LLM provider to use for this
                     specific request. If None, uses the default.

        Returns:
            A BIResult object with the final answer, data, and/or visualization.
        """
        if not question or not question.strip():
            raise ValueError("The question cannot be empty.")

        # Determine which LLM and orchestrator to use for this request
        active_llm_key = llm_key or self._default_llm_key
        if active_llm_key not in self._orchestrators:
            raise ValueError(
                f"LLM provider key '{active_llm_key}' not found. "
                f"Available keys: {list(self._orchestrators.keys())}"
            )
        orchestrator = self._orchestrators[active_llm_key]
        logger.info(f"Using LLM provider: '{active_llm_key}' for this request.")

        # Get the database context (this is LLM-agnostic or uses its own LLM)
        context = self._get_or_build_context(business_context)

        # Run the main BI orchestrator
        return orchestrator.run(
            question=question, context=context, chat_history=chat_history or []
        )


def create_intelliquery_system(
    database_engine: Engine,
    llm_settings: Dict[str, Any],
    sql_workflow_type: Literal["simple", "reflection"] = "reflection",
    context_llm_key: Optional[str] = None,
    default_agent_llm_key: Optional[str] = None,
    cache_provider: Optional[CacheProvider] = None,
    vis_provider: Optional[VisualizationProvider] = None,
) -> IntelliQuery:
    """
    Factory function to build and configure the complete IntelliQuery system.

    This is the recommended entry point for using the library.

    Args:
        database_engine: An initialized SQLAlchemy Engine.
        llm_settings: Configuration dictionary for nexus-llm.
        sql_workflow_type: The workflow for the SQL agent ('reflection' or 'simple').
        context_llm_key: (Optional) The key of a specific LLM to use for the
                         one-time database context analysis. If None, uses the
                         first available LLM.
        default_agent_llm_key: (Optional) The key of the default LLM to use for
                               agentic tasks. If None, uses the first available LLM.
        cache_provider: (Optional) A cache provider. Defaults to FileSystemCacheProvider.
        vis_provider: (Optional) A visualization provider. Defaults to PlotlyProvider.

    Returns:
        An initialized IntelliQuery instance ready to be used.
    """
    logger.info("Building IntelliQuery system...")

    # Load settings and initialize non-LLM services
    settings: Settings = load_settings(llm_settings)
    llm_provider_keys = list(settings.llm_providers.keys())
    if not llm_provider_keys:
        raise ValueError("No LLM providers found in the settings.")

    cache = cache_provider or FileSystemCacheProvider()
    vis = vis_provider or PlotlyProvider()
    db_service = DatabaseService(engine=database_engine)

    # Configure the LLM for Context Analysis
    context_llm_key = context_llm_key or llm_provider_keys[0]
    logger.info(f"Using '{context_llm_key}' for database context analysis.")
    context_llm_interface = LLMInterface(settings, context_llm_key)
    context_analyzer = DBContextAnalyzer(
        db_service=db_service,
        cache_provider=cache,
        llm_interface=context_llm_interface,
    )

    # Build an orchestrator for EACH available agent LLM provider
    orchestrators: Dict[str, BIOrchestrator] = {}
    for key in llm_provider_keys:
        logger.debug(f"Building agent stack for LLM provider: '{key}'...")
        agent_llm_interface = LLMInterface(settings, key)

        if sql_workflow_type == "reflection":
            sql_workflow = ReflectionWorkflow(agent_llm_interface, db_service)
        else:
            sql_workflow = SimpleWorkflow(agent_llm_interface, db_service)

        sql_agent = SQLAgent(db_service=db_service, workflow=sql_workflow)
        vis_agent = VisualizationAgent(llm_interface=agent_llm_interface, provider=vis)

        orchestrators[key] = BIOrchestrator(
            llm_interface=agent_llm_interface,
            sql_agent=sql_agent,
            vis_agent=vis_agent,
        )
    logger.info(f"Successfully built agent stacks for: {llm_provider_keys}")

    # Create and return the final IntelliQuery handle
    default_key = default_agent_llm_key or llm_provider_keys[0]
    return IntelliQuery(
        context_analyzer=context_analyzer,
        orchestrators=orchestrators,
        default_llm_key=default_key,
    )
