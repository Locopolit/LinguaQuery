# AskBase (LinguaQuery) 💎

AskBase is a premium, AI-powered PostgreSQL database workbench designed with a high-end "control room" aesthetic. It leverages Natural Language Processing (via Ollama) to translate plain English into optimized SQL queries, providing a transparent and efficient way to interact with your data.

## ✨ Features

- **Natural Language to SQL**: Generate complex PostgreSQL queries using simple English commands.
- **Dynamic Schema Introspection**: Automatically detects your database schema (tables, columns, types) to provide context-aware query generation.
- **Glassmorphism UI**: A stunning, moody dark-mode interface inspired by modern "control room" dashboards.
- **Real-time Results**: Execute generated queries and view results instantly in an interactive table format.
- **Auto-Initialization**: Automatically sets up a sample `emp` (employee) table if your database is empty, allowing you to get started immediately.

## 🛠 Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python), [asyncpg](https://github.com/MagicStack/asyncpg) (PostgreSQL client)
- **Frontend**: [React](https://reactjs.org/), [Tailwind CSS](https://tailwindcss.com/) (Styling), [Radix UI](https://www.radix-ui.com/) (Primitives), [Lucide](https://lucide.dev/) (Icons)
- **AI/LLM**: [Ollama](https://ollama.com/) (Local LLM hosting)
- **Database**: [PostgreSQL](https://www.postgresql.org/)

## 🚀 Getting Started

### Prerequisites

1.  **PostgreSQL**: Ensure you have a running PostgreSQL instance.
2.  **Ollama**: Install Ollama and pull the required model:
    ```bash
    ollama pull gemma4:e4b
    ```

### Backend Setup

1.  Navigate to the `backend` directory:
    ```bash
    cd backend
    ```
2.  Activate the virtual environment:
    ```bash
    source venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Configure environment variables in `.env`:
    - `DATABASE_URL`: Your PostgreSQL connection string.
    - `OLLAMA_MODEL`: The model name pulled in Ollama (default: `gemma4:e4b`).

5.  Start the server:
    ```bash
    uvicorn server:app --reload
    ```

### Frontend Setup

1.  Navigate to the `frontend` directory:
    ```bash
    cd frontend
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Start the application:
    ```bash
    npm start
    ```

## 📐 Design Guidelines

The application follows strict glassmorphism rules for a premium feel. All components use the **Outfit** font for headings and **Work Sans** for body text. Generated queries are displayed in **JetBrains Mono**.

## 🧪 Testing

Interactive elements include `data-testid` attributes for automated testing. You can run tests using:
- **Backend Tests**: `pytest backend_test.py`
- **Frontend Tests**: `npm test`