# Model-selection log

All selection used the **validation** period (days 36–45) only.

## LSTM autoencoder configuration

Validation ROC-AUC and temporal recall at a 5% FPR, per utility (electricity / gas / water):

| Candidate | Inputs | Window | Bottleneck | AUC | Temporal recall @5% FPR |
|---|---|---|---|---|---|
| A | profile_z, level, min_level, hour sin/cos | 16 | 32 | 0.80 / 0.89 / 0.70 | 0.36 / 0.59 / 0.35 |
| B | ratio to expected, hour sin/cos | 32 | 16 | 0.88 / 0.93 / 0.73 | 0.63 / 0.53 / 0.40 |
| C | ratio to expected, hour sin/cos | 16 | 16 | 0.85 / 0.93 / 0.62 | 0.55 / 0.63 / 0.36 |
| **D (chosen)** | profile_z, level, min_level, hour sin/cos | 16 | **8** | **0.87 / 0.93 / 0.78** | 0.53 / 0.57 / 0.43 |
| E | ratio, level, hour sin/cos | 32 | 16 | 0.87 / 0.89 / 0.79 | 0.53 / 0.45 / 0.42 |

D was chosen for the best mean AUC. The main effect is the tighter bottleneck: a wide autoencoder reconstructs level shifts too well.

## Other design decisions made during development

| Change | Reason | Effect (validation/test) |
|---|---|---|
| Alert budget of at most 15% flagged readings in calibration | Moving-average F1 was maximised by flagging 99% of readings | Moving-average precision 0.03 → 0.07, recall 0.99 → 0.28 (an honest weak baseline) |
| 8-step → 24-hour moving-average window | A standard daily baseline; the 8-step version had AUC < 0.5 | AUC 0.43 → 0.56 |
| LIME: discretised, and read the correct regression label | A bug read label 0 (sign-flipped weights) | SHAP-LIME agreement 0.03 → 0.59 |
| Micro-batch stream processing | 1 record per call gave 10 readings/s | 180 readings/s |
| Alert debounce | 846 candidate events, 11% precision | 461 events, 18% precision, 88% coverage |
