# IntelliQuery Demo Application: User Guide

Welcome to IntelliQuery! This guide will walk you through the features of the IntelliQuery demo application and show you how to connect to your database and start asking questions in plain English.

## 1. What is IntelliQuery?

IntelliQuery is an intelligent AI assistant designed to help you interact with your SQL databases using natural language. Instead of writing complex SQL code, you can simply ask questions, and IntelliQuery's advanced agent will translate your request into a precise, performant SQL query, run it, and show you the results.

**Key Features:**

- **Natural Language to SQL:** Ask questions like "Which 5 customers had the highest sales last month?"
- **Smart Context Analysis:** The agent analyzes your database schema to understand table relationships, column types, and even the kinds of low cardinality categorical values stored in certain columns.
- **AI-Powered Reflection:** An optional "reflection" workflow allows a second AI expert to review and improve the generated SQL for maximum performance and accuracy.
- **Full Transparency:** See the agent's reasoning and the exact SQL query it generated for every answer, building trust and allowing for verification.
- **Interactive Chat Interface:** Engage in a conversational back-and-forth, asking follow-up questions to refine your results.

## 2. Getting Started: The Sidebar

The sidebar is your main control panel, accessible from every page. It's where you manage connections and conversations.

![sidebar](./assets/sidebar.png)

### Database Connection

This is the most important section. An active connection is required to chat with your data.

- **Dropdown Menu:** Select from a list of your saved database connections. The currently active one will be displayed.
- **Manage Connections Button:** This will take you to the **Connection Manager** page, where you can add new connections or edit existing ones.

### Chat History

- **➕ New Chat Button:** Starts a fresh conversation with the currently active database connection.
- **Load Past Chat Expander:** Click to view and load your previous conversations. The app will automatically restore the chat history and its associated database connection.

## 3. Managing Your Connections

Before you can start a chat, you need to tell IntelliQuery how to connect to your database. This is done on the **Connection Manager** page.

 <!-- Screenshot of the Connection Manager page -->

### Adding a New Connection

1.  Navigate to the **Connection Manager** page from the sidebar.
2.  Fill out the "Add New Connection" form on the right:
    - **Connection Name:** A friendly, unique name (e.g., "Production Analytics DB").
    - **Database Dialect:** The type of your database (e.g., PostgreSQL).
    - **Database URL:** The connection string for your database.
    - **Include Tables (Optional):** A comma-separated list of tables you want the agent to focus on. If left blank, all tables will be included.
    - **Default Business Context (Optional):** Provide any business rules or definitions here (e.g., "A 'premium' customer is one who has spent over $1000.").

### Securing Your Credentials

For security, **do not** write your database password directly into the URL. Instead, use Streamlit's Secrets management.

1.  Create a file at `.streamlit/secrets.toml`.
2.  Store your credentials there, like this: `DB_PASSWORD = "my_secret_password"`.
3.  In the Database URL field, reference the secret using the `${...}` syntax:
    `postgresql://user:${DB_PASSWORD}@host:port/dbname`

### Saving and Analyzing

Clicking **"Save & Analyze Connection"** will:

1.  Test the database connection.
2.  Run the AI agent to analyze your database schema. This builds a cached "enriched context" that helps the agent generate better queries. This step may take a moment on the first run for a new connection.
3.  Save the connection configuration for future use.

## 4. The Chat Interface

This is where the magic happens! Once you have an active connection, you can start asking questions on the **Chat** page.

 <!-- Screenshot of the Chat Interface -->

### Session Controls (in the Sidebar)

These controls apply only to the current chat session.

- **Agent Mode:**
    - **Execute:** The default mode. The agent generates SQL and immediately runs it against your database to fetch results.
    - **Plan:** A safe mode. The agent will generate and validate the SQL query but will **not** execute it. This is useful for reviewing the agent's plan before running a potentially long query.
- **Workflow:**
    - **Simple:** The agent generates a query and executes it.
    - **Reflection:** A more advanced, two-step process. The first AI generates a query, and a second "expert" AI reviews and refines it for accuracy and performance before it's used.
- **Current Chat's Business Context:** You can add or modify business rules that apply _only_ to the current conversation. This overrides the default context set on the connection.

### Asking a Question

1.  Type your question in plain English into the input box at the bottom.
2.  Press Enter.
3.  Watch the real-time status updates as the agent works through its process (generating, reviewing, executing).

### Understanding the Results

The agent's response is more than just data.

- **The Data:** If your query returns data, it will be displayed in an interactive table.
- **Download as CSV:** A button located directly below the data table allows you to download the results for use in other tools.
- **Show Details Expander:**
    - **Agent's Reasoning Tab:** Read the agent's step-by-step explanation of how it understood your question and constructed the SQL query.
    - **SQL Query Tab:** View the final, beautifully formatted SQL query that was executed.

## 5. Tips for a Great Experience

- **Be Specific:** The more specific your question, the better the result. Instead of "show users," try "show me the email addresses of the first 5 users who signed up in May 2024."
- **Use Follow-up Questions:** The agent remembers the context of the conversation. If you get a list of products, you can ask a follow-up like, "Of those, which one has the highest profit?"
- **Leverage Business Context:** Use the context box to teach the agent your company's jargon. Defining terms like "ARR" or "active user" will dramatically improve the agent's accuracy.

---
