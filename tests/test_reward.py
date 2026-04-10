from codereview_env.models import ReviewFinding


def test_reopening_artifact_penalizes_loops(reward_computer, hard_task):
    first = reward_computer.artifact_reward(
        hard_task, "payment_client", set(), repeated=False
    )
    second = reward_computer.artifact_reward(
        hard_task, "payment_client", {"payment_client"}, repeated=True
    )
    assert first.reward > 0.0
    assert second.components["loop_penalty"] < 0.0


def test_submission_reward_scores_partial_progress(reward_computer, hard_task):
    findings = [
        ReviewFinding(
            title="Retries can duplicate refunds",
            file_path="workers/refunds.py",
            line_hint="process_refund",
            severity="critical",
            rationale="The timeout path calls the processor again without a persistent idempotency key, so a refund can be sent twice after the processor already accepted the first request.",
            recommendation="Persist and reuse an idempotency_key on every retry before calling the payment processor.",
        )
    ]
    breakdown = reward_computer.submission_reward(
        hard_task,
        findings,
        {"worker_diff", "payment_client", "incident_ticket"},
        step_count=3,
        step_limit=hard_task.step_limit,
    )
    assert 0.0 <= breakdown.score <= 1.0
    assert breakdown.score > 0.3
    assert breakdown.reward > 0.2


def test_invalid_action_returns_error(reward_computer):
    breakdown = reward_computer.invalid_action("bad action")
    assert breakdown.last_action_error == "bad action"
    assert breakdown.components["invalid_action_penalty"] < 0.0
