"""
Explainable AI: LIME-based visual explanations for the plant-image
identifier (ml/inference.py's RF-DETR model).

This complements explainability/evidence.py, which explains the *text*
side of the app (why the chatbot's answer is trustworthy -- which RAG
passages were retrieved and how similar they were). This module explains
the *image* side: given a photo the identifier called "Tulsi", which
regions of the photo actually drove that call.

RF-DETR is an object detector, not a plain classifier, so it doesn't
expose the predict_proba(images) -> (n_samples, n_classes) interface
LIME's image explainer expects. `_make_predict_fn` adapts it: LIME
generates perturbed (partially occluded) copies of the input image, and
for each batch of them we ask "does the detector still see `label` here,
and how confidently?" via PlantIdentifier.confidence_for_label_batch. Those
scores become a 2-column pseudo-probability array (label vs. not-label),
which is all LIME needs to fit its local surrogate model and rank
superpixels by contribution. It's an approximation of "true"
LIME-on-a-classifier, but a standard and legitimate way to point LIME at a
detector.

Batching matters a lot here: rfdetr's predict() accepts a *list* of images
and returns detections for all of them in one call, which is much faster
on CPU than calling it once per perturbed sample (each call has fixed
Python/model dispatch overhead that's now paid once per batch instead of
once per sample). See ml/inference.py's confidence_for_label_batch.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Callable

import numpy as np
from PIL import Image


@dataclass
class LimeExplanation:
    """`fidelity_score` is how well LIME's local linear surrogate model
    actually fits the real model's behavior in the neighborhood of this
    image (the R^2 of the weighted Ridge regression LIME fits internally).
    This is NOT the same as `confidence` (RF-DETR's own identification
    confidence) -- fidelity_score is LIME grading its own explanation.
    1.0 = the linear surrogate perfectly tracks the real model locally, so
    the highlighted regions can be trusted; values near/below 0 mean the
    surrogate barely fits better than guessing the average, so the
    highlighted regions shouldn't be read as a reliable explanation. It can
    go negative (Ridge's R^2 is unbounded below) for a genuinely poor
    local fit.
    """

    label: str
    confidence: float
    overlay_image_b64: str  # PNG, base64-encoded, ready for a data: URI
    num_samples: int
    num_features: int
    fidelity_score: float


def _make_predict_fn(confidence_batch_fn: Callable[[list[Image.Image]], list[float]]):
    """Wraps a batched `confidence_batch_fn(list[PIL.Image]) -> list[float]`
    (scores for one fixed target label) into the
    `predict_fn(images: np.ndarray[N,H,W,3]) -> np.ndarray[N,2]` signature
    LimeImageExplainer.explain_instance requires.

    Column 1 = confidence_batch_fn's score (the target label). Column 0 =
    its complement. We only ever ask LIME to explain label index 1, so
    column 0 only needs to make the row sum to something sane -- it does.

    Critically, this converts LIME's whole chunk of perturbed samples to
    PIL images and hands them to confidence_batch_fn in ONE call, rather
    than looping and calling the model once per sample -- see module
    docstring on why that's the main lever for making this fast.
    """

    def predict_fn(images: np.ndarray) -> np.ndarray:
        pil_images = [Image.fromarray(arr.astype("uint8"), mode="RGB") for arr in images]
        scores = np.array(confidence_batch_fn(pil_images), dtype=np.float64)
        return np.stack([1.0 - scores, scores], axis=1)

    return predict_fn


def explain_prediction(
    image: Image.Image,
    confidence_batch_fn: Callable[[list[Image.Image]], list[float]],
    label: str,
    confidence: float,
    num_samples: int = 150,
    num_features: int = 8,
    batch_size: int | None = None,
) -> LimeExplanation:
    """Runs LIME over `image`, treating `confidence_batch_fn` as a
    black-box classifier for `label`, and returns a heatmap overlay of the
    superpixels that most supported the prediction.

    `num_samples` defaults to 150 rather than LIME's usual 1000 because
    every sample costs a model forward pass -- see requirements.txt's note
    on this. `batch_size` controls how many perturbed samples LIME hands to
    `confidence_batch_fn` per call; defaults to `num_samples` (i.e. every
    sample in one single batched forward pass) since that minimizes the
    number of separate model invocations. Lower it if a single batch that
    size risks running out of memory on very large source images.
    """
    # Imported lazily, matching ml/inference.py's convention of not paying
    # import cost until an explanation is actually requested.
    from lime.lime_image import LimeImageExplainer
    from skimage.segmentation import mark_boundaries, slic

    image_np = np.array(image.convert("RGB"))
    predict_fn = _make_predict_fn(confidence_batch_fn)

    explainer = LimeImageExplainer()
    explanation = explainer.explain_instance(
        image_np,
        predict_fn,
        labels=(1,),
        top_labels=None,  # explain exactly label 1, not LIME's default top-5
        hide_color=0,
        num_samples=num_samples,
        batch_size=batch_size or num_samples,
        segmentation_fn=lambda img: slic(img, n_segments=num_features * 6, compactness=10),
    )

    temp, mask = explanation.get_image_and_mask(
        label=1,
        positive_only=True,
        num_features=num_features,
        hide_rest=False,
    )
    overlay = mark_boundaries(temp / 255.0, mask)
    overlay_uint8 = (np.clip(overlay, 0, 1) * 255).astype("uint8")

    buf = io.BytesIO()
    Image.fromarray(overlay_uint8).save(buf, format="PNG")
    overlay_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # `explanation.score` is the R^2 of the local linear surrogate LIME fit
    # to the perturbed samples (see LimeBase.explain_instance_with_data) --
    # it's set once per label explained, and since we only ever ask for
    # label 1, it's unambiguously the fidelity score for our one label.
    fidelity_score = float(explanation.score)

    return LimeExplanation(
        label=label,
        confidence=confidence,
        overlay_image_b64=overlay_b64,
        num_samples=num_samples,
        num_features=num_features,
        fidelity_score=fidelity_score,
    )
