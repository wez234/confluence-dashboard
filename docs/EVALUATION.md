# Evaluation

Every number below is produced by code in this repository and saved under `reports/`. To reproduce, run
`python -m confluence.evaluation.run` (about 2 minutes on 2 vCPUs). The seeded runs are deterministic up to PyTorch CPU nondeterminism.

## Setup

- **Data:** 60 days, 10 meters per utility (30 in total), plus one electricity, gas and water meter per site. The data are synthetic, with injected, labelled anomalies: spike, drop, leak, stuck meter and drift. The test period's anomaly rate is 3.3%.
- **Split (by time):** train on days 1–35 (detectors are fitted on these), validate on days 36–45 (thresholds and ensemble weights are calibrated here), and test on days 46–60 (reported). The test period was never used for model selection.
- **Detectors:** Z-score on the hourly profile, a 24-hour moving average, Isolation Forest, One-Class SVM, an LSTM autoencoder, and an ensemble (F1-weighted percentile fusion).
- **Alert budget:** calibration never flags more than 15% of readings. Without this cap, a weak detector can "win" F1 by flagging everything.

## RQ2 / Outcome 2: detection accuracy (seed 42, test period)

| Technique | Precision | Recall | F1 | ROC-AUC | Event recall |
|---|---|---|---|---|---|
| Z-score | 0.317 | 0.769 | 0.449 | 0.926 | 0.832 |
| Moving average | 0.070 | 0.276 | 0.112 | 0.564 | 0.389 |
| Isolation Forest | 0.412 | 0.574 | 0.480 | 0.933 | 0.517 |
| One-Class SVM | 0.480 | 0.599 | 0.533 | 0.877 | 0.604 |
| LSTM autoencoder | 0.590 | 0.571 | **0.580** | 0.916 | 0.396 |
| Ensemble | 0.395 | 0.755 | 0.519 | **0.946** | **0.886** |

F1 by utility (the ensemble is best on water, the LSTM on electricity and gas):

| Technique | Electricity | Gas | Water |
|---|---|---|---|
| Z-score | 0.530 | 0.539 | 0.293 |
| Isolation Forest | 0.636 | 0.425 | 0.189 |
| One-Class SVM | 0.628 | 0.491 | 0.320 |
| LSTM autoencoder | 0.683 | 0.511 | 0.270 |
| Ensemble | 0.639 | 0.432 | 0.368 |

**Robustness across 3 seeds (42, 7, 123)** — mean ± SD (`reports/robustness.json`):

| Technique | F1 | ROC-AUC | Temporal recall |
|---|---|---|---|
| Z-score | 0.433 ± 0.056 | 0.912 ± 0.015 | 0.661 ± 0.104 |
| Moving average | 0.097 ± 0.013 | 0.554 ± 0.015 | 0.176 ± 0.041 |
| Isolation Forest | 0.439 ± 0.051 | 0.923 ± 0.009 | 0.513 ± 0.058 |
| One-Class SVM | 0.486 ± 0.042 | 0.896 ± 0.018 | 0.603 ± 0.112 |
| LSTM autoencoder | 0.432 ± 0.129 | 0.896 ± 0.022 | 0.620 ± 0.076 |
| Ensemble | 0.477 ± 0.045 | **0.940 ± 0.008** | **0.671 ± 0.042** |

**Reading for RQ2.** The ensemble ranks best overall: it has the highest ROC-AUC in all three seeds, the highest event recall in two of three (One-Class SVM in seed 7), and the smallest variance. The LSTM has the best F1 on seed 42 but the largest variance across seeds. The 24-hour moving average is clearly weakest: sustained anomalies drag its baseline along with them. Water is the hardest utility for every method, because irregular readings are binned, interpolated and noisier.

## H1: LSTM recall on temporal anomalies (drift, leak, stuck)

| Seed | Basis | LSTM vs Z-score | vs Isolation Forest | H1 |
|---|---|---|---|---|
| 42 | calibrated thresholds | −26.6% | +3.3% | not supported |
| 42 | matched 5% FPR | −22.6% | −11.3% | not supported |
| 7 | calibrated thresholds | +3.6% | +26.6% | not supported |
| 7 | matched 5% FPR | −7.3% | −9.1% | not supported |
| 123 | calibrated thresholds | +9.6% | +35.2% | not supported |
| 123 | matched 5% FPR | −34.8% | −31.6% | not supported |

