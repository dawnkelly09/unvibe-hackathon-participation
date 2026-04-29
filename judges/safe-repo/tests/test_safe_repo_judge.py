"""Tests for the safe_repo_judge orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import safe_repo_judge as srj  # noqa: E402


def _make_artifact(source_url: str, files: dict[str, str]) -> str:
    header = (
        "================================================\n"
        "SAFE-REPO INGEST ARTIFACT\n"
        "================================================\n"
        f"Source URL: {source_url}\n"
        "Ingested at: 2026-04-29T12:00:00+00:00\n"
        "Repository: test/repo\n"
        "Commit: 0000000\n"
        f"Files analyzed: {len(files)}\n\n"
        "================================================\n"
        "TREE\n"
        "================================================\n"
        "Directory structure:\n\n"
        "================================================\n"
        "CONTENTS\n"
        "================================================\n"
    )
    body = "".join(
        "================================================\n"
        f"FILE: {path}\n"
        "================================================\n"
        f"{content}\n\n\n"
        for path, content in files.items()
    )
    return header + body


def _fake_repo_judge(files: dict[str, str], *, fail_with: str | None = None):
    """Build a stand-in for public_repo_check.judge.

    On success, writes a real ingest artifact so the dependency check can run
    against it. On failure, returns an error result and writes nothing.
    """

    def _impl(repo_url: str, artifact_dir: Path) -> dict:
        if fail_with is not None:
            return {
                "judge": "safe-repo",
                "repo": repo_url,
                "passed": False,
                "finding": "repo is not publicly ingestable",
                "error": fail_with,
                "artifact_path": None,
            }
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{srj._slug(repo_url)}.txt"
        artifact_path.write_text(_make_artifact(repo_url, files), encoding="utf-8")
        return {
            "judge": "safe-repo",
            "repo": repo_url,
            "passed": True,
            "finding": "ok",
            "artifact_path": str(artifact_path),
        }

    return _impl


@pytest.fixture
def dirs(tmp_path):
    return {
        "ingest_dir": tmp_path / "ingest",
        "deps_output_dir": tmp_path / "deps",
        "findings_dir": tmp_path / "findings",
    }


def test_both_pass_writes_full_outputs(monkeypatch, dirs):
    repo_url = "https://github.com/test/repo"
    files = {
        "package.json": '{"name":"x","dependencies":{"react":"18"}}',
        "package-lock.json": "{}",
    }
    monkeypatch.setattr(srj, "repo_judge", _fake_repo_judge(files))

    summary = srj.run(repo_url, **dirs)

    assert summary["passed"] is True
    assert summary["verdict"] == "passed"
    assert summary["stage_complete"] is True
    assert summary["judge"] == "safe-repo"
    assert summary["repo"] == repo_url
    assert summary["slug"] == srj._slug(repo_url)

    public_sub = summary["sub_findings"]["public-repo-check"]
    assert public_sub["passed"] is True
    assert public_sub["error"] is None
    assert public_sub["artifact_path"] is not None

    deps_sub = summary["sub_findings"]["dependency-safety-check"]
    assert deps_sub["passed"] is True
    assert deps_sub["severity"] == "pass"
    assert deps_sub["findings_path"] is not None

    slug = srj._slug(repo_url)
    summary_path = dirs["findings_dir"] / slug / "safe-repo.json"
    deps_path = dirs["deps_output_dir"] / f"{slug}.json"
    ingest_path = dirs["ingest_dir"] / f"{slug}.txt"
    assert summary_path.exists()
    assert deps_path.exists()
    assert ingest_path.exists()

    on_disk = json.loads(summary_path.read_text())
    assert on_disk == summary


def test_public_repo_failure_skips_deps(monkeypatch, dirs):
    repo_url = "https://github.com/private/repo"
    monkeypatch.setattr(
        srj, "repo_judge",
        _fake_repo_judge({}, fail_with="HTTPError: 404 Not Found"),
    )

    summary = srj.run(repo_url, **dirs)

    assert summary["passed"] is False
    assert summary["verdict"] == "failed-public-repo"
    assert summary["stage_complete"] is True

    public_sub = summary["sub_findings"]["public-repo-check"]
    assert public_sub["passed"] is False
    assert public_sub["artifact_path"] is None
    assert public_sub["error"] == "HTTPError: 404 Not Found"

    deps_sub = summary["sub_findings"]["dependency-safety-check"]
    assert deps_sub["passed"] is False
    assert deps_sub["severity"] == "skipped"
    assert deps_sub["findings_path"] is None

    slug = srj._slug(repo_url)
    assert (dirs["findings_dir"] / slug / "safe-repo.json").exists()
    assert not (dirs["deps_output_dir"] / f"{slug}.json").exists()
    assert not (dirs["ingest_dir"] / f"{slug}.txt").exists()


def test_dependency_critical_fails_stage(monkeypatch, dirs):
    repo_url = "https://github.com/test/repo"
    files = {
        "package.json": '{"name":"x","dependencies":{"event-stream":"3.3.6"}}',
    }
    monkeypatch.setattr(srj, "repo_judge", _fake_repo_judge(files))

    summary = srj.run(repo_url, **dirs)

    assert summary["passed"] is False
    assert summary["verdict"] == "failed-dependency-safety"
    assert summary["stage_complete"] is True

    assert summary["sub_findings"]["public-repo-check"]["passed"] is True

    deps_sub = summary["sub_findings"]["dependency-safety-check"]
    assert deps_sub["passed"] is False
    assert deps_sub["severity"] == "critical"
    assert deps_sub["findings_path"] is not None

    slug = srj._slug(repo_url)
    summary_path = dirs["findings_dir"] / slug / "safe-repo.json"
    deps_path = dirs["deps_output_dir"] / f"{slug}.json"
    assert summary_path.exists()
    assert deps_path.exists()

    deps_on_disk = json.loads(deps_path.read_text())
    assert deps_on_disk["severity"] == "critical"


def test_dependency_warning_still_passes(monkeypatch, dirs):
    """warning-level findings flow through without failing the stage."""
    repo_url = "https://github.com/test/repo"
    files = {
        "setup.sh": (
            "#!/bin/bash\n"
            "curl -fsSL https://get.example.com/install.sh | bash\n"
        ),
    }
    monkeypatch.setattr(srj, "repo_judge", _fake_repo_judge(files))

    summary = srj.run(repo_url, **dirs)

    assert summary["passed"] is True
    assert summary["verdict"] == "passed"
    assert summary["sub_findings"]["dependency-safety-check"]["severity"] == "warning"
