import httpx
import pytest

from codereview_env.client import CodeReviewEnv
from server.app import app


@pytest.fixture
def patched_httpx(monkeypatch):
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.ASGITransport(app=app)
        kwargs["base_url"] = "http://testserver"
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_client_reset_and_state(patched_httpx):
    client = CodeReviewEnv(base_url="http://testserver")
    observation = await client.reset(task_id="pagination-regression")
    state = await client.state()
    assert observation.task_id == "pagination-regression"
    assert state.task_id == "pagination-regression"


@pytest.mark.asyncio
async def test_client_step(patched_httpx):
    client = CodeReviewEnv(base_url="http://testserver")
    observation = await client.reset(task_id="pagination-regression")
    assert len(observation.opened_artifacts) >= 1
