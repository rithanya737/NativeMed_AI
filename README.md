# NativeMed AI

An AI-powered medicinal plant assistant that combines a curated, cited
knowledge base with image-based plant identification. Ask a question in
English, Tamil, Hindi, Malayalam, Telugu, or Kannada (typed or spoken) and
get a grounded answer traceable back to source passages and similarity
scores — or upload/photograph a plant and get it identified against a
130-plant database of traditional medicinal uses.

The project is split into two independently-run apps that talk to each
other over HTTP:

| App        | Tech                  | Port | Role                                             |
|------------|------------------------|------|---------------------------------------------------|
| `backend/` | FastAPI (Python)       | 8000 | RAG chatbot, plant identification (RF-DETR), speech, translation — the single source of truth |
| `frontend/`| Flask (Python) + HTML/JS/CSS | 5000 | User-facing web UI (dashboard, chat, identify, herb gallery, contribute) |

## 1. Architecture

```
 Browser
   │
   ├── Flask frontend (:5000) ── renders pages, proxies image uploads
   │                              to the backend, and (for legacy pages)
   │                              reads/writes a MySQL database directly
   │
   └── Browser JS calls the FastAPI backend (:8000) directly for
       /chat (AI Assistant page) — CORS is open on the backend for this

 FastAPI backend (:8000)
   │
   ├── plants.db (SQLite)        <- source of truth: 130 plants + synonyms
   │        │  rag/ingest.py (one-time / on data change)
   │        ▼
   ├── ChromaDB vector store      <- derived, rebuildable embeddings index
   │        │  rag/retriever.py
   │        ▼
   ├── translate → embed → retrieve top-K passages above similarity threshold
   │        │
   ├── llm/generator.py           <- Ollama (free/local, default) / OpenAI / offline mock
   │        │
   ├── explainability + translate back + optional TTS audio
   │        ▼
   │      JSON response
   │
   └── ml/inference.py            <- RF-DETR image model → /api/identify-plant
```

Key design decisions (see `backend/` source for full detail):

- **SQLite is the source of truth**; ChromaDB is a derived index rebuilt by
  `rag/ingest.py` and can always be safely deleted and regenerated.
- **Anti-hallucination by construction** — retrieval only returns passages
  above a similarity threshold; if nothing clears the bar, the API returns
  a fixed "I don't have enough verified information" answer instead of
  letting the LLM guess.
- **Explainability by construction** — every `/chat` response includes the
  retrieved passages, their similarity scores, and a confidence label
  derived only from retrieval, never the LLM's self-reported confidence.
- **LLM provider is swappable and free by default** — `LLM_PROVIDER=ollama`
  calls a free local model via the Ollama app (no API key, no cost, fully
  private). OpenAI and an offline extractive mock are also supported.

## 2. Repository layout

```
NativeMed-AI/
├── backend/                  FastAPI service — chatbot, plant ID, speech, translation
│   ├── app.py                 Combined app: chatbot + plant-ID routers, CORS, lifespan
│   ├── api/                   Chat/plants/health route definitions + Pydantic schemas
│   ├── routers/plant_id.py    POST /api/identify-plant (image upload → RF-DETR)
│   ├── ml/inference.py        Loads the trained RF-DETR checkpoint
│   ├── models/                Trained model weights + training config
│   ├── database/               SQLite schema, data import, query helpers
│   ├── rag/                    Ingest, embeddings, retriever, prompt building
│   ├── llm/generator.py        Ollama / OpenAI / mock LLM providers
│   ├── translation/            Language detection + translation
│   ├── speech/                 Whisper STT + gTTS TTS
│   ├── explainability/         Confidence scoring from retrieval
│   ├── utils/                  Settings, exceptions, logging
│   ├── tests/                  Pytest unit tests
│   ├── requirements.txt
│   └── .env.example            Copy to .env and fill in your values
│
├── frontend/                  Flask web UI
│   ├── app.py                  Page routes; proxies /api/identify-plant to the backend
│   ├── backend_client.py       Thin HTTP client for the FastAPI backend (list/get plants, chat, identify)
│   ├── config.py                BACKEND_API_URL / timeout / secret key, from env
│   ├── database.py              Legacy MySQL connection helper (see Known issues below)
│   ├── templates/                Jinja2 pages (dashboard, chat, identify herb, explore herbs, contribute, auth)
│   ├── static/{css,js,images}    Front-end assets
│   └── requirements.txt
│
└── Explore Herb/               Reference plant photos used by the gallery/report
```

