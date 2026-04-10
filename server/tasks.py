from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Sequence, Set

from codereview_env.models import ReviewFinding

Difficulty = Literal["easy", "medium", "hard"]
_MIN_PUBLIC_SCORE = 0.05
_MAX_PUBLIC_SCORE = 0.95


def _clamp_score(raw: float) -> float:
    """Normalize public grader scores into a conservative open interval."""
    return max(_MIN_PUBLIC_SCORE, min(_MAX_PUBLIC_SCORE, raw))


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    kind: str
    title: str
    preview: str
    content: str
    reward: float = 0.0


@dataclass(frozen=True)
class GraderCriterion:
    criterion_id: str
    description: str
    file_path: str
    severity: str
    weight: float
    required_terms: Sequence[Set[str]]
    recommendation_terms: Sequence[Set[str]] = field(default_factory=tuple)
    preferred_artifacts: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReviewTask:
    task_id: str
    title: str
    difficulty: Difficulty
    objective: str
    summary: str
    step_limit: int
    starting_artifacts: Sequence[str]
    artifacts: Dict[str, Artifact]
    grader: Sequence[GraderCriterion]


def _contains_group(text: str, groups: Sequence[Set[str]]) -> float:
    if not groups:
        return 1.0
    hits = 0
    for group in groups:
        if any(term in text for term in group):
            hits += 1
    return hits / len(groups)


def grade_findings(
    task: ReviewTask, findings: Sequence[ReviewFinding], opened_artifacts: Set[str]
) -> Dict[str, object]:
    matched = []
    total = 0.0
    finding_texts = []
    for finding in findings:
        combined = " ".join(
            [
                finding.title.lower(),
                finding.file_path.lower(),
                (finding.line_hint or "").lower(),
                finding.rationale.lower(),
                finding.recommendation.lower(),
                finding.severity.lower(),
            ]
        )
        finding_texts.append((finding, combined))

    for criterion in task.grader:
        best = 0.0
        for finding, combined in finding_texts:
            issue_score = _contains_group(combined, criterion.required_terms)
            fix_score = _contains_group(combined, criterion.recommendation_terms)
            severity_score = 1.0 if criterion.severity in combined else 0.4
            file_score = 1.0 if criterion.file_path.lower() in combined else 0.5
            evidence_score = (
                1.0
                if not criterion.preferred_artifacts
                else min(
                    1.0,
                    sum(
                        1
                        for artifact_id in criterion.preferred_artifacts
                        if artifact_id in opened_artifacts
                    )
                    / len(criterion.preferred_artifacts),
                )
            )
            score = criterion.weight * (
                0.45 * issue_score
                + 0.25 * fix_score
                + 0.15 * severity_score
                + 0.10 * file_score
                + 0.05 * evidence_score
            )
            if score > best:
                best = score
        total += best
        matched.append(
            {
                "criterion_id": criterion.criterion_id,
                "description": criterion.description,
                "score": round(best, 4),
                "weight": criterion.weight,
            }
        )

    normalized = _clamp_score(total)
    return {"score": normalized, "criteria": matched}


