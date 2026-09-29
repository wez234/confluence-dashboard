"""Alert management: severity, event grouping and escalation rules.

The platform is monitoring-only: rules raise, rank and escalate alerts for a
human operator; they never trigger automated actions on the network.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EscalationPolicy:
    critical_votes: int = 4            # >= this many detectors agree
    critical_score: float = 0.995      # ensemble percentile
    sustained_steps: int = 4           # consecutive flagged readings
    unacknowledged_minutes: int = 30   # escalate if nobody acknowledges
    cross_utility_window: str = "2h"   # co-occurring anomalies at one site


def site_of(meter_id: str) -> str:
    """Meters E003 / G003 / W003 belong to the same property SITE-003."""
    return f"SITE-{meter_id[1:]}"


def severity(score: float, votes: int, steps: int, policy: EscalationPolicy = EscalationPolicy()) -> str:
    if votes >= policy.critical_votes or score >= policy.critical_score or steps >= 3 * policy.sustained_steps:
        return "critical"
    if votes >= 2 or steps >= policy.sustained_steps:
        return "warning"
    return "info"


def group_events(scored: pd.DataFrame, flag_col: str = "flag_ensemble", gap_steps: int = 1,
                 min_steps: int = 2, min_votes_single: int = 3) -> pd.DataFrame:
    """Merge consecutive flagged readings of one meter into alert events."""
    rows = []
    for (utility, meter), g in scored.sort_values("ts").groupby(["utility", "meter_id"]):
        f = g[flag_col].values.astype(bool)
        if not f.any():
            continue
        idx = np.where(f)[0]
        splits = np.where(np.diff(idx) > gap_steps + 1)[0] + 1
        for block in np.split(idx, splits):
            seg = g.iloc[block[0]:block[-1] + 1]
            peak = seg.loc[seg["score_ensemble"].idxmax()]
            rows.append({
                "utility": utility, "meter_id": meter, "site_id": site_of(meter),
                "start": seg["ts"].iloc[0], "end": seg["ts"].iloc[-1], "steps": int(f[block[0]:block[-1] + 1].sum()),
                "peak_ts": peak["ts"], "peak_value": float(peak["value"]),
                "peak_score": float(peak["score_ensemble"]), "max_votes": int(seg["votes"].max()),
                "truth": bool(seg["is_anomaly"].any()) if "is_anomaly" in seg else None,
                "anomaly_type": (seg["anomaly_type"].replace("", np.nan).dropna().mode().iloc[0]
                                 if "anomaly_type" in seg and seg["anomaly_type"].astype(bool).any() else ""),
            })
    ev = pd.DataFrame(rows)
    if ev.empty:
        return ev
    ev["severity"] = [severity(s, v, n) for s, v, n in zip(ev.peak_score, ev.max_votes, ev.steps)]
    # debounce: an isolated single flagged reading only becomes an alert when
    # several detectors agree — reduces alert fatigue from one-off noise
    ev["raised"] = (ev.steps >= min_steps) | (ev.max_votes >= min_votes_single)
    return ev.sort_values("peak_ts").reset_index(drop=True)


def cross_utility_escalations(events: pd.DataFrame, policy: EscalationPolicy = EscalationPolicy()) -> pd.DataFrame:
    """Flag events where >= 2 utilities at the same site are anomalous together."""
    if events.empty:
        return events.assign(cross_utility=False)
    ev = events.copy()
    ev["cross_utility"] = False
    win = pd.Timedelta(policy.cross_utility_window)
    for site, g in ev.groupby("site_id"):
        for i, r in g.iterrows():
            others = g[(g.utility != r.utility) & (g.start <= r.end + win) & (g.end >= r.start - win)]
            if len(others):
                ev.loc[i, "cross_utility"] = True
    ev.loc[ev.cross_utility & (ev.severity == "info"), "severity"] = "warning"
    return ev


def needs_escalation(created_at: pd.Timestamp, acknowledged: bool, now: pd.Timestamp,
                     policy: EscalationPolicy = EscalationPolicy()) -> bool:
    return (not acknowledged) and (now - created_at) > pd.Timedelta(minutes=policy.unacknowledged_minutes)
