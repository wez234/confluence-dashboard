"""Kafka consumer: the real-time analytics path of the Kappa architecture.

poll -> StreamProcessor (validate, clean, normalise, features, detect, explain)
     -> TimescaleDB (raw, processed, anomalies) + alert topic

    python -m confluence.ingestion.consumer
"""
from __future__ import annotations

import json
import time

import numpy as np

from confluence.alerts.rules import severity, site_of
from confluence.config import settings
from confluence.detection.engine import DetectionEngine
from confluence.explain.xai import Explainer
from confluence.ingestion.stream_processor import StreamProcessor
from confluence.logging_setup import get_logger, log_metric
from confluence.storage import db

log = get_logger("consumer")


def main():
    from kafka import KafkaConsumer, KafkaProducer
    import pandas as pd
    engine = DetectionEngine.load(settings.artifacts_dir / "engine.joblib")
    bg = pd.read_parquet(settings.artifacts_dir / "scored.parquet")
    bg = bg[bg.split == "train"].assign(scorable=True).dropna()
    processor = StreamProcessor(engine, Explainer(engine, bg))
    for i in range(30):
        try:
            consumer = KafkaConsumer(settings.raw_topic, bootstrap_servers=settings.kafka_bootstrap,
                                     group_id="confluence-analytics", auto_offset_reset="latest",
                                     value_deserializer=lambda b: json.loads(b.decode()), max_poll_records=200)
            alerts_out = KafkaProducer(bootstrap_servers=settings.kafka_bootstrap,
                                       value_serializer=lambda v: json.dumps(v, default=str).encode())
            break
        except Exception as e:
            log.warning("kafka not ready (%s)", e); time.sleep(2)
    conn_ctx = db.connect(); conn = conn_ctx.__enter__()
    log.info("consumer started on %s", settings.raw_topic)
    lat, n = [], 0
    while True:
        batch = consumer.poll(timeout_ms=500)
        recs = [m.value for msgs in batch.values() for m in msgs]
        if not recs:
            continue
        try:
            out = processor.process_batch(recs, [r.pop("produced_at", None) for r in recs])
            _persist(conn, out, alerts_out)
        except Exception:
            log.exception("batch failed (%d records) - skipped", len(recs))
            conn.rollback()
            continue
        if out:
            now = time.time()   # after commit: alert is visible to the dashboard/API
            lat += [now - o.produced_at for o in out if o.produced_at]
            _append_latency(out, now)
            n += len(out)
        if len(lat) >= 500:
            log_metric(log, "latency", readings=n, mean_ms=1000 * float(np.mean(lat)),
                       p95_ms=1000 * float(np.percentile(lat, 95)), target_ms=1000 * settings.latency_target_s)
            lat = []


LATENCY_LOG = settings.reports_dir / "stream_latency.csv"


def _append_latency(out, committed_at):
    new = not LATENCY_LOG.exists()
    with LATENCY_LOG.open("a") as f:
        if new:
            f.write("ts,meter_id,utility,is_alert,produced_at,decided_at,committed_at\n")
        for o in out:
            if o.produced_at:
                f.write(f"{o.ts},{o.meter_id},{o.utility},{int(o.is_alert)},{o.produced_at:.6f},"
                        f"{o.decided_at:.6f},{committed_at:.6f}\n")


def _persist(conn, out, alerts_out):
    if not out:
        return
    db.insert_processed(conn, out)
    for r in out:
        if r.is_alert:
            sev = severity(r.ensemble_score, r.votes, 1)
            db.insert_alert(conn, r, sev, site_of(r.meter_id))
            alerts_out.send(settings.alert_topic, {"ts": r.ts, "meter_id": r.meter_id, "utility": r.utility,
                                                    "severity": sev, "score": r.ensemble_score,
                                                    "explanation": r.shap_top})
    conn.commit()


if __name__ == "__main__":
    main()
