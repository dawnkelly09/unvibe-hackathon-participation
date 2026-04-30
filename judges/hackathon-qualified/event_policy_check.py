"""event-policy judge: verify a project meets the event's eligibility window.

Sub-checks:
  - first-commit-in-window — first commit on or after event.start_date when
    new_repo_required is true (gating)
  - last-commit-before-deadline — last commit on or before
    event.submission_deadline (gating)
  - timeline-plausibility — soft signals for human reviewers (never gates)

See judges/hackathon-qualified/SKILL.md for the contract this script
implements.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "judges" / "safe-repo" / "scripts"))
from public_repo_check import _slug  # noqa: E402

JUDGE_NAME = "event-policy"
DEFAULT_FINDINGS_DIR = Path(__file__).parent / "findings"
DEFAULT_SAFE_REPO_FINDINGS_DIR = _REPO_ROOT / "judges" / "safe-repo" / "findings"
DEFAULT_EVENT_CONFIG = _REPO_ROOT / "event.yaml"

# Timeline-plausibility thresholds. Documented in SKILL.md so reviewers can
# interpret warnings without reading code.
BULK_COMMIT_LINE_THRESHOLD = 5000
LARGE_GAP_DAYS = 30
MIDNIGHT_PROXIMITY_HOURS = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, data: dict) -> None:
    """Write data as pretty JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _load_event_config(path: Path) -> dict:
    """Parse event.yaml and return a dict with normalized native types.

    Raises FileNotFoundError if missing, ValueError if required fields are
    absent or malformed.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"event config not found at {path}; create one with "
            "start_date, submission_deadline, and new_repo_required"
        )
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = ("start_date", "submission_deadline", "new_repo_required")
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"event config missing required fields: {missing}")

    start = cfg["start_date"]
    if isinstance(start, str):
        start = date.fromisoformat(start)
    elif isinstance(start, datetime):
        start = start.date()
    elif not isinstance(start, date):
        raise ValueError("start_date must be an ISO 8601 date")

    deadline = cfg["submission_deadline"]
    if isinstance(deadline, str):
        deadline = datetime.fromisoformat(deadline)
    if not isinstance(deadline, datetime):
        raise ValueError("submission_deadline must be an ISO 8601 datetime")
    if deadline.tzinfo is None:
        raise ValueError("submission_deadline must include a timezone offset")

    return {
        "start_date": start,
        "submission_deadline": deadline,
        "new_repo_required": bool(cfg["new_repo_required"]),
    }


def _serialize_event_config(cfg: dict) -> dict:
    """Serialize the normalized event config back to JSON-friendly strings."""
    return {
        "start_date": cfg["start_date"].isoformat(),
        "submission_deadline": cfg["submission_deadline"].isoformat(),
        "new_repo_required": cfg["new_repo_required"],
    }


def _load_safe_repo_finding(path: Path) -> dict:
    """Load the upstream safe-repo summary finding."""
    if not path.exists():
        raise FileNotFoundError(
            f"safe-repo finding not found at {path}; run the safe-repo "
            "judge first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _git(args: list[str], cwd: Path) -> str:
    """Run a git command in cwd and return stdout. Raises on non-zero exit."""
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {proc.stderr.strip()}"
        )
    return proc.stdout


def _clone_metadata(repo_url: str, dest: Path) -> None:
    """Bare-clone repo_url into dest. No working tree, full history.

    A bare clone is the cheapest way to get the commit graph plus enough
    object data to run `git show --shortstat`, and is fully offline once
    finished.
    """
    proc = subprocess.run(
        ["git", "clone", "--bare", repo_url, str(dest)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {proc.stderr.strip()}")


def _commit_dates(clone_dir: Path) -> list[datetime]:
    """All commit author dates, oldest first."""
    out = _git(["log", "--reverse", "--format=%aI"], clone_dir).strip()
    if not out:
        return []
    return [datetime.fromisoformat(line) for line in out.splitlines()]


def _first_commit_sha(clone_dir: Path) -> str:
    """SHA of the first (oldest) commit on the default branch."""
    out = _git(["log", "--reverse", "--format=%H"], clone_dir).strip()
    return out.splitlines()[0]


def _commit_lines_changed(clone_dir: Path, sha: str) -> int:
    """Insertions + deletions for sha as reported by `git show --shortstat`."""
    out = _git(["show", "--shortstat", "--format=", sha], clone_dir).strip()
    if not out:
        return 0
    last = out.splitlines()[-1]
    ins = 0
    dels = 0
    m = re.search(r"(\d+)\s+insertions?\(\+\)", last)
    if m:
        ins = int(m.group(1))
    m = re.search(r"(\d+)\s+deletions?\(-\)", last)
    if m:
        dels = int(m.group(1))
    return ins + dels


def _check_first_commit(
    first: datetime, start_date: date, new_repo_required: bool
) -> dict:
    """Gate: first commit must be on or after start_date if new_repo_required."""
    if not new_repo_required:
        return {
            "passed": True,
            "first_commit_date": first.isoformat(),
            "enforced": False,
            "note": "new_repo_required is false; first-commit window not enforced",
        }
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    passed = first >= start_dt
    return {
        "passed": passed,
        "first_commit_date": first.isoformat(),
        "enforced": True,
        "note": (
            None
            if passed
            else (
                f"first commit {first.isoformat()} predates "
                f"start_date {start_date.isoformat()}"
            )
        ),
    }


def _check_last_commit(last: datetime, deadline: datetime) -> dict:
    """Gate: last commit must be on or before submission_deadline."""
    passed = last <= deadline
    return {
        "passed": passed,
        "last_commit_date": last.isoformat(),
        "note": (
            None
            if passed
            else (
                f"last commit {last.isoformat()} is after "
                f"submission_deadline {deadline.isoformat()}"
            )
        ),
    }


def _check_timeline(
    commit_dates: list[datetime],
    first_commit_lines: int,
    cfg: dict,
) -> dict:
    """Soft signals for a human reviewer. Never gates the stage."""
    warnings: list[dict] = []
    start_date = cfg["start_date"]
    deadline = cfg["submission_deadline"]

    if not commit_dates:
        return {"severity": "pass", "warnings": warnings}

    first = commit_dates[0]

    if first_commit_lines > BULK_COMMIT_LINE_THRESHOLD:
        warnings.append(
            {
                "type": "bulk-first-commit",
                "message": (
                    f"first commit changed {first_commit_lines} lines "
                    f"(>{BULK_COMMIT_LINE_THRESHOLD}); may indicate a history dump"
                ),
            }
        )

    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    in_window = [d for d in commit_dates if start_dt <= d <= deadline]
    for prev, nxt in zip(in_window, in_window[1:]):
        gap = nxt - prev
        if gap > timedelta(days=LARGE_GAP_DAYS):
            warnings.append(
                {
                    "type": "large-gap",
                    "message": (
                        f"{gap.days}-day gap between {prev.isoformat()} "
                        f"and {nxt.isoformat()} inside event window"
                    ),
                }
            )

    midnight = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    if abs(first - midnight) <= timedelta(hours=MIDNIGHT_PROXIMITY_HOURS):
        warnings.append(
            {
                "type": "midnight-proximity",
                "message": (
                    f"first commit {first.isoformat()} is within "
                    f"{MIDNIGHT_PROXIMITY_HOURS}h of start_date midnight UTC; "
                    "could indicate backdating"
                ),
            }
        )

    severity = "warning" if warnings else "pass"
    return {"severity": severity, "warnings": warnings}


def _verdict(first_passed: bool, last_passed: bool) -> str:
    if first_passed and last_passed:
        return "passed"
    if not first_passed and not last_passed:
        return "failed-both"
    if not first_passed:
        return "failed-first-commit"
    return "failed-last-commit"


def run(
    repo_url: str,
    *,
    event_config_path: Path = DEFAULT_EVENT_CONFIG,
    safe_repo_findings_dir: Path = DEFAULT_SAFE_REPO_FINDINGS_DIR,
    findings_dir: Path = DEFAULT_FINDINGS_DIR,
) -> dict:
    """Run the event-policy judge end-to-end and write the summary finding."""
    slug = _slug(repo_url)
    finding_path = findings_dir / slug / "event-policy.json"

    cfg = _load_event_config(event_config_path)
    safe_repo_path = safe_repo_findings_dir / slug / "safe-repo.json"
    safe_repo_finding = _load_safe_repo_finding(safe_repo_path)

    if not safe_repo_finding.get("passed", False):
        summary = {
            "judge": JUDGE_NAME,
            "repo": repo_url,
            "slug": slug,
            "passed": False,
            "stage_complete": True,
            "verdict": "skipped-upstream-failed",
            "sub_findings": {
                "first-commit-in-window": None,
                "last-commit-before-deadline": None,
                "timeline-plausibility": None,
            },
            "event_config": _serialize_event_config(cfg),
            "completed_at": _now_iso(),
        }
        _write_json(finding_path, summary)
        return summary

    artifact_path = (
        safe_repo_finding.get("sub_findings", {})
        .get("public-repo-check", {})
        .get("artifact_path")
    )
    if not artifact_path or not Path(artifact_path).exists():
        raise FileNotFoundError(
            f"safe-repo ingest artifact missing at {artifact_path!r}; "
            "cannot proceed"
        )

    with tempfile.TemporaryDirectory(prefix="event-policy-") as td:
        clone_dir = Path(td) / "repo.git"
        _clone_metadata(repo_url, clone_dir)
        commit_dates = _commit_dates(clone_dir)
        if not commit_dates:
            raise RuntimeError(f"repo {repo_url} has no commits")
        first = commit_dates[0]
        last = commit_dates[-1]
        first_sha = _first_commit_sha(clone_dir)
        first_lines = _commit_lines_changed(clone_dir, first_sha)

    first_finding = _check_first_commit(
        first, cfg["start_date"], cfg["new_repo_required"]
    )
    last_finding = _check_last_commit(last, cfg["submission_deadline"])
    timeline_finding = _check_timeline(commit_dates, first_lines, cfg)

    verdict = _verdict(first_finding["passed"], last_finding["passed"])
    summary = {
        "judge": JUDGE_NAME,
        "repo": repo_url,
        "slug": slug,
        "passed": verdict == "passed",
        "stage_complete": True,
        "verdict": verdict,
        "sub_findings": {
            "first-commit-in-window": first_finding,
            "last-commit-before-deadline": last_finding,
            "timeline-plausibility": timeline_finding,
        },
        "event_config": _serialize_event_config(cfg),
        "completed_at": _now_iso(),
    }
    _write_json(finding_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="event-policy judge")
    parser.add_argument("repo_url", help="Git repository URL to evaluate")
    parser.add_argument(
        "--event-config",
        type=Path,
        default=DEFAULT_EVENT_CONFIG,
        help=f"path to event config (default: {DEFAULT_EVENT_CONFIG})",
    )
    parser.add_argument(
        "--safe-repo-findings-dir",
        type=Path,
        default=DEFAULT_SAFE_REPO_FINDINGS_DIR,
        help=(
            "directory containing safe-repo summary findings "
            f"(default: {DEFAULT_SAFE_REPO_FINDINGS_DIR})"
        ),
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
        event_config_path=args.event_config,
        safe_repo_findings_dir=args.safe_repo_findings_dir,
        findings_dir=args.findings_dir,
    )
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
