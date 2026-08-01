"""Unit test for routers/plant_id.py's _fidelity_label helper.

_fidelity_label maps LIME's fidelity_score (the R^2 of its local linear
surrogate -- see explainability/lime_explain.py's LimeExplanation
docstring) to a coarse, human-readable label surfaced in the
/api/identify-plant explanation payload.
"""

from __future__ import annotations

from routers.plant_id import _fidelity_label


def test_fidelity_label_thresholds():
    assert _fidelity_label(0.95) == "high"
    assert _fidelity_label(0.7) == "high"
    assert _fidelity_label(0.69) == "medium"
    assert _fidelity_label(0.4) == "medium"
    assert _fidelity_label(0.39) == "low"
    assert _fidelity_label(0.01) == "low"
    assert _fidelity_label(0.0) == "unreliable"
    assert _fidelity_label(-0.5) == "unreliable"
