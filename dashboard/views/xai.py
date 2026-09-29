"""Panel 6 — Explainable AI insights (SHAP + LIME + plain-language narrative)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import (DISPLAY, FEATURE_LABELS, FEATURES, SEVCOLOR, UCOLOR, UTILITIES, BASE_DETECTORS, audit, explanation_bars,
                  fmt_ts, header, load_alerts, load_json, load_scored, style, tag)


def render():
    header("Explainable AI insights", "Why did the system raise this alert? SHAP and LIME attribute the decision to "
           "the input features; the narrative translates the top reasons into operator language.")
    al = load_alerts()
    ss = st.session_state
    c = st.columns([1, 1, 2])
    u = c[0].selectbox("Utility", ["all"] + list(UTILITIES), key="xai_u")
    sev = c[1].selectbox("Severity", ["all", "critical", "warning", "info"], key="xai_s")
    pool = al[((al.utility == u) | (u == "all")) & ((al.severity == sev) | (sev == "all"))].sort_values("start", ascending=False)
    if pool.empty:
        st.info("No alerts match.")
        return
    ids = pool.alert_id.tolist()
    default = ids.index(ss.selected_alert) if ss.selected_alert in ids else 0
    label = {r.alert_id: f"#{r.alert_id} · {r.utility} {r.meter_id} · {fmt_ts(r.start)} · {r.severity}" for r in pool.itertuples()}
    aid = c[2].selectbox("Alert", ids, index=default, format_func=label.get)
    ss.selected_alert = aid
    a = al[al.alert_id == aid].iloc[0]

    with st.container(border=True):
        st.markdown(f"{tag(a.severity.upper(), SEVCOLOR[a.severity])} <b>{a.utility.title()} meter {a.meter_id}</b> · "
                    f"{fmt_ts(a.start)} · {a.steps} flagged reading(s) · {a.max_votes} of 5 detectors agree",
                    unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:1.02rem;font-weight:550;line-height:1.5;margin-top:.3rem'>{a.narrative}</div>", unsafe_allow_html=True)
    l, r = st.columns(2)
    with l:
        st.plotly_chart(explanation_bars(a.shap, "SHAP — Isolation Forest (TreeSHAP)", "#0B6E69"), width="stretch")
    with r:
        st.plotly_chart(explanation_bars(a.lime, "LIME — tabular ensemble surrogate", "#6A3FB5"), width="stretch")
    st.caption("Bars to the right push the reading towards 'anomalous'. SHAP explains the Isolation Forest exactly; LIME fits a "
               "local linear surrogate to the ensemble of Z-score, moving average, Isolation Forest and One-Class SVM. The LSTM "
               "autoencoder reads 4-hour windows rather than one feature vector, so it is not covered by these per-reading "
               "attributions — its vote is shown below.")

    df = load_scored()
    g = df[(df.meter_id == a.meter_id) & (df.ts >= a.start - pd.Timedelta(hours=30)) & (df.ts <= a.end + pd.Timedelta(hours=8))]
    peak = g[g.ts == a.peak_ts]
    left, right = st.columns([2, 1])
    with left:
        fig = go.Figure()
        fig.add_scatter(x=g.ts, y=g.expected, name="expected", line=dict(color="#B9B4A7", dash="dot", width=1))
        fig.add_scatter(x=g.ts, y=g.value, name=f"reading ({a.unit})", line=dict(color=UCOLOR[a.utility], width=1.6))
        fl = g[g.flag_ensemble]
        fig.add_scatter(x=fl.ts, y=fl.value, mode="markers", name="ensemble flag", marker=dict(color=SEVCOLOR["critical"], size=7))
        fig.add_vrect(x0=a.start, x1=a.end + pd.Timedelta("15min"), fillcolor="rgba(179,38,30,0.07)", line_width=0)
        fig.update_layout(title=dict(text="Context: 30 hours before to 8 hours after", font=dict(size=13)))
        st.plotly_chart(style(fig, 300), width="stretch")
    with right:
        st.markdown("**Detector votes at the peak reading**")
        if len(peak):
            p = peak.iloc[0]
            for d in BASE_DETECTORS:
                on = bool(p[f"flag_{d}"])
                st.markdown(f"{tag('FLAG' if on else 'ok', '#B3261E' if on else '#9AA3A8')} {DISPLAY[d]}", unsafe_allow_html=True)
        fv = pd.DataFrame({"feature": [FEATURE_LABELS[f] for f in FEATURES], "value": np.round(a.features, 3)})
        st.dataframe(fv, hide_index=True, width="stretch", height=240)

    with st.expander("Global view — which features drive alerts overall"):
        gs = load_json("engine_summary.json", "artifacts").get("global_shap", {})
        cols = st.columns(len(gs) or 1)
        for i, (ut, vals) in enumerate(gs.items()):
            v = np.array([vals[f] for f in FEATURES])
            cols[i].plotly_chart(explanation_bars(v, f"{ut.title()} — mean |SHAP| over alerts", UCOLOR[ut], k=6),
                                 width="stretch")
    if ss.get("_last_xai") != aid:
        audit("view_explanation", f"alert:{aid}")
        ss["_last_xai"] = aid
