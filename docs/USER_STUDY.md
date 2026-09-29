# User study protocol (RQ3, H3, SUS, TAM)

**Design:** between-subjects A/B test. Each participant is randomly assigned by a hash of their random code to one of two conditions:
- **XAI:** the alert shows the expected-value line, a plain-language narrative and the top SHAP factors.
- **Black box:** the same alert and chart, with the anomaly score only.

**Procedure (about 15 min),** on the dashboard's User study page:
1. Participant information and consent (two checkboxes), plus a background question. No name or email is collected.
2. Eight alerts, the same for every participant and in fixed random order: 5 genuine anomalies (one each of spike, leak, stuck, drift and drop) and 3 false alarms. For each alert the participant chooses investigate or dismiss and rates their confidence (1–5). Decision time is recorded.
3. Questionnaires: trust (6 items, 7-point, adapted from Jian et al., 2000), SUS (10 items, Brooke, 1996), and TAM perceived usefulness and ease of use (4 + 4 items, 7-point, Davis, 1989).

**Data:** `reports/study/responses.csv`, plus the `study_responses` table when a database is configured. Each record holds a random participant code, the condition, the item, the response, correctness and time. Participants can withdraw by quoting their code.

**Analysis:** `python -m confluence.evaluation.user_study`
- SUS is scored with the standard method: odd items r − 1, even items 5 − r, total × 2.5. The target is a mean above 70.
- Trust, PU and PEOU are item means. Decision accuracy compares the choice with ground truth.
- Conditions are compared with a Mann-Whitney U test and effect size r.
- **H3:** (trust_XAI − trust_blackbox) / trust_blackbox ≥ 0.20, reported together with p.

**Sample size:** with small samples, report effect sizes and treat the results as indicative. About 15 participants per condition gives roughly 80% power only for large effects (r ≈ 0.5).

**Before running:** get approval from the University of Wolverhampton ethics process, and download responses regularly if you use the hosted demo, because Streamlit Community Cloud storage is not persistent.

**Forcing a condition** (e.g. for piloting): add `?condition=xai` or `?condition=blackbox` to the study URL.
