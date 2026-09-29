# Evaluation report

Generated 2026-09-29T04:13:07.941632+00:00 · data source: **synthetic** · 10 meters per utility · 60 days · seed 42

> Detection metrics are computed on the held-out **test period** only. Thresholds were calibrated on the validation period. With synthetic data the anomalies are injected, so results show how the methods compare on these anomaly types — not how they would perform on a real utility network.

## Detection accuracy (point level, test period)

| Technique | Family | Precision | Recall | F1 | ROC-AUC | Recall@5%FPR | Event recall |
|---|---|---|---|---|---|---|---|
| Z-score | Statistical | 0.317 | 0.769 | 0.449 | 0.926 | 0.755 | 0.832 |
| Moving average | Statistical | 0.070 | 0.276 | 0.112 | 0.564 | 0.116 | 0.389 |
| Isolation Forest | Machine learning | 0.412 | 0.574 | 0.480 | 0.933 | 0.653 | 0.517 |
| One-Class SVM | Machine learning | 0.480 | 0.599 | 0.533 | 0.877 | 0.731 | 0.604 |
| LSTM autoencoder | Deep learning | 0.590 | 0.571 | 0.580 | 0.916 | 0.548 | 0.396 |
| Ensemble | Ensemble | 0.395 | 0.755 | 0.519 | 0.946 | 0.781 | 0.886 |

## F1 by utility

| Technique | Electricity | Gas | Water |
|---|---|---|---|
| Z-score | 0.530 | 0.539 | 0.293 |
| Moving average | 0.170 | 0.075 | 0.047 |
| Isolation Forest | 0.636 | 0.425 | 0.189 |
| One-Class SVM | 0.628 | 0.491 | 0.320 |
| LSTM autoencoder | 0.683 | 0.511 | 0.270 |
| Ensemble | 0.639 | 0.432 | 0.368 |

## Recall by anomaly type

| Technique | drift | drop | leak | spike | stuck | temporal* | temporal @5%FPR |
|---|---|---|---|---|---|---|---|
| Z-score | 0.843 | 0.784 | 0.679 | 1.000 | 0.544 | 0.755 | 0.724 |
| Moving average | 0.285 | 0.402 | 0.198 | 0.829 | 0.018 | 0.223 | 0.119 |
| Isolation Forest | 0.569 | 0.658 | 0.313 | 1.000 | 0.877 | 0.537 | 0.632 |
| One-Class SVM | 0.565 | 0.714 | 0.391 | 1.000 | 0.868 | 0.556 | 0.664 |
| LSTM autoencoder | 0.691 | 0.563 | 0.288 | 0.800 | 0.544 | 0.555 | 0.561 |
| Ensemble | 0.697 | 0.925 | 0.720 | 1.000 | 0.702 | 0.704 | 0.724 |

*temporal = drift, leak and stuck-meter anomalies (sustained patterns).

## Hypothesis H1 — LSTM autoencoder recall on temporal anomalies (target: ≥15% higher)

**Basis: calibrated thresholds** — LSTM recall 0.555 → **NOT SUPPORTED**

| Compared with | Recall | Relative improvement | Absolute (pp) |
|---|---|---|---|
| Z-score | 0.755 | -26.6% | -20.1 |
| Moving average | 0.223 | +148.4% | +33.1 |
| Isolation Forest | 0.537 | +3.3% | +1.8 |

**Basis: matched 5% false-positive rate** — LSTM recall 0.561 → **NOT SUPPORTED**

| Compared with | Recall | Relative improvement | Absolute (pp) |
|---|---|---|---|
| Z-score | 0.724 | -22.6% | -16.4 |
| Moving average | 0.119 | +372.0% | +44.2 |
| Isolation Forest | 0.632 | -11.3% | -7.1 |

## Hypothesis H2 — alert latency (target: mean < 2.5 s)

**SUPPORTED** — mean 608.3 ms, p95 779.8 ms, p99 825.2 ms, max 825.2 ms over 2833 readings.

Throughput 82 records/s (single consumer process, micro-batches of 50) · CPU 52% · RSS 823 MB.

_in-process processing latency (validate->clean->normalise->features->5 models+ensemble->SHAP); Kafka + TimescaleDB transit is measured by the docker pipeline (latency_ms column)._

## Explainability

- Alerts explained with TreeSHAP: 2056 (3.17 ms/alert)
- LIME on the tabular ensemble: 36 ms/alert (sample of 60)
- KernelSHAP on the tabular ensemble: 111 ms/alert
- Plausibility on true-positive alerts (top SHAP feature is one of the anomaly type's expected drivers): top-1 78.6% (chance ≈ 24%), top-3 98.0%
- Top-3 agreement, KernelSHAP vs LIME on the same ensemble (Jaccard): 0.59
- Top-3 agreement, TreeSHAP (Isolation Forest) vs LIME (ensemble) (Jaccard): 0.49

H3 (operator trust) can only be tested with participants — see `docs/USER_STUDY.md` and `python -m confluence.evaluation.user_study`.

## Ingestion

```json
{
  "raw_records": 121817,
  "validation": {
    "ok": 121345,
    "missing_value": 472
  },
  "cleaning": {
    "input": 121817,
    "duplicates_removed": 488,
    "negatives_nulled": 100,
    "missing_values": 569
  },
  "normalised_rows": 129599,
  "rows_per_utility": {
    "electricity": 57600,
    "gas": 14400,
    "water": 57599
  },
  "interpolated_values": 15298
}
```
