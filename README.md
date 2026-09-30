# AI-Powered Business Database Assistant

Stage 1 provides the SQLite database foundation. Stage 2 adds the controlled database tools and parser-backed SQL safety layer. Stage 3 adds the LangGraph/Ollama tool-calling agent and Streamlit frontend.

## Requirements

- Python 3.11 or newer
- Windows PowerShell or Command Prompt

## Setup on Windows

From the project root, create a virtual environment:

```powershell
py -3.11 -m venv venv
```

Activate it in PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Or activate it in Command Prompt:

```bat
venv\Scripts\activate.bat
```

Install the current stage dependencies:

```powershell
python -m pip install -r requirements.txt
```

Stage 3 requires Pydantic, SQLGlot, LangGraph, LangChain Core, LangChain Ollama, the Ollama Python package, and Streamlit.

## Initialize the database

Run this from the project root:

```powershell
python -m db.init_db
```

This creates `data/insurance.db`, applies `db/schema.sql`, and loads `db/seed.sql` when the database contains no data. Re-running the command is safe and does not duplicate the seed records.

## Verify the database

Run the verification tests:

```powershell
python -m unittest tests.test_database_setup -v
```

Run the complete test suite with:

```powershell
python -m unittest discover -v
```

The checks confirm that the database opens, all five application tables exist, the supplied seed data is present, basic parameterized `SELECT` queries work, and unsafe SQL is rejected before SQLite execution.

## Run the Stage 3 Streamlit app with Ollama

Start Ollama and confirm the model is available:

```powershell
ollama serve
ollama list
```

If needed, download the model:

```powershell
ollama pull qwen3:1.7b
```

Then start the Streamlit app:

```powershell
streamlit run app.py
```

Open the local URL shown by Streamlit, usually `http://localhost:8501`. The frontend keeps the current conversation in the Streamlit session and displays safe tool-call metadata for each answer.
