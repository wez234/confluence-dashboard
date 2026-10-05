"""Supplementary experiments for the dissertation results chapter.

1. STL decomposition baseline (Cleveland et al., 1990) - offline/retrospective.
   Per meter: STL(period = 1 day, robust) on the cleaned series; score = |residual|
   divided by the residual MAD on the training period. Threshold calibrated on the
   validation period with the same F1 / 15% alert-budget rule as every other detector.
   STL needs the whole window (it is centred, not causal), so it is reported as an
   offline comparator, not part of the streaming engine.
2. Per-detector inference cost (ms per 1,000 readings) on the test period.
3. Detection delay (median steps / minutes from anomaly onset to first flag).

Writes reports/supplementary.json.  Run:  PYTHONPATH=src python scripts/supplementary_experiments.py
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from confluence.config import UTILITIES, settings
from confluence.detection.base import calibrate_threshold
from confluence.detection.engine import DetectionEngine
from confluence.evaluation.run import event_recall, point_metrics

TEMPORAL = {"drift", "leak", "stuck"}


def step_minutes(u):
    return pd.Timedelta(UTILITIES[u].freq).total_seconds() / 60


def stl_scores(df: pd.DataFrame) -> tuple[np.ndarray, float]:
    out = np.full(len(df), np.nan)
    t0 = time.perf_counter()
    for _, idx in df.groupby("meter_id").groups.items():
        g = df.loc[idx].sort_values("ts")
        u = g.utility.iloc[0]
        period = int(round(24 * 60 / step_minutes(u)))
        y = g.value.interpolate(limit_direction="both").values
        res = STL(y, period=period, robust=True).fit().resid
        tr = (g.split == "train").values
        mad = np.median(np.abs(res[tr] - np.median(res[tr]))) * 1.4826 + 1e-9
        out[df.index.get_indexer(g.index)] = np.abs(res) / mad
    return out, time.perf_counter() - t0


def main():
    d = pd.read_parquet(settings.artifacts_dir / "scored.parquet").reset_index(drop=True)
    eng = DetectionEngine.load(settings.artifacts_dir / "engine.joblib")
    res = {"stl": {}, "inference_ms_per_1000": {}, "detection_delay": {}}

    # ---- STL
    s, secs = stl_scores(d)
    d["score_stl"] = s
    d["flag_stl"] = False
    for u in UTILITIES:
        va = (d.utility == u) & (d.split == "validation")
        thr = calibrate_threshold(d.loc[va, "score_stl"].values, d.loc[va, "is_anomaly"].values.astype(int))
        m = d.utility == u
        d.loc[m, "flag_stl"] = d.loc[m, "score_stl"].fillna(-np.inf) >= thr
    d["scorable"] = d.score_ensemble.notna()
    te = d[(d.split == "test")].copy()
    te.loc[~te.score_ensemble.notna(), "score_stl"] = np.nan   # same scorable rows as the engine
    y = te.is_anomaly.values.astype(int)
    te[["ts", "meter_id", "utility", "score_stl", "flag_stl"]].to_parquet(settings.reports_dir / "stl_test_scores.parquet")
    res["stl"]["overall"] = point_metrics(y, te.score_stl.values, te.flag_stl.values)
    res["stl"]["by_utility_f1"] = {}
    for u in UTILITIES:
        g = te[te.utility == u]
        res["stl"]["by_utility_f1"][u] = point_metrics(g.is_anomaly.values.astype(int), g.score_stl.values, g.flag_stl.values)["f1"]
    rec = {}
    ok = te.score_stl.notna()
    for t in sorted(te.anomaly_type[te.is_anomaly.astype(bool)].unique()):
        mm = ok & (te.anomaly_type == t)
        rec[t] = float(te.loc[mm, "flag_stl"].mean())
    mm = ok & te.anomaly_type.isin(TEMPORAL)
    rec["temporal"] = float(te.loc[mm, "flag_stl"].mean())
    # recall at matched 5% FPR on temporal
    neg = te.loc[ok & ~te.is_anomaly.astype(bool), "score_stl"].values
    thr5 = np.quantile(neg, 0.95)
    rec["temporal_at_fpr5"] = float((te.loc[mm, "score_stl"] >= thr5).mean())
    res["stl"]["recall_by_type"] = rec
    res["stl"]["event"] = event_recall(te, "flag_stl")
    res["stl"]["fit_score_seconds_all_meters_60_days"] = secs

    # ---- detection delay per detector (minutes, median over detected events)
    for name in ["zscore", "moving_average", "isolation_forest", "one_class_svm", "lstm_autoencoder", "ensemble", "stl"]:
        per = {}
        for u in UTILITIES:
            g = te[te.utility == u]
            e = event_recall(g, f"flag_{name}")
            per[u] = {"events": e["events"], "detected": e["detected"],
                      "median_delay_minutes": e["median_delay_steps"] * step_minutes(u)}
        res["detection_delay"][name] = per

    # ---- inference cost per detector on the test period
    feats = d[d.split == "test"]
    for u, um in eng.models.items():
        g = feats[feats.utility == u].sort_values(["meter_id", "ts"])
        for name, det in um.detectors.items():
            ts = []
            for _ in range(3):
                t0 = time.perf_counter(); det.score(g); ts.append(time.perf_counter() - t0)
            res["inference_ms_per_1000"].setdefault(name, {})[u] = 1000 * min(ts) / len(g) * 1000
    res["inference_ms_per_1000"] = {k: {**v, "mean": float(np.mean(list(v.values())))} for k, v in res["inference_ms_per_1000"].items()}
    res["note"] = ("Inference cost is batch scoring time on the test period divided by readings (best of 3), "
                   "single process, 2 vCPU. STL is offline (centred decomposition over the full 60 days).")
    out = settings.reports_dir / "supplementary.json"
    out.write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({"stl": res["stl"]["overall"], "stl_types": rec, "stl_event": res["stl"]["event"],
                      "stl_util": res["stl"]["by_utility_f1"], "secs": secs}, indent=1, default=float))
    print(json.dumps(res["inference_ms_per_1000"], indent=1))
    print(json.dumps({k: {u: round(x["median_delay_minutes"], 1) for u, x in v.items()} for k, v in res["detection_delay"].items()}, indent=1))


if __name__ == "__main__":
    main()
