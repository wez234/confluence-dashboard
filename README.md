# Confluence: real-time multi-utility analytics with explainable anomaly detection

This is the software artefact for the 7CS077 dissertation *Real-Time Multi-Utility Analytics Platform with Explainable Anomaly Detection* (Design Science Research). It ingests electricity (15-minute), gas (hourly) and water (irregular) smart-meter streams through Apache Kafka and stores them in TimescaleDB/PostgreSQL. Each reading is scored by five detectors and an ensemble, and every alert is explained with SHAP, LIME and a plain-language narrative in a Streamlit dashboard.

![architecture](docs/architecture.png)

## What is in the repository

| Path | Contents |
|---|---|
| `src/confluence/data` | Synthetic multi-utility generator with labelled anomalies; SGCC and London (UK) smart-meter adapters |
| `src/confluence/ingestion` | Kafka producer and consumer; validation, cleaning, UTC normalisation, causal features, micro-batch stream processor |
| `src/confluence/storage` | TimescaleDB schema (hypertables, continuous aggregate, compression, retention, roles, audit tables) |
| `src/confluence/detection` | Z-score, moving average, Isolation Forest, One-Class SVM, LSTM autoencoder (PyTorch), weighted ensemble |
| `src/confluence/explain` | TreeSHAP, KernelSHAP, LIME, narratives |
| `src/confluence/alerts` | Severity, debounce, escalation, cross-utility co-occurrence |
| `src/confluence/api` | FastAPI REST layer |
| `src/confluence/evaluation` | One-command evaluation (H1/H2/XAI), Kafka latency analysis, user-study analysis (H3) |
| `dashboard/` | Streamlit dashboard: monitoring, historical, cross-utility, alerts, model performance, XAI, user study, about and ethics |
| `prototype/` | Early HTML design prototype, **simulated values only** (served by GitHub Pages) |
| `docs/` | [Requirements and traceability](docs/REQUIREMENTS.md) · [Architecture](docs/ARCHITECTURE.md) · [Evaluation](docs/EVALUATION.md) · [Experiments](docs/EXPERIMENTS.md) · [User study](docs/USER_STUDY.md) · [Deployment and UK recommendations](docs/DEPLOYMENT.md) |

## Quick start

```bash
# dashboard only (demo mode, uses committed artifacts)
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py

# full rebuild of every model and number
make install && make evaluate && make test

# full streaming stack
cp .env.example .env && docker compose up --build
```

## Results so far (synthetic data, test period)

| Question | Result |
|---|---|
| RQ2: best balance | The ensemble has the highest ROC-AUC (0.940 ± 0.008 over 3 seeds) and 88.6% event recall. The LSTM has the best single-run F1 (0.580) but is the least stable. |
| H1: LSTM ≥ 15% higher temporal recall | **Not supported.** The LSTM misses the +15% margin over Z-score in all 6 seed and basis combinations, and Z-score is outright higher in 4 of them. |
| H2: mean alert latency < 2.5 s | **Supported.** Kafka and PostgreSQL run: 0.69 s mean, 1.28 s p95, 100% of readings under 2.5 s. |
| XAI plausibility | Top SHAP factor matches the anomaly type's expected driver in 78.6% of cases (chance ≈ 24%). TreeSHAP takes 3.2 ms per alert. |
| H3, SUS, TAM | **Pending participants.** The study instrument and analysis are built and tested. |

Full details, limitations and threats to validity are in [docs/EVALUATION.md](docs/EVALUATION.md). The numbers come from synthetic data with injected anomalies. They rank the methods, but they do not predict field performance.

## Ethics

The platform uses public or synthetic data only, with no personal information. It is monitoring only: thresholds change only through an operator, and every change and alert action is written to an audit log. Study participants give informed consent and are identified only by a random code.
