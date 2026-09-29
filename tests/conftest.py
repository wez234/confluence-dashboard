import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from confluence.data.generator import GeneratorConfig, generate  # noqa: E402
from confluence.ingestion.cleaning import clean  # noqa: E402
from confluence.ingestion.features import Profile, compute_features  # noqa: E402
from confluence.ingestion.normalise import normalise  # noqa: E402
from confluence.ingestion.validation import validate  # noqa: E402


@pytest.fixture(scope="session")
def raw():
    return generate(GeneratorConfig(days=8, meters_per_utility=3, seed=1))


@pytest.fixture(scope="session")
def norm(raw):
    v, _ = validate(raw)
    c, _ = clean(v)
    return normalise(c)


@pytest.fixture(scope="session")
def feats(norm):
    cut = norm.ts.min() + pd.Timedelta(days=5)
    p = Profile().fit(norm[norm.ts < cut])
    return compute_features(norm, p), p, cut
