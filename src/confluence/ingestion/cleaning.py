"""Ingestion step 2 — data cleaning.

* removes exact duplicate transmissions (same meter + timestamp)
* treats negative sentinel values (e.g. -1) as missing
* missing values are left as NaN here and filled after timestamp
  normalisation, where the regular grid makes interpolation well defined
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    n0 = len(df)
    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    neg = df["value"] < 0
    df.loc[neg, "value"] = np.nan
    df = df.drop_duplicates(subset=["meter_id", "ts"], keep="first")
    stats = {"input": n0, "duplicates_removed": n0 - len(df), "negatives_nulled": int(neg.sum()),
             "missing_values": int(df["value"].isna().sum())}
    return df, stats
