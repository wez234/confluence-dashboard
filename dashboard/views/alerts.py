"""Panel 4 — Alerts & notifications (operator-mediated, audited)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import (SEVCOLOR, UTILITIES, audit, banner, current_flags, ensemble_threshold, fmt_ts, header,
                  load_alerts, load_json, load_scored, style, tag)

ESCALATE_AFTER = pd.Timedelta(minutes=30)


def _status(aid: int, start: pd.Timestamp, now: pd.Timestamp) -> str:
    s = st.session_state.alert_status.get(int(aid))
    if s:
        return s
    return "escalated" if now - start > ESCALATE_AFTER else "open"


def render():
    header("Alerts & notifications", "Every alert needs a human decision. The system never acts on the network by itself.")
    ss = st.session_state
    al = load_alerts().copy()
    now = ss.cursor if ss.get("cursor") is not None else al.start.max()
    al = al[al.start <= now]
    period = st.segmented_control("Period", ["Last 24 hours", "Last 7 days", "Whole test period"],
                                  default="Last 24 hours", key="al_period") or "Last 24 hours"
    span = {"Last 24 hours": pd.Timedelta(days=1), "Last 7 days": pd.Timedelta(days=7)}.get(period)
    if span is not None:
        al = al[al.start > now - span]
    st.caption(f"Simulated clock: {fmt_ts(now)} (advance it with Play on the Real-time monitoring page).")
    al["status"] = [_status(a, s, now) for a, s in zip(al.alert_id, al.start)]
    tab1, tab2, tab3 = st.tabs(["Alert queue", "Thresholds", "Audit trail"])

    with tab1:
        c = st.columns([1.2, 1.2, 1.2, 1.4])
        sev = c[0].multiselect("Severity", ["critical", "warning", "info"], default=["critical", "warning", "info"])
        uts = c[1].multiselect("Utility", list(UTILITIES), default=list(UTILITIES), key="al_u")
        stat = c[2].multiselect("Status", ["open", "escalated", "acknowledged", "dismissed"], default=["open", "escalated"])
        ss.actor = c[3].text_input("Operator name (for the audit trail)", value=ss.actor, max_chars=40)
        view = al[al.severity.isin(sev) & al.utility.isin(uts) & al.status.isin(stat)].sort_values("start", ascending=False)
        k = st.columns(4)
        k[0].metric("Shown", len(view))
        k[1].metric("Escalated (>30 min)", int((al.status == "escalated").sum()))
        k[2].metric("Acknowledged", int((al.status == "acknowledged").sum()))
        k[3].metric("Dismissed", int((al.status == "dismissed").sum()))
        table = view.assign(raised=view.start.map(fmt_ts), score=view.peak_score.round(3))[
            ["alert_id", "raised", "severity", "status", "utility", "meter_id", "site_id", "steps", "max_votes", "score",
             "cross_utility"]]
        ev = st.dataframe(table, hide_index=True, width="stretch", height=300, on_select="rerun",
                          selection_mode="single-row", key="alert_table",
                          column_config={"steps": st.column_config.NumberColumn("readings", help="consecutive flagged readings"),
                                         "max_votes": st.column_config.NumberColumn("detectors agreeing"),
                                         "cross_utility": st.column_config.CheckboxColumn("multi-utility")})
        rows = ev.selection.rows if ev and ev.selection else []
        if rows:
            ss.selected_alert = int(table.iloc[rows[0]].alert_id)
        if ss.selected_alert is not None and ss.selected_alert in set(al.alert_id):
            a = al[al.alert_id == ss.selected_alert].iloc[0]
            with st.container(border=True):
                st.markdown(f"{tag(a.severity.upper(), SEVCOLOR[a.severity])} <b>Alert #{a.alert_id}</b> — "
                            f"{a.utility} meter {a.meter_id} ({a.site_id}), {fmt_ts(a.start)} to {fmt_ts(a.end)}, "
                            f"status <b>{a.status}</b>", unsafe_allow_html=True)
                st.write(a.narrative)
                note = st.text_input("Note (optional)", key=f"note-{a.alert_id}")
                b = st.columns(4)
                for i, (label, status) in enumerate((("Acknowledge", "acknowledged"), ("Dismiss as false alarm", "dismissed"),
                                                     ("Escalate", "escalated"))):
                    if b[i].button(label, key=f"{status}-{a.alert_id}", width="stretch",
                                   type="primary" if i == 0 else "secondary"):
                        if not ss.actor.strip():
                            st.warning("Enter your operator name first — every action is recorded in the audit trail.")
                        else:
                            ss.alert_status[int(a.alert_id)] = status
                            audit(status, f"alert:{a.alert_id}", note=note, severity=a.severity)
                            st.rerun()
                if b[3].button("Open explanation", key=f"xai-{a.alert_id}", width="stretch"):
                    audit("view_explanation", f"alert:{a.alert_id}")
                    st.switch_page(st.session_state["_pages"]["xai"])
        else:
            st.caption("Select a row to review, acknowledge, dismiss or escalate an alert.")

    with tab2:
        banner("Thresholds are <b>operator-mediated</b>: defaults were calibrated on the validation period, and any change "
               "needs a reason and is written to the audit trail. The impact preview uses the labelled test period.")
        df = load_scored()
        test = df[df.split == "test"]
        summary = load_json("engine_summary.json", "artifacts")
        u = st.selectbox("Utility", list(UTILITIES), key="thr_u")
        g = test[test.utility == u]
        default = summary["thresholds"][u]["ensemble"]
        cur = ensemble_threshold(u)
        new = st.slider("Ensemble alert threshold (weighted percentile score)", 0.80, 0.999, float(cur), 0.001, format="%.3f")
        qs = np.linspace(0.80, 0.999, 60)
        y = g.is_anomaly.values
        s = g.score_ensemble.fillna(-1).values
        prec = [((s >= q) & y).sum() / max((s >= q).sum(), 1) for q in qs]
        rec = [((s >= q) & y).sum() / max(y.sum(), 1) for q in qs]
        vol = [(s >= q).sum() / (len(g) / (96 if u != "gas" else 24)) / g.meter_id.nunique() for q in qs]
        fig = go.Figure()
        fig.add_scatter(x=qs, y=prec, name="precision")
        fig.add_scatter(x=qs, y=rec, name="recall")
        fig.add_vline(x=default, line_dash="dot", line_color="#6B7378", annotation_text="calibrated default")
        fig.add_vline(x=new, line_color="#B3261E", annotation_text="selected")
        st.plotly_chart(style(fig, 280), width="stretch")
        f = s >= new
        m = st.columns(3)
        m[0].metric("Precision (test)", f"{(f & y).sum() / max(f.sum(), 1):.2f}")
        m[1].metric("Recall (test)", f"{(f & y).sum() / max(y.sum(), 1):.2f}")
        m[2].metric("Flagged readings per meter per day", f"{np.interp(new, qs, vol):.2f}")
        reason = st.text_input("Reason for change", key="thr_reason")
        if st.button("Apply threshold", type="primary", disabled=abs(new - cur) < 1e-9):
            if not ss.actor.strip() or len(reason.strip()) < 3:
                st.warning("An operator name and a reason are required.")
            else:
                ss.threshold_override[u] = new
                audit("threshold_change", f"{u}:ensemble", old=cur, new=new, reason=reason)
                st.success(f"{u.title()} ensemble threshold set to {new:.3f}. Monitoring panels now use it.")
        st.caption("Via the REST API the same change is POST /thresholds (API key required), which persists it to the engine.")

    with tab3:
        log = pd.DataFrame(ss.audit)
        if log.empty:
            st.caption("No actions recorded in this session yet.")
        else:
            st.dataframe(log.iloc[::-1], hide_index=True, width="stretch")
        st.caption("In the docker deployment every action is also stored in the audit_log and threshold_changes tables.")
