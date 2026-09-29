"""Analyse user-study responses (RQ3 / H3).

    python -m confluence.evaluation.user_study [--responses reports/study/responses.csv]

Computes per participant: SUS (0-100), TAM perceived usefulness / ease of use
(1-7), trust (1-7), decision accuracy and time per alert; compares the XAI and
black-box conditions (Mann-Whitney U, effect size r) and tests H3: trust in the
XAI condition >= 20% higher than in the black-box condition.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from confluence.config import settings


def sus_score(items: list[int]) -> float:
    """Standard SUS scoring (Brooke 1996): odd items r-1, even items 5-r, sum x 2.5."""
    if len(items) != 10:
        raise ValueError("SUS needs 10 items")
    return 2.5 * sum((r - 1) if i % 2 == 0 else (5 - r) for i, r in enumerate(map(int, items)))


def per_participant(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid, g in df.groupby("participant"):
        get = lambda prefix: pd.to_numeric(g[g.item.str.match(rf"^{prefix}_\d+$")].sort_values("item", key=lambda s: s.str.split("_").str[1].astype(int)).response, errors="coerce")
        sus = get("sus")
        tasks = g[g.kind == "task"]
        conf = pd.to_numeric(g[g.kind == "task_confidence"].response, errors="coerce")
        if len(sus) != 10:
            continue   # incomplete
        rows.append({"participant": pid, "condition": g.condition.iloc[0], "sus": sus_score(sus.tolist()),
                     "trust": get("trust").mean(), "tam_pu": get("pu").mean(), "tam_peou": get("peou").mean(),
                     "accuracy": tasks.correct.astype(str).str.lower().eq("true").mean() if len(tasks) else np.nan,
                     "seconds_per_alert": pd.to_numeric(tasks.seconds, errors="coerce").mean(),
                     "confidence": conf.mean()})
    return pd.DataFrame(rows)


def compare(pp: pd.DataFrame) -> dict:
    out = {"n": {c: int((pp.condition == c).sum()) for c in ("xai", "blackbox")}, "measures": {}}
    for m in ("trust", "sus", "tam_pu", "tam_peou", "accuracy", "seconds_per_alert", "confidence"):
        a, b = pp[pp.condition == "xai"][m].dropna(), pp[pp.condition == "blackbox"][m].dropna()
        res = {"xai_mean": float(a.mean()) if len(a) else None, "blackbox_mean": float(b.mean()) if len(b) else None,
               "xai_sd": float(a.std()) if len(a) > 1 else None, "blackbox_sd": float(b.std()) if len(b) > 1 else None}
        if len(a) >= 2 and len(b) >= 2:
            u, p = mannwhitneyu(a, b, alternative="two-sided")
            n1, n2 = len(a), len(b)
            z = (u - n1 * n2 / 2) / np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
            res.update(U=float(u), p=float(p), effect_r=float(abs(z) / np.sqrt(n1 + n2)))
        out["measures"][m] = res
    t = out["measures"]["trust"]
    if t["xai_mean"] and t["blackbox_mean"]:
        imp = (t["xai_mean"] - t["blackbox_mean"]) / t["blackbox_mean"]
        out["H3"] = {"relative_trust_improvement": imp, "target": 0.20, "meets_target": bool(imp >= 0.20),
                     "significant_p05": bool(t.get("p", 1) < 0.05)}
    out["sus_overall_mean"] = float(pp.sus.mean()) if len(pp) else None
    out["sus_target_met"] = bool(pp.sus.mean() > 70) if len(pp) else None
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--responses", default=str(settings.reports_dir / "study" / "responses.csv"))
    ap.add_argument("--out", default=str(settings.reports_dir / "user_study_results.json"))
    a = ap.parse_args(argv)
    df = pd.read_csv(a.responses)
    pp = per_participant(df)
    res = compare(pp)
    res["participants"] = pp.round(3).to_dict("records")
    with open(a.out, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "participants"}, indent=2, default=str))
    return res


if __name__ == "__main__":
    main()
