"""Panel 2 — Historical analysis."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import DISPLAY, SEVCOLOR, UCOLOR, UTILITIES, BASE_DETECTORS, header, load_scored, style


def render():
    header("Historical analysis", "Explore any meter across the full 60-day record: consumption against its learned "
           "profile, and where each detector fired.")
    df = load_scored()
    c = st.columns([1, 1, 2, 2])
    utility = c[0].selectbox("Utility", list(UTILITIES), key="hist_u")
    meters = sorted(df[df.utility == utility].meter_id.unique())
    meter = c[1].selectbox("Meter", meters, key="hist_m")
    tmin, tmax = df.ts.min().date(), df.ts.max().date()
    rng = c[2].date_input("Date range", value=(tmax - pd.Timedelta(days=14), tmax), min_value=tmin, max_value=tmax)
    dets = c[3].multiselect("Show detector flags", BASE_DETECTORS + ["ensemble"], default=["ensemble"],
                            format_func=lambda d: DISPLAY[d])
    if isinstance(rng, tuple) and len(rng) == 2:
        start, end = pd.Timestamp(rng[0], tz="UTC"), pd.Timestamp(rng[1], tz="UTC") + pd.Timedelta(days=1)
    else:
        start, end = pd.Timestamp(tmin, tz="UTC"), pd.Timestamp(tmax, tz="UTC")
    g = df[(df.meter_id == meter) & (df.ts >= start) & (df.ts < end)].sort_values("ts")
    if g.empty:
        st.info("No readings in this range.")
        return
    unit = UTILITIES[utility].unit
    fig = go.Figure()
    fig.add_scatter(x=g.ts, y=g.expected, name="expected (learned profile)", line=dict(color="#B9B4A7", width=1, dash="dot"))
    fig.add_scatter(x=g.ts, y=g.value, name=f"reading ({unit})", line=dict(color=UCOLOR[utility], width=1.4))
    lab = g[g.is_anomaly]
    fig.add_scatter(x=lab.ts, y=lab.value, mode="markers", name="injected anomaly (ground truth)",
                    marker=dict(symbol="square-open", color="#6B7378", size=7))
    palette = ["#B3261E", "#6A3FB5", "#0B6E69", "#C77700", "#2F5FB3", "#1D2327"]
    for i, d in enumerate(dets):
        h = g[g[f"flag_{d}"]]
        fig.add_scatter(x=h.ts, y=h.value, mode="markers", name=f"{DISPLAY[d]} flag",
                        marker=dict(color=palette[i % len(palette)], size=5 + 2 * (d == "ensemble")))
    for split, color in (("train", "rgba(11,110,105,0.04)"), ("validation", "rgba(199,119,0,0.06)"), ("test", "rgba(47,95,179,0.05)")):
        s = g[g.split == split]
        if len(s):
            fig.add_vrect(x0=s.ts.min(), x1=s.ts.max(), fillcolor=color, line_width=0, annotation_text=split,
                          annotation_position="top left", annotation_font_size=10)
    st.plotly_chart(style(fig, 380), width="stretch")

    a, b = st.columns(2)
    with a:
        factor, dunit = {"electricity": (1, "kWh"), "gas": (1, "m3"), "water": (15, "litres")}[utility]
        daily = g.set_index("ts").value.resample("1D").sum() * factor
        fig2 = go.Figure(go.Bar(x=daily.index, y=daily.values, marker_color=UCOLOR[utility]))
        fig2.update_layout(title=dict(text=f"Daily consumption ({dunit})", font=dict(size=13)))
        st.plotly_chart(style(fig2, 260, False), width="stretch")
    with b:
        fig3 = go.Figure()
        for d in dets:
            fig3.add_scatter(x=g.ts, y=g[f"score_{d}"], name=DISPLAY[d], line=dict(width=1))
        fig3.update_layout(title=dict(text="Detector scores (raw scale)", font=dict(size=13)))
        st.plotly_chart(style(fig3, 260), width="stretch")
    s = g[["is_anomaly"] + [f"flag_{d}" for d in dets]].sum()
    st.caption(f"In this window: {int(s.is_anomaly)} labelled anomalous readings; " +
               ", ".join(f"{DISPLAY[d]} flagged {int(s[f'flag_{d}'])}" for d in dets) + ".")
