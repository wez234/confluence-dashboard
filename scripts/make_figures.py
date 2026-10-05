"""Figures for the dissertation results chapter (all from measured outputs in artifacts/ and reports/)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve

R = Path("reports"); A = Path("artifacts"); OUT = Path("docs/figures"); OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 11, "axes.titleweight": "bold", "figure.dpi": 200, "savefig.bbox": "tight"})
M = json.load(open(R / "metrics.json")); S = json.load(open(R / "supplementary.json")); ROB = json.load(open(R / "robustness.json"))
NAMES = {"zscore": "Z-score", "moving_average": "Moving avg (24 h)", "stl": "STL (offline)", "isolation_forest": "Isolation Forest",
         "one_class_svm": "One-Class SVM", "lstm_autoencoder": "LSTM autoencoder", "ensemble": "Ensemble"}
ORDER = ["zscore", "moving_average", "stl", "isolation_forest", "one_class_svm", "lstm_autoencoder", "ensemble"]
COL = {"zscore": "#20808D", "moving_average": "#BCE2E7", "stl": "#848456", "isolation_forest": "#A84B2F",
       "one_class_svm": "#944454", "lstm_autoencoder": "#1B474D", "ensemble": "#FFC553"}
TICK = {k: v.replace(" (", "\n(").replace("One-Class SVM", "One-Class\nSVM").replace("LSTM autoencoder", "LSTM\nautoencoder").replace("Isolation Forest", "Isolation\nForest") for k, v in NAMES.items()}
UTIL_COL = {"electricity": "#DA7101", "gas": "#006494", "water": "#20808D"}


def overall(n):
    return S["stl"]["overall"] if n == "stl" else M["detection"]["overall"][n]


d = pd.read_parquet(A / "scored.parquet")
te = d[d.split == "test"].copy()
stl = pd.read_parquet(R / "stl_test_scores.parquet")
te = te.merge(stl[["ts", "meter_id", "score_stl", "flag_stl"]], on=["ts", "meter_id"], how="left")

# Fig 2 — one meter per utility, 5 test days, anomalies shaded
fig, axes = plt.subplots(3, 1, figsize=(9, 6.2), sharex=True)
start = te.ts.min() + pd.Timedelta(days=2); end = start + pd.Timedelta(days=5)
for ax, (u, mid) in zip(axes, [("electricity", None), ("gas", None), ("water", None)]):
    g = te[(te.utility == u)]
    # choose the meter with most labelled anomalies in the window
    w = g[(g.ts >= start) & (g.ts < end)]
    mid = w.groupby("meter_id").is_anomaly.sum().idxmax()
    w = w[w.meter_id == mid].sort_values("ts")
    ax.plot(w.ts, w.value, color=UTIL_COL[u], lw=1, label="reading")
    ax.plot(w.ts, w.expected, color="#7A7974", lw=0.8, ls="--", label="expected (training profile)")
    an = w.is_anomaly.astype(bool).values
    ax.fill_between(w.ts, 0, 1, where=an, transform=ax.get_xaxis_transform(), color="#A13544", alpha=0.15, lw=0, label="injected anomaly")
    fl = w.flag_ensemble.astype(bool)
    ax.scatter(w.ts[fl], w.value[fl], s=8, color="#A13544", zorder=3, label="ensemble flag")
    unit = {"electricity": "kWh / 15 min", "gas": "m³ / h", "water": "L/min"}[u]
    ax.set_ylabel(unit); ax.set_title(f"{u.capitalize()} meter {mid}", loc="left", fontsize=10)
axes[0].legend(ncol=4, fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(0, 1.35))
fig.savefig(OUT / "fig2_sample_series.png"); plt.close(fig)

# Fig 4 — F1 and ROC-AUC per technique
fig, ax = plt.subplots(figsize=(9, 3.8))
x = np.arange(len(ORDER)); wdt = 0.38
f1 = [overall(n)["f1"] for n in ORDER]; auc = [overall(n)["roc_auc"] for n in ORDER]
b1 = ax.bar(x - wdt / 2, f1, wdt, color="#20808D", label="F1 (calibrated threshold)")
b2 = ax.bar(x + wdt / 2, auc, wdt, color="#A84B2F", label="ROC-AUC (threshold-free)")
for b, v in list(zip(b1, f1)) + list(zip(b2, auc)):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.2f}", ha="center", fontsize=8)
ax.set_xticks(x, [TICK[n] for n in ORDER], fontsize=9); ax.set_ylim(0, 1.18); ax.set_yticks(np.arange(0, 1.01, 0.2)); ax.set_ylabel("score (test period)")
ax.legend(frameon=False, ncol=2, loc="upper left")
fig.savefig(OUT / "fig4_f1_auc.png"); plt.close(fig)

# Fig 5 — recall by anomaly type heatmap
types = ["spike", "drop", "drift", "leak", "stuck"]
mat = []
for n in ORDER:
    r = S["stl"]["recall_by_type"] if n == "stl" else M["detection"]["per_type_recall"][n]
    mat.append([r[t] for t in types])
mat = np.array(mat)
fig, ax = plt.subplots(figsize=(6.4, 3.9))
im = ax.imshow(mat, cmap="BuGn", vmin=0, vmax=1, aspect="auto")
ax.set_xticks(range(len(types)), [t.capitalize() for t in types]); ax.set_yticks(range(len(ORDER)), [NAMES[n] for n in ORDER])
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=8.5, color="white" if mat[i, j] > 0.6 else "#28251D")
ax.spines[:].set_visible(False); fig.colorbar(im, ax=ax, fraction=0.04, label="recall")
fig.savefig(OUT / "fig5_recall_by_type.png"); plt.close(fig)

# Fig 6 — ROC curves
fig, ax = plt.subplots(figsize=(5.6, 4.6))
styles = {"zscore": "-", "moving_average": ":", "stl": "-.", "isolation_forest": "--", "one_class_svm": (0, (3, 1, 1, 1)),
          "lstm_autoencoder": "-", "ensemble": "-"}
for n in ORDER:
    s = te[f"score_{n}"].values.astype(float); y = te.is_anomaly.values.astype(int)
    ok = ~np.isnan(s) & te.score_ensemble.notna().values
    fpr, tpr, _ = roc_curve(y[ok], s[ok])
    ax.plot(fpr, tpr, ls=styles[n], color=COL[n] if n != "moving_average" else "#5591C7", lw=2.2 if n == "ensemble" else 1.3,
            label=f"{NAMES[n]} (AUC {overall(n)['roc_auc']:.3f})")
ax.plot([0, 1], [0, 1], color="#BAB9B4", lw=0.8)
ax.axvline(0.05, color="#7A7974", lw=0.6, ls="--"); ax.text(0.06, 0.03, "5% FPR", fontsize=8, color="#7A7974")
ax.set_xlabel("false-positive rate"); ax.set_ylabel("true-positive rate (recall)"); ax.legend(fontsize=7.5, frameon=False, loc="lower right")
fig.savefig(OUT / "fig6_roc.png"); plt.close(fig)

# Fig 7 — F1 by utility
utils = ["electricity", "gas", "water"]
fig, ax = plt.subplots(figsize=(9, 3.6))
x = np.arange(len(ORDER)); wdt = 0.26
for k, u in enumerate(utils):
    vals = [S["stl"]["by_utility_f1"][u] if n == "stl" else M["detection"]["per_utility"][n][u]["f1"] for n in ORDER]
    ax.bar(x + (k - 1) * wdt, vals, wdt, color=UTIL_COL[u], label=u.capitalize())
ax.set_xticks(x, [TICK[n] for n in ORDER], fontsize=9); ax.set_ylabel("F1 (test period)"); ax.set_ylim(0, 0.8)
ax.legend(frameon=False, ncol=3, loc="upper left")
fig.savefig(OUT / "fig7_f1_by_utility.png"); plt.close(fig)

# Fig 8 — end-to-end latency through Kafka
L = pd.read_csv(R / "stream_latency.csv").sort_values("produced_at").reset_index(drop=True)
L["e2e"] = L.committed_at - L.produced_at
L["run"] = (L.produced_at.diff() > 30).cumsum()
steady = L[L.run == 0]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.4))
a1.hist(steady.e2e, bins=40, color="#20808D")
a1.axvline(steady.e2e.mean(), color="#28251D", lw=1); a1.text(steady.e2e.mean() + 0.03, a1.get_ylim()[1] * 0.9, f"mean {steady.e2e.mean():.2f} s", fontsize=8)
a1.axvline(2.5, color="#A13544", lw=1, ls="--"); a1.text(2.45, a1.get_ylim()[1] * 0.9, "H2 target 2.5 s", fontsize=8, color="#A13544", ha="right")
a1.set_xlim(0, 2.7); a1.set_xlabel("producer → database commit (s)"); a1.set_ylabel("readings"); a1.set_title("Steady replay (n = 3,968)", loc="left", fontsize=10)
xs = np.sort(steady.e2e.values); a2.plot(xs, np.arange(1, len(xs) + 1) / len(xs), color="#20808D", label="steady replay")
xs2 = np.sort(L[L.run == 1].e2e.values); a2.plot(xs2, np.arange(1, len(xs2) + 1) / len(xs2), color="#A84B2F", ls="--", label="stress (backlog)")
a2.axvline(2.5, color="#A13544", lw=1, ls="--"); a2.set_xscale("log"); a2.set_xlabel("latency (s, log scale)"); a2.set_ylabel("cumulative share")
a2.legend(frameon=False, fontsize=8, loc="upper left"); a2.set_title("Cumulative distribution", loc="left", fontsize=10)
fig.savefig(OUT / "fig8_latency.png"); plt.close(fig)

# Fig 9 — H1 temporal recall across seeds
seeds = ["42", "7", "123"]
runs = {"42": M, "7": json.load(open("reports/seeds/metrics_seed7.json")) if Path("reports/seeds/metrics_seed7.json").exists() else None,
        "123": json.load(open("reports/seeds/metrics_seed123.json")) if Path("reports/seeds/metrics_seed123.json").exists() else None}
dets = ["zscore", "moving_average", "isolation_forest", "lstm_autoencoder"]
fig, ax = plt.subplots(figsize=(8, 3.4))
x = np.arange(len(seeds)); wdt = 0.2
h1rows = {}
for k, n in enumerate(dets):
    vals = [runs[s]["detection"]["per_type_recall"][n]["temporal"] for s in seeds]
    h1rows[n] = vals
    bars = ax.bar(x + (k - 1.5) * wdt, vals, wdt, color=COL[n] if n != "moving_average" else "#5591C7", label=NAMES[n])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=7.5)
ax.set_xticks(x, [f"seed {s}" for s in seeds]); ax.set_ylabel("recall on drift, leak, stuck"); ax.set_ylim(0, 0.95)
ax.legend(frameon=False, ncol=4, fontsize=8, loc="upper left")
fig.savefig(OUT / "fig9_h1_seeds.png"); plt.close(fig)
json.dump(h1rows, open(R / "h1_seed_recalls.json", "w"), indent=1)

# Fig 10 — accuracy vs inference cost
fig, ax = plt.subplots(figsize=(6.4, 4))
for n in ["zscore", "moving_average", "isolation_forest", "one_class_svm", "lstm_autoencoder"]:
    c = S["inference_ms_per_1000"][n]["mean"] / 1000 * 1000  # µs per reading
    ax.scatter(c, overall(n)["f1"], s=60, color=COL[n] if n != "moving_average" else "#5591C7", zorder=3)
    ax.annotate(NAMES[n], (c, overall(n)["f1"]), textcoords="offset points", xytext=(6, 4), fontsize=8.5)
ax.set_xscale("log"); ax.set_xlabel("marginal scoring cost (µs per reading, log scale)"); ax.set_ylabel("F1 (test period)")
ax.set_ylim(0, 0.7)
fig.savefig(OUT / "fig10_cost_vs_f1.png"); plt.close(fig)
print("figures written:", sorted(p.name for p in OUT.iterdir()))
