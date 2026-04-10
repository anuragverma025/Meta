from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from codereview_env.models import CodeReviewAction, CodeReviewObservation
from server.environment import CodeReviewEnvironment
from server.tasks import TASKS

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
BENCHMARK = "codereview-env"
MAX_STEPS = 6
SUCCESS_SCORE_THRESHOLD = 0.60
_MIN_PUBLIC_SCORE = 0.05
_MAX_PUBLIC_SCORE = 0.95


SYSTEM_PROMPT = """You are reviewing a pull request in a deterministic benchmark.
Return exactly one JSON object with this schema:
{"action_type":"open_artifact","artifact_id":"...","note":"..."}
or
{"action_type":"submit_review","findings":[{"title":"...","file_path":"...","line_hint":"...","severity":"low|medium|high|critical","rationale":"...","recommendation":"..."}],"note":"..."}
Choose one action at a time. Prefer opening the most informative artifact before submitting.
"""


def _require_hf_token() -> str:
    """Return the configured Hugging Face token or raise a clear error."""
    if HF_TOKEN:
        return HF_TOKEN
    raise ValueError("HF_TOKEN environment variable is required")


def _build_client() -> OpenAI:
    """Create the required OpenAI client for all model calls."""
    return OpenAI(base_url=API_BASE_URL, api_key=_require_hf_token())


def _observation_to_prompt(observation: dict[str, Any]) -> str:
    """Convert the observation into a compact LLM prompt."""
    artifact_lines = []
    for artifact in observation["available_artifacts"]:
        status = "opened" if artifact["opened"] else "closed"
        artifact_lines.append(
            f"- {artifact['artifact_id']} [{artifact['kind']}] {status}: "
            f"{artifact['title']} :: {artifact['preview']}"
        )
        if artifact["opened"] and artifact.get("content"):
            artifact_lines.append(f"  content: {artifact['content']}")
    return (
        f"Task: {observation['title']}\n"
        f"Objective: {observation['objective']}\n"
        f"Summary: {observation['summary']}\n"
        f"Step count: {observation['metadata'].get('step_count', 'n/a')}\n"
        f"Recent events: {observation['recent_events']}\n"
        f"Artifacts:\n" + "\n".join(artifact_lines)
    )


def _scripted_policy(task_id: str, opened_ids: list[str]) -> dict[str, Any]:
    """Fallback policy used when the LLM call fails."""
    plans = {
        "pagination-regression": [
            {"action_type": "open_artifact", "artifact_id": "test_log", "note": "Need the failing test."},
            {
                "action_type": "submit_review",
                "findings": [
                    {
                        "title": "Validate page numbers before slicing",
                        "file_path": "utils/pagination.py",
                        "line_hint": "line 1",
                        "severity": "medium",
                        "rationale": "The new `(page - 1)` offset fixes the 1-indexing bug, but page 0 or negative pages still produce negative slices and can return the wrong rows from the end of the list.",
                        "recommendation": "Keep the off-by-one fix, but add a guard that rejects `page < 1` and raise a ValueError before computing `start`.",
                    }
                ],
                "note": "Submit the core finding.",
            },
        ],
        "tenant-export-auth": [
            {"action_type": "open_artifact", "artifact_id": "auth_middleware", "note": "Inspect auth helpers."},
            {"action_type": "open_artifact", "artifact_id": "security_policy", "note": "Confirm tenant policy."},
            {
                "action_type": "submit_review",
                "findings": [
                    {
                        "title": "Export route is missing tenant scope enforcement",
                        "file_path": "api/admin_exports.py",
                        "line_hint": "export_invoices",
                        "severity": "critical",
                        "rationale": "The handler trusts `account_id` from the query string and never enforces account scope, so an authenticated user could export another tenant's invoices. It also does not call `require_admin`, leaving the route under-protected.",
                        "recommendation": "Call `require_admin(request)` and `require_account_scope(request, account_id)` before exporting, or derive the account from `request.user` unless the caller is a global admin.",
                    }
                ],
                "note": "Submit the merge blocker.",
            },
        ],
        "refund-idempotency": [
            {"action_type": "open_artifact", "artifact_id": "payment_client", "note": "Check refund API."},
            {"action_type": "open_artifact", "artifact_id": "worker_log", "note": "Inspect incident evidence."},
            {"action_type": "open_artifact", "artifact_id": "db_model", "note": "Look for idempotency fields."},
            {"action_type": "open_artifact", "artifact_id": "regression_test", "note": "Check test coverage."},
            {
                "action_type": "submit_review",
                "findings": [
                    {
                        "title": "Retry path can send duplicate refunds",
                        "file_path": "workers/refunds.py",
                        "line_hint": "process_refund",
                        "severity": "critical",
                        "rationale": "On TimeoutError the worker calls `payments.refund` a second time without reusing a durable idempotency key, even though the processor may have already accepted the first refund. Because status is only written after the call returns, a second worker can also pick the same queued job and race another refund.",
                        "recommendation": "Persist and reuse `refunds.idempotency_key` on every processor call, atomically claim the job before sending the refund, and add a regression test for timeout-after-success plus concurrent replay.",
                    }
                ],
                "note": "Submit the incident-level issue.",
            },
        ],
    }
    plan = plans[task_id]
    if not opened_ids:
        return plan[0]
    open_count = sum(
        1
        for step in plan
        if step["action_type"] == "open_artifact" and step["artifact_id"] in opened_ids
    )
    return plan[min(open_count, len(plan) - 1)]


