"""User study mode (RQ3 / H3): XAI vs black-box alerts, SUS, TAM and trust.

Between-subjects design. Each participant is randomly assigned to the XAI
condition (alerts with SHAP/LIME explanations and narrative) or the black-box
condition (same alerts, score only), reviews the same 8 alerts, then completes
trust, SUS and TAM questionnaires. Only a random participant code is stored.
"""
from __future__ import annotations

import csv
import hashlib
import secrets
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import (SEVCOLOR, UCOLOR, banner, db_source, explanation_bars, fmt_ts, header, load_alerts, load_scored,
                  settings, style, tag)

STUDY_DIR = settings.reports_dir / "study"
N_TASKS = 8
TRUST = [  # adapted from Jian, Bisantz & Drury (2000), 7-point
    "I can trust the alerts this system raises.",
    "I understand why the system raised each alert.",
    "I am confident in the decisions I made with this system.",
    "The system's reasoning is transparent to me.",
    "I would rely on this system in day-to-day network operations.",
    "The system behaves in a predictable, dependable way.",
]
SUS = [  # Brooke (1996), 5-point
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to be able to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
]
TAM_PU = ["Using the system would improve my performance in monitoring utility networks.",
          "Using the system would make it easier to spot problems early.",
          "The system would be useful in my job.",
          "Using the system would increase my productivity."]
TAM_PEOU = ["Learning to operate the system would be easy for me.",
            "My interaction with the system is clear and understandable.",
            "It would be easy for me to become skilful at using the system.",
            "I find the system easy to use."]


@st.cache_data(show_spinner=False)
def task_set(seed: int = 7) -> pd.DataFrame:
    """Fixed, balanced set: 5 genuine anomalies of different types + 3 false alarms."""
    al = load_alerts()
    rng = np.random.default_rng(seed)
    picks = []
    for t in ["spike", "leak", "stuck", "drift", "drop"]:
        c = al[(al.truth) & (al.anomaly_type == t)]
        if len(c):
            picks.append(c.iloc[rng.integers(len(c))])
    fp = al[~al.truth]
    for i in rng.choice(len(fp), size=min(N_TASKS - len(picks), len(fp)), replace=False):
        picks.append(fp.iloc[i])
    out = pd.DataFrame(picks)
    return out.iloc[rng.permutation(len(out))].reset_index(drop=True)


def _save(rows: list[dict]):
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    p = STUDY_DIR / "responses.csv"
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["at", "participant", "condition", "kind", "item", "response", "correct", "seconds"])
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    db = db_source()
    if db is not None:
        try:
            with db.connect() as c, c.cursor() as cur:
                for r in rows:
                    cur.execute("INSERT INTO study_responses (participant, condition, kind, item, response, correct, seconds) "
                                "VALUES (%s,%s,%s,%s,%s,%s,%s)", (r["participant"], r["condition"], r["kind"], r["item"],
                                                                   str(r.get("response", "")), r.get("correct"), r.get("seconds")))
        except Exception:
            pass


def _row(kind, item, response, correct=None, seconds=None):
    s = st.session_state.study
    return {"at": pd.Timestamp.now("UTC").isoformat(), "participant": s["pid"], "condition": s["condition"],
            "kind": kind, "item": item, "response": response, "correct": correct, "seconds": seconds}


def _likert(q: str, n: int, key: str, lo: str, hi: str):
    return st.radio(q, list(range(1, n + 1)), index=None, horizontal=True, key=key,
                    captions=[lo] + [""] * (n - 2) + [hi])


