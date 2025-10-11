# IntelliQuery: The Agentic SQL Toolkit

**Turn natural language questions into high-quality, executable SQL queries with a powerful, context-aware AI agent.**

IntelliQuery is a Python toolkit designed to **democratize data access**.
It bridges the gap between complex databases and non-technical users by providing an intelligent orchestration layer that can understand questions, analyze database schemas, and generate accurate SQL.

---

## What is IntelliQuery?

Accessing data from databases often requires specialized knowledge of SQL and a deep understanding of the underlying schema. This creates a bottleneck, limiting data access to a small group of technical experts.

IntelliQuery solves this problem by providing a smart, agent-based system. It uses Large Language Models (LLMs) not just to translate text-to-SQL, but to first build a deep, rich understanding of your database's context. It then uses this context to power an orchestrator that can generate, review, and execute queries, effectively acting as an automated data analyst.

## Key Features

- **Automated, Deep Context Awareness**: IntelliQuery doesn't just look at table and column names. It connects directly to your database, analyzes the schema, and intelligently identifies categorical columns (like `status`, `type`, or `category`). It then fetches the distinct values from these columns to enrich the context, allowing the AI to generate queries with correct `WHERE` clauses (e.g., `WHERE status IN ('shipped', 'delivered')`).
- **Dual Workflow Architecture**: Choose the right tool for the job.
    - **Simple Workflow**: A fast, direct path from question to SQL. Ideal for simpler queries and rapid development.
    - **Reflection Workflow**: A more robust, multi-step process where a "reviewer" AI agent examines the generated SQL for correctness, efficiency, and alignment with the user's intent. It provides feedback for self-correction, resulting in higher-quality, more performant queries.
- **Conversational Memory**: The orchestrator maintains a chat history, allowing users to ask follow-up questions (e.g., "Of those, which ones were sold last month?") and get contextually aware answers.
- **Modular and Extensible**: The core logic is cleanly separated into `core` components (database, analysis), `models` (data structures), and `workflows` (agent logic). This makes the system easy to understand, maintain, and extend with new capabilities.
- **Database Agnostic**: Built on top of SQLAlchemy, IntelliQuery can connect to a wide variety of SQL databases (PostgreSQL, MySQL, SQLite, etc.) with minimal configuration changes.

## Who is this for?

- **Developers**: Quickly embed powerful natural language database querying into your applications.
- **Data Teams**: Build internal tools that allow business analysts, product managers, and other stakeholders to self-serve their data needs without writing SQL.
- **Enterprises**: Create a scalable, reliable layer for natural language interaction with your data warehouses and operational databases.

---

## Getting Started

### 1. Installation

Install IntelliQuery and its core dependencies using pip. For development, include the `[dev]` optional dependencies to get testing and linting tools.

```bash
# For production use
pip install intelliquery

# For development (from the root of the project repository)
pip install -e .[dev]
```

### 2. Configuration

Create a `.env` file in your project root to store your database connection string and LLM API keys.

```.env
# Example for a PostgreSQL database
DATABASE_URL="postgresql://username:password@localhost:5432/your_database"

# Your Google API key for the Gemini model or any other LLM provider
GOOGLE_API_KEY="your_google_api_key_here"
```

Of course, you could use ENV variables instead of a `.env` file.

