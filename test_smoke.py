"""Quick smoke test - run with: python test_smoke.py"""

from codereview_env.models import CodeReviewAction, ReviewFinding
from server.environment import CodeReviewEnvironment
from server.tasks import grade_submission, list_tasks

print("=== Smoke Test ===")

tasks = list_tasks()
print(f"Tasks ({len(tasks)}): {[t['task_id'] for t in tasks]}")
assert len(tasks) == 3, f"Expected 3 tasks, got {len(tasks)}"

difficulties = [t["difficulty"] for t in tasks]
assert "easy" in difficulties
assert "medium" in difficulties
assert "hard" in difficulties
print(f"  Difficulties: {difficulties} ok")

for task_meta in tasks:
    tid = task_meta["task_id"]
    result = grade_submission(tid, "looks good lgtm", [])
    assert 0.0 <= result["score"] <= 1.0
    print(f"  Grader {tid}: lazy_review={result['score']:.3f}")

easy_id = [t["task_id"] for t in tasks if t["difficulty"] == "easy"][0]
print(f"\n--- Episode: {easy_id} ---")
env = CodeReviewEnvironment()
obs = env.reset(task_id=easy_id)
print(f"  Reset OK: task={obs.task_id} difficulty={obs.difficulty}")
assert obs.available_artifacts

result = env.step(CodeReviewAction(action_type="open_artifact", artifact_id="test_log"))
print(f"  open_artifact 'test_log': reward={result.reward:.3f} done={result.done}")
assert result.reward > 0.0
assert not result.done

result2 = env.step(
    CodeReviewAction(
        action_type="submit_review",
        findings=[
            ReviewFinding(
                title="Still missing page validation",
                file_path="utils/pagination.py",
                line_hint="start = (page - 1) * page_size",
                severity="medium",
                rationale="The off-by-one fix is correct, but page 0 or negative values still produce negative slicing from the end of the list.",
                recommendation="Validate page >= 1 and raise ValueError before computing slice boundaries.",
            )
        ],
    )
)
print(
    f"  submit_review: reward={result2.reward:.3f} score={result2.score:.3f} done={result2.done}"
)
assert result2.done
assert result2.score > 0.1

medium_id = [t["task_id"] for t in tasks if t["difficulty"] == "medium"][0]
print(f"\n--- Episode: {medium_id} ---")
env2 = CodeReviewEnvironment()
obs2 = env2.reset(task_id=medium_id)
print(f"  Reset OK: {obs2.task_id}, step_limit={obs2.step_limit}")
r_m = env2.step(
    CodeReviewAction(
        action_type="submit_review",
        findings=[
            ReviewFinding(
                title="Export route is missing authz guards",
                file_path="api/admin_exports.py",
                line_hint="export_invoices",
                severity="critical",
                rationale="The endpoint trusts account_id from the query string and never checks admin role or tenant scope, which can leak another tenant's invoice data.",
                recommendation="Call require_admin and require_account_scope before reading account_id or exporting CSV data.",
            )
        ],
    )
)
print(f"  Medium score: {r_m.score:.3f}")
assert r_m.score > 0.1

state = env.state
print(f"\n  state: done={state.task_metadata['done']} score={state.score}")
assert state.task_metadata["done"] is True

r_after = env.step(CodeReviewAction(action_type="open_artifact", artifact_id="ticket"))
assert r_after.last_action_error is not None
print(f"  Step-after-done error: '{r_after.last_action_error}' ok")

hard_id = [t["task_id"] for t in tasks if t["difficulty"] == "hard"][0]
env3 = CodeReviewEnvironment()
obs3 = env3.reset(task_id=hard_id)
print(f"\n  Hard task reset OK: {obs3.task_id} (step_limit={obs3.step_limit})")

print("\n=== ALL SMOKE TESTS PASSED ===")
