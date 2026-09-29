"""Kafka producer: replays multi-utility meter readings as a real-time stream.

Readings are sorted by their UTC timestamp and emitted at ``REPLAY_SPEED`` x
real time (600 = one 15-minute interval every 1.5 s).  Each message carries a
``produced_at`` wall-clock stamp so the consumer can measure end-to-end latency.

    python -m confluence.ingestion.producer --source synthetic --days 60
"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from confluence.config import settings
from confluence.data.generator import GeneratorConfig, generate
from confluence.logging_setup import get_logger, log_metric

log = get_logger("producer")


def make_producer(retries: int = 30):
    from kafka import KafkaProducer
    for i in range(retries):
        try:
            return KafkaProducer(bootstrap_servers=settings.kafka_bootstrap, linger_ms=5, acks=1,
                                 value_serializer=lambda v: json.dumps(v).encode(),
                                 key_serializer=lambda k: k.encode())
        except Exception as e:  # broker not up yet
            log.warning("kafka not ready (%s), retry %d", e, i)
            time.sleep(2)
    raise RuntimeError("Kafka unavailable")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--meters", type=int, default=10)
    ap.add_argument("--start-day", type=int, default=45, help="replay from this day (test period)")
    ap.add_argument("--speed", type=float, default=settings.replay_speed)
    ap.add_argument("--replay-days", type=float, default=None, help="stop after this many simulated days")
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args(argv)
    raw = generate(GeneratorConfig(days=args.days, meters_per_utility=args.meters, seed=settings.seed))
    raw["_t"] = pd.to_datetime(raw["ts"], utc=True, format="ISO8601")
    start = raw._t.min() + pd.Timedelta(days=args.start_day)
    raw = raw[raw._t >= start - pd.Timedelta(hours=26)].sort_values("_t")   # 26h warm-up for 24h features
    if args.replay_days:
        raw = raw[raw._t < start + pd.Timedelta(days=args.replay_days)]
    producer = make_producer()
    while True:
        t_sim0, t_wall0, sent = raw._t.iloc[0], time.time(), 0
        for rec in raw.to_dict("records"):
            due = t_wall0 + (rec["_t"] - t_sim0).total_seconds() / args.speed
            if (d := due - time.time()) > 0:
                time.sleep(d)
            msg = {k: (None if isinstance(v, float) and v != v else v) for k, v in rec.items() if k != "_t"}
            msg["produced_at"] = time.time()
            producer.send(settings.raw_topic, key=msg["meter_id"], value=msg)
            sent += 1
            if sent % 1000 == 0:
                log_metric(log, "produced", records=sent, sim_time=str(rec["_t"]))
        producer.flush()
        log.info("replay finished: %d records", sent)
        if not args.loop:
            break


if __name__ == "__main__":
    main()
