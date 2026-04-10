from __future__ import annotations

import importlib
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def inference_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HF_TOKEN", "test-token")
    import inference

    return importlib.reload(inference)


def test_require_hf_token_raises_at_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    import inference

    module = importlib.reload(inference)

    with pytest.raises(ValueError, match="HF_TOKEN environment variable is required"):
        module._require_hf_token()


def test_run_task_emits_required_stdout_format(
    inference_module, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def choose_action(
        client: MagicMock,
        task_id: str,
        observation: dict[str, object],
        opened_ids: list[str],
    ) -> dict[str, object]:
        return inference_module._scripted_policy(task_id, opened_ids)

    monkeypatch.setattr(inference_module, "_choose_action", choose_action)

    inference_module._run_task("pagination-regression", MagicMock())

    lines = capsys.readouterr().out.strip().splitlines()

    assert re.fullmatch(
        rf"\[START\] task=pagination-regression env={inference_module.BENCHMARK} "
        rf"model={re.escape(inference_module.MODEL_NAME)}",
        lines[0],
    )
    assert re.fullmatch(
        r'\[STEP\] step=1 action=\{"action_type":"open_artifact","artifact_id":"test_log","note":"Need the failing test\."\} reward=\d+\.\d{2} done=false error=null',
        lines[1],
    )
    assert re.fullmatch(
        r"\[END\] success=true steps=2 rewards=\d+\.\d{2},\d+\.\d{2}",
        lines[-1],
    )
    assert "score=" not in lines[-1]
    assert '"metadata"' not in lines[1]
