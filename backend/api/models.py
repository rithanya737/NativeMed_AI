from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    llm_provider: str
    llm_model: str
    database_ready: bool
    vectorstore_ready: bool


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's question, in any supported language.")
    top_k: int | None = Field(None, ge=1, le=20, description="Override the number of passages retrieved.")


class RetrievedPassageModel(BaseModel):
    plant_id: int
    common_name: str
    botanical_name: str | None = None
    diseases_treated: str | None = None
    medicinal_properties: str | None = None
    traditional_uses: str | None = None
    cultural_significance: str | None = None
    preparation_method: str | None = None
    how_to_take: str | None = None
    general_disclaimer: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    similarity_score: float
    source: str


class ChatResponse(BaseModel):
    question: str
    language: str
    language_name: str
    translated_question: str | None = None
    answer: str
    translated_answer: str | None = None
    sources: list[str]
    retrieved_passages: list[RetrievedPassageModel]
    similarity_scores: list[float]
    confidence_label: str
    confidence_score: float
    audio_path: str | None = None
    processing_time: float
    status: str = "success"


class SpeechChatResponse(ChatResponse):
    transcription: str
    whisper_detected_language: str | None = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: str = Field("en", description="ISO 639-1 code: en, ta, hi, ml, te, kn")


class TTSResponse(BaseModel):
    audio_path: str
    language: str
    status: str = "success"


class PlantResponse(BaseModel):
    plant_id: int
    common_name: str
    botanical_name: str | None
    medicinal_properties: str | None
    traditional_uses: str | None
    cultural_significance: str | None
    diseases_treated: str | None
    preparation_method: str | None = None
    how_to_take: str | None = None
    general_disclaimer: str | None = None
    medicinal_properties_list: list[str]
    diseases_treated_list: list[str]
    synonyms: list[str]


class PlantListItem(BaseModel):
    plant_id: int
    common_name: str
    botanical_name: str | None = None
    medicinal_properties: str | None = None
    traditional_uses: str | None = None
    cultural_significance: str | None = None
    diseases_treated: str | None = None
    preparation_method: str | None = None
    how_to_take: str | None = None
    general_disclaimer: str | None = None
    medicinal_properties_list: list[str] = Field(default_factory=list)
    diseases_treated_list: list[str] = Field(default_factory=list)


class PlantListResponse(BaseModel):
    count: int
    query: str | None = None
    plants: list[PlantListItem]


class PlantLookupResponse(BaseModel):
    found: bool
    plant: PlantListItem | None = None
    message: str | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error_type: str
    detail: str
