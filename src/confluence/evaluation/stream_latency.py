"""Summarise end-to-end latency recorded by the Kafka consumer (H2 evidence).

latency = committed_at (alert/reading committed to the database, visible to the
dashboard and API) - produced_at (producer wall-clock stamp before Kafka send).

    python -m confluence.evaluation.stream_latency --since <unix-seconds>
"""
from __future__ import annotations

import argparse
import json
import platform

import numpy as np
import pandas as pd
import psutil

from confluence.config import settings


def summarise(since: float = 0.0, note: str = "") -> dict:
    d = pd.read_csv(settings.reports_dir / "stream_latency.csv")
    d = d[d.produced_at > since]
    e2e = (d.committed_at - d.produced_at).values
    dec = (d.decided_at - d.produced_at).values
    alerts = e2e[d.is_alert.values == 1]
    span = d.committed_at.max() - d.produced_at.min()
    q = lambda a, p: float(np.percentile(a, p)) if len(a) else float("nan")
    out = {"readings": int(len(d)), "alerts": int(len(alerts)), "span_s": float(span),
           "throughput_readings_per_s": float(len(d) / span) if span else float("nan"),
           "e2e_mean_s": float(e2e.mean()), "e2e_p50_s": q(e2e, 50), "e2e_p95_s": q(e2e, 95),
           "e2e_p99_s": q(e2e, 99), "e2e_max_s": float(e2e.max()),
           "alert_e2e_mean_s": float(alerts.mean()) if len(alerts) else float("nan"),
           "alert_e2e_p95_s": q(alerts, 95), "decision_mean_s": float(dec.mean()),
           "share_under_target": float((e2e < settings.latency_target_s).mean()),
           "target_s": settings.latency_target_s, "H2_supported": bool(e2e.mean() < settings.latency_target_s),
           "environment": {"cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
                           "python": platform.python_version()}, "note": note}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=float, default=0.0)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    res = summarise(a.since, a.note)
    (settings.reports_dir / "stream_kafka_latency.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
