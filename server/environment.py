from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from openenv.core import Environment

from codereview_env.models import (
    CodeReviewAction,
    CodeReviewObservation,
    CodeReviewState,
    ReviewArtifact,
    ReviewFinding,
)
from server.reward import RewardBreakdown, RewardComputer
from server.tasks import TASKS, TASKS_BY_ID, ReviewTask

_MIN_PUBLIC_SCORE = 0.05
_MAX_PUBLIC_SCORE = 0.95


def _clamp_score(raw: float) -> float:
    """Keep validator-visible scores inside a conservative open interval."""
    return max(_MIN_PUBLIC_SCORE, min(_MAX_PUBLIC_SCORE, raw))


class CodeReviewEnvironment(
    Environment[CodeReviewObservation, CodeReviewAction, CodeReviewState]
):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, reward_computer: Optional[RewardComputer] = None):
        super().__init__()
        self.reward_computer = reward_computer or RewardComputer()
        self.task: Optional[ReviewTask] = None
        self._opened_artifact_ids: Set[str] = set()
        self._submitted_findings: List[ReviewFinding] = []
        self._recent_events: List[str] = []
        self._cumulative_reward = _MIN_PUBLIC_SCORE
        self._score = _MIN_PUBLIC_SCORE
        self._last_action_error: Optional[str] = None
        self._step_limit = 0
        self._task_index = 0
        self._episode_done = False
        self.episode_id = None
        self.step_count = 0

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": "codereview-env",
            "domain": "software engineering",
            "description": "A deterministic code review benchmark for real pull request triage.",
            "tasks": [task.task_id for task in TASKS],
        }

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeReviewObservation:
        task_id = kwargs.get("task_id")
        if isinstance(seed, str) and not task_id:
            task_id = seed
            seed = None
        if task_id:
            task = TASKS_BY_ID[task_id]
        elif seed is not None:
            task = TASKS[seed % len(TASKS)]
        else:
            task = TASKS[self._task_index % len(TASKS)]
            self._task_index += 1

        self.task = task
        self.episode_id = episode_id or task.task_id
        self.step_count = 0
        self._step_limit = task.step_limit
        self._opened_artifact_ids = set(task.starting_artifacts)
        self._submitted_findings = []
        self._recent_events = ["Episode reset."]
        self._cumulative_reward = _MIN_PUBLIC_SCORE
        self._score = _MIN_PUBLIC_SCORE
        self._last_action_error = None
        self._episode_done = False
        return self._build_observation(reward=_MIN_PUBLIC_SCORE, done=False)

    def step(
        self, action: CodeReviewAction, timeout_s: Optional[float] = None, **kwargs: Any
    ) -> CodeReviewObservation:
        if self.task is None:
            raise RuntimeError("reset() must be called before step().")
        if self._episode_done:
            self._last_action_error = "Episode already finished."
            return self._build_observation(reward=_MIN_PUBLIC_SCORE, done=True)

        self.step_count += 1
        reward_breakdown: RewardBreakdown

        if action.action_type == "open_artifact":
            reward_breakdown = self._handle_open_artifact(action)
            done = False
        elif action.action_type == "submit_review":
            reward_breakdown = self._handle_submit(action)
            done = True
        else:
            reward_breakdown = self.reward_computer.invalid_action(
                "Unsupported action_type."
            )
            done = False

        if self.step_count >= self._step_limit and not done:
            self._recent_events.append(
                "Step limit reached before review was submitted."
            )
            done = True

        self._episode_done = done
        self._last_action_error = reward_breakdown.last_action_error
        self._cumulative_reward = max(0.05, min(0.95, self._cumulative_reward + reward_breakdown.reward))
        self._recent_events.append(
            f"Step {self.step_count}: {action.action_type} -> reward {reward_breakdown.reward:.2f}"
        )
        return self._build_observation(
            reward=reward_breakdown.reward,
            done=done,
            extra_metadata={
                "reward_breakdown": reward_breakdown.components,
                "grader_details": reward_breakdown.grader_details,
            },
        )

    @property
    def state(self) -> CodeReviewState:
        task_metadata = {
            "step_limit": self._step_limit,
            "done": self._episode_done,
        }
        return CodeReviewState(
            episode_id=self.episode_id,
            step_count=self.step_count,
            task_id=self.task.task_id if self.task else None,
            difficulty=self.task.difficulty if self.task else None,
            title=self.task.title if self.task else None,
            opened_artifact_ids=sorted(self._opened_artifact_ids),
            submitted_findings=self._submitted_findings,
            cumulative_reward=round(_clamp_score(self._cumulative_reward), 6),
            score=round(_clamp_score(self._score), 6),
            last_action_error=self._last_action_error,
            task_metadata=task_metadata,
        )

    def _handle_open_artifact(self, action: CodeReviewAction) -> RewardBreakdown:
        artifact_id = action.artifact_id
        if not artifact_id:
            return self.reward_computer.invalid_action(
                "artifact_id is required for open_artifact."
            )
        if artifact_id not in self.task.artifacts:
            return self.reward_computer.invalid_action(
                f"Unknown artifact_id: {artifact_id}"
            )

        repeated = artifact_id in self._opened_artifact_ids
        self._opened_artifact_ids.add(artifact_id)
        artifact = self.task.artifacts[artifact_id]
        self._recent_events.append(f"Opened {artifact.title}.")
        return self.reward_computer.artifact_reward(
            self.task, artifact_id, self._opened_artifact_ids, repeated
        )

    def _handle_submit(self, action: CodeReviewAction) -> RewardBreakdown:
        self._submitted_findings = list(action.findings)
        breakdown = self.reward_computer.submission_reward(
            self.task,
            action.findings,
            self._opened_artifact_ids,
            self.step_count,
            self._step_limit,
        )
        self._score = _clamp_score(breakdown.score)
        self._recent_events.append(f"Submitted {len(action.findings)} findings.")
        return breakdown

    def _build_observation(
        self,
        reward: float,
        done: bool,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> CodeReviewObservation:
        opened_artifacts = []
        available_artifacts = []
        if self.task is not None:
            for artifact_id, artifact in self.task.artifacts.items():
                model = ReviewArtifact(
                    artifact_id=artifact.artifact_id,
                    kind=artifact.kind,  # type: ignore[arg-type]
                    title=artifact.title,
                    preview=artifact.preview,
                    opened=artifact_id in self._opened_artifact_ids,
                    content=(
                        artifact.content
                        if artifact_id in self._opened_artifact_ids
                        else None
                    ),
                )
                available_artifacts.append(model)
                if model.opened:
                    opened_artifacts.append(model)

        metadata = {
            "task_id": self.task.task_id if self.task else None,
            "score": round(_clamp_score(self._score), 6),
            "step_count": self.step_count,
            "opened_artifact_ids": sorted(self._opened_artifact_ids),
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        return CodeReviewObservation(
            task_id=self.task.task_id if self.task else "",
            difficulty=self.task.difficulty if self.task else "easy",
            title=self.task.title if self.task else "",
            objective=self.task.objective if self.task else "",
            summary=self.task.summary if self.task else "",
            step_limit=self._step_limit,
            opened_artifacts=opened_artifacts,
            available_artifacts=available_artifacts,
            recent_events=self._recent_events[-6:],
            last_action_error=self._last_action_error,
            score=round(_clamp_score(self._score), 6),
            done=done,
            reward=round(_clamp_score(reward), 6),
            metadata=metadata,
        )
