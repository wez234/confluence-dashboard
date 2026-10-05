import numpy as np
import pandas as pd
import pytest

from confluence.alerts.rules import group_events, needs_escalation, severity, site_of
from confluence.detection.base import calibrate_threshold
from confluence.detection.engine import BASE_DETECTORS, DetectionEngine
from confluence.explain.narrative import narrative, top
from confluence.ingestion.features import FEATURES


@pytest.fixture(scope="module")
def engine(feats):
    f, p, cut = feats
    tr = f[f.ts < cut]
    va = f[(f.ts >= cut) & (f.ts < cut + pd.Timedelta(days=1.5))]
    return DetectionEngine(profile=p, seed=0).fit(tr, va), f[f.ts >= cut + pd.Timedelta(days=1.5)]


def test_threshold_respects_alert_budget():
    rng = np.random.default_rng(0)
    s = rng.normal(size=5000)
    y = rng.random(5000) < 0.03
    thr = calibrate_threshold(s, y, "f1", max_alert_rate=0.1)
    assert (s >= thr).mean() <= 0.1 + 1e-9


def test_engine_scores_every_detector(engine):
    eng, test = engine
    out = eng.score_frame(test)
    for d in BASE_DETECTORS + ["ensemble"]:
        assert f"score_{d}" in out and f"flag_{d}" in out
    assert out.score_ensemble.dropna().between(0, 1).all()
    assert out.votes.between(0, len(BASE_DETECTORS)).all()


def test_threshold_override_is_applied(engine):
    eng, test = engine
    before = eng.score_frame(test).flag_ensemble.sum()
    old = eng.thresholds()["gas"]["ensemble"]
    eng.set_threshold("gas", "ensemble", 1.01)
    after = eng.score_frame(test)
    assert not after[after.utility == "gas"].flag_ensemble.any()
    eng.set_threshold("gas", "ensemble", old)
    assert eng.score_frame(test).flag_ensemble.sum() == before


def test_explainer_shap_and_lime(engine, feats):
    from confluence.explain.xai import Explainer
    eng, test = engine
    f, _, cut = feats
    ex = Explainer(eng, f[f.ts < cut])
    x = test[test.scorable][FEATURES].iloc[:3].fillna(0).values
    sv = ex.shap_values("electricity", x)
    assert sv.shape == (3, len(FEATURES))
    lv = ex.lime_values("electricity", x[0], num_samples=200)
    assert lv.shape == (len(FEATURES),) and np.abs(lv).sum() > 0


def test_stream_processor_matches_record_path(engine, raw, feats):
    from confluence.ingestion.stream_processor import StreamProcessor
    eng, _ = engine
    from confluence.explain.xai import Explainer
    f, _, cut = feats
    sp = StreamProcessor(eng, explainer=Explainer(eng, f[f.ts < cut]))
    recs = raw.assign(_t=pd.to_datetime(raw.ts, utc=True, format="ISO8601")).sort_values("_t").drop(columns="_t")
    recs = recs.head(3000).to_dict("records")
    for r in recs:
        r["value"] = None if r["value"] != r["value"] else r["value"]
    out = []
    for i in range(0, len(recs), 100):
        out += sp.process_batch(recs[i:i + 100])
    assert len(out) > 1000
    assert all(o.processing_latency_s >= 0 for o in out)
    assert sp.stats["cleaning:duplicate"] > 0
    alerts = [o for o in out if o.is_alert]
    assert alerts and all(o.shap_top and o.narrative.startswith(o.utility.title()) for o in alerts)


def test_alert_rules():
    assert site_of("W007") == "SITE-007"
    assert severity(0.999, 1, 1) == "critical"
    assert severity(0.9, 2, 1) == "warning"
    assert severity(0.9, 1, 1) == "info"
    t = pd.Timestamp("2026-01-01", tz="UTC")
    assert needs_escalation(t, False, t + pd.Timedelta(minutes=31))
    assert not needs_escalation(t, True, t + pd.Timedelta(hours=5))
    ts = pd.date_range(t, periods=6, freq="15min")
    df = pd.DataFrame({"ts": ts, "utility": "gas", "meter_id": "G001", "value": 1.0, "votes": [0, 3, 3, 0, 0, 1],
                       "score_ensemble": [.1, .99, .98, .1, .1, .9], "flag_ensemble": [0, 1, 1, 0, 0, 1],
                       "is_anomaly": [0, 1, 1, 0, 0, 0], "anomaly_type": ["", "spike", "spike", "", "", ""]})
    ev = group_events(df)
    assert len(ev) == 2 and ev.raised.tolist() == [True, False]


def test_narrative_is_direction_aware():
    v = np.zeros(len(FEATURES)); v[FEATURES.index("profile_z")] = 1
    low = narrative("gas", "G001", 0.0, "m3", top(v), {"profile_z": -5})
    high = narrative("gas", "G001", 9.0, "m3", top(v), {"profile_z": 5})
    assert "below" in low and "above" in high
