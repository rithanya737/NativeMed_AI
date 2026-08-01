"""
LLM service layer.

The rest of the codebase never imports `openai` directly -- it only calls
`generate_answer()` below. This makes it trivial to swap providers (Claude,
Ollama, a local model, etc.) later by adding a new `LLMProvider` subclass
and registering it in `_build_provider()`, with zero changes to
rag/retriever.py or api/routes.py.

Don't want to use OpenAI?
-------------------------
Set `LLM_PROVIDER=ollama` in `.env` (this is now the default) to use a free,
fully local model served by Ollama (https://ollama.com) -- no API key of any
kind. Install Ollama, run `ollama pull llama3.2` (or whatever `OLLAMA_MODEL`
is set to), and the rest of the pipeline is unchanged.

If `LLM_PROVIDER=mock`, or no provider is reachable, this module falls back
to `MockLLMProvider`, which builds a safe, extractive answer directly from
the retrieved passages -- no external call at all, no hallucination risk.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from utils.config import get_settings
from utils.exceptions import LLMError
from utils.logger import logger

NO_EVIDENCE_ANSWER = (
    "I don't have enough verified medicinal information to answer that question."
)

SYSTEM_PROMPT = """You are NativeMed AI, a careful medicinal-plant information assistant.

Rules you MUST follow:
1. Answer ONLY using the information in the provided context passages.
2. Never invent, guess, or embellish medicinal claims that are not explicitly
   supported by the context.
3. If the context does not contain enough relevant information to answer the
   question, respond exactly with:
   "I don't have enough verified medicinal information to answer that question."
4. Be concise and factual. Prefer plain, clear language over jargon.
5. When you state a claim, mention which plant/source it comes from.
6. If the evidence is partial or uncertain, say so explicitly rather than
   overstating confidence.
7. This is informational content, not a medical diagnosis or prescription;
   do not tell the user to disregard professional medical advice, but you
   do not need to repeat a disclaimer in every sentence.
8. Only discuss preparation method, dosage, or how to take/apply a plant if
   the user's question is actually asking about that. If the context
   includes a "Preparation method", "How to take/apply", or "Disclaimer"
   field, and the question asked about it, always pass along any safety
   note or disclaimer alongside the preparation details -- never give
   preparation/dosage instructions without their accompanying safety note.
"""


@dataclass
class LLMResponse:
    answer: str
    provider: str
    model: str
    latency_seconds: float
    used_context: bool
    raw_usage: dict = field(default_factory=dict)


class LLMProvider(abc.ABC):
    """Base interface every LLM backend must implement."""

    name: str = "base"

    @abc.abstractmethod
    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the raw completion text for the given prompts."""

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        start = time.perf_counter()
        try:
            text = self._complete(system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001 - convert any provider error uniformly
            logger.error(f"[{self.name}] LLM generation failed: {exc}")
            raise LLMError(f"LLM provider '{self.name}' failed: {exc}") from exc

        latency = time.perf_counter() - start
        return LLMResponse(
            answer=text.strip(),
            provider=self.name,
            model=getattr(self, "model", "unknown"),
            latency_seconds=round(latency, 3),
            used_context=True,
        )


class OpenAIProvider(LLMProvider):
    """Wraps the OpenAI Chat Completions API (default: gpt-4o-mini)."""

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI  # imported lazily so `openai` isn't required in mock mode

        self.client = OpenAI(api_key=api_key)
        self.model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        choice = response.choices[0]
        if not choice.message or not choice.message.content:
            raise LLMError("OpenAI returned an empty completion.")
        return choice.message.content


class OllamaProvider(LLMProvider):
    """Calls a local Ollama server (https://ollama.com) instead of a paid API.

    Fully free and fully offline/private -- no API key of any kind. Requires
    the Ollama app to be installed and running locally (it runs as a
    background service after install) and the configured model to already be
    pulled, e.g.:

        ollama pull llama3.2

    If the server can't be reached, `_complete` raises a clear `LLMError`
    explaining how to fix it -- it never silently falls back or hallucinates.
    """

    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        import httpx  # imported lazily so httpx isn't required in mock mode

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        # Without a cap, Ollama generates until it hits a
                        # natural stop token or the model's context limit --
                        # on CPU-only hardware (no GPU) that's the single
                        # biggest source of multi-minute responses. 400 is
                        # roughly in line with OpenAIProvider's max_tokens=500
                        # above, and this system prompt already asks for
                        # concise answers, so it shouldn't visibly truncate
                        # normal responses.
                        "num_predict": 400,
                    },
                },
                timeout=120.0,
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMError(
                f"Could not reach Ollama at {self.base_url}. Make sure the "
                "Ollama app is installed and running (download it from "
                "https://ollama.com), and that you've pulled the model with "
                f"`ollama pull {self.model}`."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"Ollama returned an error ({exc.response.status_code}): "
                f"{exc.response.text}. If this mentions the model name, run "
                f"`ollama pull {self.model}` first."
            ) from exc

        data = response.json()
        content = (data.get("message") or {}).get("content", "")
        if not content:
            raise LLMError("Ollama returned an empty completion.")
        return content


class MockLLMProvider(LLMProvider):
    """Deterministic, offline fallback used when no LLM API key is configured.

    Produces a safe, extractive answer built directly from the retrieved
    passages (never fabricates), so the rest of the system (retrieval,
    explainability, translation, speech) can be fully exercised without an
    OpenAI key.
    """

    name = "mock"
    model = "extractive-mock-v1"

    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        # user_prompt is built by rag/prompts.py and contains a
        # "Context:" section followed by "Question:". We extract the
        # context passages back out to build a templated, non-hallucinated
        # answer. See rag/prompts.py for the exact format.
        context_marker = "Context:"
        question_marker = "Question:"

        if context_marker not in user_prompt:
            return NO_EVIDENCE_ANSWER

        context_block = user_prompt.split(context_marker, 1)[1]
        if question_marker in context_block:
            context_block = context_block.split(question_marker, 1)[0]
        context_block = context_block.strip()

        if not context_block or context_block.lower().startswith("no relevant"):
            return NO_EVIDENCE_ANSWER

        # Take the first passage (highest-ranked retrieval result) as the
        # basis for a concise, templated answer.
        first_passage = context_block.split("\n\n")[0].strip()
        return (
            f"{first_passage}\n\n"
            "(Note: this answer was generated in offline/mock mode because no "
            "LLM API key is configured. It is an extractive summary of the "
            "top retrieved passage, not a model-generated synthesis.)"
        )


def _build_provider() -> LLMProvider:
    settings = get_settings()
    provider_name = settings.llm_provider.lower()

    if provider_name == "openai" and settings.is_llm_configured:
        logger.info(f"Using OpenAI LLM provider (model={settings.llm_model}).")
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.llm_model)

    if provider_name == "ollama":
        logger.info(
            f"Using Ollama LLM provider (model={settings.ollama_model} at "
            f"{settings.ollama_base_url}). No API key required."
        )
        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)

    logger.warning(
        "LLM_PROVIDER=mock (or unrecognized) -- falling back to MockLLMProvider. "
        "Set LLM_PROVIDER=ollama (free, local, default) or LLM_PROVIDER=openai "
        "in .env to enable real LLM-generated answers."
    )
    return MockLLMProvider()


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


def generate_answer(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> LLMResponse:
    """Public entrypoint used by api/routes.py. Never raises hallucinated
    content -- either a grounded answer, the fixed no-evidence string, or an
    LLMError if the provider itself fails.
    """
    provider = get_provider()
    return provider.generate(system_prompt=system_prompt, user_prompt=user_prompt)