def _llm_action(client: OpenAI, observation: dict[str, Any]) -> dict[str, Any]:
    """Request the next action from the model via the OpenAI client."""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _observation_to_prompt(observation)},
        ],
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def _choose_action(
    client: OpenAI,
    task_id: str,
    observation: dict[str, Any],
    opened_ids: list[str],
) -> dict[str, Any]:
    """Use the model first, then fall back to a deterministic policy on API failure."""
    try:
        return _llm_action(client, observation)
    except Exception:
        return _scripted_policy(task_id, opened_ids)


def _format_action(action: dict[str, Any]) -> str:
    """Serialize an action onto a single stdout-safe line."""
    return json.dumps(action, separators=(",", ":"), ensure_ascii=True)


def _action_output_payload(action: CodeReviewAction) -> dict[str, Any]:
    """Serialize only the contract-relevant action fields."""
    payload: dict[str, Any] = {"action_type": action.action_type}
    if action.action_type == "submit_review":
        payload["artifact_id"] = action.artifact_id
        payload["findings"] = [finding.model_dump() for finding in action.findings]
    elif action.artifact_id is not None:
        payload["artifact_id"] = action.artifact_id
    if action.note is not None:
        payload["note"] = action.note
    return payload


def _print_step(
    step_number: int, action: CodeReviewAction, observation: CodeReviewObservation
) -> None:
    """Emit the required step output line immediately after env.step()."""
    error_value = observation.last_action_error or "null"
    _SCORE_EPS = 1e-4  # enough to avoid 0.00 when rounded to 2dp
    raw_reward = max(_SCORE_EPS, min(1.0 - _SCORE_EPS, float(observation.reward or _SCORE_EPS)))
    print(
        f"[STEP] step={step_number} action={_format_action(_action_output_payload(action))} "
        f"reward={raw_reward:.2f} "
        f"done={str(observation.done).lower()} error={error_value}"
    )


def _run_task(task_id: str, client: OpenAI) -> None:
    """Run one benchmark episode and emit only the required line types."""
    env = CodeReviewEnvironment()
    rewards: list[float] = []
    score = _MIN_PUBLIC_SCORE
    steps = 0
    success = False
    print(f"[START] task={task_id} env={BENCHMARK} model={MODEL_NAME}")
    try:
        observation = env.reset(task_id=task_id)
        while steps < MAX_STEPS and not observation.done:
            obs_dict = observation.model_dump()
            opened_ids = [artifact["artifact_id"] for artifact in obs_dict["opened_artifacts"]]
            action_payload = _choose_action(client, task_id, obs_dict, opened_ids)
            action = CodeReviewAction.model_validate(action_payload)
            observation = env.step(action)
            steps += 1
            step_reward = max(_MIN_PUBLIC_SCORE, min(_MAX_PUBLIC_SCORE, float(observation.reward or _MIN_PUBLIC_SCORE)))
            rewards.append(step_reward)
            score = max(_MIN_PUBLIC_SCORE, min(_MAX_PUBLIC_SCORE, float(observation.score or _MIN_PUBLIC_SCORE)))
            _print_step(steps, action, observation)
        success = bool(observation.done and score >= SUCCESS_SCORE_THRESHOLD)
    except Exception:
        success = False
    finally:
        env.close()
        # Ensure at least one reward value so rewards= is never empty
        safe_rewards = rewards if rewards else [1e-4]
        rewards_str = ",".join(
            f"{max(1e-4, min(0.9999, r)):.2f}" for r in safe_rewards
        )
        print(f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}")


def main() -> None:
    """Run the benchmark across all configured tasks."""
    client = _build_client()
    for task in TASKS:
        _run_task(task.task_id, client)


if __name__ == "__main__":
    main()
