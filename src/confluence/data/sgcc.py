"""SGCC electricity data adapter (State Grid Corporation of China benchmark).

The public SGCC dataset (42,372 customers, daily kWh, Jan 2014 - Oct 2016,
customer-level theft FLAG) is a common electricity-theft benchmark.  Download
``data.csv`` (e.g. from https://github.com/henryRDlab/ElectricityTheftDetection)
into ``data/sgcc/``.

Because SGCC is *daily* and labelled per customer rather than per reading, the
adapter builds a semi-synthetic multi-utility stream:

* electricity = real SGCC daily totals of FLAG=0 customers, disaggregated to
  15-minute readings with a typical UK load shape (keeps real day-to-day
  variation, weekly patterns and customer heterogeneity)
* gas and water = simulated (as stated in the proposal)
* labelled anomalies are injected into all three so that point-level
  precision / recall can be measured
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from confluence.data import generator as gen


def load_sgcc_daily(path: str, meters: int, days: int = 60, seed: int = 42) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["FLAG"] == 0].drop(columns=["FLAG"]).set_index("CONS_NO")
    df.columns = pd.to_datetime(df.columns, errors="coerce")
    df = df.loc[:, df.columns.notna()].sort_index(axis=1)
    window = df.iloc[:, -days:]
    window = window[window.notna().mean(axis=1) > 0.95]
    window = window[(window.fillna(0) > 0).mean(axis=1) > 0.95]
    rng = np.random.default_rng(seed)
    pick = window.iloc[rng.choice(len(window), meters, replace=False)]
    return pick.T.interpolate().bfill()   # days x meters


def load_sgcc_multi_utility(path: str, meters: int = 10, days: int = 60, seed: int = 42) -> pd.DataFrame:
    cfg = gen.GeneratorConfig(days=days, meters_per_utility=meters, seed=seed)
    synthetic = gen.generate(cfg)
    rest = synthetic[synthetic.utility != "electricity"]
    daily = load_sgcc_daily(path, meters, days, seed)
    rng = np.random.default_rng(seed + 1)
    ts = pd.date_range(pd.Timestamp(cfg.start, tz="UTC"), periods=days * 96, freq="15min")
    local = ts.tz_convert("Europe/London")
    hour = local.hour.values + local.minute.values / 60
    shape = gen._profile("electricity", hour, local.dayofweek.values >= 5)
    frames = []
    for m, col in enumerate(daily.columns):
        day_idx = np.arange(len(ts)) // 96
        s = shape.reshape(days, 96)
        s = (s / s.sum(axis=1, keepdims=True)).ravel()
        vals = daily[col].values[day_idx] * s * rng.lognormal(0, 0.15, len(ts))
        vals, lab, kind = gen._inject(vals, ts, "electricity", cfg, rng, float(vals.mean()))
        frames.append(pd.DataFrame({"ts": ts.strftime("%Y-%m-%dT%H:%M:%S%z"), "meter_id": f"E{m:03d}",
                                    "utility": "electricity", "value": np.round(vals, 4),
                                    "is_anomaly": lab, "anomaly_type": kind}))
    return pd.concat(frames + [rest], ignore_index=True)
