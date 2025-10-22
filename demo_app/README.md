# IntelliQuery Demo Application

This interactive tool showcases the power of using a natural language interface to query your SQL databases. Ask questions in plain English, and our AI-powered agent will translate them into SQL, execute the query, and deliver the results.

## Key Features

- **Natural Language to SQL:** Ask questions like "Which 5 customers had the highest sales last month?"
- **Smart Context Analysis:** The agent analyzes your database schema to understand table relationships, column types, and even the kinds of low cardinality categorical values stored in certain columns.
- **AI-Powered Reflection:** An optional "reflection" workflow allows a second AI expert to review and improve the generated SQL for maximum performance and accuracy.
- **Full Transparency:** See the agent's reasoning and the exact SQL query it generated for every answer, building trust and allowing for verification.
- **Interactive Chat Interface:** Engage in a conversational back-and-forth, asking follow-up questions to refine your results.

## Getting Started

### Prerequisites

- Python 3.10+
- An SQL database (PostgreSQL, MySQL, SQLite, etc.)

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/muhammad-abdelsattar/intelliquery.git
    cd intelliquery
    ```

2.  **Create a virtual environment (recommended):**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the core IntelliQuery library:**
    From the root of the project (`intelliquery/`), install the library in editable mode. This makes the demo app aware of the main toolkit's code.

    ```bash
    pip install -e .
    ```

4.  **Install Demo App dependencies:**
    Now, navigate to the demo application directory and install its specific requirements.

    ```bash
    cd demo_app
    pip install -r requirements.txt
    ```

5.  **Configure your LLM providers:**
    In the `demo_app` directory, rename `llm_providers.yaml.example` to `llm_providers.yaml`. Edit this file to configure your preferred LLM provider (e.g., Google Gemini, OpenAI). You will need to set the corresponding API key (e.g., `GOOGLE_API_KEY`) as an environment variable or in a `.env` file within the `demo_app` directory.

6.  **Set up your database credentials:**
    For security, **do not** write your database password directly into the connection URL. Instead, use Streamlit's Secrets management.

    1.  Create a file at `.streamlit/secrets.toml`.
    2.  Store your credentials there, like this: `DB_PASSWORD = "my_secret_password"`.
    3.  In the Database URL field in the app, reference the secret using the `${...}` syntax:
        `postgresql://user:${DB_PASSWORD}@host:port/dbname`

### Running the Application

Once you have installed the dependencies and configured your settings, run the application from the `demo_app` directory:

```bash
streamlit run main.py
```

## Usage

### 1. Manage Connections

- Before you can chat with your data, you need to add a database connection.
- Navigate to the **Manage Connections** page from the sidebar.
- Fill out the form to add a new connection, providing a name, dialect, URL, and optional settings like included tables and business context.
- Click **Save & Analyze Connection**. This will test the connection and analyze your database schema to build an "enriched context" for the AI agent.

### 2. Start Chatting

- Once a connection is active, go to the **Chat** page.
- Use the sidebar to configure the session controls:
    - **AI Model:** Choose from the LLMs you configured.
- Type your question in the chat input box and press Enter.

### 3. Understand the Results

- The agent will show you the data in an interactive table and an interactive chart if applicable.
- You can download the results as a CSV file.
- The **Show Details** expander reveals the agent's reasoning and the final SQL query.

## Project Structure

```
/
├───.connections.json           # Stores saved database connections
├───llm_providers.yaml          # Configuration for LLM providers
├───main.py                     # Main Streamlit application file
├───README.md                   # This file
├───state.py                    # Manages the application's session state
├───.cache/                     # Caches database context analysis
├───.chat_history/              # Stores chat history for each session
├───services/
│   ├───chat_service.py         # Handles chat history and conversation logic
│   ├───connection_service.py   # Manages database connections and credentials
│   └───llm_service.py          # Interface for interacting with LLMs
└───ui_components/
    ├───chat_renderer.py        # Renders the chat messages and results
    └───sidebar.py              # Builds the main navigation sidebar
```

## Tips for a Great Experience

- **Be Specific:** The more specific your question, the better the result. Instead of "show users," try "show me the email addresses of the first 5 users who signed up in May 2024."
- **Use Follow-up Questions:** The agent remembers the context of the conversation. If you get a list of products, you can ask a follow-up like, "Of those, which one has the highest profit?"
- **Leverage Business Context:** Use the context box to teach the agent your company's jargon. Defining terms like "ARR" or "active user" will dramatically improve the agent's accuracy.
