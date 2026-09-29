"""Confluence — Streamlit dashboard entry point.

    streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Confluence — multi-utility anomaly monitoring", layout="wide",
                   initial_sidebar_state="expanded")

from core import artifacts_ready, db_source, init_state  # noqa: E402
from views import about, alerts, cross_utility, historical, monitoring, performance, study, xai  # noqa: E402

init_state()

st.logo(str(Path(__file__).resolve().parent / "assets" / "logo.svg"), size="large")

with st.sidebar:
    live = db_source() is not None
    st.caption("Multi-utility anomaly monitoring  \n" + ("Data: **live pipeline (database)**" if live
               else "Data: **demo artifacts — test-period replay**"))

if not artifacts_ready():
    st.error("Model artifacts not found. Run `python -m confluence.evaluation.run` to train and evaluate the detectors.")
    st.stop()

pages = {
    "monitoring": st.Page(monitoring.render, title="Real-time monitoring", icon=":material/monitoring:", url_path="monitoring", default=True),
    "historical": st.Page(historical.render, title="Historical analysis", icon=":material/history:", url_path="historical"),
    "cross": st.Page(cross_utility.render, title="Cross-utility comparison", icon=":material/compare_arrows:", url_path="cross-utility"),
    "alerts": st.Page(alerts.render, title="Alerts & notifications", icon=":material/notifications:", url_path="alerts"),
    "performance": st.Page(performance.render, title="Model performance", icon=":material/insights:", url_path="performance"),
    "xai": st.Page(xai.render, title="Explainable AI", icon=":material/psychology:", url_path="explain"),
    "study": st.Page(study.render, title="User study", icon=":material/assignment:", url_path="study"),
    "about": st.Page(about.render, title="About & ethics", icon=":material/info:", url_path="about"),
}
st.session_state["_pages"] = pages
nav = st.navigation({"Operate": [pages[k] for k in ("monitoring", "historical", "cross", "alerts")],
                     "Evaluate": [pages[k] for k in ("performance", "xai", "study")], "Project": [pages["about"]]})
nav.run()
