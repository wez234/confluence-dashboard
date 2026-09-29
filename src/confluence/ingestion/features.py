"""Ingestion step 4 — feature extraction.

All features are *causal* (they use only the current and past readings of a
meter), so exactly the same code runs offline for training/evaluation and
online inside the Kafka consumer.

Feature                 Meaning (used by the explainability module)
----------------------  ---------------------------------------------------
profile_z               deviation from the meter's usual value for this hour
ma_z                    deviation from the recent moving average
rate_of_change          step change vs previous reading (relative)
volatility              recent rolling std (relative)
flat_run                how long the reading has been exactly constant
min_level               recent rolling minimum (relative) — leaks lift it
cross_meter_z           deviation from other meters of the same utility now
level                   reading relative to the meter's mean
hour_sin / hour_cos     time of day
is_weekend              weekend flag
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

FEATURES = ["profile_z", "ma_z", "rate_of_change", "volatility", "flat_run", "min_level",
            "cross_meter_z", "level", "hour_sin", "hour_cos", "is_weekend"]

FEATURE_LABELS = {
    "profile_z": "Deviation from usual hourly profile",
    "ma_z": "Deviation from 24-hour moving average",
    "rate_of_change": "Rate of change",
    "volatility": "Recent volatility",
    "flat_run": "Constant-reading duration",
    "min_level": "Elevated baseline (rolling minimum)",
    "cross_meter_z": "Deviation from peer meters",
    "level": "Consumption level",
    "hour_sin": "Time of day (sin)",
    "hour_cos": "Time of day (cos)",
    "is_weekend": "Weekend",
}

WINDOW = 8  # steps for short rolling statistics
DAY_STEPS = {"electricity": 96, "gas": 24, "water": 96}


def _local_hour(ts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    local = ts.dt.tz_convert("Europe/London")
    return local.dt.hour.values, (local.dt.dayofweek.values >= 5)


@dataclass
class Profile:
    """Per-meter, per-hour, weekday/weekend baseline learned from training data."""
    median: dict = field(default_factory=dict)   # (meter, hour, weekend) -> median
    scale: dict = field(default_factory=dict)    # (meter, hour, weekend) -> robust std
    meter_mean: dict = field(default_factory=dict)

    def fit(self, norm: pd.DataFrame) -> "Profile":
        d = norm.dropna(subset=["value"]).copy()
        d["hour"], d["weekend"] = _local_hour(d["ts"])
        g = d.groupby(["meter_id", "hour", "weekend"])["value"]
        med = g.median()
        mad = g.apply(lambda s: np.median(np.abs(s - np.median(s)))) * 1.4826
        self.median = {k: float(v) for k, v in med.items()}
        self.meter_mean = {k: float(v) for k, v in d.groupby("meter_id")["value"].mean().items()}
        floor = {m: 0.05 * mu + 1e-6 for m, mu in self.meter_mean.items()}
        self.scale = {k: max(float(v), floor[k[0]]) for k, v in mad.items()}
        return self

    def to_dict(self) -> dict:
        return {"median": [[*k, v] for k, v in self.median.items()],
                "scale": [[*k, v] for k, v in self.scale.items()],
                "meter_mean": self.meter_mean}

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        p = cls()
        p.median = {(m, int(h), bool(w)): v for m, h, w, v in d["median"]}
        p.scale = {(m, int(h), bool(w)): v for m, h, w, v in d["scale"]}
        p.meter_mean = d["meter_mean"]
        return p


def compute_features(norm: pd.DataFrame, profile: Profile) -> pd.DataFrame:
    """Add FEATURES columns to a normalised frame (single or multiple utilities)."""
    df = norm.sort_values(["meter_id", "ts"]).copy()
    hour, weekend = _local_hour(df["ts"])
    df["hour_sin"], df["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    df["is_weekend"] = weekend.astype(float)
    keys = list(zip(df["meter_id"], hour.astype(int), weekend.astype(bool)))
    mean = df["meter_id"].map(profile.meter_mean).astype(float)
    med = np.array([profile.median.get(k, np.nan) for k in keys])
    sc = np.array([profile.scale.get(k, np.nan) for k in keys])
    med = np.where(np.isnan(med), mean, med)
    sc = np.where(np.isnan(sc), 0.25 * mean + 1e-6, sc)
    v = df["value"]
    df["level"] = v / mean
    df["profile_z"] = (v - med) / sc
    df["expected"] = med                                   # typical value for this meter/hour/day type
    df["ratio"] = (v / (med + 0.02 * mean)).clip(0, 20)   # reading / expected reading (LSTM input)

    g = v.groupby(df["meter_id"])
    # 24-hour moving average baseline (96 steps at 15-min, 24 steps hourly)
    day = df["utility"].map(lambda u: DAY_STEPS.get(u, 96)).astype(int)
    prev_mean = pd.Series(np.nan, index=df.index); prev_std = pd.Series(np.nan, index=df.index)
    for w in day.unique():
        m = day == w
        gg = v[m].groupby(df.loc[m, "meter_id"])
        prev_mean[m] = gg.transform(lambda s: s.shift(1).rolling(w, min_periods=4).mean())
        prev_std[m] = gg.transform(lambda s: s.shift(1).rolling(w, min_periods=4).std())
    df["ma_z"] = (v - prev_mean) / (prev_std + 0.05 * mean)
    df["rate_of_change"] = g.diff() / mean
    df["volatility"] = g.transform(lambda s: s.rolling(WINDOW, min_periods=3).std()) / mean
    df["min_level"] = g.transform(lambda s: s.rolling(WINDOW, min_periods=3).min()) / mean

    same = (g.diff() == 0).astype(int)
    run = same.groupby([df["meter_id"], (same == 0).cumsum()]).cumsum()
    df["flat_run"] = np.minimum(run, 12) / 12.0

    lvl = df.groupby(["utility", "ts"])["level"]
    peer_med = lvl.transform("median")
    peer_iqr = lvl.transform(lambda s: s.quantile(0.75) - s.quantile(0.25))
    df["cross_meter_z"] = (df["level"] - peer_med) / (peer_iqr + 0.1)

    df[FEATURES] = df[FEATURES].clip(-50, 50)
    df["scorable"] = df[FEATURES].notna().all(axis=1)
    return df