Against the moving average, the LSTM is 148–631% better in every case, so H1 holds against that baseline alone, but not against Z-score or Isolation Forest. **H1 is therefore not supported.** A plausible explanation is that the Z-score detector compares each reading with the meter's own hour-of-day profile, and that profile already encodes the temporal context the LSTM has to learn. The LSTM configuration was chosen on the validation period from five candidates (see `EXPERIMENTS.md`); it was not tuned on the test period to rescue the hypothesis.

## H2: latency, throughput and resources

| Measurement | Result |
|---|---|
| End-to-end latency, Kafka run: producer stamp → Kafka → consumer (5 detectors + ensemble + SHAP) → PostgreSQL commit | mean **0.69 s**, p50 0.74 s, p95 1.28 s, p99 1.36 s, max 1.56 s |
| Readings under 2.5 s | **100%** of 3,968 |
| Alerts only | mean 0.54 s, p95 1.14 s |
| In-process processing only (no Kafka), 2,833 readings in micro-batches of 50 | mean 0.61 s, p95 0.78 s |
| Saturated throughput, one consumer | about 180 readings/s |
| Consumer CPU / memory | ~52% of 2 vCPUs, ~820 MB RSS |

Environment: Apache Kafka 3.9.1 (KRaft, single broker) and PostgreSQL 16.4 (without the TimescaleDB extension) on one 2-vCPU / 7.8 GB machine, with the producer replaying at 1,800× real time. **H2 is supported** in this environment. Most of the latency is micro-batch scoring, so smaller poll batches or more partitions and consumers reduce it. The measurement should be repeated on the target deployment hardware with TimescaleDB.

## Explainability (supports RQ3)

| Metric | Result |
|---|---|
| Alerts explained with TreeSHAP | 2,056, 3.2 ms per alert |
| Top SHAP feature is a domain-expected driver of the anomaly type (true positives) | top-1 **78.6%** (chance ≈ 24%), top-3 98.0% |
| KernelSHAP vs LIME on the same ensemble, top-3 Jaccard | 0.59 |
| TreeSHAP (Isolation Forest) vs LIME (ensemble), top-3 Jaccard | 0.49 |
| LIME / KernelSHAP cost | 36 ms / 111 ms per alert |

## Alert management

Of 846 candidate alert events, the debounce rule (at least 2 consecutive flags, or at least 3 detectors agreeing on a single reading) raises 461. This lifts event precision from 11% to 18% while still covering 88% of true anomaly events. Alert-level precision is the platform's weakest operational number: most false alerts are single readings at evening peaks. That makes the operator-adjustable threshold and the explanations important in practice.

## H3, SUS and TAM

These are **not yet measured**. They need participants, and the study protocol is in `USER_STUDY.md`. No trust or usability numbers in this repository come from real people.

## Threats to validity

- The data are synthetic: the anomaly shapes and noise are designed, so absolute scores do not transfer to real networks. The method ranking is the transferable result.
- Only 30 meters were used. Per-utility F1 for water and gas rests on a few hundred anomalous readings.
- Latency was measured on a single broker. Network hops in a real deployment add time.
- The LSTM is not covered by per-reading SHAP/LIME (it reads windows); its vote is shown separately.

## Supplementary: STL comparator, scoring cost and detection delay

From `scripts/supplementary_experiments.py` (`reports/supplementary.json`). STL is offline only, because its centred decomposition needs readings after time t.

| Technique | Precision | Recall | F1 | ROC-AUC | Event recall | Scoring cost (µs/reading) |
|---|---|---|---|---|---|---|
| STL (robust, daily period) | 0.175 | 0.416 | 0.246 | 0.780 | 0.732 | ~400 (batch, offline) |
| Z-score / moving average | — | — | — | — | — | < 0.01 (they read precomputed features) |
| Isolation Forest / One-Class SVM / LSTM | — | — | — | — | — | 8.5 / 5.0 / 6.3 |

STL scores below the profile Z-score because the robust decomposition absorbs drift and leaks into its trend component. Figures for the results chapter are generated by `scripts/make_figures.py` and saved in `docs/figures/`.
