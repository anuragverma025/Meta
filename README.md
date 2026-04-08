---
title: CodeReview-Env
emoji: 🔍
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---
# 🔍 CodeReview-Env

> **A real-world OpenEnv Reinforcement Learning environment** that trains LLM agents
> to write high-quality, actionable code reviews across three difficulty tiers.

[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compliant-blue)](https://github.com/huggingface/openenv)
[![HF Spaces](https://img.shields.io/badge/🤗-HuggingFace%20Space-yellow)](https://huggingface.co/spaces)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-green)](https://python.org)

---

## 🎯 What This Solves

Every software team spends hours on code review. LLMs today give generic "looks good!" 
feedback that misses real bugs. **CodeReview-Env** trains agents to:

- **Spot bugs** — off-by-one errors, race conditions, logic flaws
- **Find security vulnerabilities** — SQL injection, plaintext passwords, missing rate limits
- **Understand concurrency** — TOCTOU races, broken locks, async pitfalls
- **Write actionable feedback** — specific line references, root cause, concrete fix

---

## 🗂️ Tasks (Easy → Medium → Hard)

| Task ID | Difficulty | Title | Key Bug |
|---|---|---|---|
| `easy-bug-hunt` | 🟢 Easy | Spot the Off-by-One Bug | Pagination index formula changed — breaks page ≥ 2 |
| `medium-security-audit` | 🟡 Medium | Security Audit: Login Endpoint | SQL injection + plaintext password + no rate limiting |
| `hard-async-race` | 🔴 Hard | Async Race Condition in Payment Processor | TOCTOU race + missing optimistic lock + float precision |

### Grader Design

Each task uses a **deterministic keyword-based grader** (no LLM required for grading):

- Maps `review_text + findings` against an expected keyword list
- Requires 40% of keywords for a full keyword score
- Adds a quality bonus for length, actionability, and non-laziness
- Weighted by difficulty: easy (80/20), medium (70/30), hard (60/40)

---

## 🏗️ Environment Design

### Action Space

```json
// Explore: open an artifact for more context (+0.05 reward each)
{"action_type": "open_artifact", "artifact_id": "diff-001"}

// Submit: final review with structured findings
{
  "action_type": "submit_review",
  "review_comment": "Overall summary...",
  "findings": [
    {
      "title": "SQL Injection via f-string",
      "file_path": "auth/login.py",
      "line_hint": "line 7",
      "severity": "critical",
      "rationale": "User input is interpolated directly into the SQL query...",
      "recommendation": "Use parameterized queries: cursor.execute(q, (username, password))"
    }
  ]
}
```

### Observation Space

Each step the agent sees:

| Field | Type | Description |
|---|---|---|
| `task_id` | str | Which task is active |
| `difficulty` | easy/medium/hard | Task difficulty tier |
| `pr_diff` | str | The git diff to review |
| `available_artifacts` | list | Artifacts not yet opened (preview only) |
| `opened_artifacts` | list | Artifacts opened this episode (with full content) |
| `step_count` / `step_limit` | int | Current and max steps |
| `score` | float | Running score after submission |
| `last_action_error` | str | Error message if last action failed |

### Reward Function

```
reward = 0.70 × task_grader_score + 0.30 × llm_reward_score
       + 0.05 × num_artifacts_opened  (exploration bonus, pre-submission)
```

- **task_grader_score** ∈ [0, 1]: Deterministic, keyword-based, reproducible
- **llm_reward_score** ∈ [0, 1]: Two-layer (0.40 programmatic + 0.60 LLM semantic)
- **exploration_bonus**: Partial progress signal between steps

### Episode Flow

```
reset(task_name) → Observation
    │
    ├── step(open_artifact)  →  [+0.05 partial reward, artifact revealed]
    ├── step(open_artifact)  →  [+0.05 partial reward, more context]
    │
    └── step(submit_review)  →  [grader score, episode done]
```

### 🖥️ Interactive Web Dashboard

To make RL debugging and evaluation intuitive, CodeReview-Env ships with a **built-in interactive web UI**.  
Available at the root (`/`) when running the server, the dashboard provides:
- **Live Episode Tracking**: Watch the AI open artifacts and form its review in real-time.
- **Diff & Artifact Viewer**: Render git diffs and code files directly in the browser.
- **Reward Breakdown**: See exactly how the keyword grader and reward function evaluate a finding.

---

## 🚀 Quick Start

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Set up environment
cp .env.example .env
# Edit .env: add your HF_TOKEN

# 3. Run the server
uvicorn server.app:app --host 0.0.0.0 --port 7860

# 4. Check health
curl http://localhost:7860/health

# 5. Run baseline inference
HF_TOKEN=hf_xxx MODEL_NAME=Qwen/Qwen2.5-72B-Instruct python inference.py
```

## 🐳 Docker

```bash
# Build
docker build -t codereview-env .

# Run
docker run -p 7860:7860 -e HF_TOKEN=hf_xxx codereview-env

# Test
curl http://localhost:7860/health
curl http://localhost:7860/tasks
```

## 🤗 HuggingFace Spaces

```bash
openenv push --repo-id your-username/codereview-env
```

---

## 📡 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness check |
| `/tasks` | GET | List all 3 tasks |
| `/tasks/{task_id}` | GET | Task detail |
| `/reset` | POST | Start episode: `{"task_name": "easy-bug-hunt"}` |
| `/step` | POST | Execute action: `{"session_id": "...", "action": {...}}` |
| `/state/{session_id}` | GET | Current episode state |
| `/grade` | POST | One-shot grading (no session): `{"task_id": ..., "review_comment": ...}` |
| `/reward-breakdown` | POST | Raw LLM reward breakdown |
| `/demo` | GET | Side-by-side bad vs. good review demo |
| `/docs` | GET | Interactive Swagger UI |

---

## 📊 Baseline Scores

Measured with `Qwen/Qwen2.5-72B-Instruct` via HF router:

| Task | Score | Steps | Success |
|---|---|---|---|
| `easy-bug-hunt` | ~0.72 | 2 | ✅ |
| `medium-security-audit` | ~0.58 | 3 | ✅ |
| `hard-async-race` | ~0.34 | 4 | ❌ |
| **Average** | **~0.55** | | |

---

## 📁 Project Structure

```
codereview_env/
├── Dockerfile                # Root-level — HF Spaces requirement
├── openenv.yaml              # OpenEnv spec: tasks, models, reward
├── inference.py              # Baseline inference (OpenAI client, [START]/[STEP]/[END])
├── server/
│   ├── app.py                # FastAPI routes
│   ├── environment.py        # CodeReviewEnvironment (reset/step/state)
│   ├── tasks.py              # 3 tasks + deterministic graders
│   ├── reward.py             # Two-layer LLM reward (RewardComputer)
│   ├── dataset_loader.py     # microsoft/CodeReviewer loader + fallback
│   └── requirements.txt
├── codereview_env/           # Python package (Pydantic models, client)
│   ├── models.py
│   └── client.py
├── frontend/                 # Dashboard UI
└── tests/                    # Regression tests
```

---

## 🙏 Credits

- [OpenEnv](https://github.com/huggingface/openenv) by Meta × HuggingFace
- [microsoft/CodeReviewer](https://huggingface.co/datasets/microsoft/CodeReviewer) dataset
- [HuggingFace TRL](https://github.com/huggingface/trl) for RL training utilities