## 3. Setup

### 3.1 Prerequisites

- Python 3.10+
- `ffmpeg` on your PATH (required by Whisper for audio decoding, backend only)
- MySQL server (only needed for the frontend's `/dashboard` and
  `/explore-herbs` pages — see Known issues)
- Internet access for first-time setup (Hugging Face embedding model
  download, and optionally Ollama/OpenAI/Google Translate/gTTS at runtime)

### 3.2 Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Default LLM_PROVIDER=ollama — install Ollama (https://ollama.com) and run
# `ollama pull llama3.2` once. Prefer no local install? Set LLM_PROVIDER=mock
# for a zero-setup, extractive-only fallback, or LLM_PROVIDER=openai with an
# OPENAI_API_KEY.

python -m database.create_db      # creates database/plants.db schema
python -m database.import_data    # imports the source .xlsx datasets
python -m rag.ingest               # embeds all plants into ChromaDB

uvicorn app:app --reload --port 8000
# or, on Windows: double-click run_backend.bat
```

Open `http://127.0.0.1:8000/docs` for interactive API docs, or
`http://127.0.0.1:8000/health` to confirm readiness.

Run the test suite (mocks every network/ML dependency, runs in seconds):

```bash
pytest tests/ -v
```

### 3.3 Frontend

```bash
cd frontend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The frontend expects the backend running at `http://127.0.0.1:8000` by
default (override via `BACKEND_API_URL` in a `frontend/.env` file — see
`config.py`). The `/dashboard` and `/explore-herbs` pages additionally
require a MySQL database (`MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`,
`MYSQL_DATABASE` env vars — see Known issues below).

```bash
python app.py
```

Visit `http://127.0.0.1:5000`.

## 4. Features

- **AI Assistant** (`/chat`) — RAG-powered chat backed by the 130-plant
  knowledge base, multilingual, with cited sources and a confidence score.
- **Identify Herb** (`/identify-herb`) — upload a photo or capture one live
  from your camera; a trained RF-DETR model identifies the plant and looks
  up its traditional uses.
- **Herb Knowledge** (`/explore-herbs`) — searchable gallery of the full
  plant database.
- **Dashboard** (`/dashboard`) — herb counts and activity overview.
- **Contribute** (`/contribute`) — community contribution page.

## 5. API reference (backend)

| Method | Path                    | Purpose                                             |
|--------|-------------------------|------------------------------------------------------|
| GET    | `/health`               | Readiness/status: LLM provider, DB, vector store     |
| POST   | `/chat`                 | Ask a text question, get a grounded answer + audio   |
| POST   | `/speech`               | Upload audio, transcribe, then run the same pipeline |
| POST   | `/tts`                  | Synthesize speech for arbitrary text                 |
| GET    | `/plants`               | List/search plants                                   |
| GET    | `/plants/{id}`          | Look up a single plant record directly               |
| GET    | `/plants/lookup`        | Resolve a raw ML label to a plant record              |
| POST   | `/api/identify-plant`   | Upload a photo, get the identified plant (RF-DETR)    |
| GET    | `/`                     | Service banner / links to docs and health              |

Every error response has a consistent structured shape:

```json
{ "detail": { "status": "error", "error_type": "RetrievalError", "detail": "..." } }
```

See `http://127.0.0.1:8000/docs` for full request/response schemas.

## 6. Known issues / things to clean up

- **`frontend/database.py` (MySQL) is legacy but still in active use.** Its
  own docstring says it's unused, but `frontend/app.py`'s `/dashboard` and
  `/explore-herbs` routes still call it directly. The rest of the frontend
  (plant lookups, chat, identify) goes through the FastAPI backend instead
  (SQLite-backed). These two routes should either be migrated to
  `backend_client.py` or the MySQL dependency should be documented as a
  hard requirement.
- **`MYSQL_PASSWORD` has a hardcoded fallback value** in
  `frontend/database.py` despite the docstring claiming otherwise —
  rotate/remove that default and require the env var to be set explicitly.
- **`frontend/app.py`'s `/api/identify-plant` and `/api/chat` routes bypass
  `backend_client.py` and `config.py`**, hardcoding `BACKEND_URL` instead of
  reusing the centralized `BACKEND_API_URL` setting. `/api/chat` is also
  currently a placeholder that doesn't call the real backend (the AI
  Assistant page instead calls the FastAPI backend directly from browser
  JS). Worth consolidating so there's exactly one code path per feature.
#   N a t i v e M e d _ A I _ S y s t e m  
 