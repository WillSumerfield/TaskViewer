import pytest

from taskviewer_app.state import State

from app_helpers import FakeClock


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def state(clock):
    return State(clock)
