"""Panel 5 — KPI & model performance (real evaluation outputs)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import ALL_DETECTORS, DISPLAY, FAMILY, UTILITIES, banner, header, load_json, style

FAM_COLOR = {"Statistical": "#9A8F7A", "Machine learning": "#2F5FB3", "Deep learning": "#6A3FB5", "Ensemble": "#0B6E69"}


def verdict(ok: bool) -> str:
    return "<span class='verdict-pass'>SUPPORTED</span>" if ok else "<span class='verdict-fail'>NOT SUPPORTED</span>"


def render():
    header("Model performance & KPIs", "Measured results from the evaluation pipeline — nothing on this page is simulated.")
    M = load_json("metrics.json")
    K = load_json("stream_kafka_latency.json")
    S = load_json("stream_kafka_stress.json")
    if not M:
        st.error("reports/metrics.json not found — run `python -m confluence.evaluation.run`.")
        return
    banner(f"Held-out test period ({M['split']['test'][0][:10]} to {M['split']['test'][1][:10]}), "
           f"{M['config']['meters']} meters per utility, <b>{M['config']['source']}</b> data with injected, labelled anomalies. "
           "Thresholds were calibrated on the validation period only.")
    d = M["detection"]
    c = st.columns(4)
    e = d["overall"]["ensemble"]
    c[0].metric("Ensemble F1", f"{e['f1']:.3f}")
    c[1].metric("Ensemble ROC-AUC", f"{e['roc_auc']:.3f}")
    c[2].metric("Kafka end-to-end latency (mean)", f"{1000 * K.get('e2e_mean_s', float('nan')):.0f} ms",
                help="producer -> Kafka -> consumer (all detectors + SHAP) -> database commit")
    c[3].metric("Anomaly events caught by an alert", f"{M['alerts']['true_event_coverage']:.0%}")

    st.subheader("Hypotheses")
    h = st.columns(3)
    h1 = M["H1"]["temporal"]; h1b = M["H1"]["temporal_at_fpr5"]
    with h[0].container(border=True):
        st.markdown(f"**H1** LSTM ≥15% higher recall on temporal anomalies — {verdict(h1['supported'])}", unsafe_allow_html=True)
        st.caption(f"LSTM recall {h1['lstm_recall']:.2f} vs Z-score {h1['vs']['zscore']['recall']:.2f}, "
                   f"Isolation Forest {h1['vs']['isolation_forest']['recall']:.2f} (calibrated thresholds). At a matched "
                   f"5% false-positive rate: LSTM {h1b['lstm_recall']:.2f} vs {h1b['vs']['zscore']['recall']:.2f} / "
                   f"{h1b['vs']['isolation_forest']['recall']:.2f}.")
    with h[1].container(border=True):
        ok = K.get("H2_supported", M["H2"]["supported"])
        st.markdown(f"**H2** alert latency < 2.5 s — {verdict(ok)}", unsafe_allow_html=True)
        st.caption(f"Kafka + database: mean {1000 * K.get('e2e_mean_s', 0):.0f} ms, p95 {1000 * K.get('e2e_p95_s', 0):.0f} ms, "
                   f"max {1000 * K.get('e2e_max_s', 0):.0f} ms over {K.get('readings', 0):,} readings. In-process: mean "
                   f"{1000 * M['streaming']['latency_mean_s']:.0f} ms.")
    with h[2].container(border=True):
        st.markdown("**H3** XAI improves operator trust ≥20% — <span class='note'>PENDING USER STUDY</span>",
                    unsafe_allow_html=True)
        st.caption("Requires participants. Run the study from the User study page; analyse with "
                   "`python -m confluence.evaluation.user_study`.")

    st.subheader("Detection accuracy by technique")
    rows = []
    for k in ALL_DETECTORS:
        o, ev = d["overall"][k], d["event_level"][k]
        rows.append({"Technique": DISPLAY[k], "Family": FAMILY[k], "Precision": o["precision"], "Recall": o["recall"],
                     "F1": o["f1"], "ROC-AUC": o["roc_auc"], "Recall @5% FPR": o["recall_at_fpr5"],
                     "Event recall": ev["event_recall"], "Temporal recall": d["per_type_recall"][k]["temporal"]})
    t = pd.DataFrame(rows)
    a, b = st.columns([1.35, 1])
    with a:
        show = t[["Technique", "Family", "Precision", "Recall", "F1", "ROC-AUC", "Event recall"]]
        st.dataframe(show.style.format({c: "{:.3f}" for c in show.columns[2:]}).background_gradient(
            subset=["F1", "ROC-AUC"], cmap="Greens", vmin=0, vmax=1.6), hide_index=True, width="stretch")
        st.caption("Event recall: share of injected anomaly events with at least one flagged reading. "
                   "Recall at a matched 5% false-positive rate is in the full report below.")
    with b:
        fig = go.Figure(go.Bar(x=t.F1, y=t.Technique, orientation="h", marker_color=[FAM_COLOR[f] for f in t.Family],
                               text=t.F1.round(3), textposition="outside"))
        fig.update_layout(title=dict(text="F1 (test period)", font=dict(size=13)), xaxis_range=[0, 1])
        st.plotly_chart(style(fig, 260, False), width="stretch")

    a, b = st.columns(2)
    with a:
        z = [[d["per_utility"][k][u]["f1"] for u in UTILITIES] for k in ALL_DETECTORS]
        fig = go.Figure(go.Heatmap(z=z, x=[u.title() for u in UTILITIES], y=[DISPLAY[k] for k in ALL_DETECTORS],
                                   colorscale=[[0, "#F7F6F2"], [1, "#0B6E69"]], zmin=0, zmax=1, showscale=False,
                                   text=[[f"{v:.2f}" for v in r] for r in z], texttemplate="%{text}"))
        fig.update_layout(title=dict(text="F1 by utility type", font=dict(size=13)), yaxis_autorange="reversed")
        st.plotly_chart(style(fig, 300, False), width="stretch")
    with b:
        types = [x for x in d["per_type_recall"]["zscore"] if x not in ("temporal", "temporal_at_fpr5")]
        z = [[d["per_type_recall"][k][ty] for ty in types] for k in ALL_DETECTORS]
        fig = go.Figure(go.Heatmap(z=z, x=types, y=[DISPLAY[k] for k in ALL_DETECTORS],
                                   colorscale=[[0, "#F7F6F2"], [1, "#6A3FB5"]], zmin=0, zmax=1, showscale=False,
                                   text=[[f"{v:.2f}" for v in r] for r in z], texttemplate="%{text}"))
        fig.update_layout(title=dict(text="Recall by anomaly type", font=dict(size=13)), yaxis_autorange="reversed")
        st.plotly_chart(style(fig, 300, False), width="stretch")

    st.subheader("Streaming performance and resources")
    s = M["streaming"]
    c = st.columns(5)
    c[0].metric("Kafka p95 latency", f"{1000 * K.get('e2e_p95_s', float('nan')):.0f} ms")
    c[1].metric("Within 2.5 s target", f"{K.get('share_under_target', float('nan')):.0%}")
    c[2].metric("Max sustained throughput", f"{S.get('max_throughput_readings_per_s', float('nan')):.0f} /s",
                help="Single consumer process on 2 vCPUs, saturated backlog test")
    c[3].metric("Consumer CPU", f"{s['cpu_utilisation_pct']:.0f}%")
    c[4].metric("Consumer memory", f"{s['peak_rss_mb']:.0f} MB")
    thr = S.get("max_throughput_readings_per_s")
    if thr:
        st.caption(f"At {thr:.0f} readings/s one consumer can keep up with about {thr * 900:,.0f} meters reporting every "
                   "15 minutes; Kafka partitions let additional consumers scale this horizontally. "
                   f"Environment: {K.get('environment', {})}. {K.get('note', '')}")

    st.subheader("Explainability")
    x = M["explainability"]
    c = st.columns(4)
    c[0].metric("TreeSHAP per alert", f"{x['shap_ms_per_alert']:.1f} ms")
    c[1].metric("Plausible top reason", f"{x['plausibility_top1']:.0%}", help=f"chance level ≈ {x['plausibility_top1_chance']:.0%}")
    c[2].metric("KernelSHAP vs LIME agreement", f"{x['kernelshap_vs_lime_same_model_jaccard']:.2f}", help="top-3 Jaccard, same model")
    c[3].metric("LIME per alert", f"{x['lime_ms_per_alert']:.0f} ms")

    with st.expander("Data ingestion quality"):
        st.json(M["ingestion"])
    with st.expander("Full evaluation report (reports/evaluation_report.md)"):
        from core import settings
        p = settings.reports_dir / "evaluation_report.md"
        st.markdown(p.read_text() if p.exists() else "not found")
