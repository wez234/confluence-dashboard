"""About: architecture, data, ethics and limitations."""
from __future__ import annotations

import streamlit as st

from core import ROOT, header, load_json


def render():
    header("About, ethics & limitations", "Confluence — explainable real-time anomaly detection across electricity, gas and water.")
    img = ROOT / "docs" / "architecture.png"
    if img.exists():
        st.image(str(img), width="stretch")
    M = load_json("metrics.json")
    st.markdown(f"""
### What this is
A Kappa-architecture prototype for the MSc dissertation *Real-Time Multi-Utility Analytics Platform with Explainable
Anomaly Detection*. One streaming path ingests readings through Apache Kafka, validates and cleans them, normalises
timestamps to UTC and a canonical grid, extracts causal features, scores each reading with five detectors plus a weighted
ensemble, attaches a SHAP explanation to every alert and writes everything to TimescaleDB for this dashboard.

### Data
- **Electricity** — 15-minute readings. Synthetic UK-style load profiles by default; the SGCC adapter
  (`confluence.data.sgcc`) substitutes real SGCC daily consumption when the dataset is downloaded.
- **Gas** — hourly readings, synthetic with a heating-degree pattern.
- **Water** — irregular 5-30 minute readings recorded in UK local time (tests DST-aware normalisation).
- Labelled anomalies (spike, drop, leak, stuck meter, drift) are injected so precision and recall can be measured.
- Raw records this run: {M.get('ingestion', {}).get('raw_records', 'n/a'):,} · generated {M.get('generated_at', '')[:10]}.

### Ethics
- Public or synthetic data only. No personally identifiable information is stored.
- **Monitoring only**: the system raises alerts; it never acts on the network. Thresholds are operator-mediated and
  every threshold change, acknowledgement, dismissal and escalation is written to an audit trail.
- Every alert carries a SHAP explanation; LIME is available for comparison.
- The user study uses informed consent, random participant codes, and the right to withdraw.
- Security: secrets via environment variables, least-privilege database roles, API key on state-changing endpoints.

### Limitations
- Detection metrics come from synthetic data with injected anomalies; they compare methods under controlled
  conditions and do not predict field performance on a real network.
- The LSTM autoencoder is not covered by per-reading SHAP/LIME attributions (it reads windows).
- Latency was measured on a single-broker, 2-vCPU setup; production sizing needs a load test on target hardware.
- H3 (trust) is untested until the user study has participants.
""")
