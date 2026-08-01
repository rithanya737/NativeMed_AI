from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from routers import plant_id
from utils.logger import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NativeMed AI backend starting up...")
    yield
    logger.info("NativeMed AI backend shutting down...")


app = FastAPI(
    title="NativeMed AI Backend",
    description=(
        "Backend API for NativeMed AI: an AI-powered medicinal plant "
        "information assistant. Combines Retrieval-Augmented Generation "
        "(RAG), multilingual support (English, Tamil, Hindi, Malayalam, "
        "Telugu, Kannada), speech-to-text/text-to-speech, explainable AI "
        "(every answer is backed by cited, scored retrieved passages), and "
        "image-based plant identification via a trained RF-DETR model. "
        "This single app is the one base URL your frontend needs to call."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the separately-developed frontend (running on any origin/port during
# development) to call this API directly from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten this to your actual frontend URL before deploying
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(plant_id.router, tags=["Plant Identification"])


@app.get("/", tags=["System"])
def root() -> dict:
    return {
        "service": "NativeMed AI Backend",
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "/chat",
            "/speech",
            "/tts",
            "/plants/{plant_id}",
            "/api/identify-plant",
        ],
    }
