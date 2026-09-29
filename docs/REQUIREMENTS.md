# Requirements specification

Derived from the final dissertation proposal (*Real-Time Multi-Utility Analytics Platform with Explainable Anomaly Detection*, 7CS077) and its Figure 1. Every requirement is traced to a research question (RQ), hypothesis (H), expected outcome (O) or the ethics section (E), and to the code and evidence that satisfy it.

Status: **Met** = implemented and verified by a test or a measured run. **Partial** = implemented, but not fully verified or with a stated limitation. **Pending** = needs something outside the code (participants, real data or cloud hardware).

## Traceability sources

| ID | Source in the proposal |
|---|---|
| RQ1 | How can a scalable real-time architecture integrate heterogeneous smart meter data across electricity, gas and water? |
| RQ2 | Which technique best balances detection accuracy, latency and interpretability? |
| RQ3 | How effective is an explainable real-time dashboard in supporting operational decisions? |
| H1 | LSTM autoencoder recall on temporal anomalies at least 15% higher than statistical methods and Isolation Forest |
| H2 | Mean alert latency below 2.5 s |
| H3 | XAI raises operator trust by at least 20% compared with a black box |
| O1–O4 | Validated architecture · empirical comparison across utility types · XAI trust evidence · UK deployment recommendations |
| E | Ethics: public or synthetic data, no PII, informed consent, monitoring only, operator-mediated thresholds, explanations with audit trails |

## Functional requirements

| ID | Requirement | Trace | Implementation | Verification | Status |
|---|---|---|---|---|---|
| FR-01 | Ingest electricity (15-min), gas (hourly) and water (irregular) readings | RQ1, O1 | `data/generator.py`, `ingestion/producer.py` | `test_generator_has_all_utilities_and_labels`; Kafka run | Met |
| FR-02 | Support public datasets: SGCC electricity and UK smart-meter data | RQ1 | `data/sgcc.py`, `data/uk_lcl.py` | `test_uk_lcl_adapter` (format fixture) | Partial: adapters exist, but the reported results use synthetic data |
| FR-03 | Stream readings through Apache Kafka | RQ1, O1 | `ingestion/producer.py`, `ingestion/consumer.py` | Kafka 3.9.1 integration run (`reports/stream_kafka_latency.json`) | Met |
| FR-04 | Validate records (schema, utility, timestamp, numeric, plausibility) | RQ1 | `ingestion/validation.py` | `test_validation_rejects_bad_records` | Met |
| FR-05 | Clean data (duplicates, negative sentinels, short gaps) | RQ1 | `ingestion/cleaning.py`, `stream_processor.py` | `test_stream_processor_matches_record_path`; ingestion stats in the report | Met |
| FR-06 | Normalise timestamps to UTC and a canonical grid per utility (DST-safe) | RQ1 | `ingestion/normalise.py` | `test_timestamps_normalised_to_utc_grid`, `test_to_utc_handles_london_dst` | Met |
| FR-07 | Causal feature extraction, identical offline and online | RQ1, RQ2 | `ingestion/features.py` | `test_features_are_causal` | Met |
| FR-08 | Partitioned time-series storage: raw, processed, historical, anomalies | RQ1, O1 | `storage/schema.sql` (hypertables, continuous aggregate, compression, retention) | Schema created on PostgreSQL 16; TimescaleDB-only statements skipped when the extension is absent | Partial: the TimescaleDB extension itself was not available in the test environment |
| FR-09 | Statistical detectors: Z-score and moving average | RQ2, O2 | `detection/models.py` | `test_engine_scores_every_detector` | Met |
| FR-10 | ML detectors: Isolation Forest and One-Class SVM | RQ2, O2 | `detection/models.py` | same | Met |
| FR-11 | Deep learning detector: LSTM autoencoder | RQ2, H1 | `detection/lstm_autoencoder.py` | same; H1 evaluation | Met |
| FR-12 | Ensemble with weighted voting and decision fusion | RQ2 | `detection/engine.py` | same | Met |
| FR-13 | SHAP explanation for every alert | RQ3, H3, E | `explain/xai.py` (TreeSHAP), `stream_processor.py` | `test_explainer_shap_and_lime`; 2,056 alerts explained | Met |
| FR-14 | LIME explanation (on demand / for comparison) | RQ3, E | `explain/xai.py` | same; SHAP-LIME agreement metric | Met |
| FR-15 | Plain-language explanation narrative | RQ3 | `explain/narrative.py` | `test_narrative_is_direction_aware` | Met |
| FR-16 | Alert management: severity, debounce, escalation, cross-utility co-occurrence | Fig. 1, RQ3 | `alerts/rules.py` | `test_alert_rules` | Met |
| FR-17 | Operator actions: acknowledge, dismiss, escalate, all audited | E, RQ3 | Alerts panel, `POST /alerts/{id}/ack`, `audit_log` table | Dashboard QA | Met |
| FR-18 | Operator-mediated, audited threshold changes (never automatic) | E | Alerts > Thresholds panel, `POST /thresholds`, `threshold_changes` table | `test_threshold_override_is_applied` | Met |
| FR-19 | Streamlit dashboard: real-time monitoring | RQ3, O1 | `dashboard/views/monitoring.py` | Dashboard QA | Met |
| FR-20 | Historical analysis | RQ3 | `dashboard/views/historical.py` | Dashboard QA | Met |
| FR-21 | Cross-utility comparison on a common axis | RQ1, RQ3 | `dashboard/views/cross_utility.py`, `hourly_common_axis` | `test_hourly_common_axis`; QA | Met |
| FR-22 | Alerts and notifications panel | RQ3 | `dashboard/views/alerts.py` | QA | Met |
| FR-23 | KPI / model-performance panel showing measured values only | O2 | `dashboard/views/performance.py` | reads `reports/*.json` | Met |
| FR-24 | Explainable AI insights panel | RQ3, H3 | `dashboard/views/xai.py` | QA | Met |
| FR-25 | REST API layer | Fig. 1 | `api/main.py` (FastAPI) | `test_api_health_and_readings_demo` | Met |
| FR-26 | User-study mode: consent, XAI vs black-box A/B, tasks, trust, SUS, TAM | RQ3, H3, E | `dashboard/views/study.py` | QA of the consent and task flow | Met (instrument), Pending (data) |
| FR-27 | Study analysis: SUS, TAM, trust, accuracy, Mann-Whitney U, H3 test | H3, O3 | `evaluation/user_study.py` | `test_sus_scoring_reference_values`, `test_study_analysis_on_fabricated_fixture` | Met |
| FR-28 | Backup and recovery | Fig. 1 | `ops/backup/backup.sh`, `backup` compose service | Script review | Partial: not run against TimescaleDB here |
| FR-29 | Monitoring and logging | Fig. 1 | `logging_setup.py` (JSON logs), latency CSV | Consumer logs from the Kafka run | Met |

