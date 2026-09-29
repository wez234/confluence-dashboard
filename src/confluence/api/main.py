"""REST API layer (cross-cutting service in Figure 1).

    uvicorn confluence.api.main:app --port 8000

Read endpoints are open in demo mode; state-changing endpoints (acknowledge,
threshold changes) require the ``X-API-Key`` header when ``API_KEY`` is set,
and every change is written to the audit log.
"""
from __future__ import annotations

import json
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from confluence import __version__
from confluence.config import settings
from confluence.datasource import DatabaseSource, get_source

app = FastAPI(title="Confluence multi-utility anomaly API", version=__version__)
_source = None
STARTED = time.time()


def source():
    global _source
    if _source is None:
        _source = get_source()
    return _source


def require_key(x_api_key: str | None = Header(default=None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid API key")


class Ack(BaseModel):
    actor: str = Field(min_length=1, max_length=64)
    action: str = Field(pattern="^(acknowledged|dismissed|escalated)$")
    note: str = ""


class ThresholdChange(BaseModel):
    actor: str = Field(min_length=1, max_length=64)
    utility: str = Field(pattern="^(electricity|gas|water)$")
    detector: str
    value: float
    reason: str = Field(min_length=3)


def _records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


@app.get("/health")
def health():
    return {"status": "ok", "source": source().name, "uptime_s": round(time.time() - STARTED, 1),
            "version": __version__}


@app.get("/readings")
def readings(utility: str | None = None, meter: str | None = None, start: str | None = None,
             end: str | None = None, limit: int = 2000):
    df = source().readings(utility, meter, start, end)
    cols = [c for c in ("ts", "meter_id", "utility", "value", "score_ensemble", "ensemble_score",
                        "flag_ensemble", "is_alert", "votes") if c in df.columns]
    return _records(df[cols].tail(limit))


@app.get("/anomalies")
def anomalies(limit: int = 200):
    return _records(source().anomalies(limit))


@app.get("/metrics")
def metrics():
    s = source()
    if hasattr(s, "metrics"):
        return {"offline": s.metrics, "stream": s.stream}
    from confluence.storage import db
    lat = db.query("SELECT avg(latency_ms) mean_ms, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) p95_ms, "
                   "count(*) n FROM processed_readings WHERE ts > now() - interval '1 day'")
    return _records(lat)[0]


@app.get("/thresholds")
def thresholds():
    from confluence.detection.engine import DetectionEngine
    return DetectionEngine.load(settings.artifacts_dir / "engine.joblib").thresholds()


@app.post("/alerts/{alert_id}/ack", dependencies=[Depends(require_key)])
def ack(alert_id: int, body: Ack):
    s = source()
    if not isinstance(s, DatabaseSource):
        raise HTTPException(409, "acknowledgement requires the database-backed pipeline")
    from confluence.storage import db
    with db.connect() as c, c.cursor() as cur:
        cur.execute("UPDATE anomalies SET status=%s WHERE id=%s", (body.action, alert_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "alert not found")
        db.audit(c, body.actor, body.action, f"alert:{alert_id}", {"note": body.note})
    return {"id": alert_id, "status": body.action}


@app.post("/thresholds", dependencies=[Depends(require_key)])
def change_threshold(body: ThresholdChange):
    """Operator-mediated threshold change (never automatic), always audited."""
    from confluence.detection.engine import DetectionEngine
    path = settings.artifacts_dir / "engine.joblib"
    eng = DetectionEngine.load(path)
    old = eng.thresholds()[body.utility].get(body.detector)
    if old is None:
        raise HTTPException(404, "unknown detector")
    eng.set_threshold(body.utility, body.detector, body.value)
    eng.save(path)
    entry = {"utility": body.utility, "detector": body.detector, "old": old, "new": body.value, "reason": body.reason}
    if isinstance(source(), DatabaseSource):
        from confluence.storage import db
        with db.connect() as c, c.cursor() as cur:
            cur.execute("INSERT INTO threshold_changes (actor, utility, detector, old_value, new_value, reason) "
                        "VALUES (%s,%s,%s,%s,%s,%s)", (body.actor, body.utility, body.detector, old, body.value, body.reason))
            db.audit(c, body.actor, "threshold_change", f"{body.utility}:{body.detector}", entry)
    else:
        with (settings.reports_dir / "audit_log.jsonl").open("a") as f:
            f.write(json.dumps({"at": time.time(), "actor": body.actor, "action": "threshold_change", **entry}) + "\n")
    return entry
