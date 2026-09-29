"""Ingestion step 1 — data validation.

Checks schema, types and physical plausibility of each raw reading.  Invalid
records are not silently dropped: they are flagged so they can be counted and
logged (cross-cutting monitoring).
"""
from __future__ import annotations

import pandas as pd

from confluence.config import UTILITIES

REQUIRED = ("ts", "meter_id", "utility", "value")
# generous physical upper bounds per canonical reading
MAX_VALUE = {"electricity": 50.0, "gas": 50.0, "water": 500.0}


def validate_record(rec: dict) -> tuple[bool, str]:
    """Validate a single streaming record. Returns (ok, reason)."""
    for k in REQUIRED:
        if k not in rec:
            return False, f"missing_field:{k}"
    if rec["utility"] not in UTILITIES:
        return False, "unknown_utility"
    try:
        pd.Timestamp(rec["ts"])
    except Exception:  # noqa: BLE001
        return False, "bad_timestamp"
    v = rec["value"]
    if v is None:
        return True, "missing_value"  # repairable by cleaning
    try:
        v = float(v)
    except (TypeError, ValueError):
        return False, "non_numeric"
    if v > MAX_VALUE[rec["utility"]]:
        return False, "implausible_high"
    return True, "ok"


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Vectorised validation. Returns (valid_rows, reason_counts)."""
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    reason = pd.Series("ok", index=df.index)
    reason[~df["utility"].isin(list(UTILITIES))] = "unknown_utility"
    ts = pd.to_datetime(df["ts"], errors="coerce", utc=True, format="ISO8601")
    reason[ts.isna()] = "bad_timestamp"
    val = pd.to_numeric(df["value"], errors="coerce")
    limit = df["utility"].map(MAX_VALUE)
    reason[(val > limit)] = "implausible_high"
    reason[val.isna() & (reason == "ok")] = "missing_value"
    keep = reason.isin(["ok", "missing_value"])
    return df[keep].copy(), reason.value_counts()
