from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from codereview_env.models import CodeReviewAction, CodeReviewObservation, CodeReviewState


class SyncCodeReviewEnv:
    def __init__(self, async_client: "CodeReviewEnv"):
        self._async_client = async_client

    def reset(self, **kwargs: Any) -> CodeReviewObservation:
        return asyncio.run(self._async_client.reset(**kwargs))

    def step(self, action: CodeReviewAction) -> CodeReviewObservation:
        return asyncio.run(self._async_client.step(action))

    def state(self) -> CodeReviewState:
        return asyncio.run(self._async_client.state())

    def __enter__(self) -> "SyncCodeReviewEnv":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class CodeReviewEnv:
    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url.rstrip("/")
        self._last_observation: Optional[CodeReviewObservation] = None

    async def reset(self, **kwargs: Any) -> CodeReviewObservation:
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            response = await client.post("/reset", json=kwargs or {})
            response.raise_for_status()
            payload = response.json()
            observation = CodeReviewObservation.model_validate(payload.get("observation", payload))
            if "reward" in payload:
                observation.reward = payload["reward"]
            if "done" in payload:
                observation.done = payload["done"]
            self._last_observation = observation
            return observation

    async def step(self, action: CodeReviewAction) -> CodeReviewObservation:
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            response = await client.post("/step", json={"action": action.model_dump()})
            response.raise_for_status()
            payload = response.json()
            observation = CodeReviewObservation.model_validate(payload.get("observation", payload))
            if "reward" in payload:
                observation.reward = payload["reward"]
            if "done" in payload:
                observation.done = payload["done"]
            self._last_observation = observation
            return observation

    async def state(self) -> CodeReviewState:
        if self._last_observation is None:
            return CodeReviewState()
        return CodeReviewState(
            episode_id=self._last_observation.task_id,
            step_count=int(self._last_observation.metadata.get("step_count", 0)),
            task_id=self._last_observation.task_id,
            difficulty=self._last_observation.difficulty,
            title=self._last_observation.title,
            opened_artifact_ids=list(self._last_observation.metadata.get("opened_artifact_ids", [])),
            cumulative_reward=0.0,
            score=self._last_observation.score,
            last_action_error=self._last_observation.last_action_error,
            task_metadata={"source": "client-cache"},
        )

    def sync(self) -> SyncCodeReviewEnv:
        return SyncCodeReviewEnv(self)
