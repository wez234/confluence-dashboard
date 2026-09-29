"""Detection techniques compared in the dissertation.

Statistical        : Z-score (profile deviation), Moving-average deviation
Machine learning   : Isolation Forest, One-Class SVM
Deep learning      : LSTM autoencoder (sequence reconstruction error)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from confluence.detection.base import Detector
from confluence.ingestion.features import FEATURES


def _X(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    ok = df["scorable"].values if "scorable" in df else df[FEATURES].notna().all(axis=1).values
    return df[FEATURES].fillna(0).values, ok


class ZScoreDetector(Detector):
    name, family, interpretability = "zscore", "statistical", "High"

    def score(self, df):
        s = np.abs(df["profile_z"].values.astype(float))
        return np.where(df["scorable"].values, s, np.nan)


class MovingAverageDetector(Detector):
    name, family, interpretability = "moving_average", "statistical", "High"

    def score(self, df):
        s = np.abs(df["ma_z"].values.astype(float))
        return np.where(df["scorable"].values, s, np.nan)


class IsolationForestDetector(Detector):
    name, family, interpretability = "isolation_forest", "machine_learning", "Medium (TreeSHAP)"

    def __init__(self, n_estimators: int = 200, seed: int = 42):
        super().__init__()
        self.model = IsolationForest(n_estimators=n_estimators, max_samples=512,
                                     contamination="auto", random_state=seed, n_jobs=-1)

    def fit(self, df):
        X, ok = _X(df)
        self.model.fit(X[ok])
        return self

    def score(self, df):
        X, ok = _X(df)
        return np.where(ok, -self.model.score_samples(X), np.nan)


class OneClassSVMDetector(Detector):
    name, family, interpretability = "one_class_svm", "machine_learning", "Low (model-agnostic XAI)"

    def __init__(self, nu: float = 0.05, max_train: int = 3000, seed: int = 42):
        super().__init__()
        self.scaler = StandardScaler()
        self.model = OneClassSVM(nu=nu, kernel="rbf", gamma="scale")
        self.max_train, self.seed = max_train, seed

    def fit(self, df):
        X, ok = _X(df)
        X = X[ok]
        rng = np.random.default_rng(self.seed)
        if len(X) > self.max_train:
            X = X[rng.choice(len(X), self.max_train, replace=False)]
        self.model.fit(self.scaler.fit_transform(X))
        return self

    def score(self, df):
        X, ok = _X(df)
        return np.where(ok, -self.model.decision_function(self.scaler.transform(X)), np.nan)
