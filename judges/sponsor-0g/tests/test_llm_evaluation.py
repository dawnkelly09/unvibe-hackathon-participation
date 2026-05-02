"""Tests for sponsor-0g llm_evaluation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import llm_evaluation as le  # noqa: E402
import sponsor_0g_judge as wrap  # noqa: E402
from _ingest_parsing import ParsedRepo  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parsed(*, readme: str | None = "# Demo\n\nA toy project.\n",
                 files: dict[str, str] | None = None) -> ParsedRepo:
    files = dict(files or {})
    if readme is not None:
        files.setdefault("README.md", readme)
    return ParsedRepo(
        metadata={"source_url": "https://github.com/test/proj", "repository": "test/proj", "commit": "abc"},
        files=files,
        readme_path="README.md" if readme is not None else None,
        readme_content=readme,
    )


def _prefilter(items: dict | None = None) -> dict:
    return {
        "judge": "sponsor-0g",
        "phase": "deterministic-prefilter",
        "items": items or {},
    }


def _good_call_a(*, framework: bool = True, agents: bool = True) -> dict:
    return {
        "framework_applicable": framework,
        "agents_applicable": agents,
        "components_used": ["Storage", "Compute"],
        "reasoning": "Project uses 0G Storage in src/store.ts and 0G Compute via HTTP proxy.",
        "confidence": "medium",
    }


def _good_call_b(items: tuple[str, ...]) -> dict:
    return {
        "rubric_items": {item: "pass" for item in items},
        "integration_verdict": "present",
        "reasoning": "All rubric items satisfied per repo evidence.",
    }


class _StubModel:
    """Stand-in for ``call_model_for_json`` that returns queued responses."""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, prompt, *, record_dir, record_label, model=None, **kwargs):
        self.calls.append({
            "label": record_label,
            "prompt": prompt,
            "model": model,
            "record_dir": record_dir,
        })
        if not self._responses:
            raise AssertionError(
                f"unexpected LLM call (label={record_label!r}); no responses queued"
            )
        return self._responses.pop(0)


# ===========================================================================
# Context pack
# ===========================================================================

def test_context_pack_happy_path():
    src = (
        "import { ZgStorage } from '@0glabs/0g-ts-sdk';\n"
        "// line 2\n"
        "// line 3\n"
        "// line 4\n"
        "// line 5\n"
        "const s = new ZgStorage();\n"
    )
    parsed = _make_parsed(
        readme="# Project\n\nUses 0G Storage.\n",
        files={
            "package.json": '{"dependencies": {"@0glabs/0g-ts-sdk": "^0.1.0"}}',
            "src/store.ts": src,
        },
    )
    prefilter = _prefilter({
        "0g-sdk-imports": {
            "present": True,
            "evidence": [
                {"file": "src/store.ts", "line": 1, "snippet": "import...", "identifier": "@0glabs/0g-ts-sdk"},
            ],
        },
    })
    pack = le._build_context_pack(parsed, prefilter)

    # README content present
    assert "Uses 0G Storage." in pack
    # Manifest present, fenced as JSON
    assert "### package.json" in pack
    assert '"@0glabs/0g-ts-sdk"' in pack
    # Source-file excerpt under SDK import sites
    assert "## SDK import sites" in pack
    assert "### src/store.ts (line 1)" in pack
    assert "ZgStorage" in pack


def test_context_pack_no_readme():
    parsed = _make_parsed(readme=None, files={"package.json": "{}"})
    pack = le._build_context_pack(parsed, _prefilter())
    assert "## README" in pack
    assert "_No README found in the repo._" in pack


def test_context_pack_token_ceiling_truncates_readme():
    big_readme = "# Project\n\n" + "\n".join(
        f"line-{i:05d} " + "x" * 80 for i in range(2000)
    )
    assert len(big_readme) > 100_000
    parsed = _make_parsed(readme=big_readme, files={"package.json": "{}"})
    pack = le._build_context_pack(parsed, _prefilter())

    assert "_[truncated for length]_" in pack
    # First README lines preserved
    assert "line-00000" in pack
    # Last README lines preserved
    assert "line-01999" in pack
    # And the pack came down a lot from the raw input.
    assert len(pack) < len(big_readme)


# ===========================================================================
# Phase 2 — both tracks applicable
# ===========================================================================

def test_phase2_both_tracks_applicable(tmp_path, monkeypatch):
    parsed = _make_parsed()
    stub = _StubModel([
        _good_call_a(framework=True, agents=True),
        _good_call_b(le.FRAMEWORK_RUBRIC_ITEMS),
        _good_call_b(le.AGENTS_RUBRIC_ITEMS),
    ])
    monkeypatch.setattr(le, "call_model_for_json", stub)

    result = le.run_llm_evaluation(
        repo_url="https://github.com/test/proj",
        prefilter=_prefilter(),
        parsed=parsed,
        records_dir=tmp_path,
        model="ollama:fake",
    )

    assert [c["label"] for c in stub.calls] == [
        "track-classification", "framework-rubric", "agents-rubric",
    ]
    assert result["tracks"]["framework"] is not None
    assert result["tracks"]["agents"] is not None
    assert set(result["tracks"]["framework"]["rubric_items"]) == set(le.FRAMEWORK_RUBRIC_ITEMS)
    assert set(result["tracks"]["agents"]["rubric_items"]) == set(le.AGENTS_RUBRIC_ITEMS)
    assert result["model"] == "ollama:fake"


def test_phase2_neither_track_applicable(tmp_path, monkeypatch):
    parsed = _make_parsed()
    stub = _StubModel([_good_call_a(framework=False, agents=False)])
    monkeypatch.setattr(le, "call_model_for_json", stub)

    result = le.run_llm_evaluation(
        repo_url="https://github.com/test/proj",
        prefilter=_prefilter(),
        parsed=parsed,
        records_dir=tmp_path,
        model="ollama:fake",
    )

    assert len(stub.calls) == 1
    assert stub.calls[0]["label"] == "track-classification"
    assert result["tracks"]["framework"] is None
    assert result["tracks"]["agents"] is None


# ===========================================================================
# Schema validation
# ===========================================================================

def test_phase2_invalid_components_used_raises(tmp_path, monkeypatch):
    bad_a = _good_call_a()
    bad_a["components_used"] = ["storage"]  # lowercase — invalid
    stub = _StubModel([bad_a])
    monkeypatch.setattr(le, "call_model_for_json", stub)

    with pytest.raises(le.LLMSchemaError) as excinfo:
        le.run_llm_evaluation(
            repo_url="https://github.com/test/proj",
            prefilter=_prefilter(),
            parsed=_make_parsed(),
            records_dir=tmp_path,
            model="ollama:fake",
        )
    msg = str(excinfo.value)
    assert "components_used" in msg
    assert "storage" in msg


def test_phase2_missing_rubric_item_raises(tmp_path, monkeypatch):
    bad_b = _good_call_b(le.FRAMEWORK_RUBRIC_ITEMS)
    # Drop one required item.
    del bad_b["rubric_items"]["working-example-agent"]
    stub = _StubModel([_good_call_a(framework=True, agents=False), bad_b])
    monkeypatch.setattr(le, "call_model_for_json", stub)

    with pytest.raises(le.LLMSchemaError) as excinfo:
        le.run_llm_evaluation(
            repo_url="https://github.com/test/proj",
            prefilter=_prefilter(),
            parsed=_make_parsed(),
            records_dir=tmp_path,
            model="ollama:fake",
        )
    msg = str(excinfo.value)
    assert "working-example-agent" in msg


# ===========================================================================
# Wrapper — --skip-upstream-check
# ===========================================================================

def test_wrapper_skip_upstream_check_bypasses_failed_upstream(
    tmp_path, monkeypatch, capsys
):
    repo_url = "https://github.com/test/proj"
    slug = "github.com_test_proj"

    safe_repo_root = tmp_path / "safe-repo-findings"
    hackathon_root = tmp_path / "hackathon-findings"
    prefilter_dir = tmp_path / "prefilter"
    llm_output_dir = tmp_path / "llm-output"
    records_root = tmp_path / "records"
    findings_dir = tmp_path / "findings"

    safe_repo_path = safe_repo_root / slug / "safe-repo.json"
    safe_repo_path.parent.mkdir(parents=True)
    safe_repo_path.write_text(json.dumps({"passed": True}))

    hackathon_path = hackathon_root / slug / "event-policy.json"
    hackathon_path.parent.mkdir(parents=True)
    hackathon_path.write_text(json.dumps({
        "passed": False,
        "verdict": "failed-first-commit",
    }))

    monkeypatch.setattr(wrap, "SAFE_REPO_FINDINGS_DIR", safe_repo_root)
    monkeypatch.setattr(wrap, "HACKATHON_FINDINGS_DIR", hackathon_root)
    monkeypatch.setattr(wrap, "DEFAULT_PREFILTER_DIR", prefilter_dir)
    monkeypatch.setattr(wrap, "DEFAULT_LLM_OUTPUT_DIR", llm_output_dir)
    monkeypatch.setattr(wrap, "DEFAULT_RECORDS_DIR", records_root)

    def stub_phase1(_repo_url):
        prefilter_dir.mkdir(parents=True, exist_ok=True)
        (prefilter_dir / f"{slug}.json").write_text(json.dumps({
            "judge": "sponsor-0g",
            "phase": "deterministic-prefilter",
            "items": {},
        }))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    def stub_phase2(_repo_url, _model):
        llm_output_dir.mkdir(parents=True, exist_ok=True)
        (llm_output_dir / f"{slug}.json").write_text(json.dumps({
            "judge": "sponsor-0g",
            "phase": "llm-evaluation",
            "classification": {
                "framework_applicable": True,
                "agents_applicable": False,
                "components_used": ["Storage"],
                "reasoning": "Uses 0G Storage.",
                "confidence": "medium",
            },
            "tracks": {
                "framework": {
                    "rubric_items": {
                        item: "pass" for item in le.FRAMEWORK_RUBRIC_ITEMS
                    },
                    "integration_verdict": "present",
                    "reasoning": "All items pass.",
                },
                "agents": None,
            },
        }))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(wrap, "_run_phase1", stub_phase1)
    monkeypatch.setattr(wrap, "_run_phase2", stub_phase2)

    summary, rc = wrap.run(
        repo_url,
        findings_dir=findings_dir,
        skip_upstream_check=True,
    )

    assert rc == 0
    assert summary["verdict"] != "skipped-upstream-failed"
    assert summary["upstream_check_skipped"] is True
    assert summary["tracks"] is not None
    assert summary["tracks"]["framework"]["verdict"] == "pass"
    assert summary["tracks"]["agents"]["verdict"] == "not-classified"

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "skip-upstream-check" in err
    assert slug in err
