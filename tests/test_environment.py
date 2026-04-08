from codereview_env.models import CodeReviewAction, CodeReviewState, ReviewFinding


def test_reset_returns_task_observation(env):
    observation = env.reset(task_id="pagination-regression")
    assert observation.task_id == "pagination-regression"
    assert observation.done is False
    assert len(observation.available_artifacts) >= 2


def test_open_artifact_gives_partial_reward(env):
    env.reset(task_id="pagination-regression")
    observation = env.step(CodeReviewAction(action_type="open_artifact", artifact_id="test_log"))
    assert 0.0 < observation.reward <= 0.2
    assert any(artifact.artifact_id == "test_log" for artifact in observation.opened_artifacts)


def test_submit_review_finishes_episode_with_score(env):
    env.reset(task_id="tenant-export-auth")
    env.step(CodeReviewAction(action_type="open_artifact", artifact_id="auth_middleware"))
    observation = env.step(
        CodeReviewAction(
            action_type="submit_review",
            findings=[
                ReviewFinding(
                    title="Missing tenant scope",
                    file_path="api/admin_exports.py",
                    line_hint="export_invoices",
                    severity="critical",
                    rationale="The handler trusts account_id from a query parameter and can leak another tenant's invoice data.",
                    recommendation="Call require_admin and require_account_scope before exporting the CSV.",
                )
            ],
        )
    )
    assert observation.done is True
    assert 0.0 <= observation.score <= 1.0
    assert observation.score > 0.4


def test_state_reports_progress(env):
    env.reset(task_id="refund-idempotency")
    env.step(CodeReviewAction(action_type="open_artifact", artifact_id="payment_client"))
    state = env.state
    assert isinstance(state, CodeReviewState)
    assert state.step_count == 1
    assert "payment_client" in state.opened_artifact_ids


def test_step_limit_ends_episode(env):
    observation = env.reset(task_id="pagination-regression")
    for _ in range(observation.step_limit):
        observation = env.step(CodeReviewAction(action_type="open_artifact", artifact_id="ticket"))
    assert observation.done is True