TASKS: List[ReviewTask] = [
    ReviewTask(
        task_id="pagination-regression",
        title="Review a pagination bug fix before release",
        difficulty="easy",
        objective="Identify whether the change really fixes the paging bug and call out any remaining production risk.",
        summary=(
            "A product engineer changed the pagination helper after customer reports that page 2 sometimes skips results. "
            "You are the final reviewer before the patch is merged."
        ),
        step_limit=4,
        starting_artifacts=("ticket", "helper_diff"),
        artifacts={
            "ticket": Artifact(
                artifact_id="ticket",
                kind="ticket",
                title="Support ticket",
                preview="Customers say page 2 repeats the first record and page 3 skips one row.",
                content=(
                    "Customer impact: exporting page 2 shows one duplicate row and drops one expected row. "
                    "The issue reproduces when page numbers are 1-indexed in the API layer."
                ),
            ),
            "helper_diff": Artifact(
                artifact_id="helper_diff",
                kind="file",
                title="utils/pagination.py diff",
                preview="Diff updates `start = page * page_size` to `(page - 1) * page_size`.",
                content=(
                    "@@ utils/pagination.py\n"
                    "- start = page * page_size\n"
                    "+ start = (page - 1) * page_size\n"
                    "  end = start + page_size\n"
                    "  return items[start:end]\n"
                ),
                reward=0.08,
            ),
            "test_log": Artifact(
                artifact_id="test_log",
                kind="test",
                title="Failing test excerpt",
                preview="One regression test still fails around invalid page numbers.",
                content=(
                    "FAILED tests/test_pagination.py::test_page_zero_returns_error\n"
                    "Expected ValueError('page must be >= 1') but helper returned items[-10:0]."
                ),
                reward=0.10,
            ),
        },
        grader=(
            GraderCriterion(
                criterion_id="page-zero-validation",
                description="Reviewer flags that page 0 or negative pages still slice from the end and need validation.",
                file_path="utils/pagination.py",
                severity="medium",
                weight=0.65,
                required_terms=(
                    {
                        "page 0",
                        "page zero",
                        "negative page",
                        "page must be >= 1",
                        "invalid page",
                    },
                    {"slice", "negative index", "items[-", "from the end"},
                ),
                recommendation_terms=(
                    {"validate", "guard", "reject", "raise"},
                    {"valueerror", "page must be >= 1", "before slicing"},
                ),
                preferred_artifacts=("helper_diff", "test_log"),
            ),
            GraderCriterion(
                criterion_id="off-by-one-context",
                description="Reviewer confirms why the 1-indexing fix is correct instead of rejecting it.",
                file_path="utils/pagination.py",
                severity="low",
                weight=0.35,
                required_terms=(
                    {"1-index", "1 indexed", "page - 1", "off by one"},
                    {"page 2", "duplicate", "skip", "customer"},
                ),
                recommendation_terms=({"keep", "correct", "right fix", "expected"},),
                preferred_artifacts=("ticket", "helper_diff"),
            ),
        ),
    ),
    ReviewTask(
        task_id="tenant-export-auth",
        title="Review a multi-tenant export endpoint",
        difficulty="medium",
        objective="Decide whether the export endpoint is safe for a SaaS deployment and report any merge blockers.",
        summary=(
            "Finance customers can export invoice CSVs. The team added a convenience endpoint for admins, "
            "but this service runs in a multi-tenant environment."
        ),
        step_limit=5,
        starting_artifacts=("pr_summary", "route_diff"),
        artifacts={
            "pr_summary": Artifact(
                artifact_id="pr_summary",
                kind="ticket",
                title="PR summary",
                preview="Adds `/api/admin/invoices/export` and reuses the invoice repository.",
                content=(
                    "Author note: internal support asked for a quick CSV export endpoint. "
                    "The route is only linked from the admin console."
                ),
            ),
            "route_diff": Artifact(
                artifact_id="route_diff",
                kind="file",
                title="api/admin_exports.py diff",
                preview="New route returns repository.export_csv(account_id=request.query_params['account_id']).",
                content=(
                    "@@ api/admin_exports.py\n"
                    "@router.get('/api/admin/invoices/export')\n"
                    "async def export_invoices(request):\n"
                    "    account_id = request.query_params['account_id']\n"
                    "    csv_bytes = await invoice_repo.export_csv(account_id=account_id)\n"
                    "    return Response(csv_bytes, media_type='text/csv')\n"
                ),
                reward=0.08,
            ),
            "auth_middleware": Artifact(
                artifact_id="auth_middleware",
                kind="file",
                title="middleware/authz.py",
                preview="Helpers expose `require_admin(request)` and `require_account_scope(request, account_id)`.",
                content=(
                    "def require_admin(request):\n"
                    "    if request.user.role != 'admin':\n"
                    "        raise Forbidden('admin role required')\n\n"
                    "def require_account_scope(request, account_id):\n"
                    "    if request.user.account_id != account_id and not request.user.is_global_admin:\n"
                    "        raise Forbidden('cross-tenant export denied')\n"
                ),
                reward=0.12,
            ),
            "security_policy": Artifact(
                artifact_id="security_policy",
                kind="policy",
                title="Tenant isolation policy",
                preview="All admin endpoints must validate both actor role and tenant/account scope.",
                content=(
                    "Security policy: multi-tenant admin features must enforce actor role and tenant scope. "
                    "Reading an arbitrary `account_id` from request parameters is not sufficient."
                ),
                reward=0.10,
            ),
        },
        grader=(
            GraderCriterion(
                criterion_id="missing-tenant-scope",
                description="Reviewer catches missing tenant scoping on account_id, creating a cross-tenant data leak.",
                file_path="api/admin_exports.py",
                severity="critical",
                weight=0.7,
                required_terms=(
                    {
                        "cross-tenant",
                        "tenant",
                        "account scope",
                        "data leak",
                        "authorization",
                    },
                    {"query param", "account_id", "untrusted", "arbitrary"},
                ),
                recommendation_terms=(
                    {"require_account_scope", "tenant check", "scope", "authorize"},
                    {"before export", "request.user.account_id", "is_global_admin"},
                ),
                preferred_artifacts=(
                    "route_diff",
                    "auth_middleware",
                    "security_policy",
                ),
            ),
            GraderCriterion(
                criterion_id="missing-admin-gate",
                description="Reviewer notes that the route never calls require_admin, so any authenticated user could hit it if routed.",
                file_path="api/admin_exports.py",
                severity="high",
                weight=0.3,
                required_terms=(
                    {"require_admin", "admin role", "admin gate", "privilege"},
                    {"missing", "not called", "no check", "unguarded"},
                ),
                recommendation_terms=(
                    {"call require_admin", "guard", "before reading params"},
                ),
                preferred_artifacts=("route_diff", "auth_middleware"),
            ),
        ),
    ),
    ReviewTask(
        task_id="refund-idempotency",
        title="Review a refund worker retry patch",
        difficulty="hard",
        objective="Determine whether the retry patch is safe under real payment retries and concurrent workers.",
        summary=(
            "Payments saw duplicate refunds during a processor outage. An engineer added a retry path in the refund worker. "
            "You need to decide if the patch prevents another incident."
        ),
        step_limit=6,
        starting_artifacts=("incident_ticket", "worker_diff"),
        artifacts={
            "incident_ticket": Artifact(
                artifact_id="incident_ticket",
                kind="ticket",
                title="Incident summary",
                preview="Processor timeout caused the worker to retry refunds; some customers were refunded twice.",
                content=(
                    "Root cause under investigation: payment processor timed out after accepting the refund. "
                    "The worker retried and created a second refund because no durable idempotency key was recorded."
                ),
            ),
            "worker_diff": Artifact(
                artifact_id="worker_diff",
                kind="file",
                title="workers/refunds.py diff",
                preview="Patch wraps `payments.refund` in retry logic and writes status after success.",
                content=(
                    "@@ workers/refunds.py\n"
                    "async def process_refund(job):\n"
                    "    try:\n"
                    "        result = await payments.refund(job.charge_id, amount=job.amount)\n"
                    "        await db.execute('UPDATE refunds SET status = ? WHERE id = ?', ['sent', job.id])\n"
                    "        return result\n"
                    "    except TimeoutError:\n"
                    "        return await payments.refund(job.charge_id, amount=job.amount)\n"
                ),
                reward=0.08,
            ),
            "payment_client": Artifact(
                artifact_id="payment_client",
                kind="file",
                title="integrations/payments.py",
                preview="`refund` accepts an optional idempotency_key but callers rarely pass it.",
                content=(
                    "async def refund(charge_id, amount, idempotency_key=None):\n"
                    "    payload = {'charge_id': charge_id, 'amount': amount}\n"
                    "    headers = {}\n"
                    "    if idempotency_key:\n"
                    "        headers['Idempotency-Key'] = idempotency_key\n"
                    "    return await processor.post('/refunds', json=payload, headers=headers)\n"
                ),
                reward=0.12,
            ),
            "db_model": Artifact(
                artifact_id="db_model",
                kind="file",
                title="models/refund.py",
                preview="Rows include `idempotency_key`, `status`, and `processor_refund_id`.",
                content=(
                    "refunds(id, charge_id, amount, status, idempotency_key, processor_refund_id, updated_at)\n"
                    "status values: queued, sent, confirmed, failed\n"
                ),
                reward=0.08,
            ),
            "worker_log": Artifact(
                artifact_id="worker_log",
                kind="log",
                title="Worker log excerpt",
                preview="Two workers processed the same refund id during retry storm.",
                content=(
                    "worker-a refund_id=rf_102 timeout from processor after 30s\n"
                    "worker-b refund_id=rf_102 picked queued job after visibility timeout\n"
                    "both requests returned processor_refund_id values"
                ),
                reward=0.10,
            ),
            "regression_test": Artifact(
                artifact_id="regression_test",
                kind="test",
                title="Missing regression test note",
                preview="No test covers timeout-after-success or concurrent dequeue.",
                content=(
                    "TODO: add integration test where processor commits refund then times out, and a second worker replays the same job."
                ),
                reward=0.07,
            ),
        },
        grader=(
            GraderCriterion(
                criterion_id="retry-without-idempotency",
                description="Reviewer flags that the retry calls refund twice without a durable idempotency key.",
                file_path="workers/refunds.py",
                severity="critical",
                weight=0.5,
                required_terms=(
                    {
                        "idempotency",
                        "duplicate refund",
                        "same refund twice",
                        "processor accepted",
                    },
                    {"timeout", "retry", "second call", "replay"},
                ),
                recommendation_terms=(
                    {"idempotency_key", "persist", "reuse"},
                    {"before calling processor", "db", "same key on retry"},
                ),
                preferred_artifacts=(
                    "worker_diff",
                    "payment_client",
                    "db_model",
                    "incident_ticket",
                ),
            ),
            GraderCriterion(
                criterion_id="status-update-race",
                description="Reviewer notes that status is updated only after the processor call, so concurrent workers can both send the refund.",
                file_path="workers/refunds.py",
                severity="high",
                weight=0.35,
                required_terms=(
                    {
                        "concurrent",
                        "two workers",
                        "race",
                        "visibility timeout",
                        "picked queued job",
                    },
                    {"status", "after success", "not locked", "before call"},
                ),
                recommendation_terms=(
                    {
                        "claim",
                        "lock",
                        "transaction",
                        "update status first",
                        "compare-and-set",
                    },
                ),
                preferred_artifacts=("worker_diff", "worker_log"),
            ),
            GraderCriterion(
                criterion_id="missing-regression-test",
                description="Reviewer asks for a test covering timeout-after-success and replay.",
                file_path="workers/refunds.py",
                severity="medium",
                weight=0.15,
                required_terms=(
                    {"test", "regression", "integration test"},
                    {
                        "timeout after success",
                        "replay",
                        "concurrent worker",
                        "duplicate refund",
                    },
                ),
                recommendation_terms=({"add", "cover", "simulate"},),
                preferred_artifacts=("regression_test",),
            ),
        ),
    ),
]


