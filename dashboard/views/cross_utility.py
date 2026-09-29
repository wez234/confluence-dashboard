"""Panel 3 — Cross-utility comparison on a common hourly axis."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import SEVCOLOR, UCOLOR, UTILITIES, fmt_ts, header, load_alerts, load_scored, style


@st.cache_data(show_spinner=False)
def hourly(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["site_id"] = "SITE-" + d.meter_id.str[1:]
    d["hour"] = d.ts.dt.floor("1h")
    h = d.groupby(["site_id", "utility", "hour"]).agg(value=("value", "mean"), expected=("expected", "mean"),
                                                        alerts=("flag_ensemble", "sum")).reset_index()
    base = h.groupby(["site_id", "utility"]).value.transform("mean")
    h["index"] = 100 * h.value / base
    h["expected_index"] = 100 * h.expected / base
    return h


def render():
    header("Cross-utility comparison", "Electricity (15-min), gas (hourly) and water (irregular) aligned on a common "
           "hourly UTC axis. Each property (site) has one meter of each utility.")
    df = load_scored()
    h = hourly(df[["ts", "meter_id", "utility", "value", "expected", "flag_ensemble"]])
    sites = sorted(h.site_id.unique())
    c = st.columns([1, 2])
    site = c[0].selectbox("Site", sites, key="cx_site")
    days = c[1].slider("Days shown (ending at the last reading)", 2, 30, 7)
    end = h.hour.max()
    g = h[(h.site_id == site) & (h.hour > end - pd.Timedelta(days=days))]
    al_all = load_alerts()
    site_alerts = al_all[(al_all.site_id == site)]
    fig = go.Figure()
    for u in UTILITIES:
        s = g[g.utility == u]
        fig.add_scatter(x=s.hour, y=s["index"], name=u.title(), line=dict(color=UCOLOR[u], width=1.6))
        hours = site_alerts[site_alerts.utility == u].peak_ts.dt.floor("1h")
        hit = s[s.hour.isin(hours)]
        fig.add_scatter(x=hit.hour, y=hit["index"], mode="markers", showlegend=False,
                        marker=dict(color=UCOLOR[u], size=9, line=dict(color=SEVCOLOR["critical"], width=2)),
                        hovertemplate=f"{u}: alert<extra></extra>")
    fig.update_layout(title=dict(text=f"{site} — hourly consumption index (100 = site mean for that utility); "
                                      "ringed points are raised alerts", font=dict(size=13)), yaxis_title="index")
    st.plotly_chart(style(fig, 360), width="stretch")

    a, b = st.columns([1, 1.3])
    with a:
        piv = h[h.site_id == site].pivot_table(index="hour", columns="utility", values="index")
        corr = piv.corr().round(2)
        fig2 = go.Figure(go.Heatmap(z=corr.values, x=[c.title() for c in corr.columns], y=[c.title() for c in corr.index],
                                    colorscale=[[0, "#F1EEE6"], [1, "#0B6E69"]], zmin=-1, zmax=1,
                                    text=corr.values, texttemplate="%{text}", showscale=False))
        fig2.update_layout(title=dict(text="Hourly correlation between utilities (whole record)", font=dict(size=13)))
        st.plotly_chart(style(fig2, 300, False), width="stretch")
    with b:
        st.subheader("Co-occurring alerts across utilities")
        co = al_all[al_all.cross_utility].sort_values("start", ascending=False)
        st.caption(f"{co.site_id.nunique()} sites had anomalies in two or more utilities within a 2-hour window "
                   f"({len(co)} alert events). These are escalated one severity level because a shared cause "
                   "(e.g. occupancy change, a faulty building system) is more likely.")
        view = co[co.site_id == site] if (co.site_id == site).any() else co
        st.dataframe(view.assign(start=view.start.map(fmt_ts))[["site_id", "utility", "meter_id", "start", "severity",
                                                                  "max_votes"]].head(12),
                     hide_index=True, width="stretch")
