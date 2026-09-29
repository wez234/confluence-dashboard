"""Plain-language explanation helpers (dependency-free, used by the dashboard)."""
from __future__ import annotations

import numpy as np

from confluence.ingestion.features import FEATURE_LABELS, FEATURES

# which features a domain expert would expect to drive each anomaly type
EXPECTED_DRIVERS = {
    "spike": {"profile_z", "ma_z", "rate_of_change"},
    "drop": {"profile_z", "level", "cross_meter_z"},
    "leak": {"min_level", "profile_z"},
    "stuck": {"flat_run", "volatility"},
    "drift": {"profile_z", "level", "cross_meter_z"},
}

def hint(feature: str, x: float | None, utility: str = "water") -> str:
    """Direction-aware, plain-language reading of one feature value."""
    hi = x is None or x >= 0
    return {
        "profile_z": ("the reading is far above" if hi else "the reading is far below")
                     + " what this meter normally uses at this time of day",
        "ma_z": "the reading " + ("jumps above" if hi else "falls below") + " the last 24 hours' average",
        "rate_of_change": "the reading " + ("rose" if hi else "fell") + " suddenly from the previous interval",
        "volatility": "recent readings are unusually erratic",
        "flat_run": "the meter has reported exactly the same value for a long run — possibly stuck",
        "min_level": (("consumption never drops back to its normal minimum — typical of a leak"
                       if utility in ("water", "gas") else "base load stays unusually high — something is left running")
                      if (x or 0) > 0.6 else "the recent minimum is unusually low"),
        "cross_meter_z": "this meter is " + ("well above" if hi else "well below")
                         + " other meters of the same utility right now",
        "level": "consumption is " + ("well above" if (x or 1) >= 1 else "well below") + " this meter's average",
        "hour_sin": "time of day", "hour_cos": "time of day", "is_weekend": "weekday / weekend pattern",
    }.get(feature, FEATURE_LABELS.get(feature, feature).lower())


def top(values, k: int = 3, positive_only: bool = True) -> list[dict]:
    values = np.asarray(values, dtype=float)
    order = np.argsort(-values if positive_only else -np.abs(values))
    return [{"feature": FEATURES[i], "label": FEATURE_LABELS[FEATURES[i]], "contribution": float(values[i])}
            for i in order[:k]]


def narrative(utility: str, meter_id: str, value: float, unit: str, top_items: list[dict],
              feature_values: dict | None = None) -> str:
    fv = feature_values or {}
    if not top_items:
        return f"{utility.title()} meter {meter_id} read {value:.2f} {unit}; no explanation available."
    lead = top_items[0]
    s = f"{utility.title()} meter {meter_id} read {value:.2f} {unit}. Main reason: {hint(lead['feature'], fv.get(lead['feature']), utility)}."
    rest = [hint(t["feature"], fv.get(t["feature"]), utility) for t in top_items[1:3] if t["contribution"] > 0]
    rest = [r for r in rest if r != "time of day"] or rest
    if rest:
        s += " Also contributing: " + "; ".join(dict.fromkeys(rest)) + "."
    return s
