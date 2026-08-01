import time
from functools import partial

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from PIL import Image
import io
from ml.inference import get_plant_identifier
from database.database import find_plant_by_any_name
from explainability.lime_explain import explain_prediction
from utils.logger import logger

router = APIRouter()

# On CPU-only setups (confirmed via torch.version: this project's backend
# venv ships torch 2.13.0+cpu, no CUDA), running RF-DETR once per LIME
# sample sequentially measured out to well over 120s at 150 samples -- long
# enough that the Flask frontend's proxy timeout gave up before FastAPI
# ever finished. Two things address this:
#   1. confidence_for_label_batch() (ml/inference.py) batches every
#      perturbed sample into ONE rfdetr.predict(list_of_images) call
#      instead of N sequential single-image calls -- rfdetr supports batched
#      input natively, so this cuts most of the per-call overhead.
#   2. 40 is still a deliberately conservative sample count (a coarser
#      heatmap, but a much smaller/faster batch); raise it via the
#      lime_num_samples query param if your hardware handles it well.
DEFAULT_LIME_NUM_SAMPLES = 40

# How many perturbed samples get sent to RF-DETR in a single batched call.
# Ideally this equals lime_num_samples (one giant batch, fewest possible
# model invocations), but very large source photos x a big batch can spike
# memory before rfdetr's internal resize-to-384 kicks in, so this caps the
# batch at 16 by default -- still a big drop in call count vs. one-at-a-time.
DEFAULT_LIME_BATCH_SIZE = 16


def _fidelity_label(score: float) -> str:
    """Maps LIME's fidelity_score (R^2 of its local linear surrogate) to a
    coarse, human-readable label -- mirrors the style of
    explainability/evidence.py's _confidence_label, but for a different
    thing: this is LIME grading how trustworthy its OWN explanation is, not
    how confident the identification is."""
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    if score > 0.0:
        return "low"
    return "unreliable"  # R^2 <= 0: the surrogate fit no better than guessing the average


@router.post("/api/identify-plant")
async def identify_plant(
    file: UploadFile = File(...),
    explain: bool = Query(
        False,
        description=(
            "If true, also run a LIME visual explanation highlighting which "
            "regions of the photo drove the prediction. Reruns the model "
            "once per perturbed sample (see lime_num_samples), so it's much "
            "slower than plain identification -- expect anywhere from ~10s "
            "on GPU to a minute+ on CPU -- leave off unless the caller is "
            "going to show it."
        ),
    ),
    lime_num_samples: int = Query(
        DEFAULT_LIME_NUM_SAMPLES,
        ge=10,
        le=500,
        description="LIME perturbed-sample count; higher = sharper but slower (each sample is a full model forward pass).",
    ),
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image file")

    # Lazily loads (and caches) the RF-DETR model on first call, rather than
    # at import time -- see ml/inference.get_plant_identifier() docstring.
    identifier = get_plant_identifier()
    result = identifier.predict(image)
    if result is None:
        return {
            "identified": False,
            "message": "No plant detected with sufficient confidence",
            "common_name": "Unknown Plant",
            "scientific_name": "",
            "confidence": 0.0,
        }

    confidence_pct = round(result["confidence"] * 100, 2)

    def _with_explanation(response: dict) -> dict:
        if not explain:
            return response
        # The LIME explanation is a "nice to have" on top of an identification
        # that has *already succeeded* -- if it blows up (missing optional
        # dependency, a slow/timed-out inference loop, an unexpected image
        # shape, etc.) we log it and still return the successful
        # identification, rather than turning a working identification into
        # a hard 500 just because the bonus explanation step failed.
        started_at = time.monotonic()
        try:
            confidence_batch_fn = partial(identifier.confidence_for_label_batch, label=result["label"])
            lime_result = explain_prediction(
                image=image,
                confidence_batch_fn=confidence_batch_fn,
                label=result["label"],
                confidence=result["confidence"],
                num_samples=lime_num_samples,
                batch_size=min(lime_num_samples, DEFAULT_LIME_BATCH_SIZE),
            )
        except Exception:
            elapsed = time.monotonic() - started_at
            logger.exception(
                "LIME explanation failed for label={} after {:.1f}s ({} samples)",
                result["label"], elapsed, lime_num_samples,
            )
            response["explanation_error"] = (
                "Couldn't generate the AI explanation for this image. "
                "The identification above is unaffected."
            )
            return response

        elapsed = time.monotonic() - started_at
        logger.info(
            "LIME explanation for label={} took {:.1f}s ({} samples)",
            result["label"], elapsed, lime_num_samples,
        )

        response["explanation"] = {
            "overlay_image_base64": lime_result.overlay_image_b64,
            "num_samples": lime_result.num_samples,
            "num_features": lime_result.num_features,
            "fidelity_score": round(lime_result.fidelity_score, 4),
            "fidelity_label": _fidelity_label(lime_result.fidelity_score),
            "note": "Highlighted regions are the image areas LIME found most supportive of this label -- not a guarantee of correctness.",
            "fidelity_note": (
                "How well LIME's simplified local model actually matches the "
                "real AI's behavior for this image -- high means the highlighted "
                "regions are a trustworthy explanation, low/unreliable means "
                "treat them with more skepticism."
            ),
        }
        return response

    # The model only knows the raw training label (e.g. "AloeVera") -- look
    # it up against the plants DB to get the human-facing name and the rest
    # of the medicinal info the frontend displays.
    plant = find_plant_by_any_name(result["label"])
    if plant:
        return _with_explanation({
            "identified": True,
            "common_name": plant.get("common_name"),
            "scientific_name": plant.get("botanical_name"),
            "confidence": confidence_pct,
            "medicinal_properties": plant.get("medicinal_properties"),
            "traditional_uses": plant.get("traditional_uses"),
            "cultural_significance": plant.get("cultural_significance"),
            "diseases_treated": plant.get("diseases_treated"),
            "preparation_method": plant.get("preparation_method"),
            "how_to_take": plant.get("how_to_take"),
            "general_disclaimer": plant.get("general_disclaimer"),
            "raw_label": result["label"],
            "bbox": result["bbox"],
            "total_detections": result["total_detections"],
        })

    # Model detected something, but no matching record in the plants DB --
    # still surface the raw label rather than claiming total ignorance.
    return _with_explanation({
        "identified": True,
        "common_name": result["label"],
        "scientific_name": "",
        "confidence": confidence_pct,
        "note": "Detailed medicinal information for this plant is not available in our database.",
        "raw_label": result["label"],
        "bbox": result["bbox"],
        "total_detections": result["total_detections"],
    })