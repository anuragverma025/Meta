from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from openai import OpenAI

from codereview_env.models import CodeReviewAction
from server.environment import CodeReviewEnvironment
from server.tasks import TASKS

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")

if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")
BENCHMARK = "codereview-env"
MAX_STEPS = 6
SUCCESS_SCORE_THRESHOLD = 0.60


SYSTEM_PROMPT = """You are reviewing a pull request in a deterministic benchmark.
Return exactly one JSON object with this schema:
{"action_type":"open_artifact","artifact_id":"...","note":"..."}
or
{"action_type":"submit_review","findings":[{"title":"...","file_path":"...","line_hint":"...","severity":"low|medium|high|critical","rationale":"...","recommendation":"..."}],"note":"..."}
Choose one action at a time. Prefer opening the most informative artifact before submitting.
"""


def _observation_to_prompt(observation: Dict[str, Any]) -> str:
    artifact_lines = []
    for artifact in observation["available_artifacts"]:
        status = "opened" if artifact["opened"] else "closed"
        artifact_lines.append(
            f"- {artifact['artifact_id']} [{artifact['kind']}] {status}: {artifact['title']} :: {artifact['preview']}"
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


def _scripted_policy(task_id: str, opened_ids: List[str]) -> Dict[str, Any]:
    plans = {
        "pagination-regression": [
            {
                "action_type": "open_artifact",
                "artifact_id": "test_log",
                "note": "Need the failing test.",
            },
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
            {
                "action_type": "open_artifact",
                "artifact_id": "auth_middleware",
                "note": "Inspect auth helpers.",
            },
            {
                "action_type": "open_artifact",
                "artifact_id": "security_policy",
                "note": "Confirm tenant policy.",
            },
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
            {
                "action_type": "open_artifact",
                "artifact_id": "payment_client",
                "note": "Check refund API.",
            },
            {
                "action_type": "open_artifact",
                "artifact_id": "worker_log",
                "note": "Inspect incident evidence.",
            },
            {
                "action_type": "open_artifact",
                "artifact_id": "db_model",
                "note": "Look for idempotency fields.",
            },
            {
                "action_type": "open_artifact",
                "artifact_id": "regression_test",
                "note": "Check test coverage.",
            },
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


def _llm_action(client: OpenAI, observation: Dict[str, Any]) -> Dict[str, Any]:
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


def _format_action(action: Dict[str, Any]) -> str:
    return json.dumps(action, separators=(",", ":"), ensure_ascii=True)


def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    for task in TASKS:
        env = CodeReviewEnvironment()
        rewards: List[float] = []
        steps = 0
        score = 0.0
        success = False
        observation = env.reset(task_id=task.task_id)
        print(f"[START] task={task.task_id} env={BENCHMARK} model={MODEL_NAME}")
        last_error = None
        try:
            while steps < MAX_STEPS and not observation.done:
                obs_dict = observation.model_dump()
                opened_ids = [
                    artifact["artifact_id"] for artifact in obs_dict["opened_artifacts"]
                ]
                action_payload = (
                    _llm_action(client, obs_dict)
                    if client
                    else _scripted_policy(task.task_id, opened_ids)
                )
                action = CodeReviewAction.model_validate(action_payload)
                observation = env.step(action)
                steps += 1
                reward = float(observation.reward or 0.0)
                rewards.append(reward)
                score = float(observation.score)
                last_error = observation.last_action_error
                print(
                    f"[STEP] step={steps} action={_format_action(action.model_dump())} "
                    f"reward={reward:.2f} done={str(observation.done).lower()} "
                    f"error={last_error if last_error is not None else 'null'}"
                )
            success = score >= SUCCESS_SCORE_THRESHOLD
        except Exception as exc:
            last_error = str(exc)
        finally:
            if hasattr(env, "close"):
                env.close()
            rewards_str = ",".join(f"{reward:.2f}" for reward in rewards)
            print(
                f"[END] success={str(success).lower()} steps={steps} "
                f"rewards={rewards_str}"
            )


if __name__ == "__main__":
    main()
