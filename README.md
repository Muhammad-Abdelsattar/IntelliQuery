# IntelliQuery: The Agentic BI & Visualization Toolkit

**Go from natural language questions to data, insights, and visualizations with a powerful, context-aware AI agent.**

IntelliQuery is a Python toolkit designed to **democratize data access**. It provides a complete, agentic Business Intelligence (BI) system that understands user questions, orchestrates complex data retrieval, synthesizes insights, and generates interactive visualizations.

---

🚀 **Want to see it in action?** Check out our interactive [Streamlit Demo Application](./demo_app/README.md) to try IntelliQuery with your own database right in your browser.

---

## What is IntelliQuery?

IntelliQuery is not just a text-to-SQL tool; it's an **automated data analyst**. It uses a sophisticated orchestration agent that manages a team of specialized sub-agents to handle the entire lifecycle of a data query:

1.  **Understanding Intent**: The main BI agent parses the user's question, understands the core intent (whether it's asking for a number, a list, or a chart), and maintains conversational context.
2.  **Enriching Context**: It intelligently analyzes your database schema to understand not just tables and columns, but the actual data within them, leading to far more accurate queries.
3.  **Generating SQL**: It delegates the task of writing SQL to a specialized agent, which can operate in a fast, direct mode or a more robust "reflection" mode where a second AI reviews the query for quality and performance.
4.  **Executing & Analyzing**: It runs the query and analyzes the resulting data.
5.  **Generating Visualizations**: If requested, it passes the data to a visualization agent that chooses and creates the most effective chart to represent the information.
6.  **Synthesizing Answers**: Finally, the main BI agent provides a complete, natural language answer summarizing the findings, along with the underlying data and visualizations.

## Key Features

- **Agentic BI Orchestrator**: A high-level agent understands user intent, breaks down questions, and coordinates specialized sub-agents (for SQL and visualizations) to deliver a complete answer.
- **Automated, Deep Context Awareness**: IntelliQuery connects directly to your database, analyzes the schema, and intelligently fetches distinct values for categorical columns (like `status`, `type`). This enriches the context, allowing the AI to generate queries with correct `WHERE` clauses (e.g., `WHERE status IN ('shipped', 'delivered')`).
- **Integrated Visualization Agent**: Don't just get tables of data. Ask for a "bar chart," "line graph," or "pie chart," and the system will generate an interactive Plotly visualization for you.
- **Robust SQL Generation with Reflection**: Choose the right SQL generation workflow for the job.
- **Conversational Memory**: The system maintains a chat history, allowing users to ask follow-up questions (e.g., "Of those, which ones were sold last month?") and get contextually aware answers.
- **Database Agnostic**: Built on top of SQLAlchemy, IntelliQuery can connect to a wide variety of SQL databases (PostgreSQL, MySQL, SQLite, etc.).

## Who is this for?

- **Developers**: Quickly embed powerful natural language data analysis and visualization into your applications.
- **Data Teams**: Build internal tools that allow business analysts, product managers, and other stakeholders to self-serve their data needs without writing SQL.
- **Enterprises**: Create a scalable, reliable layer for natural language interaction with your data warehouses and operational databases.

---

## Getting Started

### 1. Installation

Install IntelliQuery and its core dependencies using pip.

```bash
# For production use
pip install "git+https://github.com/Muhammad-Abdelsattar/IntelliQuery.git#egg=intelliquery"
```

### 2. Configuration

Create a `.env` file in your project root to store your database connection string and LLM API keys.

```.env
# Example for a PostgreSQL database
DATABASE_URL="postgresql://username:password@localhost:5432/your_database"

# Your Google API key for the Gemini model or any other LLM provider
GOOGLE_API_KEY="your_google_api_key_here"
```

