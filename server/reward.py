from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Set

from codereview_env.models import ReviewFinding
from server.tasks import ReviewTask, grade_findings

_SCORE_EPS = 1e-6


def _clamp_score(raw: float) -> float:
    """Ensure externally visible scores stay strictly within (0, 1)."""
    return max(_SCORE_EPS, min(1.0 - _SCORE_EPS, raw))


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
                reward=_SCORE_EPS,
                score=_SCORE_EPS,
                components={"artifact_progress": 0.0, "loop_penalty": -0.03},
                grader_details=[],
            )
        artifact = task.artifacts[artifact_id]
        reward = _clamp_score(max(0.0, min(0.2, artifact.reward)))
        return RewardBreakdown(
            reward=reward,
            score=_SCORE_EPS,
            components={"artifact_progress": reward, "loop_penalty": 0.0},
            grader_details=[],
        )

    def invalid_action(self, message: str) -> RewardBreakdown:
        return RewardBreakdown(
            reward=_SCORE_EPS,
            score=_SCORE_EPS,
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
        efficiency_bonus = max(0.0, 0.08 - 0.02 * max(0, step_count - 2))
        empty_penalty = -0.12 if not findings else 0.0
        overstep_penalty = -0.05 if step_count > step_limit else 0.0
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
