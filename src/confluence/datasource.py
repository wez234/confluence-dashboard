"""Data access used by the API and the dashboard.

* ``DatabaseSource`` reads the live pipeline tables (TimescaleDB / PostgreSQL).
* ``DemoSource`` reads the artifacts written by ``confluence.evaluation.run``
  so the dashboard works (e.g. on Streamlit Community Cloud) without Kafka or a
  database.  The demo replays the held-out test period.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from confluence.config import settings


class DemoSource:
    name = "demo"

    def __init__(self, artifacts: Path | None = None):
        a = artifacts or settings.artifacts_dir
        self.scored = pd.read_parquet(a / "scored.parquet")
        self.scored["ts"] = pd.to_datetime(self.scored["ts"], utc=True)
        p = a / "alerts.parquet"
        self.alerts = pd.read_parquet(p) if p.exists() else pd.DataFrame()
        m = settings.reports_dir / "metrics.json"
        self.metrics = json.loads(m.read_text()) if m.exists() else {}
        k = settings.reports_dir / "stream_kafka_latency.json"
        self.stream = json.loads(k.read_text()) if k.exists() else {}

    def readings(self, utility=None, meter=None, start=None, end=None) -> pd.DataFrame:
        d = self.scored
        if utility:
            d = d[d.utility == utility]
        if meter:
            d = d[d.meter_id == meter]
        if start is not None:
            d = d[d.ts >= pd.Timestamp(start)]
        if end is not None:
            d = d[d.ts <= pd.Timestamp(end)]
        return d

    def anomalies(self, limit: int = 500) -> pd.DataFrame:
        return self.alerts.sort_values("peak_ts", ascending=False).head(limit) if len(self.alerts) else self.alerts


class DatabaseSource:
    name = "database"

    def __init__(self, url: str | None = None):
        from confluence.storage import db
        self.db, self.url = db, url

    def readings(self, utility=None, meter=None, start=None, end=None, limit=20000) -> pd.DataFrame:
        q, p = ["SELECT ts, meter_id, utility, value, ensemble_score, votes, is_alert, latency_ms FROM processed_readings WHERE TRUE"], []
        for col, v in (("utility", utility), ("meter_id", meter)):
            if v:
                q.append(f"AND {col} = %s"); p.append(v)
        if start is not None:
            q.append("AND ts >= %s"); p.append(pd.Timestamp(start).to_pydatetime())
        if end is not None:
            q.append("AND ts <= %s"); p.append(pd.Timestamp(end).to_pydatetime())
        q.append("ORDER BY ts DESC LIMIT %s"); p.append(limit)
        return self.db.query(" ".join(q), p, self.url)

    def anomalies(self, limit: int = 500) -> pd.DataFrame:
        return self.db.query("SELECT * FROM anomalies ORDER BY ts DESC LIMIT %s", [limit], self.url)


def get_source():
    from confluence.storage import db
    if settings.data_mode != "demo" and db.available():
        return DatabaseSource()
    return DemoSource()
