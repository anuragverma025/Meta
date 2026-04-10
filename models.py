from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from openenv.core import Action, Observation, State


class ReviewFinding(BaseModel):
    title: str = Field(..., min_length=5, description="Short review finding title.")
    file_path: str = Field(..., min_length=3, description="File containing the issue.")
    line_hint: Optional[str] = Field(
        default=None,
        description="Approximate line or symbol reference, for example 'line 18' or 'process_refund'.",
    )
    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Estimated impact of the issue."
    )
    rationale: str = Field(
        ...,
        min_length=20,
        description="Why this matters in production and what behavior is affected.",
    )
    recommendation: str = Field(
        ...,
        min_length=12,
        description="Concrete fix suggestion that an engineer could act on.",
    )


class ReviewArtifact(BaseModel):
    artifact_id: str
    kind: Literal["file", "test", "log", "policy", "ticket"]
    title: str
    preview: str
    opened: bool = False
    content: Optional[str] = None


class CodeReviewAction(Action):
    action_type: Literal["open_artifact", "submit_review"] = Field(
        ..., description="Open more evidence or submit review findings."
    )
    artifact_id: Optional[str] = Field(
        default=None, description="Artifact id for open_artifact actions."
    )
    findings: List[ReviewFinding] = Field(
        default_factory=list,
        description="Structured review findings when action_type is submit_review.",
    )
    note: Optional[str] = Field(
        default=None, description="Optional short note about why the action was chosen."
    )


class CodeReviewObservation(Observation):
    task_id: str
    difficulty: Literal["easy", "medium", "hard"]
    title: str
    objective: str
    summary: str
    step_limit: int
    opened_artifacts: List[ReviewArtifact] = Field(default_factory=list)
    available_artifacts: List[ReviewArtifact] = Field(default_factory=list)
    recent_events: List[str] = Field(default_factory=list)
    last_action_error: Optional[str] = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    # Step-level signals (populated by environment)
    done: bool = Field(default=False, description="Whether the episode has ended.")
    reward: float = Field(default=0.0, description="Reward earned on this step.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Extra per-step metadata."
    )


class CodeReviewState(State):
    episode_id: Optional[str] = None
    task_id: Optional[str] = None
    difficulty: Optional[str] = None
    title: Optional[str] = None
    step_count: int = 0
    opened_artifact_ids: List[str] = Field(default_factory=list)
    submitted_findings: List[ReviewFinding] = Field(default_factory=list)
    cumulative_reward: float = Field(default=0.0, ge=0.0, le=1.0)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    last_action_error: Optional[str] = None
    task_metadata: Dict[str, Any] = Field(default_factory=dict)
