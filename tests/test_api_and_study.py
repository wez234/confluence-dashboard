import numpy as np
import pandas as pd

from confluence.evaluation.user_study import compare, per_participant, sus_score


def test_sus_scoring_reference_values():
    assert sus_score([5, 1] * 5) == 100
    assert sus_score([1, 5] * 5) == 0
    assert sus_score([3] * 10) == 50


def test_study_analysis_on_fabricated_fixture():
    """Fixture data only — checks the arithmetic, not a real result."""
    rows = []
    for i, (cond, trust) in enumerate([("xai", 6), ("xai", 5), ("blackbox", 4), ("blackbox", 4)]):
        pid = f"P{i}"
        rows += [{"participant": pid, "condition": cond, "kind": "trust", "item": f"trust_{k}", "response": trust} for k in range(1, 7)]
        rows += [{"participant": pid, "condition": cond, "kind": "sus", "item": f"sus_{k}", "response": 4 if k % 2 else 2} for k in range(1, 11)]
        rows += [{"participant": pid, "condition": cond, "kind": "tam", "item": f"pu_{k}", "response": 5} for k in range(1, 5)]
        rows += [{"participant": pid, "condition": cond, "kind": "tam", "item": f"peou_{k}", "response": 6} for k in range(1, 5)]
        rows += [{"participant": pid, "condition": cond, "kind": "task", "item": f"alert:{k}", "response": "investigate",
                  "correct": k % 2 == 0, "seconds": 10} for k in range(8)]
    pp = per_participant(pd.DataFrame(rows))
    assert len(pp) == 4 and np.allclose(pp.sus, 75)
    res = compare(pp)
    assert abs(res["H3"]["relative_trust_improvement"] - (5.5 - 4) / 4) < 1e-9


def test_api_health_and_readings_demo(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "demo")
    import importlib
    import confluence.config as cfg
    importlib.reload(cfg)
    from pathlib import Path
    if not (cfg.settings.artifacts_dir / "scored.parquet").exists():
        import pytest
        pytest.skip("artifacts not built")
    import confluence.datasource as ds
    importlib.reload(ds)
    import confluence.api.main as api
    importlib.reload(api)
    from fastapi.testclient import TestClient
    c = TestClient(api.app)
    assert c.get("/health").json()["source"] == "demo"
    r = c.get("/readings", params={"utility": "gas", "limit": 10}).json()
    assert len(r) == 10 and all(x["utility"] == "gas" for x in r)
    assert c.post("/alerts/1/ack", json={"actor": "t", "action": "acknowledged"}).status_code in (401, 409)
