"""Common detector interface and threshold calibration."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve


class Detector:
    """Unsupervised anomaly detector over feature frames.

    ``score`` returns higher-is-more-anomalous values (NaN where a row cannot be
    scored).  ``threshold`` converts scores into alerts; it is calibrated on a
    validation period and can be overridden by an operator (ethics requirement:
    thresholds are configurable and operator-mediated).
    """

    name: str = "base"
    family: str = "base"          # statistical | machine_learning | deep_learning | ensemble
    interpretability: str = "n/a"

    def __init__(self):
        self.threshold: float = np.inf

    def fit(self, df: pd.DataFrame) -> "Detector":
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError

    def predict(self, df: pd.DataFrame, scores: np.ndarray | None = None) -> np.ndarray:
        s = self.score(df) if scores is None else scores
        return np.nan_to_num(s, nan=-np.inf) >= self.threshold

    def calibrate(self, scores: np.ndarray, y: np.ndarray, mode: str = "f1",
                  contamination: float = 0.03) -> float:
        self.threshold = calibrate_threshold(scores, y, mode, contamination)
        return self.threshold


def calibrate_threshold(scores: np.ndarray, y: np.ndarray | None, mode: str = "f1",
                        contamination: float = 0.03, max_alert_rate: float = 0.15) -> float:
    """Pick an alert threshold on the validation period.

    ``f1``       maximise F1 against validation labels (semi-supervised calibration)
    ``quantile`` flag the top ``contamination`` share of readings (fully unsupervised)

    In both modes the threshold never flags more than ``max_alert_rate`` of
    readings — an operational alert budget that stops a weak detector from
    "winning" F1 by alerting on almost everything.
    """
    ok = ~np.isnan(scores)
    s = scores[ok]
    floor = float(np.quantile(s, 1 - max_alert_rate))
    if mode == "quantile" or y is None:
        return max(float(np.quantile(s, 1 - contamination)), floor)
    p, r, t = precision_recall_curve(y[ok].astype(int), s)
    if not len(t):
        return max(float(np.quantile(s, 0.97)), floor)
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    f1[t < floor] = -1
    return float(t[int(np.argmax(f1))])
