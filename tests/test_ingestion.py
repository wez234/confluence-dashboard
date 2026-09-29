import numpy as np
import pandas as pd

from confluence.config import UTILITIES
from confluence.ingestion.features import FEATURES
from confluence.ingestion.normalise import hourly_common_axis, to_utc
from confluence.ingestion.validation import validate_record


def test_generator_has_all_utilities_and_labels(raw):
    assert set(raw.utility) == set(UTILITIES)
    assert raw.is_anomaly.any() and (raw.anomaly_type[raw.is_anomaly] != "").all()


def test_validation_rejects_bad_records():
    ok, _ = validate_record({"ts": "2026-01-05T00:00:00+00:00", "meter_id": "E001", "utility": "electricity", "value": 0.3})
    assert ok
    assert not validate_record({"ts": "not-a-date", "meter_id": "E001", "utility": "electricity", "value": 1})[0]
    assert not validate_record({"ts": "2026-01-05T00:00:00+00:00", "meter_id": "E001", "utility": "steam", "value": 1})[0]
    # a missing value is kept (repairable by cleaning) but tagged
    assert validate_record({"ts": "2026-01-05T00:00:00+00:00", "meter_id": "E001", "utility": "gas", "value": None}) == (True, "missing_value")
    assert not validate_record({"ts": "2026-01-05T00:00:00+00:00", "meter_id": "E001", "utility": "gas", "value": "abc"})[0]


def test_timestamps_normalised_to_utc_grid(norm):
    assert str(norm.ts.dt.tz) == "UTC"
    for u, spec in UTILITIES.items():
        ts = norm[norm.utility == u].ts
        assert (ts == ts.dt.floor(spec.freq)).all(), u
    assert not norm.duplicated(["meter_id", "ts"]).any()


def test_to_utc_handles_london_dst():
    # UK clocks go forward at 01:00 UTC on 29 Mar 2026: 00:30 GMT and 02:30 BST are one hour apart
    df = pd.DataFrame({"ts": ["2026-03-29T00:30:00+00:00", "2026-03-29T02:30:00+01:00"]})
    out = to_utc(df).ts
    assert out.diff().iloc[1] == pd.Timedelta(hours=1)


def test_hourly_common_axis(norm):
    h = hourly_common_axis(norm)
    assert (h.ts == h.ts.dt.floor("1h")).all()
    assert set(h.utility) == set(UTILITIES)


def test_features_are_causal(norm, feats):
    f, p, cut = feats
    from confluence.ingestion.features import compute_features
    head = norm[norm.ts < norm.ts.min() + pd.Timedelta(days=3)]
    f_short = compute_features(head, p).set_index(["meter_id", "ts"])[FEATURES]
    f_full = f.set_index(["meter_id", "ts"])[FEATURES].loc[f_short.index]
    common = [c for c in FEATURES if c != "cross_meter_z"]
    np.testing.assert_allclose(f_short[common].values, f_full[common].values, rtol=1e-6, atol=1e-8, equal_nan=True)


def test_features_present(feats):
    f, _, _ = feats
    assert set(FEATURES) <= set(f.columns)
    assert f[f.scorable][FEATURES].notna().all().all()


def test_uk_lcl_adapter(tmp_path):
    from confluence.data.uk_lcl import load_lcl
    rows = ["LCLid,stdorToU,DateTime,KWH/hh (per half hour) "]
    t = pd.date_range("2013-06-01", periods=96, freq="30min")
    for i, x in enumerate(t):
        rows.append(f"MAC000002,Std,{x:%Y-%m-%d %H:%M:%S}.0000000,{0.2 + 0.01 * (i % 5):.3f}")
    p = tmp_path / "lcl.csv"
    p.write_text("\n".join(rows))
    out = load_lcl(str(p), meters=1, days=5)
    assert len(out) == 192 and set(out.meter_id) == {"E000"}
    ts = pd.to_datetime(out.ts, utc=True, format="ISO8601")
    assert ts.diff().dropna().eq(pd.Timedelta(minutes=15)).all()
    assert abs(out.value.sum() - sum(0.2 + 0.01 * (i % 5) for i in range(96))) < 1e-6
