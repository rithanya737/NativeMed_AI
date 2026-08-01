# NativeMed AI

**NativeMed AI** is an AI-powered medicinal plant assistant that combines a curated, cited knowledge base with image-based plant identification.

Users can ask questions in **English, Tamil, Hindi, Malayalam, Telugu, or Kannada**, either by typing or speaking, and receive grounded answers that are traceable to source passages and similarity scores. Users can also upload or capture a plant image and identify it against a database of **130 medicinal plants** containing traditional medicinal knowledge and uses.

The system is divided into two independently running applications that communicate over HTTP:

| Application | Technology                   |   Port | Role                                                                                          |
| ----------- | ---------------------------- | -----: | --------------------------------------------------------------------------------------------- |
| `backend/`  | FastAPI (Python)             | `8000` | RAG chatbot, plant identification (RF-DETR), speech, translation — the single source of truth |
| `frontend/` | Flask (Python) + HTML/JS/CSS | `5000` | User-facing web UI — dashboard, chat, plant identification, herb gallery, and contribution    |

---

# 1. Architecture

```text
                              Browser
                                 │
                 ┌───────────────┴────────────────┐
                 │                                │
                 ▼                                ▼
      Flask Frontend (:5000)          FastAPI Backend (:8000)
      - Renders web pages             - RAG chatbot
      - Proxies image uploads         - Plant identification
      - Legacy MySQL access           - Speech processing
                                      - Translation
                                      - API services
                                                │
                                                ▼
                                      ┌───────────────────┐
                                      │    plants.db      │
                                      │      SQLite       │
                                      │                   │
                                      │  Source of truth  │
                                      │  130 plants +     │
                                      │  synonyms         │
                                      └─────────┬─────────┘
                                                │
                                         rag/ingest.py
                                       (one-time / updates)
                                                │
                                                ▼
                                      ┌───────────────────┐
                                      │     ChromaDB      │
                                      │   Vector Store    │
                                      │                   │
                                      │ Derived / rebuildable
                                      │ embedding index   │
                                      └─────────┬─────────┘
                                                │
                                       rag/retriever.py
                                                │
                                                ▼
                                  Translate → Embed → Retrieve
                                  Top-K passages above threshold
                                                │
                                                ▼
                                      ┌───────────────────┐
                                      │ llm/generator.py  │
                                      │                   │
                                      │ Ollama / OpenAI   │
                                      │ / Offline Mock    │
                                      └─────────┬─────────┘
                                                │
                                  Explainability + Translation
                                      + Optional TTS Audio
                                                │
                                                ▼
                                          JSON Response

                                      ┌───────────────────┐
                                      │  ml/inference.py  │
                                      │                   │
                                      │ RF-DETR Image     │
                                      │ Model Inference   │
                                      └─────────┬─────────┘
                                                │
                                                ▼
                                   /api/identify-plant
```

### Key Design Decisions

#### 1. SQLite as the Source of Truth

**SQLite** is the authoritative database containing the 130 medicinal plants and their synonyms.

**ChromaDB** is only a derived vector index. It can safely be deleted and regenerated using:

```bash
python -m rag.ingest
```

#### 2. Anti-Hallucination by Construction

The retrieval pipeline only accepts passages whose similarity score exceeds a predefined threshold.

If no passage meets the required threshold, the API returns a fixed response:

> "I don't have enough verified information."

This prevents the LLM from generating unsupported answers.

#### 3. Explainability by Construction

Every `/chat` response includes:

* Retrieved source passages
* Similarity scores
* Retrieval-based confidence label

The confidence score is calculated from the **retrieval results**, not from the LLM's self-reported confidence.

#### 4. Swappable LLM Providers

The LLM provider can be changed without modifying the overall architecture.

The default configuration uses:

```text
LLM_PROVIDER=ollama
```

Ollama provides a free, local, and private LLM without requiring an API key.

Other supported providers include:

* **Ollama** — free/local
* **OpenAI** — API-based
* **Mock provider** — offline extractive fallback

---

# 2. Repository Layout

