"""Multi-model AI anomaly detection engine with ensemble decision fusion.

One set of detectors is trained per utility (electricity, gas, water) because
their frequencies and consumption patterns differ.  The ensemble converts each
detector's score into a percentile against the validation period (so scores
on different scales become comparable) and combines them with weights equal to
each detector's validation F1 (weighted voting / decision fusion).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from confluence.detection.base import calibrate_threshold
from confluence.detection.lstm_autoencoder import LSTMAutoencoderDetector
from confluence.detection.models import (IsolationForestDetector, MovingAverageDetector,
                                         OneClassSVMDetector, ZScoreDetector)
from confluence.ingestion.features import Profile

from confluence.detection.names import ALL_DETECTORS, BASE_DETECTORS, DISPLAY, FAMILY  # noqa: E402,F401


def _make(name: str, seed: int):
    return {"zscore": ZScoreDetector, "moving_average": MovingAverageDetector,
            "isolation_forest": lambda: IsolationForestDetector(seed=seed),
            "one_class_svm": lambda: OneClassSVMDetector(seed=seed),
            "lstm_autoencoder": lambda: LSTMAutoencoderDetector(seed=seed)}[name]()


@dataclass
class UtilityModels:
    detectors: dict = field(default_factory=dict)
    ref_scores: dict = field(default_factory=dict)     # sorted validation scores per detector
    weights: dict = field(default_factory=dict)
    ensemble_threshold: float = 0.9
    fit_seconds: dict = field(default_factory=dict)

    def _pct(self, name: str, s: np.ndarray) -> np.ndarray:
        ref = self.ref_scores[name]
        p = np.searchsorted(ref, np.nan_to_num(s, nan=-np.inf), side="right") / max(len(ref), 1)
        return np.where(np.isnan(s), np.nan, p)


@dataclass
class DetectionEngine:
    profile: Profile
    models: dict = field(default_factory=dict)   # utility -> UtilityModels
    calibration_mode: str = "f1"
    seed: int = 42

    # ------------------------------------------------------------------ training
    def fit(self, train: pd.DataFrame, val: pd.DataFrame, log=print) -> "DetectionEngine":
        for utility in sorted(train["utility"].unique()):
            tr = train[train.utility == utility].sort_values(["meter_id", "ts"])
            va = val[val.utility == utility].sort_values(["meter_id", "ts"])
            um = UtilityModels()
            yv = va["is_anomaly"].values if "is_anomaly" in va else None
            f1s = {}
            for name in BASE_DETECTORS:
                t0 = time.perf_counter()
                det = _make(name, self.seed).fit(tr)
                um.fit_seconds[name] = time.perf_counter() - t0
                sv = det.score(va)
                det.calibrate(sv, yv, mode=self.calibration_mode if yv is not None else "quantile")
                um.detectors[name] = det
                um.ref_scores[name] = np.sort(sv[~np.isnan(sv)])
                if yv is not None:
                    ok = ~np.isnan(sv)
                    f1s[name] = f1_score(yv[ok], sv[ok] >= det.threshold)
                log(f"  [{utility}] {name:17s} fit {um.fit_seconds[name]:6.1f}s  val-F1 {f1s.get(name, float('nan')):.3f}")
            tot = sum(f1s.values()) or 1.0
            um.weights = {k: (f1s.get(k, 1.0) / tot) for k in BASE_DETECTORS}
            ens = self._ensemble_score(um, va)
            um.ensemble_threshold = calibrate_threshold(
                ens, yv, self.calibration_mode if yv is not None else "quantile")
            self.models[utility] = um
        return self

    # ------------------------------------------------------------------ scoring
    @staticmethod
    def _ensemble_score(um: UtilityModels, df: pd.DataFrame, raw: dict | None = None) -> np.ndarray:
        acc = np.zeros(len(df)); wsum = np.zeros(len(df))
        for name, det in um.detectors.items():
            s = raw[name] if raw is not None else det.score(df)
            p = um._pct(name, s)
            ok = ~np.isnan(p)
            acc[ok] += um.weights[name] * p[ok]; wsum[ok] += um.weights[name]
        out = np.where(wsum > 0, acc / np.maximum(wsum, 1e-12), np.nan)
        return np.where(df["scorable"].values, out, np.nan)

    def score_frame(self, feats: pd.DataFrame) -> pd.DataFrame:
        """Score a feature frame; adds score_*, flag_*, votes, ensemble columns."""
        parts = []
        for utility, g in feats.groupby("utility", sort=False):
            g = g.sort_values(["meter_id", "ts"]).copy()
            um = self.models[utility]
            raw = {}
            for name, det in um.detectors.items():
                raw[name] = det.score(g)
                g[f"score_{name}"] = raw[name]
                g[f"flag_{name}"] = np.nan_to_num(raw[name], nan=-np.inf) >= det.threshold
            ens = self._ensemble_score(um, g, raw)
            g["score_ensemble"] = ens
            g["flag_ensemble"] = np.nan_to_num(ens, nan=-1) >= um.ensemble_threshold
            g["votes"] = g[[f"flag_{n}" for n in um.detectors]].sum(axis=1)
            parts.append(g)
        return pd.concat(parts).sort_values(["utility", "meter_id", "ts"])

    def thresholds(self) -> dict:
        return {u: {**{n: float(d.threshold) for n, d in um.detectors.items()},
                    "ensemble": float(um.ensemble_threshold)} for u, um in self.models.items()}

    def set_threshold(self, utility: str, detector: str, value: float):
        """Operator override (audited by the caller)."""
        if detector == "ensemble":
            self.models[utility].ensemble_threshold = float(value)
        else:
            self.models[utility].detectors[detector].threshold = float(value)

    # ------------------------------------------------------------------ persistence
    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> "DetectionEngine":
        return joblib.load(path)
