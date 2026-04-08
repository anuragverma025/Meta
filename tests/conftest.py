import pytest

from server.environment import CodeReviewEnvironment
from server.reward import RewardComputer
from server.tasks import TASKS_BY_ID


@pytest.fixture
def env() -> CodeReviewEnvironment:
    return CodeReviewEnvironment()


@pytest.fixture
def reward_computer() -> RewardComputer:
    return RewardComputer()


@pytest.fixture
def hard_task():
    return TASKS_BY_ID["refund-idempotency"]