The library is LLM-agnostic and uses the [Nexus LLM](https://github.com/Muhammad-Abdelsattar/nexus-llm) interface. You can configure multiple providers in a dictionary or a YAML file.

> Note: You should install the database drivers for your chosen database. For example, to use PostgreSQL, you would run `pip install psycopg2-binary`.

### 3. Core Usage Example

The following example demonstrates the recommended end-to-end flow using the `create_intelliquery_system` facade to get an insight, the data, and a visualization.

```python
import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Import the main factory function from IntelliQuery
from intelliquery import create_intelliquery_system, BIResult

# Load environment variables from .env file
load_dotenv()

# Define LLM and Database configurations
llm_settings = {
    "llm_providers": {
        "google_gemini": {
            "class_path": "langchain_google_genai.ChatGoogleGenerativeAI",
            "params": {
                "model": "gemini-2.5-flash",
                "google_api_key": os.getenv("GOOGLE_API_KEY"),
                "temperature": 0.1,
            },
        }
    }
}
engine = create_engine(os.getenv("DATABASE_URL"))

# Create the IntelliQuery System
# This factory function initializes all components and analyzes database context on first run.
print("Initializing IntelliQuery system...")
intelliquery_system = create_intelliquery_system(
    database_engine=engine,
    llm_settings=llm_settings,
    sql_workflow_type="reflection",  # Use "reflection" for quality, "simple" for speed
)
print("System is ready!")

# Ask a question that requires data, insight, and a visualization
question = "What is the total revenue per product category? Also, create a bar chart to visualize this."
chat_history = []  # Keep track of the conversation for follow-ups

result: BIResult = intelliquery_system.ask(
    question=question,
    chat_history=chat_history,
)

# Handle the rich BIResult object
if result.status == "success":
    print("\n--- Agent's Answer ---")
    print(result.final_answer)

    if result.sql_query:
        print("\n--- Generated SQL ---")
        print(result.sql_query)

    if result.dataframe is not None:
        print("\n--- Retrieved Data ---")
        print(result.dataframe.to_string())

    if result.visualization:
        print("\n--- Visualization Generated ---")
        print("A Plotly figure object has been created. To display it, you would use:")
        print("# result.visualization.show()")
        # To save it to a file:
        # result.visualization.write_html("chart.html")

    # Update history for the next turn
    if result.final_answer:
        chat_history.append((question, result.final_answer))

elif result.status == "clarification_needed":
    print(f"\nAgent needs clarification: {result.final_answer}")
else:
    print(f"\nAn error occurred: {result.error_message}")

```

## Core Concepts Explained

### The Context Engine

The magic of IntelliQuery begins with the `DBContextAnalyzer`. When the system is first initialized, it performs a sophisticated, multi-step process to build a deep understanding of your data, which is then cached for performance. This involves schema extraction, intelligent LLM-based analysis to find categorical columns, and targeted queries to fetch their unique values, which are then injected back into the schema as comments.

### The Agentic BI Workflow

The `IntelliQuery` system, created via `create_intelliquery_system`, is your primary interface. It manages a complete, multi-agent workflow:

1.  **Orchestration**: The top-level **BI Orchestrator** receives the user's question. It analyzes the intent and determines the sequence of actions needed.

2.  **Delegation to SQL Agent**: The orchestrator passes a context-aware question to the **SQL Agent**. This agent's sole focus is to generate the best possible SQL query. You configure its behavior (`simple` or `reflection`) when you create the main system.

3.  **Data Retrieval**: The generated SQL is executed, and the resulting data (as a pandas DataFrame) is returned to the orchestrator.

4.  **Delegation to Visualization Agent**: If the user's request included a visualization, the orchestrator now passes the DataFrame and the original intent to the **Visualization Agent**. This agent selects the best chart type and generates an interactive visualization object (e.g., a Plotly figure).

5.  **Final Response Synthesis**: The orchestrator gathers all the artifacts—the natural language insight, the data, the SQL query, and the visualization—and packages them into a single, comprehensive `BIResult` object for you to use.

This multi-agent, orchestrated approach ensures that each part of the problem is handled by a specialized component, leading to higher quality and more comprehensive results than a simple text-to-SQL model.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.