TASKS_BY_ID = {task.task_id: task for task in TASKS}


# ──────────────────────────────────────────────────────────────────────────────
# Compatibility shims — used by environment.py, app.py, and inference.py
# ──────────────────────────────────────────────────────────────────────────────


def list_tasks() -> List[Dict[str, object]]:
    """Return lightweight task metadata list (for /tasks endpoint)."""
    return [
        {
            "task_id": t.task_id,
            "difficulty": t.difficulty,
            "title": t.title,
            "objective": t.objective,
            "step_limit": t.step_limit,
        }
        for t in TASKS
    ]


def get_task(task_id: str) -> Dict[str, object]:
    """Return a task as a plain dict by ID. Raises ValueError if unknown."""
    if task_id not in TASKS_BY_ID:
        raise ValueError(
            f"Unknown task '{task_id}'. Available: {list(TASKS_BY_ID.keys())}"
        )
    t = TASKS_BY_ID[task_id]

    # Build the dict shape expected by environment.py
    return {
        "task_id": t.task_id,
        "difficulty": t.difficulty,
        "title": t.title,
        "objective": t.objective,
        "summary": t.summary,
        "step_limit": t.step_limit,
        "filename": _primary_file(t),
        "language": "python",
        "patch": _primary_diff(t),
        "artifacts": [
            {
                "artifact_id": a.artifact_id,
                "kind": a.kind,
                "title": a.title,
                "preview": a.preview,
                "content": a.content,
            }
            for a in t.artifacts.values()
        ],
        # Keep the native grader criteria accessible
        "_grader": t.grader,
    }


