"""Synthetic multi-utility smart-meter data with labelled anomalies.

Why synthetic?  Public smart-meter datasets (SGCC, London Smart Meters) cover a
single utility and carry no point-level anomaly labels, so detection accuracy
cannot be measured on them directly.  This generator produces electricity, gas
and water streams with *known* injected anomalies so precision / recall / F1 /
ROC-AUC can be computed.  Results on synthetic data must be reported as such;
see ``confluence.data.sgcc`` for running the pipeline on the real SGCC data.

Realism features
----------------
* heterogeneous frequencies: electricity 15-min, gas hourly, water irregular 5-30 min
* diurnal + weekly profiles, per-meter scale, multiplicative noise
* data-quality faults the ingestion layer must fix (duplicates, missing values,
  negative sentinels, water timestamps reported in local time)
* anomaly types: spike, outage/theft-like drop, leak, stuck meter, drift
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

ANOMALY_TYPES = ("spike", "drop", "leak", "stuck", "drift")


@dataclass
class GeneratorConfig:
    days: int = 60
    meters_per_utility: int = 10
    start: str = "2026-01-05"          # a Monday
    seed: int = 42
    events_per_meter: int = 9
    dirty_rate: float = 0.004


def _profile(utility: str, hour: np.ndarray, weekend: np.ndarray) -> np.ndarray:
    """Expected consumption shape as a function of fractional hour of day."""
    g = lambda mu, sig: np.exp(-((hour - mu) ** 2) / (2 * sig ** 2))
    shift = np.where(weekend, 1.5, 0.0)  # people get up later at weekends
    if utility == "electricity":
        return 0.12 + 0.35 * g(7.5 + shift, 1.2) + 0.55 * g(19.0, 2.2) + 0.08 * g(13, 3)
    if utility == "gas":
        return 0.05 + 0.9 * g(7.0 + shift, 1.3) + 1.1 * g(19.5, 2.0)
    if utility == "water":
        return 0.25 + 7.5 * g(7.2 + shift, 0.8) + 4.0 * g(19.0, 1.5) + 1.2 * g(12.5, 1.5)
    raise ValueError(utility)


def _timestamps(utility: str, cfg: GeneratorConfig, rng: np.random.Generator) -> pd.DatetimeIndex:
    start = pd.Timestamp(cfg.start, tz="UTC")
    end = start + pd.Timedelta(days=cfg.days)
    if utility == "electricity":
        return pd.date_range(start, end, freq="15min", inclusive="left")
    if utility == "gas":
        return pd.date_range(start, end, freq="1h", inclusive="left")
    # water: irregular reporting interval
    n = int(cfg.days * 24 * 60 / 15 * 1.1)
    gaps = rng.uniform(5, 30, size=n)
    offs = np.cumsum(gaps) - gaps[0]
    offs = offs[offs < cfg.days * 24 * 60]
    return start + pd.to_timedelta(offs, unit="min")


def _inject(values: np.ndarray, ts: pd.DatetimeIndex, utility: str, cfg: GeneratorConfig,
            rng: np.random.Generator, mean_level: float):
    labels = np.zeros(len(values), dtype=bool)
    kinds = np.array([""] * len(values), dtype=object)
    allowed = ["spike", "drop", "stuck"] + (["leak"] if utility in ("gas", "water") else []) + \
              (["drift"] if utility == "electricity" else [])
    tsv = ts.values
    t0, t1 = tsv[0], tsv[-1]
    span = (t1 - t0) / np.timedelta64(1, "h")
    for _ in range(cfg.events_per_meter):
        w = np.array([{"spike": .32, "drop": .2, "stuck": .16, "leak": .2, "drift": .12}[k] for k in allowed])
        kind = rng.choice(allowed, p=w / w.sum())
        start_h = rng.uniform(24, span - 72)
        dur_h = {"spike": rng.uniform(0.25, 1.0) if utility != "gas" else rng.uniform(1, 2.5),
                 "drop": rng.uniform(3, 10), "leak": rng.uniform(6, 18),
                 "stuck": rng.uniform(3, 12), "drift": rng.uniform(12, 30)}[kind]
        a = t0 + np.timedelta64(int(start_h * 3600), "s")
        b = a + np.timedelta64(int(dur_h * 3600), "s")
        idx = np.where((tsv >= a) & (tsv < b))[0]
        if len(idx) == 0:
            continue
        if kind == "spike":
            values[idx] = values[idx] * rng.uniform(3, 6) + mean_level * rng.uniform(1.5, 3)
        elif kind == "drop":
            values[idx] = values[idx] * rng.uniform(0.0, 0.12)
        elif kind == "leak":
            values[idx] = values[idx] + mean_level * rng.uniform(0.5, 1.0)
        elif kind == "stuck":
            values[idx] = values[idx[0]]
        elif kind == "drift":
            values[idx] = values[idx] * np.linspace(1.3, 2.2, len(idx))
        labels[idx] = True
        kinds[idx] = kind
    return values, labels, kinds


def generate(cfg: GeneratorConfig | None = None) -> pd.DataFrame:
    """Return *raw* readings in long format.

    Columns: ``ts`` (ISO-8601 string with offset, as a device would send it),
    ``meter_id``, ``utility``, ``value`` (may be NaN / negative / duplicated),
    ``is_anomaly`` (ground truth), ``anomaly_type``.
    """
    cfg = cfg or GeneratorConfig()
    rng = np.random.default_rng(cfg.seed)
    frames = []
    for utility in ("electricity", "gas", "water"):
        for m in range(cfg.meters_per_utility):
            ts = _timestamps(utility, cfg, rng)
            local = ts.tz_convert("Europe/London")
            hour = local.hour.values + local.minute.values / 60
            weekend = local.dayofweek.values >= 5
            scale = rng.lognormal(0, 0.35)
            base = _profile(utility, hour, weekend) * scale
            season = 1 + 0.15 * np.cos(2 * np.pi * np.arange(len(ts)) / len(ts))
            noise_sd = {"electricity": 0.18, "gas": 0.15, "water": 0.35}[utility]
            vals = base * season * rng.lognormal(0, noise_sd, size=len(ts))
            vals, lab, kind = _inject(vals, ts, utility, cfg, rng, float(base.mean()))
            # ---- device-side data quality faults (not anomalies) ----
            vals = vals.astype(float)
            n_dirty = int(len(vals) * cfg.dirty_rate)
            vals[rng.choice(len(vals), n_dirty, replace=False)] = np.nan
            vals[rng.choice(len(vals), max(1, n_dirty // 4), replace=False)] = -1.0
            if utility == "water":   # water meters report local time
                ts_str = local.strftime("%Y-%m-%dT%H:%M:%S%z")
            else:
                ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S%z")
            df = pd.DataFrame({
                "ts": ts_str, "meter_id": f"{utility[0].upper()}{m:03d}", "utility": utility,
                "value": np.round(vals, 4), "is_anomaly": lab, "anomaly_type": kind,
            })
            dup = df.sample(frac=cfg.dirty_rate, random_state=int(rng.integers(1e9)))
            frames.append(pd.concat([df, dup]))
    out = pd.concat(frames, ignore_index=True)
    return out.sample(frac=1.0, random_state=cfg.seed).reset_index(drop=True)  # out-of-order arrival
