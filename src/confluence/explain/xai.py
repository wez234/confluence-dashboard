"""Explainability module (SHAP / LIME).

* SHAP  — exact TreeSHAP (Lundberg & Lee, 2017) on the Isolation Forest of each
  utility.  Fast enough (milliseconds) to attach to every alert in the
  streaming path.
* LIME  — local surrogate (Ribeiro et al., 2016) of the *tabular ensemble*
  (Z-score, moving average, Isolation Forest, One-Class SVM).  Used on demand
  in the dashboard and in the offline explanation-agreement evaluation.

The LSTM autoencoder consumes windows rather than single feature vectors, so
it is not included in the LIME surrogate; this limitation is reported.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap
from lime.lime_tabular import LimeTabularExplainer

from confluence.detection.engine import DetectionEngine
from confluence.ingestion.features import FEATURE_LABELS, FEATURES

TABULAR = ["zscore", "moving_average", "isolation_forest", "one_class_svm"]

from confluence.explain.narrative import EXPECTED_DRIVERS, narrative, top  # noqa: E402,F401


class Explainer:
    def __init__(self, engine: DetectionEngine, background: pd.DataFrame, seed: int = 42):
        self.engine = engine
        self.tree = {}
        self.lime = {}
        self.bg_summary = {}
        rng = np.random.default_rng(seed)
        for utility, um in engine.models.items():
            self.tree[utility] = shap.TreeExplainer(um.detectors["isolation_forest"].model)
            bg = background[(background.utility == utility) & background.scorable][FEATURES]
            bg = bg.iloc[rng.choice(len(bg), min(2000, len(bg)), replace=False)].values
            self.bg_summary[utility] = shap.kmeans(bg, 20)
            self.lime[utility] = LimeTabularExplainer(
                bg, feature_names=FEATURES, mode="regression", discretize_continuous=True,
                discretizer="decile", random_state=seed)

    # -------------------------------------------------------------- SHAP
    def shap_values(self, utility: str, X: np.ndarray) -> np.ndarray:
        # IsolationForest SHAP explains the path length (higher = more normal);
        # negate so positive contributions push towards "anomalous".
        return -np.asarray(self.tree[utility].shap_values(X))

    # -------------------------------------------------------------- LIME
    def _tabular_fn(self, utility: str):
        um = self.engine.models[utility]
        wsum = sum(um.weights[n] for n in TABULAR)

        def f(X: np.ndarray) -> np.ndarray:
            df = pd.DataFrame(X, columns=FEATURES)
            df["scorable"] = True
            acc = np.zeros(len(df))
            for n in TABULAR:
                acc += um.weights[n] * um._pct(n, um.detectors[n].score(df))
            return acc / wsum
        return f

    def lime_values(self, utility: str, x: np.ndarray, num_samples: int = 800) -> np.ndarray:
        exp = self.lime[utility].explain_instance(x, self._tabular_fn(utility),
                                                  num_features=len(FEATURES), num_samples=num_samples)
        # Standard (discretised) LIME: each weight is the effect of the instance's
        # decile bin for that feature, so positive = pushes towards anomalous.
        # NB: in regression mode LIME stores the fitted weights under label 1
        # (label 0 holds their negation).
        m = exp.as_map()
        out = np.zeros(len(FEATURES))
        for i, w in m[1 if 1 in m else 0]:
            out[i] = w
        return out

    def kernel_shap_values(self, utility: str, x: np.ndarray, nsamples: int = 300) -> np.ndarray:
        """Model-agnostic KernelSHAP on the same tabular ensemble LIME explains."""
        ke = shap.KernelExplainer(self._tabular_fn(utility), self.bg_summary[utility])
        return np.asarray(ke.shap_values(x[None, :], nsamples=nsamples, silent=True))[0]

    # -------------------------------------------------------------- helpers
    top = staticmethod(top)
