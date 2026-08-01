"""
Unit tests for explainability/lime_explain.py.

These run the real `lime` and `scikit-image` libraries end-to-end, but
against a fake, batched `confidence_batch_fn` -- there's no need to load
RF-DETR/torch or the trained checkpoint just to verify the LIME adapter and
overlay plumbing work. Image size and num_samples are kept small so the
test suite stays fast.
"""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from explainability.lime_explain import LimeExplanation, _make_predict_fn, explain_prediction


def _greenish_image(size: int = 32) -> Image.Image:
    """A small synthetic image: green on the left half, red on the right.
    Used so a fake confidence_batch_fn can respond to *which half* of the
    image it's given, without needing a real model.
    """
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    arr[:, : size // 2, 1] = 200  # left half green
    arr[:, size // 2 :, 0] = 200  # right half red
    return Image.fromarray(arr, mode="RGB")


def _confidence_batch_from_green(images: list[Image.Image]) -> list[float]:
    """Fake confidence_batch_fn standing in for
    PlantIdentifier.confidence_for_label_batch: the 'more green' an image
    looks, the more confident the fake detector is that it's still looking
    at the target label. Batched (takes a list, returns a list) to match
    the real batched interface used against rfdetr's list-in/list-out
    predict()."""
    scores = []
    for image in images:
        arr = np.array(image.convert("RGB"), dtype=np.float64)
        green_fraction = arr[:, :, 1].mean() / 255.0
        scores.append(float(np.clip(green_fraction, 0.0, 1.0)))
    return scores


def test_make_predict_fn_batches_and_shapes_scores():
    predict_fn = _make_predict_fn(_confidence_batch_from_green)

    all_green = np.zeros((2, 4, 4, 3), dtype=np.uint8)
    all_green[:, :, :, 1] = 255
    all_red = np.zeros((2, 4, 4, 3), dtype=np.uint8)
    all_red[:, :, :, 0] = 255

    batch = np.concatenate([all_green, all_red], axis=0)
    probs = predict_fn(batch)

    assert probs.shape == (4, 2)
    # All-green images: column 1 (target label) should be near 1.
    assert probs[0, 1] > 0.9
    assert probs[1, 1] > 0.9
    # All-red images: column 1 should be near 0, column 0 near 1.
    assert probs[2, 1] < 0.1
    assert probs[3, 1] < 0.1
    # Rows should sum to 1 (by construction: column0 = 1 - column1).
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_make_predict_fn_calls_batch_fn_once_per_chunk():
    """The whole point of batching is fewer calls to the underlying model --
    verify predict_fn hands LIME's chunk to confidence_batch_fn in a single
    call rather than looping and calling it once per image."""
    call_count = 0
    call_sizes = []

    def _counting_batch_fn(images):
        nonlocal call_count
        call_count += 1
        call_sizes.append(len(images))
        return [0.5] * len(images)

    predict_fn = _make_predict_fn(_counting_batch_fn)
    batch = np.zeros((7, 4, 4, 3), dtype=np.uint8)
    predict_fn(batch)

    assert call_count == 1  # one call for the whole chunk, not one per image
    assert call_sizes == [7]


def test_explain_prediction_returns_valid_overlay():
    image = _greenish_image(size=32)

    result = explain_prediction(
        image=image,
        confidence_batch_fn=_confidence_batch_from_green,
        label="AloeVera",
        confidence=0.87,
        num_samples=25,  # small for test speed; production default is 40
        num_features=4,
    )

    assert isinstance(result, LimeExplanation)
    assert result.label == "AloeVera"
    assert result.confidence == 0.87
    assert result.num_samples == 25
    assert result.num_features == 4

    # fidelity_score is LIME's own R^2 for its local surrogate -- a plain
    # float, not NaN/inf, but otherwise unconstrained (can be negative for a
    # poor fit). Here the fake confidence_batch_fn is a clean, near-linear
    # function of green-channel intensity, so the local Ridge model should
    # fit it well: expect a strongly positive score, not just "some number".
    assert isinstance(result.fidelity_score, float)
    assert np.isfinite(result.fidelity_score)
    assert result.fidelity_score > 0.5

    # overlay_image_b64 must decode to a real PNG the same size as the input.
    png_bytes = base64.b64decode(result.overlay_image_b64)
    overlay_image = Image.open(io.BytesIO(png_bytes))
    assert overlay_image.format == "PNG"
    assert overlay_image.size == image.size


def test_explain_prediction_handles_zero_confidence_gracefully():
    """If the target label is never detected in any perturbed sample
    (confidence_batch_fn always returns 0), LIME should still produce a
    well-formed (if uninformative) explanation rather than crashing."""
    image = _greenish_image(size=32)

    result = explain_prediction(
        image=image,
        confidence_batch_fn=lambda images: [0.0] * len(images),
        label="Neem",
        confidence=0.0,
        num_samples=20,
        num_features=4,
    )

    assert result.label == "Neem"
    assert isinstance(result.fidelity_score, float)
    assert np.isfinite(result.fidelity_score)
    png_bytes = base64.b64decode(result.overlay_image_b64)
    overlay_image = Image.open(io.BytesIO(png_bytes))
    assert overlay_image.size == image.size


def test_explain_prediction_respects_smaller_batch_size():
    """batch_size caps how many perturbed samples are sent to
    confidence_batch_fn per call -- with num_samples=20 and batch_size=5,
    expect roughly 4 calls of size <=5 rather than one call of 20."""
    call_sizes = []

    def _tracking_batch_fn(images):
        call_sizes.append(len(images))
        return [0.3] * len(images)

    image = _greenish_image(size=32)
    explain_prediction(
        image=image,
        confidence_batch_fn=_tracking_batch_fn,
        label="Neem",
        confidence=0.3,
        num_samples=20,
        num_features=4,
        batch_size=5,
    )

    assert all(size <= 5 for size in call_sizes)
    assert len(call_sizes) > 1  # confirms it was actually chunked, not one giant call
