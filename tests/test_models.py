import pytest
from pydantic import ValidationError

from codereview_env.models import CodeReviewAction, CodeReviewObservation, ReviewFinding


def test_action_requires_artifact_for_open() -> None:
    action = CodeReviewAction(action_type="open_artifact", artifact_id="helper_diff")
    assert action.action_type == "open_artifact"
    assert action.artifact_id == "helper_diff"


def test_submit_review_accepts_structured_findings() -> None:
    action = CodeReviewAction(
        action_type="submit_review",
        findings=[
            ReviewFinding(
                title="Missing auth",
                file_path="api/admin_exports.py",
                severity="critical",
                rationale="The route trusts user input and can leak another tenant's invoices.",
                recommendation="Enforce admin and account scope before export.",
            )
        ],
    )
    assert len(action.findings) == 1
    assert action.findings[0].severity == "critical"


def test_findings_reject_short_rationale() -> None:
    with pytest.raises(ValidationError):
        ReviewFinding(
            title="Bad",
            file_path="a.py",
            severity="low",
            rationale="Too short",
            recommendation="Do something better.",
        )


def test_observation_has_openenv_fields() -> None:
    observation = CodeReviewObservation(
        task_id="pagination-regression",
        difficulty="easy",
        title="Review pagination",
        objective="Catch production risk",
        summary="Short summary",
        step_limit=4,
        done=False,
        reward=0.05,
    )
    assert observation.done is False
    assert observation.reward == 0.05
