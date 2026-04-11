---
title: CodeReview-Env
emoji: 🔍
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 🔍 CodeReview-Env

> **A production-grade OpenEnv Reinforcement Learning environment** for training LLM agents
> to write high-quality, actionable code reviews across three difficulty tiers — built for the
> **Meta × PyTorch × HuggingFace OpenEnv Hackathon 2026**.

[![OpenEnv Compliant](https://img.shields.io/badge/OpenEnv-Compliant-blue?logo=huggingface)](https://github.com/huggingface/openenv)
[![HF Space](https://img.shields.io/badge/🤗-Live%20on%20HuggingFace-yellow)](https://huggingface.co/spaces/Anurag137/codereview-env)
[![GitHub](https://img.shields.io/badge/GitHub-anuragverma025%2FMeta-black?logo=github)](https://github.com/anuragverma025/Meta)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-green?logo=python)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 What Problem Does This Solve?

Every software team spends **6–12 hours per week** on code reviews. Yet most LLMs today produce
generic, unhelpful feedback — "Looks good!", "LGTM" — that misses real production bugs.

**CodeReview-Env** creates a rigorous RL training ground where agents must:

| Skill | What They Learn |
|---|---|
| 🐛 **Bug Detection** | Off-by-one errors, pagination edge cases, logic flaws |
| 🔒 **Security Auditing** | SQL injection, auth bypass, cross-tenant data leaks |
| ⚡ **Concurrency Analysis** | TOCTOU races, idempotency failures, retry loops |
| 📝 **Actionable Writing** | Specific line references, root cause, concrete fix recommendations |

A model trained here can autonomously triage PRs at enterprise scale — replacing vague AI
feedback with targeted, line-specific, security-aware interventions.

---

## 🗂️ Tasks (Easy → Medium → Hard)

All three tasks are drawn from realistic engineering scenarios with **deterministic graders** —
no LLM-as-a-judge flakiness for the core reward signal.

| Task ID | Difficulty | Engineering Scenario | Core Finding |
|---|---|---|---|
| `pagination-regression` | 🟢 Easy | Pagination bug fix before release | Off-by-one fix is correct but page 0 / negative pages create dangerous negative-index slices |
| `tenant-export-auth` | 🟡 Medium | Multi-tenant finance CSV export endpoint | `account_id` read from query params with no scope validation → cross-tenant data leak + missing admin-role gate |
| `refund-idempotency` | 🔴 Hard | Refund worker retry patch | Retry without idempotency key + concurrent-worker status-update race + missing regression test |

### ⚖️ Grader Design

Each task uses a **deterministic keyword-based grader** (no external LLM calls required):

- Parses `review_comment` + `findings` against per-task expected keyword lists
- Requires ≥ 40% keyword coverage for full keyword score
- Adds quality bonus: length, actionability, non-vagueness
- Weighted by difficulty: easy (80/20 grader/quality), medium (70/30), hard (60/40)
- All scores clamped to `(0.01, 0.99)` — never exactly 0 or 1

---

## 🏗️ Architecture & Environment Design

```
┌─────────────────────────────────────────────────────────────┐
│                       RL Agent (LLM)                         │
├─────────────────────────────────────────────────────────────┤
│  Action Space (JSON)                                         │
│  ├── open_artifact  → reveal context, earn +0.05 bonus       │
│  └── submit_review  → structured findings → graded, done     │
├─────────────────────────────────────────────────────────────┤
│  Observation Space                                           │
│  ├── task_id, difficulty, pr_diff                            │
│  ├── available_artifacts / opened_artifacts                  │
│  ├── step_count / step_limit                                 │
│  ├── score (running), last_action_error                      │
├─────────────────────────────────────────────────────────────┤
│  Reward Function                                             │
│  ├── 70% task_grader_score   (deterministic, keywords)       │
│  ├── 30% llm_reward_score    (40% programmatic + 60% LLM)   │
│  └── 0.05 × artifacts opened (exploration shaping)          │
└─────────────────────────────────────────────────────────────┘
```

### 🔄 Action Space

```json
// Explore: open an artifact for more context (+0.05 reward each)
{"action_type": "open_artifact", "artifact_id": "diff-001"}

// Submit: final review with structured findings
{
  "action_type": "submit_review",
  "review_comment": "Overall summary of findings...",
  "findings": [
    {
      "title": "Cross-tenant data leak via unvalidated account_id",
      "file_path": "api/export.py",
      "line_hint": "line 14",
      "severity": "critical",
      "rationale": "account_id is taken from the query param without verifying it belongs to the authenticated tenant...",
      "recommendation": "Validate request.user.account_id == account_id; raise HTTP 403 otherwise."
    }
  ]
}
```

### 👁️ Observation Space

| Field | Type | Description |
|---|---|---|
| `task_id` | str | Active task (e.g., `pagination-regression`) |
| `difficulty` | easy / medium / hard | Task difficulty tier |
| `pr_diff` | str | The git diff to review |
| `available_artifacts` | list | Unopened artifacts (preview title only) |
| `opened_artifacts` | list | Artifacts opened this episode (with full content) |
| `step_count` / `step_limit` | int | Current and maximum steps |
| `score` | float ∈ (0.01, 0.99) | Running score after submission |
| `last_action_error` | str | Error message if last action failed |

### 📐 Episode Flow

```
reset(task_name) → Observation
    │
    ├── step(open_artifact)  →  [+0.05 partial reward, artifact revealed]
    ├── step(open_artifact)  →  [+0.05 partial reward, more evidence]
    │
    └── step(submit_review)  →  [deterministic grader + LLM reward, done=True]
```

### 🖥️ Interactive Web Dashboard

CodeReview-Env ships with a **built-in real-time web dashboard** — making RL debugging
intuitive rather than headless. Available at `/` when running the server:

- **Live Episode Tracking** — Watch the agent open artifacts and form its review in real-time
- **Diff & Artifact Viewer** — Renders git diffs and code files directly in the browser
- **Reward Breakdown** — See exactly how the keyword grader and LLM reward evaluate each finding
- **Task Selector** — Switch tasks and replay episodes interactively

---

## 🚀 Quick Start

### Local Development

```bash
# 1. Clone
git clone https://github.com/anuragverma025/Meta.git
cd Meta/codereview_env

# 2. Install
pip install -e ".[dev]"

# 3. Set up environment
cp .env.example .env
# Edit .env: add HF_TOKEN and OPENAI_BASE_URL

# 4. Run the server
uvicorn server.app:app --host 0.0.0.0 --port 7860

# 5. Health check
curl http://localhost:7860/health

# 6. Run baseline inference
HF_TOKEN=hf_xxx MODEL_NAME=Qwen/Qwen2.5-72B-Instruct python inference.py
```

### 🐳 Docker

```bash
# Build
docker build -t codereview-env .

# Run
docker run -p 7860:7860 \
  -e HF_TOKEN=hf_xxx \
  -e OPENAI_BASE_URL=https://api-inference.huggingface.co/v1 \
  codereview-env

# Verify
curl http://localhost:7860/health
curl http://localhost:7860/tasks
```

### 🤗 Deploy to HuggingFace Spaces

```bash
# Push to your HF Space
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/codereview-env
git push hf main

# Or via openenv CLI
openenv push --repo-id YOUR_USERNAME/codereview-env
```

**Live Demo**: [huggingface.co/spaces/Anurag137/codereview-env](https://huggingface.co/spaces/Anurag137/codereview-env)

---

## 📡 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness check — returns `{"status": "ok"}` |
| `/tasks` | GET | List all 3 tasks with metadata |
| `/tasks/{task_id}` | GET | Full task detail + artifacts |
| `/reset` | POST | Start episode: `{"task_name": "pagination-regression"}` |
| `/step` | POST | Execute action: `{"session_id": "...", "action": {...}}` |
| `/state/{session_id}` | GET | Current episode state |
| `/grade` | POST | One-shot grading (no session needed) |
| `/reward-breakdown` | POST | Raw LLM reward breakdown for any review |
| `/demo` | GET | Side-by-side bad vs. good review demo |
| `/docs` | GET | Interactive Swagger UI |

---

## 📊 Baseline Scores

Measured with `Qwen/Qwen2.5-72B-Instruct` via HuggingFace Inference API:

| Task | Score | Steps Used | Outcome |
|---|---|---|---|
| `pagination-regression` | ~0.74 | 2 | ✅ Pass |
| `tenant-export-auth` | ~0.61 | 3 | ✅ Pass |
| `refund-idempotency` | ~0.38 | 4 | ❌ Needs improvement |
| **Average** | **~0.58** | | |

> All scores strictly in `(0.01, 0.99)` — endpoint values are never possible by design.

---

## 📁 Project Structure

```
codereview_env/
├── Dockerfile                # Root-level — HF Spaces requirement
├── openenv.yaml              # OpenEnv spec: tasks, reward, episode config
├── inference.py              # Baseline inference (OpenAI client, [START]/[STEP]/[END] logging)
├── HACKATHON.md              # Hackathon impact statement
├── server/
│   ├── app.py                # FastAPI routes (reset, step, grade, demo, health)
│   ├── environment.py        # CodeReviewEnvironment (reset / step / compute_state)
│   ├── tasks.py              # 3 tasks + deterministic keyword graders
│   ├── reward.py             # Two-layer reward (RewardComputer: programmatic + LLM)
│   ├── dataset_loader.py     # microsoft/CodeReviewer loader + dataset fallback
│   └── requirements.txt      # Server dependencies
├── codereview_env/           # Python package (Pydantic models, HTTP client)
│   ├── models.py             # Action, Observation, Finding, Episode models
│   └── client.py             # HTTP client for remote environments
├── frontend/
│   └── index.html            # Real-time web dashboard (vanilla JS, WebSocket-ready)
├── examples/                 # Example agent scripts and usage demos
└── tests/                    # Regression + smoke tests
```

---

## 🔗 Links

| Resource | URL |
|---|---|
| 🤗 Live HF Space | https://huggingface.co/spaces/Anurag137/codereview-env |
| 💻 GitHub Repo | https://github.com/anuragverma025/Meta |
| 📖 OpenEnv Spec | https://github.com/huggingface/openenv |
| 📦 HuggingFace TRL | https://github.com/huggingface/trl |
| 📊 CodeReviewer Dataset | https://huggingface.co/datasets/microsoft/CodeReviewer |

---

## 🙏 Credits & Acknowledgements

- [OpenEnv](https://github.com/huggingface/openenv) — RL environment specification by Meta × HuggingFace
- [microsoft/CodeReviewer](https://huggingface.co/datasets/microsoft/CodeReviewer) — Code review dataset
- [HuggingFace TRL](https://github.com/huggingface/trl) — RL training utilities (GRPO, PPO)
- Compatible with: **TRL**, **Unsloth**, **SkyRL**, **openenv-core**

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

Built with ❤️ for the **Meta × PyTorch × HuggingFace OpenEnv Hackathon 2026**
