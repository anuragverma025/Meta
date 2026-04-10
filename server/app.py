from __future__ import annotations

from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
from typing import Any
import uvicorn

from codereview_env.models import (
    CodeReviewAction,
    CodeReviewObservation,
    CodeReviewState,
)
from server.environment import CodeReviewEnvironment
from server.tasks import TASKS, TASKS_BY_ID, grade_submission


def make_env() -> CodeReviewEnvironment:
    return CodeReviewEnvironment()


app = FastAPI(title="CodeReview-Env", version="2.0.0")
_sessions: dict[str, CodeReviewEnvironment] = {}
_latest_session_id: str | None = None
_session_lock = Lock()
_current_dir = Path(__file__).resolve().parent
_root_dir = _current_dir.parent

# Robust path resolution for frontend
_frontend_dir = (_root_dir / "frontend").resolve()
if not _frontend_dir.exists():
    # Attempt to find it relative to current working directory
    _frontend_dir = (Path.cwd() / "frontend").resolve()

if not _frontend_dir.exists():
    # Fallback for container structured where source might be in /app
    _frontend_dir = Path("/app/frontend").resolve()

app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")


def _serialize_step(observation: CodeReviewObservation, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "observation": observation.model_dump(),
        "reward": observation.reward,
        "done": observation.done,
    }


def _resolve_session(session_id: str | None) -> tuple[str, CodeReviewEnvironment]:
    selected_session_id = session_id or _latest_session_id
    if not selected_session_id or selected_session_id not in _sessions:
        raise HTTPException(
            status_code=404, detail="No active session. Call /reset first."
        )
    return selected_session_id, _sessions[selected_session_id]


@app.get("/", include_in_schema=False, response_model=None)
@app.get("/index.html", include_in_schema=False, response_model=None)
@app.get("/ui", include_in_schema=False, response_model=None)
def root(request: Request) -> Any:
    index_path = _frontend_dir / "index.html"

    # Debug info for logs
    print(f"DEBUG: Root request for {request.url.path}")
    print(f"DEBUG: Looking for index.html at {index_path}")

    if not index_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "Dashboard files missing",
                "searched_at": str(index_path),
                "cwd": os.getcwd(),
                "frontend_dir_exists": _frontend_dir.exists(),
                "frontend_dir": str(_frontend_dir),
                "files_in_frontend": (
                    os.listdir(str(_frontend_dir)) if _frontend_dir.exists() else []
                ),
            },
        )
    return FileResponse(index_path)


@app.get("/health", tags=["Health"])
def health() -> dict:
    return {
        "status": "ok",
        "benchmark": "codereview-env",
        "task_count": len(TASKS),
        "tasks": [task.task_id for task in TASKS],
    }


@app.get("/tasks", tags=["Environment Info"])
def tasks() -> list[dict]:
    return [
        {
            "task_id": task.task_id,
            "title": task.title,
            "difficulty": task.difficulty,
            "objective": task.objective,
            "step_limit": task.step_limit,
        }
        for task in TASKS
    ]


@app.get("/tasks/{task_id}", tags=["Environment Info"])
def task_detail(task_id: str) -> dict:
    if task_id not in TASKS_BY_ID:
        raise HTTPException(status_code=404, detail=f"Unknown task_id: {task_id}")
    task = TASKS_BY_ID[task_id]
    return {
        "task_id": task.task_id,
        "title": task.title,
        "difficulty": task.difficulty,
        "objective": task.objective,
        "summary": task.summary,
        "step_limit": task.step_limit,
        "artifacts": [artifact.artifact_id for artifact in task.artifacts.values()],
    }


@app.get("/metadata", tags=["Environment Info"])
def metadata() -> dict:
    env = make_env()
    try:
        return env.get_metadata()
    finally:
        env.close()


@app.post("/reset", tags=["Episode"])
def reset(payload: dict | None = None) -> dict:
    global _latest_session_id

    body = payload or {}
    env = make_env()
    task_id = body.get("task_id") or body.get("task_name")
    observation = env.reset(
        seed=body.get("seed"),
        episode_id=body.get("episode_id"),
        task_id=task_id,
    )
    session_id = body.get("session_id") or str(uuid4())
    with _session_lock:
        _sessions[session_id] = env
        _latest_session_id = session_id
    return _serialize_step(observation, session_id)


@app.post("/step", tags=["Episode"])
def step(payload: dict) -> dict:
    session_id, env = _resolve_session(payload.get("session_id"))
    action = CodeReviewAction.model_validate(payload.get("action", {}))
    observation = env.step(action)
    return _serialize_step(observation, session_id)


@app.get("/state", tags=["Episode"])
def state() -> CodeReviewState:
    _, env = _resolve_session(None)
    return env.state


@app.get("/state/{session_id}", tags=["Episode"])
def state_by_id(session_id: str) -> CodeReviewState:
    _, env = _resolve_session(session_id)
    return env.state


@app.post("/grade", tags=["Evaluation"])
def grade(payload: dict) -> dict:
    task_id = payload.get("task_id") or payload.get("task_name")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")
    return grade_submission(
        task_id=task_id,
        review_text=payload.get("review_comment", ""),
        findings=payload.get("findings") or [],
    )


@app.get("/demo", tags=["Evaluation"])
def demo() -> dict:
    return {
        "task_id": "tenant-export-auth",
        "bad_review": "Looks fine to me.",
        "good_review": (
            "This route is missing both require_admin and require_account_scope, "
            "so another tenant's invoices can be exported by passing an arbitrary account_id."
        ),
    }


@app.exception_handler(KeyError)
async def handle_key_error(request: Request, exc: KeyError) -> JSONResponse:
    return JSONResponse(
        status_code=400, content={"error": f"Unknown key: {exc.args[0]}"}
    )


def main() -> None:
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
