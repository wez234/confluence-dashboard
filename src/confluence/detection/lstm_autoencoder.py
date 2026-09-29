"""LSTM autoencoder detector (deep learning).

Each reading is scored with the reconstruction error of the window of the
last ``seq_len`` readings of the same meter.  The model is trained only on
windows that look normal (robust filter on the statistical profile deviation;
no ground-truth labels are used), so high reconstruction error indicates a
temporal pattern the network has not seen — drifts, leaks and stuck meters as
well as spikes.

Configuration (seq_len=16, hidden=8) was selected on the *validation* period
from five candidates (input sets x window length x bottleneck size); see
docs/EXPERIMENTS.md.  The test period was not used for model selection.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from torch import nn

from confluence.detection.base import Detector

SEQ_FEATURES = ["profile_z", "level", "min_level", "hour_sin", "hour_cos"]


class _AE(nn.Module):
    def __init__(self, n_features: int, hidden: int = 8):
        super().__init__()
        self.enc = nn.LSTM(n_features, hidden, batch_first=True)
        self.dec = nn.LSTM(hidden, hidden, batch_first=True)
        self.out = nn.Linear(hidden, n_features)

    def forward(self, x):
        _, (h, _) = self.enc(x)
        z = h[-1].unsqueeze(1).repeat(1, x.shape[1], 1)
        y, _ = self.dec(z)
        return self.out(y)


def _prep(df: pd.DataFrame) -> np.ndarray:
    X = df[SEQ_FEATURES].astype(float).fillna(0).values.copy()
    X[:, 0] = np.clip(X[:, 0], -10, 10) / 5.0
    X[:, 1:3] = np.clip(X[:, 1:3], 0, 10)
    return X.astype(np.float32)


def _windows(df: pd.DataFrame, seq_len: int):
    """Return (windows, row_positions) for every row that has a full history."""
    X = _prep(df)
    meters = df["meter_id"].values
    wins, pos = [], []
    start = 0
    for i in range(1, len(df) + 1):
        if i == len(df) or meters[i] != meters[start]:
            seg = X[start:i]
            if len(seg) >= seq_len:
                w = np.lib.stride_tricks.sliding_window_view(seg, (seq_len, seg.shape[1]))[:, 0]
                wins.append(w)
                pos.append(np.arange(start + seq_len - 1, i))
            start = i
    if not wins:
        return np.empty((0, seq_len, X.shape[1]), np.float32), np.empty(0, int)
    return np.concatenate(wins), np.concatenate(pos)


class LSTMAutoencoderDetector(Detector):
    name, family, interpretability = "lstm_autoencoder", "deep_learning", "Low (post-hoc SHAP/LIME)"

    def __init__(self, seq_len: int = 16, hidden: int = 8, epochs: int = 12,
                 max_windows: int = 15000, seed: int = 42):
        super().__init__()
        self.seq_len, self.hidden, self.epochs = seq_len, hidden, epochs
        self.max_windows, self.seed = max_windows, seed
        self.model: _AE | None = None
        self.train_loss: list[float] = []

    def fit(self, df: pd.DataFrame):
        torch.manual_seed(self.seed)
        df = df.sort_values(["meter_id", "ts"])
        W, pos = _windows(df, self.seq_len)
        # unsupervised robust filter: keep windows without extreme profile deviations
        pz = np.abs(df["profile_z"].fillna(0).values)
        mx = np.array([pz[p - self.seq_len + 1:p + 1].max() for p in pos])
        W = W[mx < 6]
        rng = np.random.default_rng(self.seed)
        if len(W) > self.max_windows:
            W = W[rng.choice(len(W), self.max_windows, replace=False)]
        self.model = _AE(W.shape[2], self.hidden)
        opt = torch.optim.Adam(self.model.parameters(), lr=3e-3)
        data = torch.from_numpy(W)
        self.model.train()
        for _ in range(self.epochs):
            perm = torch.randperm(len(data))
            tot = 0.0
            for b in range(0, len(data), 256):
                x = data[perm[b:b + 256]]
                loss = ((self.model(x) - x) ** 2).mean()
                opt.zero_grad(); loss.backward(); opt.step()
                tot += float(loss.detach()) * len(x)
            self.train_loss.append(tot / len(data))
        return self

    @torch.no_grad()
    def score(self, df: pd.DataFrame) -> np.ndarray:
        """Scores aligned with ``df`` row order (df must be sorted by meter, ts)."""
        out = np.full(len(df), np.nan)
        W, pos = _windows(df, self.seq_len)
        if len(W) == 0:
            return out
        self.model.eval()
        errs = []
        for b in range(0, len(W), 4096):
            x = torch.from_numpy(W[b:b + 4096])
            e = ((self.model(x) - x) ** 2)[:, -4:, :].mean(dim=(1, 2))  # weight recent steps
            errs.append(e.numpy())
        out[pos] = np.concatenate(errs)
        ok = df["scorable"].values if "scorable" in df else np.ones(len(df), bool)
        return np.where(ok, out, np.nan)

    def state(self) -> dict:
        return {"seq_len": self.seq_len, "hidden": self.hidden, "threshold": self.threshold,
                "weights": self.model.state_dict(), "train_loss": self.train_loss}

    @classmethod
    def from_state(cls, st: dict) -> "LSTMAutoencoderDetector":
        d = cls(seq_len=st["seq_len"], hidden=st["hidden"])
        d.model = _AE(len(SEQ_FEATURES), st["hidden"])
        d.model.load_state_dict(st["weights"])
        d.threshold, d.train_loss = st["threshold"], st.get("train_loss", [])
        return d
