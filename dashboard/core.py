"""Shared state, data loading and chart helpers for the Streamlit dashboard."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from confluence.config import UTILITIES, settings  # noqa: E402
from confluence.detection.names import ALL_DETECTORS, BASE_DETECTORS, DISPLAY, FAMILY  # noqa: E402,F401
from confluence.ingestion.features import FEATURE_LABELS, FEATURES  # noqa: E402,F401

UCOLOR = {"electricity": "#C27C0E", "gas": "#2F5FB3", "water": "#0E8A8A"}
SEVCOLOR = {"critical": "#B3261E", "warning": "#C77700", "info": "#5A6B78"}
INK, MUTED, GRID = "#1D2327", "#6B7378", "#E4E1D8"
AUDIT_FILE = settings.reports_dir / "audit_log.jsonl"


# --------------------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def load_scored() -> pd.DataFrame:
    d = pd.read_parquet(settings.artifacts_dir / "scored.parquet")
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    return d


@st.cache_data(show_spinner=False)
def load_alerts() -> pd.DataFrame:
    a = pd.read_parquet(settings.artifacts_dir / "alerts.parquet")
    for c in ("start", "end", "peak_ts"):
        a[c] = pd.to_datetime(a[c], utc=True)
    for c in ("shap", "lime", "features"):
        a[c] = a[c].map(json.loads)
    return a


@st.cache_data(show_spinner=False)
def load_json(name: str, folder: str = "reports") -> dict:
    p = (settings.reports_dir if folder == "reports" else settings.artifacts_dir) / name
    return json.loads(p.read_text()) if p.exists() else {}


def artifacts_ready() -> bool:
    return (settings.artifacts_dir / "scored.parquet").exists() and (settings.artifacts_dir / "alerts.parquet").exists()


@st.cache_resource(show_spinner=False)
def db_source():
    """Live database source when the docker pipeline is running (else None)."""
    if settings.data_mode == "demo":
        return None
    try:
        from confluence.storage import db
        return db if db.available() else None
    except Exception:
        return None


# --------------------------------------------------------------------------- state
def init_state():
    ss = st.session_state
    ss.setdefault("actor", os.environ.get("OPERATOR_NAME", ""))
    ss.setdefault("alert_status", {})          # alert_id -> status
    ss.setdefault("audit", [])
    ss.setdefault("threshold_override", {})    # utility -> ensemble threshold
    ss.setdefault("selected_alert", None)
    ss.setdefault("playing", False)
    ss.setdefault("cursor", None)


def audit(action: str, target: str, **details):
    entry = {"at": pd.Timestamp.now("UTC").isoformat(), "actor": st.session_state.get("actor") or "anonymous",
             "action": action, "target": target, **details}
    st.session_state.audit.append(entry)
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_FILE.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass
    db = db_source()
    if db is not None:
        try:
            with db.connect() as c:
                db.audit(c, entry["actor"], action, target, details)
        except Exception:
            pass


def ensemble_threshold(utility: str) -> float:
    base = load_json("engine_summary.json", "artifacts").get("thresholds", {}).get(utility, {}).get("ensemble", 0.95)
    return float(st.session_state.threshold_override.get(utility, base))


def current_flags(df: pd.DataFrame) -> pd.Series:
    """Ensemble flags under the operator's current thresholds."""
    thr = df["utility"].map(ensemble_threshold)
    return df["score_ensemble"].fillna(-1) >= thr


# --------------------------------------------------------------------------- UI helpers
CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px;}
h1, h2, h3 {letter-spacing: -0.01em;}
h1 {font-size: 1.55rem !important; font-weight: 650 !important;}
h3 {font-size: 1.05rem !important; font-weight: 600 !important;}
[data-testid="stMetricValue"] {font-size: 1.45rem; font-variant-numeric: tabular-nums;}
[data-testid="stMetricLabel"] p {font-size: 0.78rem; color: #6B7378; text-transform: uppercase; letter-spacing: .04em;}
div[data-testid="stVerticalBlockBorderWrapper"] {background: #FFFFFF;}
.tag {display:inline-block; padding:2px 8px; border-radius:10px; font-size:.75rem; font-weight:600;
      color:#fff; margin-right:4px;}
.note {font-size:.82rem; color:#6B7378;}
.banner {border:1px solid #D9D4C7; background:#FBFAF6; border-radius:8px; padding:.55rem .8rem;
         font-size:.85rem; color:#454C50; margin-bottom:.8rem;}
.verdict-pass {color:#0B6E69; font-weight:700;} .verdict-fail {color:#B3261E; font-weight:700;}
</style>
"""


def header(title: str, subtitle: str = ""):
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f"<div class='note'>{subtitle}</div>", unsafe_allow_html=True)


def banner(text: str):
    st.markdown(f"<div class='banner'>{text}</div>", unsafe_allow_html=True)


def tag(text: str, color: str) -> str:
    return f"<span class='tag' style='background:{color}'>{text}</span>"


def style(fig: go.Figure, height: int = 320, legend: bool = True) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="#FFFFFF", font=dict(family="Inter, system-ui, sans-serif", size=12, color=INK),
                      showlegend=legend, legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)),
                      hoverlabel=dict(font_size=12))
    fig.update_xaxes(gridcolor=GRID, linecolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=GRID, zeroline=False)
    return fig


def fmt_ts(ts) -> str:
    return pd.Timestamp(ts).tz_convert("Europe/London").strftime("%a %d %b %H:%M")


def explanation_bars(values, title: str, color: str = "#0B6E69", k: int = 8) -> go.Figure:
    v = np.asarray(values, dtype=float)
    order = np.argsort(-np.abs(v))[:k][::-1]
    labels = [FEATURE_LABELS[FEATURES[i]] for i in order]
    fig = go.Figure(go.Bar(x=v[order], y=labels, orientation="h",
                           marker_color=[color if v[i] > 0 else "#B9B4A7" for i in order],
                           hovertemplate="%{y}: %{x:.3f}<extra></extra>"))
    fig.update_layout(title=dict(text=title, font=dict(size=13)))
    return style(fig, height=300, legend=False)


def now_ms() -> float:
    return time.time() * 1000
