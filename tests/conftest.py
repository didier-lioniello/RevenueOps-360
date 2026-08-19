import json
from pathlib import Path

import pytest

from revenueops.models import RevenueDataset

DATA_PATH = Path(__file__).parents[1] / "data" / "synthetic_revenue.json"


@pytest.fixture
def payload():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def dataset(payload):
    return RevenueDataset.from_dict(payload)
