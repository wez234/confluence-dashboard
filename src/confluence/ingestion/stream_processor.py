"""Record-at-a-time processor used inside the Kafka consumer (Kappa architecture).

The same object is also driven directly (without Kafka) by the offline latency
benchmark, so the measured processing latency and the deployed pipeline share
one code path.

Per record:  validate -> clean -> normalise timestamp (UTC + canonical grid)
             -> feature extraction (causal, per-meter buffer)
             -> multi-model detection -> SHAP explanation for alerts
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from confluence.config import UTILITIES
from confluence.detection.engine import DetectionEngine
from confluence.ingestion.features import FEATURES, compute_features
from confluence.ingestion.validation import validate_record

BUFFER = 100   # > 24h of 15-min readings, needed by the 24-hour moving average


@dataclass
class ProcessedReading:
    ts: pd.Timestamp
    meter_id: str
    utility: str
    value: float
    features: dict
    scores: dict
    flags: dict
    ensemble_score: float
    is_alert: bool
    votes: int
    shap_top: list = field(default_factory=list)
    received_at: float = 0.0
    decided_at: float = 0.0
    produced_at: float | None = None
    truth: bool | None = None
    anomaly_type: str = ""

    @property
    def processing_latency_s(self) -> float:
        return self.decided_at - self.received_at

    @property
    def end_to_end_latency_s(self) -> float | None:
        return None if self.produced_at is None else self.decided_at - self.produced_at


class StreamProcessor:
    def __init__(self, engine: DetectionEngine, explainer=None):
        self.engine = engine
        self.explainer = explainer
        self.buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=BUFFER))
        self.open_bins: dict[str, dict] = {}
        self.seen: set = set()
        self.peer_levels: dict = defaultdict(dict)   # (utility, ts) -> {meter: level}
        self.stats = defaultdict(int)

    # ---------------------------------------------------------------- stages
    def _normalise(self, rec: dict) -> dict | None:
        """Return a canonical-grid reading, or None if the bin is still open."""
        utility = rec["utility"]
        ts = pd.Timestamp(rec["ts"]).tz_convert("UTC")
        slot = ts.floor(UTILITIES[utility].freq)
        v = rec["value"]
        v = np.nan if v is None or float(v) < 0 else float(v)      # cleaning: sentinel -> NaN
        if utility != "water":
            return {**rec, "ts": slot, "value": v}
        # water: aggregate irregular readings into 15-minute bins
        m = rec["meter_id"]
        b = self.open_bins.get(m)
        if b is None or b["ts"] == slot:
            if b is None:
                b = self.open_bins[m] = {**rec, "ts": slot, "vals": [], "truth": False, "types": set()}
            if not np.isnan(v):
                b["vals"].append(v)
            b["truth"] |= bool(rec.get("is_anomaly", False))
            if rec.get("anomaly_type"):
                b["types"].add(rec["anomaly_type"])
            return None
        closed = self.open_bins.pop(m)
        self.open_bins[m] = {**rec, "ts": slot, "vals": [] if np.isnan(v) else [v],
                             "truth": bool(rec.get("is_anomaly", False)),
                             "types": {rec["anomaly_type"]} if rec.get("anomaly_type") else set()}
        return {**closed, "value": float(np.mean(closed["vals"])) if closed["vals"] else np.nan,
                "is_anomaly": closed["truth"], "anomaly_type": max(closed["types"], default="")}

    def process(self, rec: dict, produced_at: float | None = None) -> ProcessedReading | None:
        out = self.process_batch([rec], [produced_at])
        return out[0] if out else None

    def process_batch(self, recs: list[dict], produced_at: list | None = None) -> list[ProcessedReading]:
        """Process one Kafka poll's worth of records (micro-batch).

        Every record in the batch is timestamped on arrival; all readings that
        complete in the batch are featurised and scored together, which is
        what gives the consumer its throughput.
        """
        received = time.time()
        produced_at = produced_at or [None] * len(recs)
        emitted = []
        for rec, pa in zip(recs, produced_at):
            ok, reason = validate_record(rec)
            self.stats[f"validation:{reason}"] += 1
            if not ok:
                continue
            key = (rec["meter_id"], rec["ts"])
            if key in self.seen:
                self.stats["cleaning:duplicate"] += 1
                continue
            self.seen.add(key)
            norm = self._normalise(rec)
            if norm is None:
                continue
            buf = self.buffers[norm["meter_id"]]
            if buf and np.isnan(norm["value"]) and not np.isnan(buf[-1]["value"]):
                norm["value"] = buf[-1]["value"]      # cleaning: carry forward single gaps
                self.stats["cleaning:filled"] += 1
            buf.append({k: norm.get(k) for k in ("ts", "meter_id", "utility", "value")})
            emitted.append((norm, pa))
        if len(self.seen) > 500_000:
            self.seen.clear()
        if not emitted:
            return []
        meters = sorted({n["meter_id"] for n, _ in emitted})
        frame = pd.DataFrame([r for m in meters for r in self.buffers[m]])
        feats = compute_features(frame, self.engine.profile)
        # cross-meter deviation against peers already seen for the same timestamp
        feats = feats.set_index(["meter_id", "ts"], drop=False)
        for n, _ in emitted:
            k = (n["meter_id"], n["ts"])
            lvl = feats.at[k, "level"] if k in feats.index else np.nan
            peers = self.peer_levels[(n["utility"], n["ts"])]
            peers[n["meter_id"]] = lvl
            vals = np.array([x for x in peers.values() if pd.notna(x)])
            cz = 0.0
            if len(vals) >= 3 and pd.notna(lvl):
                iqr = np.quantile(vals, .75) - np.quantile(vals, .25)
                cz = float(np.clip((lvl - np.median(vals)) / (iqr + 0.1), -50, 50))
            if k in feats.index:
                feats.at[k, "cross_meter_z"] = cz
        if len(self.peer_levels) > 5000:
            for k in list(self.peer_levels)[:2500]:
                del self.peer_levels[k]
        scored = self.engine.score_frame(feats.reset_index(drop=True)).set_index(["meter_id", "ts"], drop=False)
        out = []
        for n, pa in emitted:
            k = (n["meter_id"], n["ts"])
            if k not in scored.index:
                continue
            row = scored.loc[k]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            utility = n["utility"]
            um = self.engine.models[utility]
            alert = bool(row["flag_ensemble"])
            shap_top = []
            if alert and self.explainer is not None:
                x = row[FEATURES].astype(float).fillna(0).values[None, :]
                shap_top = self.explainer.top(self.explainer.shap_values(utility, x)[0])
            ens = float(row["score_ensemble"]) if pd.notna(row["score_ensemble"]) else float("nan")
            out.append(ProcessedReading(
                ts=n["ts"], meter_id=n["meter_id"], utility=utility, value=float(n["value"]),
                features={f: float(row[f]) for f in FEATURES if pd.notna(row[f])},
                scores={d: float(row[f"score_{d}"]) for d in um.detectors},
                flags={d: bool(row[f"flag_{d}"]) for d in um.detectors},
                ensemble_score=ens, is_alert=alert, votes=int(row["votes"]), shap_top=shap_top,
                received_at=received, decided_at=0.0, produced_at=pa,
                truth=n.get("is_anomaly"), anomaly_type=n.get("anomaly_type", "")))
        decided = time.time()
        for o in out:
            o.decided_at = decided
        self.stats["scored"] += len(out)
        self.stats["alerts"] += sum(o.is_alert for o in out)
        return out
