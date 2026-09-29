"""UK smart-meter adapter: London Datastore "Smart Meter Energy Consumption Data in
London Households" (Low Carbon London, UK Power Networks, 2011-2014).

Expected CSV columns: ``LCLid, stdorToU, DateTime, KWH/hh (per half hour)``.
Half-hourly kWh in UK local time is converted to UTC and split evenly into two
15-minute readings so it fits the platform's canonical electricity grid.
Only household pseudonymous IDs are present (no PII); IDs are re-labelled
E000, E001, ... on load.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def load_lcl(path: str, meters: int = 10, days: int = 60, seed: int = 42) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=[0, 2, 3], names=["LCLid", "DateTime", "kwh"], header=0,
                     na_values=["Null", "null", ""])
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce")
    df["ts"] = pd.to_datetime(df["DateTime"]).dt.tz_localize("Europe/London", ambiguous="NaT",
                                                               nonexistent="NaT").dt.tz_convert("UTC")
    df = df.dropna(subset=["ts"])
    rng = np.random.default_rng(seed)
    ids = df.LCLid.unique()
    ids = ids[rng.permutation(len(ids))[:meters]]
    out = []
    for m, lid in enumerate(ids):
        g = df[df.LCLid == lid].sort_values("ts")
        g = g[g.ts >= g.ts.max() - pd.Timedelta(days=days)]
        half = g.kwh / 2
        a = pd.DataFrame({"ts": g.ts, "value": half})
        b = pd.DataFrame({"ts": g.ts + pd.Timedelta(minutes=15), "value": half})
        s = pd.concat([a, b]).sort_values("ts")
        out.append(s.assign(meter_id=f"E{m:03d}", utility="electricity"))
    res = pd.concat(out, ignore_index=True)
    res["ts"] = res.ts.dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    res["is_anomaly"] = False
    res["anomaly_type"] = ""
    return res[["ts", "meter_id", "utility", "value", "is_anomaly", "anomaly_type"]]
