import pytest
from app.seed import reset

@pytest.fixture(autouse=True)
def isolated_synthetic_database():
    reset()
    yield
    reset()
