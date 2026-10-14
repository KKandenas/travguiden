import json
from pathlib import Path

import pytest

from pipeline import db

FIXTURES = Path(__file__).parent / "fixtures"


def las_fixture(namn):
    return json.loads((FIXTURES / namn).read_text(encoding="utf-8"))


@pytest.fixture
def conn():
    c = db.anslut(":memory:")
    db.migrera(c)
    yield c
    c.close()
