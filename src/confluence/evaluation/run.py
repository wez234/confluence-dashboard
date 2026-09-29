"""End-to-end offline experiment: build data, train, evaluate, benchmark, export.

    python -m confluence.evaluation.run                 # synthetic multi-utility data
    python -m confluence.evaluation.run --source sgcc --sgcc-path data/sgcc/data.csv

Outputs
    artifacts/engine.joblib           trained detection engine (all utilities)
    artifacts/scored.parquet          scored readings (dashboard demo mode)
    artifacts/alerts.parquet          grouped alert events with SHAP explanations
    reports/metrics.json              every number in the evaluation report
    reports/evaluation_report.md      tables + hypothesis verdicts (H1, H2)
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import pandas as pd
import psutil
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score, roc_curve

from confluence.alerts.rules import cross_utility_escalations, group_events
from confluence.config import UTILITIES, settings
from confluence.data.generator import GeneratorConfig, generate
from confluence.detection.engine import ALL_DETECTORS, DISPLAY, FAMILY, DetectionEngine
from confluence.explain.xai import EXPECTED_DRIVERS, Explainer
from confluence.ingestion.cleaning import clean
from confluence.ingestion.features import FEATURES, Profile, compute_features
from confluence.ingestion.normalise import normalise
from confluence.ingestion.stream_processor import StreamProcessor
from confluence.ingestion.validation import validate
from confluence.logging_setup import get_logger

log = get_logger("evaluation")
TEMPORAL = ("drift", "leak", "stuck")
SPLIT_DAYS = (35, 45)   # train < 35 <= validation < 45 <= test


def _proc() -> psutil.Process:
    return psutil.Process(os.getpid())


def load_raw(args) -> pd.DataFrame:
    if args.source == "synthetic":
        return generate(GeneratorConfig(days=args.days, meters_per_utility=args.meters, seed=args.seed))
    if args.source == "sgcc":
        from confluence.data.sgcc import load_sgcc_multi_utility
        return load_sgcc_multi_utility(args.sgcc_path, meters=args.meters, seed=args.seed)
    raise ValueError(args.source)


def point_metrics(y: np.ndarray, s: np.ndarray, flag: np.ndarray) -> dict:
    ok = ~np.isnan(s)
    y, s, flag = y[ok].astype(int), s[ok], flag[ok]
    fpr, tpr, _ = roc_curve(y, s)
    return {"precision": precision_score(y, flag, zero_division=0), "recall": recall_score(y, flag, zero_division=0),
            "f1": f1_score(y, flag, zero_division=0), "roc_auc": roc_auc_score(y, s) if y.any() else float("nan"),
            "recall_at_fpr5": float(np.interp(0.05, fpr, tpr)), "n": int(len(y)), "positives": int(y.sum())}


def event_recall(df: pd.DataFrame, flag_col: str, lag_steps: int = 2) -> dict:
    hits, total, delays = 0, 0, []
    for _, g in df.groupby("meter_id"):
        lab = g["is_anomaly"].values.astype(bool)
        fl = g[flag_col].values.astype(bool)
        i = 0
        while i < len(lab):
            if lab[i]:
                j = i
                while j < len(lab) and lab[j]:
                    j += 1
                total += 1
                w = np.where(fl[i:min(j + lag_steps, len(fl))])[0]
                if len(w):
                    hits += 1
                    delays.append(int(w[0]))
                i = j
            else:
                i += 1
    return {"events": total, "detected": hits, "event_recall": hits / total if total else float("nan"),
            "median_delay_steps": float(np.median(delays)) if delays else float("nan")}


def alert_coverage(scored: pd.DataFrame, events: pd.DataFrame, slack: str = "1h") -> float:
    """Share of true anomaly events that overlap at least one raised alert."""
    if events.empty:
        return 0.0
    hit = tot = 0
    for m, g in scored.sort_values("ts").groupby("meter_id"):
        lab = g.is_anomaly.values.astype(bool); ts = g.ts.values
        ev = events[events.meter_id == m]
        i = 0
        while i < len(lab):
            if lab[i]:
                j = i
                while j < len(lab) and lab[j]:
                    j += 1
                tot += 1
                a, b = ts[i], ts[j - 1] + np.timedelta64(pd.Timedelta(slack))
                hit += bool(((ev.start.values <= b) & (ev.end.values >= a)).any())
                i = j
            else:
                i += 1
    return hit / tot if tot else float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="synthetic", choices=["synthetic", "sgcc"])
    ap.add_argument("--sgcc-path", default="data/sgcc/data.csv")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--meters", type=int, default=10)
    ap.add_argument("--seed", type=int, default=settings.seed)
    ap.add_argument("--stream-records", type=int, default=3000)
    ap.add_argument("--lime-samples", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=50, help="records per consumer micro-batch")
    args = ap.parse_args(argv)
    art, rep = settings.artifacts_dir, settings.reports_dir
    art.mkdir(parents=True, exist_ok=True); rep.mkdir(parents=True, exist_ok=True)
    M: dict = {"config": vars(args), "generated_at": pd.Timestamp.now("UTC").isoformat()}
    t_all = time.time()

    # ---------------------------------------------------------------- ingestion (batch)
    log.info("loading data (%s)", args.source)
    raw = load_raw(args)
    valid, reasons = validate(raw)
    cleaned, cstats = clean(valid)
    norm = normalise(cleaned)
    M["ingestion"] = {"raw_records": int(len(raw)), "validation": {k: int(v) for k, v in reasons.items()},
                      "cleaning": cstats, "normalised_rows": int(len(norm)),
                      "rows_per_utility": norm.groupby("utility").size().to_dict(),
                      "interpolated_values": int(norm["value_filled"].sum())}
    t0 = norm["ts"].min()
    cut1, cut2 = t0 + pd.Timedelta(days=SPLIT_DAYS[0]), t0 + pd.Timedelta(days=SPLIT_DAYS[1])
    profile = Profile().fit(norm[norm.ts < cut1])
    feats = compute_features(norm, profile)
    train, val, test = feats[feats.ts < cut1], feats[(feats.ts >= cut1) & (feats.ts < cut2)], feats[feats.ts >= cut2]
    M["split"] = {"train": [str(t0), str(cut1)], "validation": [str(cut1), str(cut2)],
                  "test": [str(cut2), str(feats.ts.max())],
                  "anomaly_rate": {"train": float(train.is_anomaly.mean()), "validation": float(val.is_anomaly.mean()),
                                   "test": float(test.is_anomaly.mean())}}

    # ---------------------------------------------------------------- training
    log.info("training detectors per utility")
    mem0 = _proc().memory_info().rss
    engine = DetectionEngine(profile=profile, seed=args.seed).fit(train, val, log=log.info)
    engine.save(art / "engine.joblib")
    M["training"] = {u: {"fit_seconds": um.fit_seconds, "ensemble_weights": um.weights}
                     for u, um in engine.models.items()}
    M["thresholds"] = engine.thresholds()

    # ---------------------------------------------------------------- evaluation
    log.info("scoring test period")
    t1 = time.time()
    scored_test = engine.score_frame(test)
    batch_s = time.time() - t1
    M["batch_scoring"] = {"rows": int(len(test)), "seconds": batch_s, "rows_per_second": len(test) / batch_s}
    y = scored_test["is_anomaly"].values
    res = {"overall": {}, "per_utility": {}, "per_type_recall": {}, "event_level": {}}
    for d in ALL_DETECTORS:
        s, f = scored_test[f"score_{d}"].values, scored_test[f"flag_{d}"].values
        res["overall"][d] = point_metrics(y, s, f)
        res["event_level"][d] = event_recall(scored_test, f"flag_{d}")
        res["per_utility"][d] = {}
        for u, g in scored_test.groupby("utility"):
            res["per_utility"][d][u] = point_metrics(g.is_anomaly.values, g[f"score_{d}"].values, g[f"flag_{d}"].values)
        res["per_type_recall"][d] = {}
        for t in sorted(x for x in scored_test.anomaly_type.unique() if x):
            m = scored_test.anomaly_type.values == t
            res["per_type_recall"][d][t] = float(scored_test[f"flag_{d}"].values[m].mean())
        tm = np.isin(scored_test.anomaly_type.values, TEMPORAL)
        res["per_type_recall"][d]["temporal"] = float(scored_test[f"flag_{d}"].values[tm].mean())
        # threshold-free: recall on temporal anomalies at a matched 5% false-positive rate
        s_ok = ~np.isnan(s)
        neg = s[s_ok & ~y.astype(bool)]
        thr5 = np.quantile(neg, 0.95)
        res["per_type_recall"][d]["temporal_at_fpr5"] = float((np.nan_to_num(s[tm], nan=-np.inf) >= thr5).mean())
    M["detection"] = res

    # H1
    h1 = {}
    for basis in ("temporal", "temporal_at_fpr5"):
        r_lstm = res["per_type_recall"]["lstm_autoencoder"][basis]
        comp = {}
        for d in ("zscore", "moving_average", "isolation_forest"):
            r = res["per_type_recall"][d][basis]
            comp[d] = {"recall": r, "relative_improvement": (r_lstm - r) / r if r > 0 else float("inf"),
                       "absolute_pp": 100 * (r_lstm - r)}
        h1[basis] = {"lstm_recall": r_lstm, "vs": comp,
                     "supported": all(c["relative_improvement"] >= 0.15 for c in comp.values())}
    M["H1"] = h1

    # ---------------------------------------------------------------- explanations
    log.info("computing SHAP / LIME explanations")
    explainer = Explainer(engine, train, seed=args.seed)
    scored_test = scored_test.copy()
    alerts_rows = scored_test[scored_test.flag_ensemble]
    shap_cols = {}
    t2 = time.time()
    for u, g in alerts_rows.groupby("utility"):
        sv = explainer.shap_values(u, g[FEATURES].fillna(0).values)
        for i, idx in enumerate(g.index):
            shap_cols[idx] = sv[i]
    shap_s = time.time() - t2
    top1_ok, top3_ok, n_tp = 0, 0, 0
    for idx, sv in shap_cols.items():
        t = scored_test.at[idx, "anomaly_type"]
        if t:
            n_tp += 1
            order = [FEATURES[i] for i in np.argsort(-sv)[:3]]
            top1_ok += order[0] in EXPECTED_DRIVERS[t]
            top3_ok += bool(set(order) & EXPECTED_DRIVERS[t])
    rng = np.random.default_rng(args.seed)
    sample = rng.choice(list(shap_cols), size=min(args.lime_samples, len(shap_cols)), replace=False) if shap_cols else []
    jac, jac_same, lime_t, ks_t = [], [], [], []
    top3 = lambda v: set(np.argsort(-v)[:3])
    for idx in sample:
        u = scored_test.at[idx, "utility"]
        x = scored_test.loc[idx, FEATURES].astype(float).fillna(0).values
        t3 = time.time(); lv = explainer.lime_values(u, x); lime_t.append(time.time() - t3)
        t3 = time.time(); kv = explainer.kernel_shap_values(u, x); ks_t.append(time.time() - t3)
        a, b, c = top3(shap_cols[idx]), top3(lv), top3(kv)
        jac.append(len(a & b) / len(a | b))
        jac_same.append(len(c & b) / len(c | b))
    n_expected = np.mean([len(v) for v in EXPECTED_DRIVERS.values()])
    M["explainability"] = {
        "alerts_explained": len(shap_cols), "shap_ms_per_alert": 1000 * shap_s / max(len(shap_cols), 1),
        "lime_ms_per_alert": 1000 * float(np.mean(lime_t)) if lime_t else float("nan"),
        "plausibility_top1": top1_ok / n_tp if n_tp else float("nan"),
        "plausibility_top3": top3_ok / n_tp if n_tp else float("nan"),
        "plausibility_top1_chance": n_expected / len(FEATURES),
        "kernel_shap_ms_per_alert": 1000 * float(np.mean(ks_t)) if ks_t else float("nan"),
        "treeshap_if_vs_lime_ensemble_jaccard": float(np.mean(jac)) if jac else float("nan"),
        "kernelshap_vs_lime_same_model_jaccard": float(np.mean(jac_same)) if jac_same else float("nan"),
        "lime_sample": len(jac)}

    # ---------------------------------------------------------------- streaming latency benchmark
    log.info("streaming benchmark (%d records through StreamProcessor)", args.stream_records)
    sp = StreamProcessor(engine, explainer)
    raw_ts = pd.to_datetime(raw["ts"], utc=True, format="ISO8601")
    warm = raw[(raw_ts >= cut2 - pd.Timedelta(hours=10)) & (raw_ts < cut2)].assign(_t=raw_ts).sort_values("_t")
    live = raw[raw_ts >= cut2].assign(_t=raw_ts).sort_values("_t").head(args.stream_records)
    warm_recs = [_json_safe(r) for r in warm.drop(columns="_t").to_dict("records")]
    for b in range(0, len(warm_recs), args.batch_size):
        sp.process_batch(warm_recs[b:b + args.batch_size])
    live_recs = [_json_safe(r) for r in live.drop(columns="_t").to_dict("records")]
    cpu0 = _proc().cpu_times(); tstart = time.time(); lat = []; alerts_n = 0
    for b in range(0, len(live_recs), args.batch_size):
        for out in sp.process_batch(live_recs[b:b + args.batch_size]):
            lat.append(out.processing_latency_s)
            alerts_n += out.is_alert
    wall = time.time() - tstart
    cpu1 = _proc().cpu_times()
    lat = np.array(lat)
    M["streaming"] = {"records_in": int(len(live)), "batch_size": args.batch_size, "readings_scored": int(len(lat)), "alerts": int(alerts_n),
                      "latency_mean_s": float(lat.mean()), "latency_p50_s": float(np.percentile(lat, 50)),
                      "latency_p95_s": float(np.percentile(lat, 95)), "latency_p99_s": float(np.percentile(lat, 99)),
                      "latency_max_s": float(lat.max()), "throughput_records_per_s": len(live) / wall,
                      "cpu_utilisation_pct": 100 * ((cpu1.user + cpu1.system) - (cpu0.user + cpu0.system)) / wall
                      / psutil.cpu_count(), "peak_rss_mb": _proc().memory_info().rss / 2**20,
                      "training_rss_increase_mb": (_proc().memory_info().rss - mem0) / 2**20,
                      "note": "in-process processing latency (validate->clean->normalise->features->5 models+ensemble->SHAP); "
                              "Kafka + TimescaleDB transit is measured by the docker pipeline (latency_ms column)."}
    M["H2"] = {"target_s": settings.latency_target_s, "mean_s": M["streaming"]["latency_mean_s"],
               "p95_s": M["streaming"]["latency_p95_s"],
               "supported": M["streaming"]["latency_mean_s"] < settings.latency_target_s}

    # ---------------------------------------------------------------- export for dashboard
    log.info("exporting artifacts")
    full = engine.score_frame(feats)
    full["split"] = np.where(full.ts < cut1, "train", np.where(full.ts < cut2, "validation", "test"))
    keep = ["ts", "meter_id", "utility", "value", "expected", "is_anomaly", "anomaly_type", "split", "votes",
            "value_filled"] + \
           FEATURES + [c for c in full.columns if c.startswith(("score_", "flag_"))]
    out = full[keep].copy()
    for c in out.select_dtypes("float64").columns:
        out[c] = out[c].astype("float32")
    out.to_parquet(art / "scored.parquet", index=False)
    grouped = group_events(out[out.split == "test"])
    M["alert_debounce"] = {"candidate_events": int(len(grouped)),
                           "candidate_event_precision": float(grouped.truth.mean()) if len(grouped) else float("nan")}
    events = cross_utility_escalations(grouped[grouped.raised].reset_index(drop=True)) if len(grouped) else grouped
    if not events.empty:
        from confluence.explain.narrative import narrative
        shap_full, lime_full, narr, feats_at = [], [], [], []
        for _, e in events.iterrows():
            seg = scored_test[(scored_test.meter_id == e.meter_id) & (scored_test.ts == e.peak_ts)]
            idx = seg.index[0] if len(seg) else None
            x = seg.iloc[0][FEATURES].astype(float).fillna(0).values if idx is not None else np.zeros(len(FEATURES))
            sv = shap_cols.get(idx)
            if sv is None:
                sv = explainer.shap_values(e.utility, x[None, :])[0]
            lv = explainer.lime_values(e.utility, x)
            shap_full.append(json.dumps([float(v) for v in sv]))
            lime_full.append(json.dumps([float(v) for v in lv]))
            feats_at.append(json.dumps([float(v) for v in x]))
            narr.append(narrative(e.utility, e.meter_id, e.peak_value, UTILITIES[e.utility].unit, Explainer.top(sv, 3),
                                  dict(zip(FEATURES, x))))
        events["shap"] = shap_full
        events["lime"] = lime_full
        events["features"] = feats_at
        events["narrative"] = narr
        events["unit"] = events.utility.map(lambda u: UTILITIES[u].unit)
        events["alert_id"] = np.arange(1, len(events) + 1)
    (art / "profile.json").write_text(json.dumps(profile.to_dict()))
    (art / "engine_summary.json").write_text(json.dumps({
        "features": FEATURES, "thresholds": engine.thresholds(),
        "weights": {u: um.weights for u, um in engine.models.items()},
        "global_shap": {u: dict(zip(FEATURES, np.abs(np.array([v for i, v in shap_cols.items()
                        if scored_test.at[i, "utility"] == u])).mean(axis=0).tolist()))
                        for u in engine.models if any(scored_test.at[i, "utility"] == u for i in shap_cols)}},
        default=_default))
    events.to_parquet(art / "alerts.parquet", index=False)
    M["alerts"] = {"events": int(len(events)), "true_event_coverage": alert_coverage(scored_test, events),
                   "by_severity": events.severity.value_counts().to_dict() if len(events) else {},
                   "cross_utility": int(events.cross_utility.sum()) if len(events) else 0,
                   "event_precision": float(events.truth.mean()) if len(events) else float("nan")}
    M["runtime_seconds"] = time.time() - t_all
    (rep / "metrics.json").write_text(json.dumps(M, indent=2, default=_default))
    (rep / "evaluation_report.md").write_text(render_report(M))
    log.info("done in %.0fs -> %s", M["runtime_seconds"], rep / "evaluation_report.md")
    return M


def _json_safe(rec: dict) -> dict:
    v = rec.get("value")
    rec["value"] = None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
    rec["is_anomaly"] = bool(rec.get("is_anomaly", False))
    return rec


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def render_report(M: dict) -> str:
    d = M["detection"]
    L = ["# Evaluation report", "",
         f"Generated {M['generated_at']} · data source: **{M['config']['source']}** · "
         f"{M['config']['meters']} meters per utility · {M['config']['days']} days · seed {M['config']['seed']}", "",
         "> Detection metrics are computed on the held-out **test period** only. Thresholds were calibrated on the "
         "validation period. With synthetic data the anomalies are injected, so results show how the methods compare "
         "on these anomaly types — not how they would perform on a real utility network.", "",
         "## Detection accuracy (point level, test period)", "",
         "| Technique | Family | Precision | Recall | F1 | ROC-AUC | Recall@5%FPR | Event recall |",
         "|---|---|---|---|---|---|---|---|"]
    for k in ALL_DETECTORS:
        o, e = d["overall"][k], d["event_level"][k]
        L.append(f"| {DISPLAY[k]} | {FAMILY[k]} | {o['precision']:.3f} | {o['recall']:.3f} | {o['f1']:.3f} | "
                 f"{o['roc_auc']:.3f} | {o['recall_at_fpr5']:.3f} | {e['event_recall']:.3f} |")
    L += ["", "## F1 by utility", "", "| Technique | " + " | ".join(u.title() for u in UTILITIES) + " |",
          "|---|" + "---|" * len(UTILITIES)]
    for k in ALL_DETECTORS:
        L.append(f"| {DISPLAY[k]} | " + " | ".join(f"{d['per_utility'][k][u]['f1']:.3f}" for u in UTILITIES) + " |")
    types = [t for t in d["per_type_recall"]["zscore"] if t not in ("temporal", "temporal_at_fpr5")]
    L += ["", "## Recall by anomaly type", "", "| Technique | " + " | ".join(types) + " | temporal* | temporal @5%FPR |",
          "|---|" + "---|" * (len(types) + 2)]
    for k in ALL_DETECTORS:
        r = d["per_type_recall"][k]
        L.append(f"| {DISPLAY[k]} | " + " | ".join(f"{r[t]:.3f}" for t in types) +
                 f" | {r['temporal']:.3f} | {r['temporal_at_fpr5']:.3f} |")
    L += ["", "*temporal = drift, leak and stuck-meter anomalies (sustained patterns).", "",
          "## Hypothesis H1 — LSTM autoencoder recall on temporal anomalies (target: ≥15% higher)", ""]
    for basis, h in M["H1"].items():
        L.append(f"**Basis: {'calibrated thresholds' if basis == 'temporal' else 'matched 5% false-positive rate'}** — "
                 f"LSTM recall {h['lstm_recall']:.3f} → **{'SUPPORTED' if h['supported'] else 'NOT SUPPORTED'}**")
        L.append("")
        L.append("| Compared with | Recall | Relative improvement | Absolute (pp) |")
        L.append("|---|---|---|---|")
        for k, c in h["vs"].items():
            L.append(f"| {DISPLAY[k]} | {c['recall']:.3f} | {100 * c['relative_improvement']:+.1f}% | {c['absolute_pp']:+.1f} |")
        L.append("")
    s = M["streaming"]
    L += ["## Hypothesis H2 — alert latency (target: mean < 2.5 s)", "",
          f"**{'SUPPORTED' if M['H2']['supported'] else 'NOT SUPPORTED'}** — mean {s['latency_mean_s'] * 1000:.1f} ms, "
          f"p95 {s['latency_p95_s'] * 1000:.1f} ms, p99 {s['latency_p99_s'] * 1000:.1f} ms, "
          f"max {s['latency_max_s'] * 1000:.1f} ms over {s['readings_scored']} readings.", "",
          f"Throughput {s['throughput_records_per_s']:.0f} records/s (single consumer process, micro-batches of "
          f"{s['batch_size']}) · CPU "
          f"{s['cpu_utilisation_pct']:.0f}% · RSS {s['peak_rss_mb']:.0f} MB.", "", f"_{s['note']}_", "",
          "## Explainability", ""]
    x = M["explainability"]
    L += [f"- Alerts explained with TreeSHAP: {x['alerts_explained']} ({x['shap_ms_per_alert']:.2f} ms/alert)",
          f"- LIME on the tabular ensemble: {x['lime_ms_per_alert']:.0f} ms/alert (sample of {x['lime_sample']})",
          f"- KernelSHAP on the tabular ensemble: {x['kernel_shap_ms_per_alert']:.0f} ms/alert",
          f"- Plausibility on true-positive alerts (top SHAP feature is one of the anomaly type's expected drivers): "
          f"top-1 {x['plausibility_top1']:.1%} (chance ≈ {x['plausibility_top1_chance']:.0%}), top-3 {x['plausibility_top3']:.1%}",
          f"- Top-3 agreement, KernelSHAP vs LIME on the same ensemble (Jaccard): {x['kernelshap_vs_lime_same_model_jaccard']:.2f}",
          f"- Top-3 agreement, TreeSHAP (Isolation Forest) vs LIME (ensemble) (Jaccard): "
          f"{x['treeshap_if_vs_lime_ensemble_jaccard']:.2f}", "",
          "H3 (operator trust) can only be tested with participants — see `docs/USER_STUDY.md` and "
          "`python -m confluence.evaluation.user_study`.", "",
          "## Ingestion", "", f"```json\n{json.dumps(M['ingestion'], indent=2, default=_default)}\n```", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
