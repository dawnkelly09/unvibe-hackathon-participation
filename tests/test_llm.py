"""Tests for ``lib/llm.py``.

These validate the plumbing — backend dispatch, recording, retry —
not model output quality.

Tests marked ``@pytest.mark.integration`` hit a live Ollama daemon.
Skip with ``pytest -m 'not integration'`` in environments without
Ollama running. Tests for unknown-backend / missing-model do NOT need
the marker — they raise before any network call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.llm import (  # noqa: E402
    LLMCallError,
    call_model,
    call_model_for_json,
    call_model_with_record,
)

OLLAMA_TEST_MODEL = "ollama:qwen2.5:7b"


# ---------------------------------------------------------------------------
# Plumbing tests — no network
# ---------------------------------------------------------------------------

def test_unknown_backend_raises():
    """Unknown backend prefix raises before any network call."""
    with pytest.raises(LLMCallError, match="Unknown backend"):
        call_model("hi", model="fakeprovider:something")


def test_missing_model_raises(monkeypatch):
    """No ``model`` arg and no MODEL env var raises a clear error."""
    monkeypatch.delenv("MODEL", raising=False)
    with pytest.raises(LLMCallError, match="No model specified"):
        call_model("hi")


def test_invalid_model_string_raises():
    """Model strings without a backend prefix raise."""
    with pytest.raises(LLMCallError, match="Invalid model string"):
        call_model("hi", model="just-a-name")


# ---------------------------------------------------------------------------
# Integration tests — require local Ollama
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_call_model_basic():
    """Trivial prompt returns a non-empty string."""
    out = call_model(
        "Respond with the word OK and nothing else.",
        model=OLLAMA_TEST_MODEL,
    )
    assert isinstance(out, str)
    assert out.strip() != ""


@pytest.mark.integration
def test_call_model_with_record_writes_file(tmp_path):
    """A successful call writes a record with the spec'd shape."""
    out = call_model_with_record(
        "Respond with the word OK and nothing else.",
        record_dir=tmp_path,
        record_label="basic-test",
        model=OLLAMA_TEST_MODEL,
    )
    assert isinstance(out, str)

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    expected_keys = {
        "timestamp", "model", "label", "system", "prompt",
        "response", "latency_ms", "error",
    }
    assert expected_keys <= set(record)
    assert record["label"] == "basic-test"
    assert record["model"] == OLLAMA_TEST_MODEL
    assert record["error"] is None
    assert record["response"] is not None
    assert isinstance(record["latency_ms"], int)
    # Filename contains the slugified label.
    assert "basic-test" in files[0].name


@pytest.mark.integration
def test_call_model_with_record_writes_on_error(tmp_path):
    """A failing call still writes a record, then re-raises."""
    bad_model = "ollama:nonexistent-12345"
    with pytest.raises(LLMCallError):
        call_model_with_record(
            "anything",
            record_dir=tmp_path,
            record_label="error-test",
            model=bad_model,
        )

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["response"] is None
    assert record["error"] is not None
    assert record["model"] == bad_model
    assert record["label"] == "error-test"


@pytest.mark.integration
def test_call_model_for_json_basic(tmp_path):
    """JSON prompt parses into a dict with the requested keys."""
    result = call_model_for_json(
        'Respond with the JSON object {"status": "ok"} and nothing else. '
        "No prose, no code fences.",
        record_dir=tmp_path,
        record_label="json-basic",
        model=OLLAMA_TEST_MODEL,
    )
    assert isinstance(result, dict)
    assert result.get("status") == "ok"


# Note: a deterministic test for the code-fence stripping isn't possible
# because we can't force the model to wrap output in fences. The strip
# logic is exercised in real use; ``_strip_json_artifacts`` is also
# trivial enough to read.
