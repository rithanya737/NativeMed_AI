"""
API routes for NativeMed AI.

Chat endpoint workflow (per spec):

    Receive text or audio
        -> Speech-to-text (if needed)
        -> Language detection
        -> Translation (if needed)
        -> Embedding
        -> Retriever
        -> Prompt construction
        -> LLM
        -> Explainability
        -> Translation back
        -> Text-to-Speech
        -> JSON response
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    PlantListResponse,
    PlantLookupResponse,
    PlantResponse,
    SpeechChatResponse,
    TTSRequest,
    TTSResponse,
)
from database.database import find_plant_by_any_name, get_plant_by_id, search_plants
from explainability.evidence import build_evidence
from llm.generator import NO_EVIDENCE_ANSWER, generate_answer
from rag.prompts import build_user_prompt
from rag.retriever import retrieve
from speech.stt import transcribe_audio
from speech.tts import synthesize_speech
from translation.translator import translate_from_english, translate_to_english
from utils.config import get_settings
from utils.exceptions import (
    CSVImportError,
    DatabaseError,
    InvalidAudioFileError,
    LLMError,
    NativeMedError,
    PlantNotFoundError,
    RetrievalError,
    SpeechToTextError,
    TextToSpeechError,
    TranslationError,
    UnsupportedLanguageError,
)
from utils.logger import logger

router = APIRouter()

# Maps each custom exception type to the HTTP status code it should produce.
# Checked in order, most-specific first (UnsupportedLanguageError before its
# parent TranslationError).
_EXCEPTION_STATUS_MAP: list[tuple[type[NativeMedError], int]] = [
    (PlantNotFoundError, 404),
    (UnsupportedLanguageError, 400),
    (InvalidAudioFileError, 400),
    (CSVImportError, 500),
    (DatabaseError, 503),
    (RetrievalError, 503),
    (SpeechToTextError, 422),
    (TextToSpeechError, 500),
    (TranslationError, 502),
    (LLMError, 502),
]


def _status_code_for(exc: NativeMedError) -> int:
    for exc_type, status_code in _EXCEPTION_STATUS_MAP:
        if isinstance(exc, exc_type):
            return status_code
    return 500


def _handle_nativemed_error(exc: NativeMedError) -> HTTPException:
    status_code = _status_code_for(exc)
    logger.error(f"{type(exc).__name__}: {exc}")
    return HTTPException(
        status_code=status_code,
        detail={"status": "error", "error_type": type(exc).__name__, "detail": str(exc)},
    )


def _run_chat_pipeline(
    question: str, top_k: int | None = None, synthesize_audio: bool = True
) -> dict:
    """The full text-in -> JSON-out RAG pipeline shared by /chat and /speech.

    `synthesize_audio` gates the gTTS call: it's a live network request to
    Google's TTS endpoint made on every call, which meaningfully adds to
    response latency (on top of the LLM generation time), so /chat below
    passes False -- chat.js (the text chat UI) never reads `audio_path` from
    the response, so generating it there was pure wasted latency for no
    visible benefit. /speech (the voice-input endpoint) still requests it,
    since returning spoken audio is the point of a voice interaction.
    """
    start = time.perf_counter()

    detection, english_question = translate_to_english(question)

    passages = retrieve(english_question, top_k=top_k)
    prompt = build_user_prompt(english_question, passages)
    llm_response = generate_answer(prompt)

    evidence = build_evidence(passages, english_question)

    # Guard against hallucination even if the LLM ignores instructions: if
    # retrieval found nothing above threshold, force the fixed fallback
    # answer rather than trusting whatever the LLM produced.
    answer = llm_response.answer if passages else NO_EVIDENCE_ANSWER

    translated_answer = None
    translated_question = None
    audio_path = None

    if detection.language_code != "en":
        translated_question = english_question
        translated_answer = translate_from_english(answer, detection.language_code)
        if synthesize_audio:
            audio_path = synthesize_speech(translated_answer, detection.language_code)
    elif synthesize_audio:
        audio_path = synthesize_speech(answer, "en")

    processing_time = round(time.perf_counter() - start, 3)

    return {
        "question": question,
        "language": detection.language_code,
        "language_name": detection.language_name,
        "translated_question": translated_question,
        "answer": answer,
        "translated_answer": translated_answer,
        "sources": evidence.sources,
        "retrieved_passages": evidence.retrieved_passages,
        "similarity_scores": evidence.similarity_scores,
        "confidence_label": evidence.confidence_label,
        "confidence_score": evidence.confidence_score,
        "audio_path": audio_path,
        "processing_time": processing_time,
        "status": "success",
    }


@router.get("/health", response_model=HealthResponse, tags=["System"])
def health() -> HealthResponse:
    """Basic liveness/readiness check: reports LLM mode and whether the
    database and vector store are ready to serve requests."""
    settings = get_settings()

    database_ready = settings.resolved_database_path.exists()

    vectorstore_ready = False
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(settings.resolved_vectorstore_path))
        client.get_collection(settings.collection_name)
        vectorstore_ready = True
    except Exception:
        vectorstore_ready = False

    return HealthResponse(
        status="ok",
        llm_provider="openai" if settings.is_llm_configured else "mock",
        llm_model=settings.llm_model if settings.is_llm_configured else "extractive-mock-v1",
        database_ready=database_ready,
        vectorstore_ready=vectorstore_ready,
    )


@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
def chat(request: ChatRequest) -> ChatResponse:
    """Main text-based chat endpoint. See module docstring for the full
    request -> response pipeline."""
    try:
        # synthesize_audio=False: the text chat UI (chat.js) never reads
        # audio_path, so generating it was a wasted network round-trip to
        # Google's TTS on every message -- see _run_chat_pipeline's docstring.
        result = _run_chat_pipeline(request.question, top_k=request.top_k, synthesize_audio=False)
    except NativeMedError as exc:
        raise _handle_nativemed_error(exc) from exc
    return ChatResponse(**result)


@router.post("/speech", response_model=SpeechChatResponse, tags=["Chat"])
async def speech_chat(audio: UploadFile = File(...)) -> SpeechChatResponse:
    """Audio-in variant of /chat: transcribes the uploaded audio file, then
    runs it through the exact same RAG pipeline as /chat, returning both
    the transcription and the answer."""
    suffix = Path(audio.filename or "").suffix or ".wav"

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            contents = await audio.read()
            tmp.write(contents)
            tmp_path = tmp.name

        transcription_result = transcribe_audio(tmp_path)
        transcription = transcription_result["text"]

        result = _run_chat_pipeline(transcription)
        result["transcription"] = transcription
        result["whisper_detected_language"] = transcription_result.get("whisper_detected_language")
    except NativeMedError as exc:
        raise _handle_nativemed_error(exc) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True) if "tmp_path" in locals() else None

    return SpeechChatResponse(**result)


@router.post("/tts", response_model=TTSResponse, tags=["Speech"])
def tts(request: TTSRequest) -> TTSResponse:
    """Standalone text-to-speech utility endpoint (independent of /chat)."""
    try:
        audio_path = synthesize_speech(request.text, request.language)
    except NativeMedError as exc:
        raise _handle_nativemed_error(exc) from exc
    return TTSResponse(audio_path=audio_path, language=request.language)


@router.get("/plants", response_model=PlantListResponse, tags=["Plants"])
def list_or_search_plants(
    q: str | None = None, limit: int = 500, offset: int = 0
) -> PlantListResponse:
    """List every plant, or search plants by name/property/use/disease/synonym.

    Used by the frontend's Explore Herb gallery, its dashboard herb count,
    and its search box. Pass `?q=<text>` to search; omit it to list all
    plants.
    """
    try:
        plants = search_plants(query=q, limit=limit, offset=offset)
    except NativeMedError as exc:
        raise _handle_nativemed_error(exc) from exc
    return PlantListResponse(count=len(plants), query=q, plants=plants)


@router.get("/plants/lookup", response_model=PlantLookupResponse, tags=["Plants"])
def lookup_plant(name: str) -> PlantLookupResponse:
    """Resolve a plant-identification-model label (e.g. 'AloeVera',
    'Aquatic-Ginger') to a full plant record.

    Used by the plant-identification pipeline to turn the raw ML model
    prediction label into the rich plant info the frontend displays.
    Returns `found: false` (not a 404) when nothing matches, since "no
    match" is an expected, non-error outcome for this endpoint.
    """
    try:
        plant = find_plant_by_any_name(name)
    except NativeMedError as exc:
        raise _handle_nativemed_error(exc) from exc

    if plant is None:
        return PlantLookupResponse(
            found=False,
            message=f"No plant record found matching '{name}'.",
        )

    plant_with_lists = {
        **plant,
        "medicinal_properties_list": plant.get("medicinal_properties_list")
        or ([p.strip() for p in (plant.get("medicinal_properties") or "").split(",") if p.strip()]),
        "diseases_treated_list": plant.get("diseases_treated_list")
        or ([d.strip() for d in (plant.get("diseases_treated") or "").split(",") if d.strip()]),
    }
    return PlantLookupResponse(found=True, plant=plant_with_lists)


@router.get("/plants/{plant_id:int}", response_model=PlantResponse, tags=["Plants"])
def get_plant(plant_id: int) -> PlantResponse:
    """Fetch a single plant record by ID."""
    try:
        plant = get_plant_by_id(plant_id)
    except NativeMedError as exc:
        raise _handle_nativemed_error(exc) from exc
    return PlantResponse(**plant)