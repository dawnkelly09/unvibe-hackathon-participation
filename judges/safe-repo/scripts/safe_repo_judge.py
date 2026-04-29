"""safe-repo judge orchestrator: runs public_repo_check + dependency_safety_check
and writes the judge-level summary finding.

See judges/safe-repo/SKILL.md for the contract this script implements.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dependency_safety_check import DEFAULT_OUTPUT_DIR as DEFAULT_DEPS_OUTPUT_DIR
from dependency_safety_check import judge as dep_judge
from public_repo_check import DEFAULT_ARTIFACT_DIR as DEFAULT_INGEST_DIR
from public_repo_check import _slug
from public_repo_check import judge as repo_judge

JUDGE_NAME = "safe-repo"
DEFAULT_FINDINGS_DIR = Path(__file__).parent.parent / "findings"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run(
    repo_url: str,
    *,
    ingest_dir: Path = DEFAULT_INGEST_DIR,
    deps_output_dir: Path = DEFAULT_DEPS_OUTPUT_DIR,
    findings_dir: Path = DEFAULT_FINDINGS_DIR,
) -> dict:
    slug = _slug(repo_url)

    repo_result = repo_judge(repo_url, ingest_dir)
    public_sub = {
        "passed": repo_result["passed"],
        "artifact_path": repo_result.get("artifact_path"),
        "error": repo_result.get("error"),
    }

    if not repo_result["passed"]:
        deps_sub = {"passed": False, "severity": "skipped", "findings_path": None}
        verdict = "failed-public-repo"
    else:
        artifact_path = Path(repo_result["artifact_path"])
        dep_result = dep_judge(artifact_path)
        deps_path = deps_output_dir / f"{artifact_path.stem}.json"
        _write_json(deps_path, dep_result)
        deps_sub = {
            "passed": dep_result["passed"],
            "severity": dep_result["severity"],
            "findings_path": str(deps_path),
        }
        verdict = "passed" if dep_result["passed"] else "failed-dependency-safety"

    summary = {
        "judge": JUDGE_NAME,
        "repo": repo_url,
        "slug": slug,
        "passed": public_sub["passed"] and deps_sub["passed"],
        "stage_complete": True,
        "verdict": verdict,
        "sub_findings": {
            "public-repo-check": public_sub,
            "dependency-safety-check": deps_sub,
        },
        "completed_at": _now_iso(),
    }
    _write_json(findings_dir / slug / "safe-repo.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="safe-repo judge orchestrator")
    parser.add_argument("repo_url", help="Git repository URL to evaluate")
    parser.add_argument(
        "--ingest-dir",
        type=Path,
        default=DEFAULT_INGEST_DIR,
        help=f"directory for ingest artifacts (default: {DEFAULT_INGEST_DIR})",
    )
    parser.add_argument(
        "--deps-output-dir",
        type=Path,
        default=DEFAULT_DEPS_OUTPUT_DIR,
        help=f"directory for dependency findings (default: {DEFAULT_DEPS_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--findings-dir",
        type=Path,
        default=DEFAULT_FINDINGS_DIR,
        help=f"directory for the judge summary (default: {DEFAULT_FINDINGS_DIR})",
    )
    args = parser.parse_args()

    summary = run(
        args.repo_url,
        ingest_dir=args.ingest_dir,
        deps_output_dir=args.deps_output_dir,
        findings_dir=args.findings_dir,
    )
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
