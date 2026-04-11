# CodeReview-Env — Hackathon Impact Statement

**(Meta × PyTorch × HuggingFace OpenEnv Hackathon 2026)**

---

## The Problem

Code review is one of the most time-consuming, high-stakes, and yet most poorly-automated
tasks in software engineering:

- Developers spend **6–12 hours per week** reviewing pull requests.
- Most LLMs today produce dangerously generic feedback: _"Looks good!"_, _"LGTM"_, _"Maybe add a test."_
- This low-quality output creates **alert fatigue** — developers stop trusting AI feedback
  and the review becomes perfunctory.
- Real production incidents (auth bypasses, duplicate payments, pagination data corruption)
  are missed because the model never looked beyond the first few lines of a diff.

---

## Why This Environment Is Unique

### 1. Genuinely Multi-Step Episodic Structure

Most RL environments for LLMs are single-step (prompt-in, completion-out). CodeReview-Env is
**genuinely multi-step**: an agent must decide _in sequence_ whether to gather more evidence
(`open_artifact`) or commit to a final review (`submit_review`). This forces the model to
learn a temporal exploration strategy, not just a single inference pattern.

```
reset() → observe diff + ticket
  ├── open_artifact(auth_middleware)   → +0.12 reward, artifact revealed
  ├── open_artifact(security_policy)  → +0.10 reward, policy revealed
  └── submit_review(findings=[...])   → grader score + efficiency bonus, done=True
```

### 2. Deterministic, Reproducible Grading — No LLM-as-a-Judge

The core reward signal uses a **multi-criterion keyword grader** (`server/tasks.py`) with
deterministic, reproducible scoring — no external LLM calls, no flakiness:

- Per-criterion scoring uses 5 weighted factors: `issue keywords`, `recommendation keywords`,
  `severity label`, `file path`, and `evidence trail` (which artifacts were opened).
- Rewards are always in the strictly open interval `(0.05, 0.95)` — never exactly 0 or 1 —
  enforced by `_clamp_score()` at every layer (`tasks.py`, `reward.py`, `environment.py`).

### 3. Evidence-Gated Difficulty Hierarchy

The three tasks are carefully designed so that **the harder tasks require more artifact
exploration to score well**, creating a natural curriculum:

| Task | # Criteria | Artifacts Needed to Score ≥ 0.60 | Baseline Score |
|---|---|---|---|
| `pagination-regression` | 2 | 1 (`test_log`) | ~0.74 |
| `tenant-export-auth` | 2 | 2 (`auth_middleware` + `security_policy`) | ~0.61 |
| `refund-idempotency` | 3 | 4 (`payment_client` + `worker_log` + `db_model` + `regression_test`) | ~0.38 |

The hardest task (`refund-idempotency`) requires multi-artifact correlation to detect all
three issues: the **retry-without-idempotency**, the **concurrent status-update race**, and
the **missing regression test**. A model that skips evidence gathering will miss at least one.

### 4. Strict Pydantic Enforcement

Agent outputs are validated by `codereview_env/models.py` before entering the environment:
- `ReviewFinding` requires `title` (≥5 chars), `file_path` (≥3 chars), `rationale` (≥20 chars),
  `recommendation` (≥12 chars), and a valid `severity` enum.
- `CodeReviewObservation` enforces `score` and `reward` fields as Pydantic `gt=0.0`, `lt=1.0`.

This forces agents to output **structured, actionable findings** rather than free-text markdown.

### 5. Interactive Web Dashboard

Unlike typical headless RL environments, CodeReview-Env ships with a fully integrated
real-time web dashboard (`frontend/index.html`) served at `/` by the FastAPI backend:

- Live episode tracking — watch the agent open artifacts and form its review.
- Diff and artifact viewer — renders code files and policies directly in the browser.
- Reward breakdown — shows how the grader evaluated each finding in real-time.
- Task selector — switch between all three tasks interactively.

### 6. Safety Layer

`codereview_env/safety.py` provides:
- **`PaginationValidator`** — Guards all pagination inputs against type errors and out-of-range
  values before they reach the underlying pagination system. This mirrors the exact bug in the
  `pagination-regression` task, making the environment self-documenting.
- **`SafeRewardCalculator`** — Wraps reward math with the same `max/min` clamping and
  late-rounding pattern used across the rest of the codebase.

---

## Technical Novelty Summary

| Feature | Other RL Envs | CodeReview-Env |
|---|---|---|
| Episode structure | Single step | Multi-step (up to 7 steps) |
| Reward signal | LLM judge (flaky) | Deterministic keywords + evidence trail |
| Reward bounds | Often 0.0 or 1.0 | Strictly (0.05, 0.95) — enforced everywhere |
| Output validation | Free-form text | Pydantic schema with min-length constraints |
| Artifact exploration | None | 3–6 artifacts per task, each with reward |
| Difficulty tiers | Flat | 3 tiers with evidence-gated scoring |
| Training framework | Custom | TRL-compatible GRPO reward function |
| Deployment | Often local-only | Docker + HuggingFace Spaces ready |

---

## Real-World Impact

- A model trained here could autonomously triage PRs at **enterprise scale** — reviewing
  100+ PRs per day with precise, finding-level comments.
- Replaces vague AI suggestions with **targeted, line-specific security interventions** that
  static analysis tools universally miss (auth bypasses, TOCTOU races, payment idempotency).
- Trained agents learn to **justify their findings** — providing rationale and recommendation
  in a format engineers can immediately act on.

---

## Future Extensions

- **Continuous task generation** — Dynamically generate new CVE-inspired tasks to prevent
  benchmark overfitting.
- **CI/CD integration** — Deploy the trained agent as a GitHub Actions bot that reviews
  incoming PRs automatically.
- **Fix-Application loop** — Add a `push_commit` action where the agent patches the code
  based on its own review findings and verifies unit tests pass.
- **Multi-agent review** — Multiple agents reviewing the same PR and reaching consensus.

---

## Compatibility Matrix

Fully tested and optimized for:

| Framework | Usage |
|---|---|
| `openenv-core` | Environment base class (`Environment[Obs, Act, State]`) |
| `TRL` (GRPO / PPO) | Reward function via `CodeReviewEnv.get_reward_breakdown()` |
| `Unsloth` | Drop-in with TRL GRPO config |
| `SkyRL` | Compatible via standard OpenAI-style API |
| HuggingFace Spaces | Docker SDK, port 7860, root-level Dockerfile |

See [`examples/run_grpo_training.py`](examples/run_grpo_training.py) for the TRL GRPO
training integration boilerplate.
