@echo off
REM Starts the combined NativeMed AI backend (app.py) on http://127.0.0.1:8000
REM Includes BOTH the chatbot API (/chat, /speech, /tts, /plants/{id})
REM AND the plant-identification API (/api/identify-plant) on one port.
REM Uses the free local Ollama LLM provider by default -- see .env
REM (LLM_PROVIDER=ollama). Make sure Ollama is installed and running, and
REM that you've run `ollama pull llama3.2` at least once.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
uvicorn app:app --reload --port 8000
pause