```text
NativeMed-AI/
│
├── backend/
│   ├── app.py
│   │   └── Combined FastAPI application:
│   │       chatbot + plant identification routers,
│   │       CORS, and application lifespan
│   │
│   ├── api/
│   │   └── Chat, plant, health route definitions
│   │       and Pydantic schemas
│   │
│   ├── routers/
│   │   └── plant_id.py
│   │       └── POST /api/identify-plant
│   │           Image upload → RF-DETR
│   │
│   ├── ml/
│   │   └── inference.py
│   │       └── Loads the trained RF-DETR checkpoint
│   │
│   ├── models/
│   │   └── Trained model weights + training configuration
│   │
│   ├── database/
│   │   └── SQLite schema, data import, and query helpers
│   │
│   ├── rag/
│   │   └── Ingestion, embeddings, retrieval,
│   │       and prompt building
│   │
│   ├── llm/
│   │   └── generator.py
│   │       └── Ollama / OpenAI / Mock LLM providers
│   │
│   ├── translation/
│   │   └── Language detection + translation
│   │
│   ├── speech/
│   │   └── Whisper STT + gTTS TTS
│   │
│   ├── explainability/
│   │   └── Confidence scoring from retrieval
│   │
│   ├── utils/
│   │   └── Settings, exceptions, and logging
│   │
│   ├── tests/
│   │   └── Pytest unit tests
│   │
│   ├── requirements.txt
│   └── .env.example
│       └── Copy to .env and configure values
│
├── frontend/
│   ├── app.py
│   │   └── Flask page routes
│   │       + /api/identify-plant proxy
│   │
│   ├── backend_client.py
│   │   └── HTTP client for FastAPI backend
│   │       - List/get plants
│   │       - Chat
│   │       - Plant identification
│   │
│   ├── config.py
│   │   └── BACKEND_API_URL / timeout / secret key
│   │
│   ├── database.py
│   │   └── Legacy MySQL connection helper
│   │
│   ├── templates/
│   │   └── Jinja2 pages:
│   │       dashboard
│   │       chat
│   │       identify herb
│   │       explore herbs
│   │       contribute
│   │       authentication
│   │
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   │
│   └── requirements.txt
│
├── Explore Herb/
│   └── Reference plant photos used by
│       the gallery and project report
│
└── README.md
```

---

# 3. Setup

## 3.1 Prerequisites

The following software and services are required:

* **Python 3.10+**
* **FFmpeg** added to the system `PATH`

  * Required by Whisper for audio decoding
  * Backend only
* **MySQL Server**

  * Required only for the frontend `/dashboard` and `/explore-herbs` pages
  * See the Known Issues section
* **Internet access**

  * Required during first-time setup for:

    * Hugging Face embedding model download
    * Optional Ollama/OpenAI services
    * Google Translate
    * gTTS at runtime

---

# 3.2 Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create the environment file:

```bash
cp .env.example .env
```

### LLM Configuration

The default provider is:

```env
LLM_PROVIDER=ollama
```

Install Ollama and pull the model once:

```bash
ollama pull llama3.2
```

For a zero-setup offline fallback:

```env
LLM_PROVIDER=mock
```

For OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key
```

### Initialize the Database

Create the SQLite database schema:

```bash
python -m database.create_db
```

Import the source `.xlsx` datasets:

```bash
python -m database.import_data
```

Build the ChromaDB vector index:

```bash
python -m rag.ingest
```

### Start the Backend

```bash
uvicorn app:app --reload --port 8000
```

On Windows, you can alternatively use:

```text
run_backend.bat
```

### Backend URLs

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

Health check:

```text
http://127.0.0.1:8000/health
```

### Run Tests

The test suite mocks network and ML dependencies and should complete within seconds:

```bash
pytest tests/ -v
```

---

# 3.3 Frontend Setup

Navigate to the frontend directory:

```bash
cd frontend
```

Create a virtual environment:

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

The frontend expects the FastAPI backend to run at:

```text
http://127.0.0.1:8000
```

This can be overridden using:

```env
BACKEND_API_URL=http://127.0.0.1:8000
```

inside `frontend/.env`.

The following frontend pages additionally require MySQL:

* `/dashboard`
* `/explore-herbs`

Required MySQL environment variables:

```env
MYSQL_HOST=
MYSQL_USER=
MYSQL_PASSWORD=
MYSQL_DATABASE=
```

Start the Flask frontend:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

---

# 4. Features

## AI Assistant

**Route:** `/chat`

* RAG-powered conversational assistant
* 130-plant medicinal knowledge base
* Supports multiple regional languages
* Text and speech interaction
* Source citations
* Retrieved passage display
* Similarity scores
* Retrieval-based confidence score

## Identify Herb

**Route:** `/identify-herb`

Users can:

* Upload a plant image
* Capture an image using the device camera
* Identify the plant using the trained **RF-DETR** model
* Retrieve the corresponding medicinal information

## Herb Knowledge

**Route:** `/explore-herbs`

Provides:

* Searchable plant gallery
* Complete 130-plant database
* Plant images
* Medicinal knowledge

## Dashboard

**Route:** `/dashboard`

Provides:

* Herb count
* Activity overview
* System-level information

## Contribute

**Route:** `/contribute`

Provides a community contribution interface for adding or sharing medicinal plant knowledge.

---

# 5. API Reference

The FastAPI backend provides the following endpoints:

| Method | Endpoint              | Purpose                                                                    |
| ------ | --------------------- | -------------------------------------------------------------------------- |
| `GET`  | `/health`             | Returns service readiness, LLM provider, database, and vector-store status |
| `POST` | `/chat`               | Accepts a text question and returns a grounded answer with optional audio  |
| `POST` | `/speech`             | Uploads audio, performs speech-to-text, and runs the same RAG pipeline     |
| `POST` | `/tts`                | Converts arbitrary text into speech                                        |
| `GET`  | `/plants`             | Lists or searches medicinal plants                                         |
| `GET`  | `/plants/{id}`        | Retrieves a single plant record                                            |
| `GET`  | `/plants/lookup`      | Resolves a raw ML label to a plant record                                  |
| `POST` | `/api/identify-plant` | Uploads a plant image and identifies it using RF-DETR                      |
| `GET`  | `/`                   | Service banner with links to documentation and health status               |

### Error Response Format

All API errors follow a consistent structured format:

```json
{
  "detail": {
    "status": "error",
    "error_type": "RetrievalError",
    "detail": "..."
  }
}
```

For complete request and response schemas, open:

```text
http://127.0.0.1:8000/docs
```

---

# 6. Known Issues and Recommended Cleanup

## 6.1 Legacy MySQL Dependency

`frontend/database.py` is described as legacy and unused in its own documentation. However, the following routes in `frontend/app.py` still access it directly:

* `/dashboard`
* `/explore-herbs`

The rest of the frontend uses the FastAPI backend, which is backed by SQLite.

### Recommended Solution

Migrate the remaining MySQL-dependent routes to `backend_client.py`.

This would allow the entire application to use the FastAPI backend and SQLite as the single source of truth.

---

## 6.2 Hardcoded MySQL Password Fallback

`frontend/database.py` currently contains a hardcoded fallback value for `MYSQL_PASSWORD`, despite its documentation indicating that the password should come from environment variables.

### Recommended Solution

Remove the hardcoded fallback and require:

```env
MYSQL_PASSWORD=your_password
```

to be explicitly configured.

---

## 6.3 Duplicate Backend URL Configuration

The following routes in `frontend/app.py` currently bypass `backend_client.py` and `config.py`:

* `/api/identify-plant`
* `/api/chat`

They use a hardcoded `BACKEND_URL` instead of the centralized:

```env
BACKEND_API_URL
```

### Recommended Solution

Use the centralized backend configuration and `backend_client.py` consistently.

This will ensure that each feature has a single communication path to the FastAPI backend.

---

# 7. System Design Summary

NativeMed AI follows a modular, offline-friendly architecture in which:

```text
                    NativeMed AI
                         │
          ┌──────────────┴──────────────┐
          │                             │
     AI Assistant                 Plant Identification
          │                             │
       RAG Pipeline                  RF-DETR
          │                             │
    SQLite + ChromaDB             Image Inference
          │                             │
          └──────────────┬──────────────┘
                         │
                  FastAPI Backend
                         │
                  HTTP Communication
                         │
                  Flask Frontend
                         │
                       User
```

The core principle is that **SQLite remains the source of truth**, while ChromaDB provides a rebuildable retrieval index and RF-DETR handles image-based plant identification.

This architecture provides:

* **Grounded AI responses**
* **Reduced hallucination**
* **Explainable retrieval**
* **Multilingual interaction**
* **Image-based plant identification**
* **130-plant medicinal knowledge base**
* **Modular backend services**
* **Swappable LLM providers**
* **Local/offline LLM capability through Ollama**
* **Independent frontend and backend deployment**
