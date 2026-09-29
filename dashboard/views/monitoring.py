"""Panel 1 — Real-time monitoring."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import (SEVCOLOR, UCOLOR, UTILITIES, banner, current_flags, db_source, fmt_ts, header, load_alerts,
                  load_json, load_scored, style, tag)

STEP = pd.Timedelta("15min")


def _live_db_view(db):
    st.caption("Live pipeline: reading TimescaleDB / PostgreSQL written by the Kafka consumer.")
    recent = db.query("SELECT ts, meter_id, utility, value, ensemble_score, is_alert, latency_ms FROM processed_readings "
                      "WHERE ts > (SELECT max(ts) FROM processed_readings) - interval '24 hours' ORDER BY ts")
    if recent.empty:
        st.info("The consumer has not written any readings yet. Start the producer (docker compose up producer).")
        return
    lat = db.query("SELECT avg(latency_ms) m, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) p95 "
                   "FROM (SELECT latency_ms FROM processed_readings ORDER BY ts DESC LIMIT 2000) t")
    c = st.columns(4)
    c[0].metric("Readings (24 h)", f"{len(recent):,}")
    c[1].metric("Alerts (24 h)", int(recent.is_alert.sum()))
    c[2].metric("Meters reporting", recent.meter_id.nunique())
    c[3].metric("Pipeline latency (mean / p95)", f"{lat.m[0]:.0f} / {lat.p95[0]:.0f} ms")
    for u in UTILITIES:
        g = recent[recent.utility == u]
        if g.empty:
            continue
        agg = g.groupby("ts").value.sum()
        fig = go.Figure(go.Scatter(x=agg.index, y=agg.values, line=dict(color=UCOLOR[u], width=1.6), name=u))
        al = g[g.is_alert]
        fig.add_scatter(x=al.ts, y=agg.reindex(al.ts).values, mode="markers", name="alert",
                        marker=dict(color=SEVCOLOR["critical"], size=7))
        st.plotly_chart(style(fig, 220), width="stretch", key=f"live-{u}")
    alerts = db.query("SELECT id, ts, meter_id, utility, severity, ensemble_score, status FROM anomalies ORDER BY ts DESC LIMIT 20")
    st.subheader("Latest alerts")
    st.dataframe(alerts, hide_index=True, width="stretch")


def render():
    header("Real-time monitoring", "Unified live view of electricity, gas and water consumption with streaming anomaly alerts.")
    db = db_source()
    if db is not None:
        _live_db_view(db)
        return
    banner("Demo mode — replaying the held-out <b>test period</b> of the synthetic multi-utility dataset through the "
           "trained detectors. Scores and alerts are the models' real outputs on unseen data; the stream itself is simulated. "
           "Run the docker stack for the live Kafka pipeline.")
    df = load_scored()
    test = df[df.split == "test"]
    ts_all = test.ts.sort_values().unique()
    ss = st.session_state
    if ss.cursor is None:
        ss.cursor = pd.Timestamp(ts_all[0]) + pd.Timedelta(hours=30)

    c1, c2, c3, c4 = st.columns([1, 1, 2, 3])
    if c1.button("Pause" if ss.playing else "Play", width="stretch", type="primary"):
        ss.playing = not ss.playing
        st.rerun()
    if c2.button("Reset", width="stretch"):
        ss.cursor = pd.Timestamp(ts_all[0]) + pd.Timedelta(hours=30)
        ss.playing = False
        st.rerun()
    speed = c3.select_slider("Replay speed", options=[1, 2, 4, 8], value=ss.get("speed", 2),
                             format_func=lambda x: f"{x * 15} min / tick", key="speed")
    utilities = c4.multiselect("Utilities", list(UTILITIES), default=list(UTILITIES), key="mon_util")

    @st.fragment(run_every=1.5 if ss.playing else None)
    def live():
        if ss.playing:
            ss.cursor = min(ss.cursor + speed * STEP, pd.Timestamp(ts_all[-1]))
        now = ss.cursor
        window = test[(test.ts > now - pd.Timedelta(hours=24)) & (test.ts <= now) & test.utility.isin(utilities)].copy()
        window["flag"] = current_flags(window)
        alerts = load_alerts()
        alerts = alerts[(alerts.start <= now) & (alerts.start > now - pd.Timedelta(hours=24)) & alerts.utility.isin(utilities)]
        stream = load_json("stream_kafka_latency.json")
        k = st.columns(5)
        k[0].metric("Simulated time", fmt_ts(now))
        k[1].metric("Readings (24 h)", f"{len(window):,}")
        k[2].metric("Alerts (24 h)", len(alerts))
        k[3].metric("Critical", int((alerts.severity == "critical").sum()))
        k[4].metric("Kafka latency (mean)", f"{1000 * stream.get('e2e_mean_s', float('nan')):.0f} ms",
                    help="Measured end-to-end (producer -> Kafka -> consumer -> database) in the integration run; "
                         "see Model performance.")
        left, right = st.columns([2.2, 1])
        with left:
            for u in utilities:
                g = window[window.utility == u]
                if g.empty:
                    continue
                agg = g.groupby("ts").agg(value=("value", "sum"), expected=("expected", "sum"), nflag=("flag", "sum"))
                fig = go.Figure()
                fig.add_scatter(x=agg.index, y=agg.expected, name="expected", line=dict(color="#B9B4A7", width=1, dash="dot"))
                fig.add_scatter(x=agg.index, y=agg.value, name=f"{u} total ({UTILITIES[u].unit})",
                                line=dict(color=UCOLOR[u], width=1.8))
                hit = agg[agg.nflag > 0]
                fig.add_scatter(x=hit.index, y=hit.value, mode="markers", name="meters in alert",
                                marker=dict(color=SEVCOLOR["critical"], size=6 + 2 * hit.nflag.clip(upper=5)),
                                text=hit.nflag, hovertemplate="%{x}<br>%{text} meter(s) flagged<extra></extra>")
                fig.update_layout(title=dict(text=f"{u.title()} — {UTILITIES[u].raw_freq_note} readings, all meters",
                                             font=dict(size=13)))
                st.plotly_chart(style(fig, 230), width="stretch", key=f"mon-{u}")
        with right:
            st.subheader("Alert feed")
            if alerts.empty:
                st.caption("No alerts in the last 24 hours of the replay.")
            for _, a in alerts.sort_values("start", ascending=False).head(9).iterrows():
                with st.container(border=True):
                    st.markdown(f"{tag(a.severity.upper(), SEVCOLOR[a.severity])}"
                                f"<b>{a.utility.title()} · {a.meter_id}</b> "
                                f"<span class='note'>{fmt_ts(a.start)}</span>", unsafe_allow_html=True)
                    st.markdown(f"<div class='note'>{a.narrative}</div>", unsafe_allow_html=True)
            if ss.cursor >= pd.Timestamp(ts_all[-1]):
                st.caption("End of test period reached.")
    live()