def render():
    header("User study", "Evaluates whether explanations change operator trust and decisions (RQ3, H3).")
    ss = st.session_state
    s = ss.setdefault("study", {"stage": "consent"})
    forced = st.query_params.get("condition")

    if s["stage"] == "consent":
        banner("<b>Participant information.</b> This 15-minute study is part of an MSc dissertation on explainable anomaly "
               "detection for utility networks. You will review 8 alerts from simulated meter data and answer short "
               "questionnaires. Participation is voluntary; you can stop at any time without giving a reason. No name, "
               "email or other personal data is collected: responses are stored against a random code only. The data are "
               "used solely for the dissertation and deleted after marking.")
        c1 = st.checkbox("I have read the information above and I am 18 or over.")
        c2 = st.checkbox("I agree to take part and for my anonymous responses to be used in the dissertation.")
        role = st.selectbox("Which best describes your background?", ["Utility / network operations", "Energy or water sector (other)",
                            "Data / software", "Student", "Other"], index=None)
        if st.button("Start", type="primary", disabled=not (c1 and c2 and role)):
            pid = "P-" + secrets.token_hex(3).upper()
            cond = forced if forced in ("xai", "blackbox") else ("xai" if int(hashlib.sha256(pid.encode()).hexdigest(), 16) % 2 else "blackbox")
            s.update(stage="task", pid=pid, condition=cond, i=0, t0=time.time(), role=role)
            _save([_row("consent", "consent", "yes"), _row("demographic", "background", role)])
            st.rerun()
        return

    tasks = task_set()
    if s["stage"] == "task":
        i = s["i"]
        a = tasks.iloc[i]
        st.progress((i) / len(tasks), text=f"Alert {i + 1} of {len(tasks)}")
        with st.container(border=True):
            st.markdown(f"{tag(a.severity.upper(), SEVCOLOR[a.severity])} <b>{a.utility.title()} meter {a.meter_id}</b> · "
                        f"{fmt_ts(a.start)} · anomaly score {a.peak_score:.3f}", unsafe_allow_html=True)
            df = load_scored()
            g = df[(df.meter_id == a.meter_id) & (df.ts >= a.start - pd.Timedelta(hours=30)) & (df.ts <= a.end + pd.Timedelta(hours=6))]
            fig = go.Figure()
            fig.add_scatter(x=g.ts, y=g.value, name=f"reading ({a.unit})", line=dict(color=UCOLOR[a.utility], width=1.6))
            fig.add_vrect(x0=a.start, x1=a.end + pd.Timedelta("15min"), fillcolor="rgba(179,38,30,0.08)", line_width=0)
            if s["condition"] == "xai":
                fig.add_scatter(x=g.ts, y=g.expected, name="expected", line=dict(color="#B9B4A7", dash="dot", width=1))
            st.plotly_chart(style(fig, 260), width="stretch", key=f"st-{i}")
            if s["condition"] == "xai":
                st.markdown(f"**Why:** {a.narrative}")
                st.plotly_chart(explanation_bars(a.shap, "Top contributing factors (SHAP)", k=5), width="stretch", key=f"sx-{i}")
            else:
                st.markdown(f"**The system flagged this reading as anomalous (score {a.peak_score:.3f}).**")
        choice = st.radio("What would you do with this alert?", ["Investigate — likely a genuine problem",
                          "Dismiss — likely a false alarm"], index=None, key=f"c-{i}")
        conf = _likert("How confident are you in this decision?", 5, f"cf-{i}", "not at all", "very")
        if st.button("Next", type="primary", disabled=choice is None or conf is None):
            sec = time.time() - s["t0"]
            investigate = choice.startswith("Investigate")
            _save([_row("task", f"alert:{a.alert_id}", "investigate" if investigate else "dismiss",
                        correct=bool(investigate == bool(a.truth)), seconds=round(sec, 2)),
                   _row("task_confidence", f"alert:{a.alert_id}", conf)])
            s["i"] += 1
            s["t0"] = time.time()
            if s["i"] >= len(tasks):
                s["stage"] = "questionnaire"
            st.rerun()
        return

    if s["stage"] == "questionnaire":
        st.markdown("Please rate each statement about the system you just used.")
        ans = {}
        with st.form("q"):
            st.subheader("Trust (1 = strongly disagree, 7 = strongly agree)")
            for j, q in enumerate(TRUST):
                ans[f"trust_{j + 1}"] = _likert(q, 7, f"t{j}", "strongly disagree", "strongly agree")
            st.subheader("System Usability Scale (1 = strongly disagree, 5 = strongly agree)")
            for j, q in enumerate(SUS):
                ans[f"sus_{j + 1}"] = _likert(q, 5, f"s{j}", "strongly disagree", "strongly agree")
            st.subheader("Technology acceptance (1 = strongly disagree, 7 = strongly agree)")
            for j, q in enumerate(TAM_PU):
                ans[f"pu_{j + 1}"] = _likert(q, 7, f"pu{j}", "strongly disagree", "strongly agree")
            for j, q in enumerate(TAM_PEOU):
                ans[f"peou_{j + 1}"] = _likert(q, 7, f"pe{j}", "strongly disagree", "strongly agree")
            comment = st.text_area("Any comments? (optional — please do not include personal information)")
            done = st.form_submit_button("Submit", type="primary")
        if done:
            if any(v is None for v in ans.values()):
                st.warning("Please answer every item.")
            else:
                rows = [_row(k.split("_")[0] if not k.startswith(("pu", "peou")) else "tam", k, v) for k, v in ans.items()]
                if comment.strip():
                    rows.append(_row("comment", "comment", comment.strip()[:1000]))
                _save(rows)
                s["stage"] = "done"
                s["answers"] = ans
                st.rerun()
        return

    if s["stage"] == "done":
        st.success(f"Thank you. Your responses were saved under the code {s['pid']}. Quote this code if you want your "
                   "data withdrawn.")
        from confluence.evaluation.user_study import sus_score
        st.metric("Your SUS score", f"{sus_score([s['answers'][f'sus_{i}'] for i in range(1, 11)]):.1f} / 100")
        if st.button("Start a new participant session"):
            ss.study = {"stage": "consent"}
            st.rerun()
    with st.expander("Researcher tools"):
        p = STUDY_DIR / "responses.csv"
        if p.exists():
            st.download_button("Download all responses (CSV)", p.read_bytes(), "responses.csv", "text/csv")
            st.caption("Hosted demo storage is not permanent — download regularly, or run with a database (DATABASE_URL).")
        st.caption("Force a condition with ?condition=xai or ?condition=blackbox in the URL.")
