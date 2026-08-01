from functools import lru_cache
from pathlib import Path
from PIL import Image

BASE = Path(__file__).parent.parent / "models"
CHECKPOINT = BASE / "checkpoint_best_ema.pth"

class PlantIdentifier:
    def __init__(self):
        # rfdetr (and the torch/torchvision it pulls in) is imported here,
        # lazily, rather than at module import time. That way importing
        # ml.inference / routers.plant_id / app.py stays fast and doesn't
        # force-load the RF-DETR checkpoint until a prediction is actually
        # requested (see get_plant_identifier() below) -- important now that
        # app.py (used by the test suite too) includes this router.
        from rfdetr import RFDETRNano

        self.model = RFDETRNano(
            pretrain_weights=str(CHECKPOINT),
            resolution=384,
            num_classes=145,      # from training_config.json — critical, don't skip
            num_queries=300,      # matches training_config.json model_config
            group_detr=13,        # matches training_config.json model_config
        )
        # optimize_for_inference() is deprecated as of rfdetr 1.9.0 — safe to just drop it for now

    def predict(self, image: Image.Image, threshold: float = 0.5):
        detections = self.model.predict(image, threshold=threshold)

        if len(detections.class_id) == 0:
            return None

        class_names = detections.data.get("class_name", [])
        best_idx = detections.confidence.argmax()

        return {
            "label": class_names[best_idx] if len(class_names) else str(detections.class_id[best_idx]),
            "confidence": float(detections.confidence[best_idx]),
            "bbox": detections.xyxy[best_idx].tolist(),
            "total_detections": len(detections.class_id),
        }

    def confidence_for_label(self, image: Image.Image, label: str, threshold: float = 0.05) -> float:
        """Re-runs detection on `image` and returns the highest confidence
        found for `label` specifically (0.0 if `label` isn't detected at
        all above `threshold`).

        Used by explainability/lime_explain.py: LIME perturbs (occludes)
        copies of the original image and needs a continuous score for
        "does this still look like `label`" on each one. A low threshold
        (vs. predict()'s default 0.5) matters here -- occluded copies
        legitimately have lower confidence, and we want LIME to see that
        gradient rather than a binary cutoff at 0.5.
        """
        return self.confidence_for_label_batch([image], label, threshold=threshold)[0]

    def confidence_for_label_batch(
        self, images: list[Image.Image], label: str, threshold: float = 0.05
    ) -> list[float]:
        """Batched version of confidence_for_label: runs RF-DETR ONCE over
        the whole list of images (rfdetr's predict() accepts a list and
        returns one Detections object per image) instead of once per image.

        This is the main lever for LIME's speed: LIME needs a score for
        every perturbed copy of the original image (dozens of them), and
        calling the model once per copy is far slower on CPU than handing
        it the whole batch in a single forward pass -- per-call Python/model
        dispatch overhead is paid once instead of N times, and RF-DETR's
        own batching is more efficient than N separate single-image calls.
        """
        if not images:
            return []

        results = self.model.predict(images, threshold=threshold)
        # rfdetr returns a single Detections object (not a list) if given a
        # single image, and a list of Detections if given a list -- since we
        # always pass a list here, `results` is always a list, one entry per
        # input image, in the same order.

        scores: list[float] = []
        for detections in results:
            if len(detections.class_id) == 0:
                scores.append(0.0)
                continue
            class_names = detections.data.get("class_name", [])
            matches = [
                float(conf) for name, conf in zip(class_names, detections.confidence) if name == label
            ]
            scores.append(max(matches) if matches else 0.0)
        return scores


@lru_cache
def get_plant_identifier() -> "PlantIdentifier":
    """Builds (and caches) the RF-DETR-backed identifier on first use.

    Kept lazy/cached rather than a module-level singleton so that simply
    importing this module (e.g. via app.py in tests, or any other code path
    that doesn't actually call /api/identify-plant) never pays the cost of
    loading torch + the trained checkpoint.
    """
    return PlantIdentifier()