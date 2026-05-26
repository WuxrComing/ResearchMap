import pytest
from app.services.storage import get_engine, init_db


@pytest.fixture
def db_engine():
    engine = get_engine()
    init_db()
    yield engine
