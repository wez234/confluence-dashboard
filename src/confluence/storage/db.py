"""Thin PostgreSQL / TimescaleDB access layer (psycopg2)."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from confluence.config import settings

SCHEMA = Path(__file__).with_name("schema.sql")


def available(url: str | None = None) -> bool:
    try:
        import psycopg2
        psycopg2.connect(url or settings.database_url, connect_timeout=2).close()
        return True
    except Exception:
        return False


@contextmanager
def connect(url: str | None = None):
    import psycopg2
    conn = psycopg2.connect(url or settings.database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _statements(sql: str) -> list[str]:
    out, buf, in_dollar = [], [], False
    for line in sql.splitlines():
        if line.strip().startswith("--") and not buf:
            continue
        buf.append(line)
        in_dollar ^= line.count("$$") % 2 == 1
        if line.rstrip().endswith(";") and not in_dollar:
            out.append("\n".join(buf)); buf = []
    return out


TIMESCALE_ONLY = ("create_hypertable", "add_continuous_aggregate_policy", "add_compression_policy",
                  "add_retention_policy", "timescaledb.compress")


def init_schema(url: str | None = None, log=print) -> bool:
    """Create the schema. Returns True if TimescaleDB features were enabled.

    On plain PostgreSQL (no TimescaleDB extension) hypertable/compression/retention
    statements are skipped and the continuous aggregate becomes a normal view,
    so the platform still runs — only the partitioning optimisations are lost.
    """
    import psycopg2
    with connect(url) as c:
        c.autocommit = True
        with c.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                ts = True
            except psycopg2.Error:
                ts = False
                log("TimescaleDB extension not available - falling back to plain PostgreSQL tables")
            for stmt in _statements(SCHEMA.read_text()):
                if "CREATE EXTENSION" in stmt:
                    continue
                if not ts and any(k in stmt for k in TIMESCALE_ONLY):
                    continue
                if not ts and "timescaledb.continuous" in stmt:
                    stmt = (stmt.replace("CREATE MATERIALIZED VIEW IF NOT EXISTS", "CREATE OR REPLACE VIEW")
                            .replace("WITH (timescaledb.continuous)", "").replace("time_bucket('1 hour', ts)",
                                     "date_trunc('hour', ts)").replace("WITH NO DATA", ""))
                cur.execute(stmt)
    return ts


def _j(d) -> str:
    """JSON with NaN/inf mapped to null (PostgreSQL JSONB rejects NaN)."""
    def fix(v):
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            return None
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix(x) for x in v]
        return v
    return json.dumps(fix(d), default=str)


def _f(v):
    return None if v is None or v != v else float(v)


def insert_processed(conn, rows: list) -> None:
    """rows: list of ProcessedReading"""
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        execute_values(cur, """INSERT INTO raw_readings (ts, meter_id, utility, value) VALUES %s""",
                       [(r.ts.to_pydatetime(), r.meter_id, r.utility, _f(r.value)) for r in rows])
        execute_values(cur, """INSERT INTO processed_readings (ts, meter_id, utility, value, features, scores, flags,
                       ensemble_score, votes, is_alert, latency_ms) VALUES %s ON CONFLICT DO NOTHING""",
                       [(r.ts.to_pydatetime(), r.meter_id, r.utility, r.value, _j(r.features),
                         _j(r.scores), _j(r.flags), _f(r.ensemble_score), r.votes, r.is_alert,
                         1000 * (r.end_to_end_latency_s if r.produced_at else r.processing_latency_s))
                        for r in rows])


def insert_alert(conn, r, severity: str, site_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO anomalies (ts, meter_id, site_id, utility, value, ensemble_score, votes, severity,
                       explanation) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (r.ts.to_pydatetime(), r.meter_id, site_id, r.utility, _f(r.value), _f(r.ensemble_score), r.votes,
                     severity, _j({"shap_top": r.shap_top, "narrative": getattr(r, "narrative", "")})))


def audit(conn, actor: str, action: str, target: str, details: dict) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO audit_log (actor, action, target, details) VALUES (%s,%s,%s,%s)",
                    (actor, action, target, _j(details)))


def query(sql: str, params=None, url: str | None = None) -> pd.DataFrame:
    with connect(url) as c, c.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)