## Non-functional requirements

| ID | Requirement | Target | Trace | Measured (see `docs/EVALUATION.md`) | Status |
|---|---|---|---|---|---|
| NFR-01 | Mean alert latency, end to end (producer → Kafka → detection + SHAP → database commit) | < 2.5 s | H2 | 0.69 s mean, 1.28 s p95, 1.56 s max; 100% of readings under 2.5 s | Met (single broker, 2 vCPU) |
| NFR-02 | Throughput | Report | RQ1 | ~180 readings/s per consumer process at saturation (about 160k meters at 15-min reporting) | Met (measured) |
| NFR-03 | Resource utilisation | Report | RQ1 | ~52% CPU of 2 vCPUs, ~820 MB RSS for the consumer | Met (measured) |
| NFR-04 | Detection accuracy reported with precision, recall, F1 and ROC-AUC, overall, per utility and per anomaly type | Report | RQ2, O2 | `reports/evaluation_report.md` | Met |
| NFR-05 | H1: LSTM temporal recall at least 15% above Z-score, moving average and Isolation Forest | ≥ 15% | H1 | Not supported on 3 of 3 seeds (Z-score recall is higher) | Evaluated: hypothesis rejected |
| NFR-06 | SUS score | > 70 | RQ3 | Needs participants | Pending |
| NFR-07 | Trust improvement, XAI vs black box | ≥ 20% | H3, O3 | Needs participants | Pending |
| NFR-08 | Reproducibility: fixed seeds, one command rebuilds every number | — | DSR | `python -m confluence.evaluation.run` | Met |
| NFR-09 | Horizontal scalability | — | RQ1 | Kafka topic partitions (3 in compose) with a consumer group; stateless API | Partial: scale-out not benchmarked |
| NFR-10 | Security: secrets in the environment, least-privilege DB roles, API key on writes | — | E | `.env.example`, `schema.sql` roles, `require_key` | Met |
| NFR-11 | Privacy / GDPR: no PII; pseudonymous study codes; right to withdraw | — | E | No personal fields in any schema; study stores a random code | Met |
| NFR-12 | Portability: container deployment and a zero-infrastructure demo | — | O4 | `docker-compose.yml`; dashboard demo mode | Partial: compose file not executed here (no Docker) |
| NFR-13 | Test coverage of the core pipeline and CI | — | DSR | 18 pytest tests, GitHub Actions `ci.yml` | Met |

## Gaps and honest status

- **H1** was tested and is not supported with this data and model configuration. It is reported as a finding, not tuned away.
- **H3, SUS and TAM** need real participants. The instrument and analysis are built and tested on fixture data only.
- **Real data**: the SGCC and London smart-meter adapters are written and format-tested, but the headline numbers come from synthetic data with injected anomalies.
- **TimescaleDB and Docker**: the integration run used Apache Kafka 3.9.1 and PostgreSQL 16.4 without the TimescaleDB extension, because Docker was not available in the build environment. `docker compose up` still needs to be run once on a machine with Docker.
