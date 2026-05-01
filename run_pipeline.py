"""run_pipeline.py — orchestrator for the hackathon-judging pipeline.

This is intentionally a script. Not a DAG framework, not a watcher,
not a queue, not a job scheduler. It walks a list of repo URLs through
a fixed, ordered sequence of judges, prints one line per (repo, judge)
step, and emits a summary table at the end. That is the whole job.

It will remain a script until one of the following triggers justifies
upgrading:

  - A judge becomes long-running enough that serial per-repo execution
    blocks meaningful work, and concurrent fan-out across repos or
    judges is genuinely needed.
  - Cross-repo single-judge re-runs at scale (hundreds of repos)
    require richer caching, resume, or partial-rerun semantics than
    "skip if finding file exists, --force to redo."
  - Sponsor judges land with conditional routing (e.g. only run
    sponsor X when the project declares it), at which point a static
    judge list stops modeling reality and a routing layer is needed.

Until one of those is true, the cost of generalizing exceeds the
benefit. Resist preemptive abstraction.

The orchestrator is deliberately ignorant of how each judge works: it
shells out to each judge's CLI, then reads the contract-defined
finding file from disk. Per-judge logic stays inside the judge.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "judges" / "safe-repo" / "scripts"))
from public_repo_check import _slug  # noqa: E402

DEFAULT_EVENT_CONFIG = REPO_ROOT / "event.yaml"

JUDGES: dict[str, dict] = {
    "safe-repo": {
        "finding": "judges/safe-repo/findings/{slug}/safe-repo.json",
        "script": "judges/safe-repo/scripts/safe_repo_judge.py",
        "needs_event_config": False,
    },
    "event-policy": {
        "finding": "judges/hackathon-qualified/findings/{slug}/event-policy.json",
        "script": "judges/hackathon-qualified/event_policy_check.py",
        "needs_event_config": True,
    },
}


def _finding_path(judge: str, slug: str) -> Path:
    """Return the on-disk finding path for the named judge and slug."""
    return REPO_ROOT / JUDGES[judge]["finding"].format(slug=slug)


def _argv(judge: str, repo_url: str, event_config: Path) -> list[str]:
    """Build the subprocess argv for invoking judge against repo_url."""
    spec = JUDGES[judge]
    argv = ["uv", "run", str(REPO_ROOT / spec["script"]), repo_url]
    if spec["needs_event_config"]:
        argv += ["--event-config", str(event_config)]
    return argv


def _parse_judges(spec: str) -> list[str]:
    """Parse the --judges CSV. Raises SystemExit on unknown names."""
    names = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in JUDGES]
    if unknown:
        raise SystemExit(
            f"unknown judge(s): {', '.join(unknown)}. "
            f"valid judges: {', '.join(JUDGES)}"
        )
    return names


def _read_repos_file(path: Path) -> list[str]:
    """Read one repo URL per line; skip blanks and lines starting with '#'."""
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _dedupe(urls: list[str]) -> list[str]:
    """Return urls with duplicates removed, preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _truncate_left(s: str, width: int) -> str:
    """Left-truncate s with an ellipsis when it exceeds width."""
    return s if len(s) <= width else "…" + s[-(width - 1):]


def _read_finding(path: Path) -> dict | None:
    """Load a judge finding from disk, or return None if unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run_repo(
    repo_url: str,
    judges: list[str],
    event_config: Path,
    force: bool,
    label: str,
) -> dict[str, str]:
    """Run the configured judges for one repo. Returns judge -> verdict label."""
    slug = _slug(repo_url)
    results: dict[str, str] = {}
    for judge in judges:
        finding_path = _finding_path(judge, slug)
        cached = finding_path.exists() and not force

        if not cached:
            print(f"{label} {repo_url} :: {judge} ... running")
            subprocess.run(_argv(judge, repo_url, event_config))

        # Finding-file presence is the contract documented in each judge's
        # SKILL.md: the file exists iff the judge ran. Trust that over the
        # subprocess exit code (judges exit non-zero on failed verdicts).
        finding = _read_finding(finding_path)
        if finding is None:
            print(f"{label} {repo_url} :: {judge} ... error")
            results[judge] = "error"
            break

        verdict = str(finding.get("verdict", "unknown"))
        suffix = f"{verdict} (cached)" if cached else verdict
        print(f"{label} {repo_url} :: {judge} ... {suffix}")
        results[judge] = verdict

        if not bool(finding.get("passed", False)):
            break

    return results


def _overall(results: dict[str, str], judges: list[str]) -> str:
    """Compute the overall column for one repo's row in the summary table."""
    if any(v == "error" for v in results.values()):
        return "error"
    if any(j not in results for j in judges):
        return "failed"
    return "passed" if all(v == "passed" for v in results.values()) else "failed"


def _format_table(
    repos: list[str],
    judges: list[str],
    rows: dict[str, dict[str, str]],
) -> str:
    """Render the per-repo summary as a column-aligned plain-text table."""
    display = {u: _truncate_left(u, 60) for u in repos}
    overalls = {u: _overall(rows[u], judges) for u in repos}
    cols = ["Repo", *judges, "overall"]
    widths = [
        max(len("Repo"), *(len(display[u]) for u in repos)),
        *(max(len(j), *(len(rows[u].get(j, "-")) for u in repos)) for j in judges),
        max(len("overall"), *(len(v) for v in overalls.values())),
    ]

    def fmt(cells: list[str]) -> str:
        return " | ".join(c.ljust(w) for c, w in zip(cells, widths))

    lines = [fmt(cols), "-+-".join("-" * w for w in widths)]
    for u in repos:
        lines.append(
            fmt([display[u], *(rows[u].get(j, "-") for j in judges), overalls[u]])
        )
    return "\n".join(lines)


def main() -> int:
    """Parse CLI args, run each repo through the judge sequence, print summary."""
    parser = argparse.ArgumentParser(
        description="orchestrate the hackathon-judging pipeline across repos"
    )
    parser.add_argument("repos", nargs="*", help="repo URLs to evaluate")
    parser.add_argument(
        "--repos-file",
        type=Path,
        default=None,
        help="file with one repo URL per line; '#' and blank lines ignored",
    )
    parser.add_argument(
        "--event-config",
        type=Path,
        default=DEFAULT_EVENT_CONFIG,
        help=(
            "path forwarded to the event-policy judge "
            f"(default: {DEFAULT_EVENT_CONFIG})"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-run judges even when their finding file already exists",
    )
    parser.add_argument(
        "--judges",
        default="safe-repo,event-policy",
        help="comma-separated list of judges to run, in order",
    )
    args = parser.parse_args()

    judges = _parse_judges(args.judges)

    repos = list(args.repos)
    if args.repos_file is not None:
        repos.extend(_read_repos_file(args.repos_file))
    repos = _dedupe(repos)
    if not repos:
        parser.error("at least one repo URL is required (positional or --repos-file)")

    rows: dict[str, dict[str, str]] = {}
    for i, repo in enumerate(repos, 1):
        rows[repo] = _run_repo(
            repo, judges, args.event_config, args.force, f"[{i}/{len(repos)}]"
        )

    print()
    print(_format_table(repos, judges, rows))

    overalls = {u: _overall(rows[u], judges) for u in repos}
    return 0 if all(v == "passed" for v in overalls.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