The library is LLM-agnostic, so you can use any provider that using the [Nexus LLM](https://github.com/Muhammad-Abdelsattar/nexus-llm) interface, you could check it out to see how to configure it easily.

### 3. Core Usage Example

The following example demonstrates the complete end-to-end flow: connecting to the database, building the enriched context, and running the query orchestrator.

```python
import os
from sqlalchemy import create_engine
from nexus_llm import LLMInterface, load_settings
from dotenv import load_dotenv

# Import the core components from IntelliQuery
from intelliquery import (
    QueryOrchestrator,
    DBContextAnalyzer,
    DatabaseService,
)

# Load environment variables from .env file
load_dotenv()

# Setup your LLM interface (e.g., Gemini)
llm_settings = load_settings({ "llm_providers": { "google_gemini": {
    "class_path": "langchain_google_genai.ChatGoogleGenerativeAI",
    "params": { "model": "gemini-1.5-flash", "google_api_key": os.getenv("GOOGLE_API_KEY"), "temperature": 0.1 }
}}})
llm_interface = LLMInterface(settings=llm_settings, provider_key="google_gemini")

# Connect to your database using SQLAlchemy
engine = create_engine(os.getenv("DATABASE_URL"))
db_service = DatabaseService(engine=engine,
                             # schema="public", # Optional: Specify the schema to use
                             )


# This is a one-time (and cached) operation that analyzes your database.
print("Building database context (may take a moment on first run)...")
context_analyzer = DBContextAnalyzer(llm_interface=llm_interface, db_service=db_service)
enriched_context = context_analyzer.build_context(
    business_context="A 'premium' product is one with a price over $200."
)
print("Context is ready!")


# Choose your workflow: "simple" for speed, "reflection" for quality.
orchestrator = QueryOrchestrator(
    llm_interface=llm_interface,
    db_service=db_service,
    workflow_type="reflection"  # Switch to "simple" for the direct workflow
)

# Ask a question!
question = "Show me the names of all premium products in the 'Electronics' category."
chat_history = [] # Keep track of the conversation for follow-ups

result = orchestrator.run(
    question=question,
    context=enriched_context,
    chat_history=chat_history,
    auto_execute=True # Set to False to only generate and validate the SQL
)

# Handle the Result
if result.status == "success":
    print("\n--- Generated SQL ---")
    print(result.sql_query)
    print("\n--- Query Result ---")
    print(result.dataframe.to_string())
    # Update history for the next turn
    chat_history.append((question, result.sql_query))
elif result.status == "clarification_needed":
    print(f"\nAgent needs clarification: {result.clarification_question}")
else:
    print(f"\nAn error occurred: {result.error_message}")
```

The previous is a fairly simple example. You can build much more commplex applications using it.

## Core Concepts Explained

### The Context Engine

The magic of IntelliQuery begins with the `DBContextAnalyzer`. When you call `build_context()`, it performs a sophisticated, multi-step process:

1.  **Schema Extraction**: It retrieves the raw DDL schema from your database.
2.  **Intelligent Analysis (LLM Call)**: It sends this schema to an LLM, asking it to identify columns that are likely to be **categorical** and have a low number of unique values (low cardinality). It is explicitly instructed to ignore IDs, names, and numerical fields.
3.  **Targeted Database Queries**: Based on the LLM's plan, it queries the database to fetch the actual distinct values for the identified columns (e.g., `SELECT DISTINCT status FROM orders`).
4.  **Schema Augmentation**: It injects these values as comments directly into the DDL schema. This provides the main query-generation LLM with invaluable context, dramatically increasing the accuracy of its generated SQL.

This entire enriched context is then cached, so this expensive analysis only needs to be performed once.

### The Orchestrator and Workflows

The `QueryOrchestrator` is your primary interface with the system. Its key responsibility is to manage the flow of information through a chosen workflow.

#### Simple Workflow

When you initialize with `workflow_type="simple"`, the process is linear and fast:

1.  The orchestrator passes the question and context to the `generate_sql_node`.
2.  The LLM generates an SQL query.
3.  If `auto_execute` is `True`, the query is executed against the database.
4.  If the execution fails, it can retry a few times, feeding the error back to the LLM for self-correction.

#### Reflection Workflow

When you initialize with `workflow_type="reflection"`, you activate a more deliberate and powerful process:

1.  The `generate_sql_node` produces an initial SQL query.
2.  The query is then passed to a **`reflection_node`**. This node invokes an LLM acting as a "Senior DBA" or "Performance Expert".
3.  The reviewer agent assesses the query. It can either:
    - **Approve** it, allowing it to proceed to execution.
    - **Request Revisions**, providing specific, actionable feedback (e.g., "This `LEFT JOIN` is unnecessary; an `INNER JOIN` would be more performant.").
4.  If revisions are requested, the feedback is sent back to the `generate_sql_node`, which creates a new, improved query. This loop can run a few times to refine the query.
5.  Only the final, approved query is executed.

This workflow trades a small amount of latency for a significant increase in the quality, correctness, and performance of the final SQL query.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.
