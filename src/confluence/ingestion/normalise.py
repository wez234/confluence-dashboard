"""Ingestion step 3 — timestamp normalisation.

Devices report in different time zones and at different (and, for water,
irregular) intervals.  Every reading is converted to UTC and aggregated onto
the utility's canonical grid (electricity/water 15-min, gas hourly).  Short
gaps (<= 2 steps) are linearly interpolated; longer gaps stay missing and are
excluded from detection.  A common hourly view is also provided for
cross-utility comparison.
"""
from __future__ import annotations

import pandas as pd

from confluence.config import UTILITIES


def to_utc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
    return df


def normalise(df: pd.DataFrame, max_gap_steps: int = 2) -> pd.DataFrame:
    """Return a regular-grid frame: ts, meter_id, utility, value[, is_anomaly, anomaly_type]."""
    df = to_utc(df)
    has_label = "is_anomaly" in df.columns
    out = []
    for (utility, meter), g in df.groupby(["utility", "meter_id"], sort=False):
        freq = UTILITIES[utility].freq
        g = g.set_index("ts").sort_index()
        grid_start = g.index.min().floor(freq)
        agg = {"value": "mean"}
        if has_label:
            agg.update({"is_anomaly": "max", "anomaly_type": "max"})
        r = g.resample(freq, origin=grid_start).agg(agg)
        r["value_filled"] = r["value"].isna()
        r["value"] = r["value"].interpolate(limit=max_gap_steps, limit_area="inside")
        r["value_filled"] &= r["value"].notna()
        r["utility"], r["meter_id"] = utility, meter
        out.append(r.reset_index())
    res = pd.concat(out, ignore_index=True)
    if has_label:
        res["is_anomaly"] = res["is_anomaly"].fillna(False).astype(bool)
        res["anomaly_type"] = res["anomaly_type"].fillna("")
    return res.sort_values(["utility", "meter_id", "ts"]).reset_index(drop=True)


def hourly_common_axis(norm: pd.DataFrame) -> pd.DataFrame:
    """Hourly per-utility totals on one shared UTC axis (for cross-utility views)."""
    h = norm.set_index("ts").groupby("utility")["value"].resample("1h").mean()
    return h.reset_index()
