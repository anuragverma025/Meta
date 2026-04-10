from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Set

from codereview_env.models import ReviewFinding
from server.tasks import ReviewTask, grade_findings

_MIN_PUBLIC_SCORE = 0.05
_MAX_PUBLIC_SCORE = 0.95


def _clamp_score(raw: float) -> float:
    """Ensure externally visible scores stay strictly within a safe subrange."""
    return max(_MIN_PUBLIC_SCORE, min(_MAX_PUBLIC_SCORE, raw))


@dataclass
class RewardBreakdown:
    reward: float
    score: float
    components: Dict[str, float]
    grader_details: List[Dict[str, object]]
    last_action_error: str | None = None


class RewardComputer:
    def artifact_reward(
        self,
        task: ReviewTask,
        artifact_id: str,
        opened_artifacts: Set[str],
        repeated: bool,
    ) -> RewardBreakdown:
        if repeated:
            return RewardBreakdown(
                reward=_MIN_PUBLIC_SCORE,
                score=_MIN_PUBLIC_SCORE,
                components={"artifact_progress": 1e-4, "loop_penalty": -0.03},
                grader_details=[],
            )
        artifact = task.artifacts[artifact_id]
        reward = _clamp_score(artifact.reward)
        return RewardBreakdown(
            reward=reward,
            score=_MIN_PUBLIC_SCORE,
            components={"artifact_progress": reward, "loop_penalty": -1e-4},
            grader_details=[],
        )

    def invalid_action(self, message: str) -> RewardBreakdown:
        return RewardBreakdown(
            reward=_MIN_PUBLIC_SCORE,
            score=_MIN_PUBLIC_SCORE,
            components={"invalid_action_penalty": -0.08},
            grader_details=[],
            last_action_error=message,
        )

    def submission_reward(
        self,
        task: ReviewTask,
        findings: Sequence[ReviewFinding],
        opened_artifacts: Set[str],
        step_count: int,
        step_limit: int,
    ) -> RewardBreakdown:
        graded = grade_findings(task, findings, opened_artifacts)
        score = float(graded["score"])
        coverage_bonus = min(0.12, 0.03 * len(opened_artifacts))
        efficiency_bonus = max(1e-4, 0.08 - 0.02 * max(0, step_count - 2))
        empty_penalty = -0.12 if not findings else -1e-4
        overstep_penalty = -0.05 if step_count > step_limit else -1e-4
        shaped_reward = (
            score * 0.75
            + coverage_bonus
            + efficiency_bonus
            + empty_penalty
            + overstep_penalty
        )
        shaped_reward = _clamp_score(shaped_reward)
        return RewardBreakdown(
            reward=shaped_reward,
            score=_clamp_score(score),
            components={
                "grader_score": round(score, 4),
                "coverage_bonus": round(coverage_bonus, 4),
                "efficiency_bonus": round(efficiency_bonus, 4),
                "empty_submission_penalty": round(empty_penalty, 4),
                "overstep_penalty": round(overstep_penalty, 4),
            },
            grader_details=list(graded["criteria"]),
        )