def grade_submission(
    task_id: str,
    review_text: str,
    findings: List[Dict] = None,
) -> Dict[str, object]:
    """
    Deterministic grader shim — bridges raw text / dict findings to grade_findings().

    Returns a dict with at minimum: {"score": float, "task_id": str, "difficulty": str}
    Score is always in [0.0, 1.0].
    """
    if task_id not in TASKS_BY_ID:
        raise ValueError(f"Unknown task '{task_id}'.")

    from codereview_env.models import ReviewFinding

    task = TASKS_BY_ID[task_id]

    # Convert dict findings to ReviewFinding objects where possible
    rf_list: List[ReviewFinding] = []
    if findings:
        for f in findings:
            try:
                rf_list.append(ReviewFinding(**f))
            except Exception:
                # If the dict doesn't match the schema, synthesise a minimal finding
                try:
                    rf_list.append(
                        ReviewFinding(
                            title=f.get("title", "finding"),
                            file_path=f.get("file_path", _primary_file(task)),
                            line_hint=f.get("line_hint"),
                            severity=f.get("severity", "medium"),
                            rationale=f.get("rationale", review_text[:200]),
                            recommendation=f.get("recommendation", "see rationale"),
                        )
                    )
                except Exception:
                    pass  # Skip unparseable findings

    # If no structured findings, synthesise one from the review_comment text
    if not rf_list and review_text and review_text.strip():
        try:
            rf_list.append(
                ReviewFinding(
                    title="Free-text review",
                    file_path=_primary_file(task),
                    line_hint=None,
                    severity="medium",
                    rationale=review_text[:500],
                    recommendation=review_text[:200],
                )
            )
        except Exception:
            pass

    # Determine which artifacts were "opened" (inferred from review text mentioning artifact IDs)
    text_lower = (review_text or "").lower()
    opened: Set[str] = {
        aid
        for aid in task.artifacts
        if aid.replace("_", " ") in text_lower or aid in text_lower
    }

    result = grade_findings(task, rf_list, opened)
    result["task_id"] = task_id
    result["difficulty"] = task.difficulty
    result["keyword_matches"] = sum(
        1 for c in result.get("criteria", []) if c["score"] > 0
    )
    result["total_keywords"] = len(result.get("criteria", []))
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────


def _primary_file(task: "ReviewTask") -> str:
    """Return the first grader criterion's file_path as the 'primary' file."""
    if task.grader:
        return task.grader[0].file_path
    return "unknown"


def _primary_diff(task: "ReviewTask") -> str:
    """Return the content of the first 'file' artifact as the primary diff."""
    for a in task.artifacts.values():
        if a.kind == "file":
            return a.content
    # Fallback: concatenate all artifact contents
    return "\n\n".join(a.content for a in task.artifacts.values())
