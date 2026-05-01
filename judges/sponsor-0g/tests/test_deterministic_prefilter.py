"""Tests for sponsor-0g deterministic_prefilter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import deterministic_prefilter as dp  # noqa: E402
from _ingest_parsing import load_repo  # noqa: E402


def _load(name: str):
    path = FIXTURES / f"{name}.txt"
    parsed = load_repo(path.read_text(encoding="utf-8"))
    items = dp.run_prefilter(parsed)
    return parsed, items


# ---------------------------------------------------------------------------
# Sanity: all 12 items always appear in output
# ---------------------------------------------------------------------------

EXPECTED_ITEM_IDS = {
    "readme-present",
    "setup-instructions-present",
    "contract-addresses",
    "demo-video-link",
    "live-demo-link",
    "architecture-diagram",
    "example-agent-presence",
    "declared-tracks",
    "0g-sdk-imports",
    "0g-component-mentions",
    "inft-mentions",
    "team-contact-info",
}


def test_all_items_present_in_output():
    _, items = _load("minimal")
    assert set(items) == EXPECTED_ITEM_IDS
    for item in items.values():
        assert "present" in item
        assert "evidence" in item
        assert isinstance(item["evidence"], list)


# ---------------------------------------------------------------------------
# Rich fixture: most items match
# ---------------------------------------------------------------------------

def test_rich_fixture_readme_present():
    _, items = _load("rich")
    assert items["readme-present"]["present"] is True
    assert items["readme-present"]["evidence"][0]["file"] == "README.md"


def test_rich_fixture_setup_instructions_present():
    _, items = _load("rich")
    item = items["setup-instructions-present"]
    assert item["present"] is True
    matched_lines = [e["snippet"] for e in item["evidence"]]
    assert any("Setup" in line for line in matched_lines)


def test_rich_fixture_contract_addresses_across_files():
    """contract-addresses scans the entire repo, not just README."""
    _, items = _load("rich")
    item = items["contract-addresses"]
    assert item["present"] is True
    files = {e["file"] for e in item["evidence"]}
    assert "README.md" in files
    assert "contracts/MyContract.sol" in files
    values = {e["value"].lower() for e in item["evidence"]}
    assert "0x1234567890abcdef1234567890abcdef12345678" in values
    assert "0xabcdefabcdef1234567890abcdef1234567890ab" in values


def test_rich_fixture_demo_video_link():
    _, items = _load("rich")
    item = items["demo-video-link"]
    assert item["present"] is True
    assert any("youtube.com" in e["value"] for e in item["evidence"])


def test_rich_fixture_live_demo_link_paas_and_anchor():
    _, items = _load("rich")
    item = items["live-demo-link"]
    assert item["present"] is True
    values = [e["value"] for e in item["evidence"]]
    assert any("vercel.app" in v for v in values)


def test_rich_fixture_architecture_diagram():
    _, items = _load("rich")
    item = items["architecture-diagram"]
    assert item["present"] is True
    assert any("architecture" in e["value"].lower() or "architecture" in e["alt"].lower()
               for e in item["evidence"])


def test_rich_fixture_example_agent_presence():
    _, items = _load("rich")
    item = items["example-agent-presence"]
    assert item["present"] is True
    files = {e["file"] for e in item["evidence"]}
    assert "examples/agent.ts" in files


def test_rich_fixture_declared_tracks_records_verbatim():
    """Track phrases must be recorded with case preserved."""
    _, items = _load("rich")
    item = items["declared-tracks"]
    assert item["present"] is True
    matches = [e["match"] for e in item["evidence"]]
    assert "framework track" in matches


def test_rich_fixture_0g_sdk_imports_record_identifier():
    _, items = _load("rich")
    item = items["0g-sdk-imports"]
    assert item["present"] is True
    e = item["evidence"][0]
    assert e["file"] == "package.json"
    assert e["identifier"].startswith("@0glabs/")


def test_rich_fixture_0g_component_mentions_with_paragraph():
    _, items = _load("rich")
    item = items["0g-component-mentions"]
    assert item["present"] is True
    components = {e["component"] for e in item["evidence"]}
    assert "0G Storage" in components
    assert "0G Compute" in components
    # Snippet is the full surrounding paragraph, not just the matched line.
    storage_evidence = next(e for e in item["evidence"] if e["component"] == "0G Storage")
    assert "0G Storage" in storage_evidence["snippet"]


def test_rich_fixture_inft_mentions_in_readme_and_contract():
    _, items = _load("rich")
    item = items["inft-mentions"]
    assert item["present"] is True
    files = {e["file"] for e in item["evidence"]}
    assert "README.md" in files
    assert "contracts/MyContract.sol" in files
    matches = {e["match"].lower() for e in item["evidence"]}
    assert any("inft" in m for m in matches)
    assert any("7857" in m for m in matches)


def test_rich_fixture_team_contact_info():
    _, items = _load("rich")
    item = items["team-contact-info"]
    assert item["present"] is True
    matches = {e["match"].lower() for e in item["evidence"]}
    assert "telegram" in matches or any("@" in m for m in matches)


# ---------------------------------------------------------------------------
# Minimal fixture: most items false
# ---------------------------------------------------------------------------

def test_minimal_fixture_only_readme_present():
    _, items = _load("minimal")
    assert items["readme-present"]["present"] is True
    for item_id in (
        "setup-instructions-present",
        "contract-addresses",
        "demo-video-link",
        "live-demo-link",
        "architecture-diagram",
        "example-agent-presence",
        "declared-tracks",
        "0g-sdk-imports",
        "0g-component-mentions",
        "inft-mentions",
    ):
        assert items[item_id]["present"] is False, f"{item_id} should be False"
        assert items[item_id]["evidence"] == []


# ---------------------------------------------------------------------------
# README selection rule
# ---------------------------------------------------------------------------

def test_multiple_readmes_prefers_markdown():
    parsed, items = _load("multi-readmes")
    assert parsed.readme_path == "README.md"
    assert items["readme-present"]["evidence"][0]["file"] == "README.md"


# ---------------------------------------------------------------------------
# Tolerates malformed manifests
# ---------------------------------------------------------------------------

def test_malformed_package_json_does_not_crash_and_still_finds_sdk():
    _, items = _load("malformed-package-json")
    sdk = items["0g-sdk-imports"]
    assert "error" not in sdk
    assert sdk["present"] is True
    assert any("@0glabs/" in e["identifier"] for e in sdk["evidence"])


# ---------------------------------------------------------------------------
# Contract address inside a code comment is still detected
# ---------------------------------------------------------------------------

def test_contract_address_in_code_comment_is_detected():
    _, items = _load("contract-in-comment")
    item = items["contract-addresses"]
    assert item["present"] is True
    files = {e["file"] for e in item["evidence"]}
    assert "src/foo.ts" in files


# ---------------------------------------------------------------------------
# README-only scope for demo-video-link
# ---------------------------------------------------------------------------

def test_youtube_in_non_readme_does_not_match_demo_video():
    """demo-video-link is README-only; a youtube URL elsewhere must not trigger it."""
    parsed, items = _load("youtube-in-non-readme")
    assert "CONTRIBUTING.md" in parsed.files
    # The other file does contain the URL — this is what proves the README-only scope.
    assert "youtube.com" in parsed.files["CONTRIBUTING.md"]
    assert items["demo-video-link"]["present"] is False
    assert items["demo-video-link"]["evidence"] == []


# ---------------------------------------------------------------------------
# Top-level result shape
# ---------------------------------------------------------------------------

def test_build_result_shape(tmp_path):
    text = (FIXTURES / "rich.txt").read_text(encoding="utf-8")
    parsed = load_repo(text)
    result = dp.build_result(
        repo_url="https://github.com/test/rich",
        ingest_path=tmp_path / "rich.txt",
        parsed=parsed,
    )
    assert result["judge"] == "sponsor-0g"
    assert result["phase"] == "deterministic-prefilter"
    assert result["repo"] == "https://github.com/test/rich"
    assert result["slug"] == "github.com_test_rich"
    assert set(result["items"]) == EXPECTED_ITEM_IDS
    assert "completed_at" in result
    # Sanity: result is JSON-serializable.
    json.dumps(result)


# ---------------------------------------------------------------------------
# CLI: missing artifact fails clean
# ---------------------------------------------------------------------------

def test_main_missing_ingest_returns_1(tmp_path, capsys):
    rc = dp.main(
        [
            "https://github.com/test/missing",
            "--ingest-path", str(tmp_path / "does-not-exist.txt"),
            "--output-path", str(tmp_path / "out.json"),
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "ingest artifact not found" in captured.err
    assert not (tmp_path / "out.json").exists()


def test_main_writes_output_atomically(tmp_path, capsys):
    out = tmp_path / "rich.json"
    rc = dp.main(
        [
            "https://github.com/test/rich",
            "--ingest-path", str(FIXTURES / "rich.txt"),
            "--output-path", str(out),
        ]
    )
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["judge"] == "sponsor-0g"
    assert data["items"]["readme-present"]["present"] is True
    # No leftover .tmp files in the output dir.
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
