"""safe-repo judge/public-repo-check.py: verifies a submitted repo is publicly accessible.

A repo passes if `gitingest` can clone and ingest it with no GitHub token.
On pass, the full ingest (summary + tree + file contents) is written to disk
as the artifact for downstream judges to consume.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from gitingest import ingest

JUDGE_NAME = "safe-repo"
DEFAULT_ARTIFACT_DIR = Path(__file__).parent.parent / "artifacts" / "repo-ingest-dump"


@contextmanager
def _no_github_token():
    """Temporarily strip GITHUB_TOKEN so gitingest can't silently authenticate."""
    saved = os.environ.pop("GITHUB_TOKEN", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["GITHUB_TOKEN"] = saved


def _slug(repo_url: str) -> str:
    s = re.sub(r"^https?://", "", repo_url.rstrip("/"))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


def _parse_summary(summary: str) -> dict:
    fields: dict = {"repo_name": None, "commit": None, "files_analyzed": None}
    for line in summary.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if key == "Repository":
            fields["repo_name"] = value
        elif key == "Commit":
            fields["commit"] = value
        elif key == "Files analyzed":
            try:
                fields["files_analyzed"] = int(value)
            except ValueError:
                pass
    return fields


def _write_artifact(path: Path, repo_url: str, summary: str, tree: str, content: str) -> None:
    header = (
        "================================================\n"
        "SAFE-REPO INGEST ARTIFACT\n"
        "================================================\n"
        f"Source URL: {repo_url}\n"
        f"Ingested at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"{summary.strip()}\n\n"
        "================================================\n"
        "TREE\n"
        "================================================\n"
        f"{tree}\n"
        "================================================\n"
        "CONTENTS\n"
        "================================================\n"
    )
    path.write_text(header + content, encoding="utf-8")


def judge(repo_url: str, artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> dict:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{_slug(repo_url)}.txt"

    try:
        with _no_github_token():
            summary, tree, content = ingest(repo_url, token=None)
    except Exception as exc:
        return {
            "judge": JUDGE_NAME,
            "repo": repo_url,
            "passed": False,
            "finding": "repo is not publicly ingestable",
            "error": f"{type(exc).__name__}: {exc}",
            "artifact_path": None,
        }

    _write_artifact(artifact_path, repo_url, summary, tree, content)

    return {
        "judge": JUDGE_NAME,
        "repo": repo_url,
        "passed": True,
        "finding": "repo is publicly ingestable without a GitHub token",
        "artifact_path": str(artifact_path),
        **_parse_summary(summary),
        "tree_preview": "\n".join(tree.splitlines()[:20]),
        "content_bytes": len(content),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="safe-repo judge")
    parser.add_argument("repo_url", help="Git repository URL to evaluate")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help=f"directory for ingest artifacts (default: {DEFAULT_ARTIFACT_DIR})",
    )
    args = parser.parse_args()

    result = judge(args.repo_url, args.artifact_dir)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
