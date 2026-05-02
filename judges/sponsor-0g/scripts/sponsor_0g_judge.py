"""sponsor_0g_judge.py — sponsor-0g judge wrapper.

Reads upstream findings (``safe-repo`` and ``hackathon-qualified``), runs the
Phase 1 deterministic prefilter (idempotent) and the Phase 2 LLM evaluation
as subprocesses, and writes the judge-level summary finding to
``judges/sponsor-0g/findings/<slug>/sponsor-0g.json``.

The summary shape and verdict logic are specified in
``judges/sponsor-0g/SKILL.md``. The script is the layer that catches LLM
failures and degrades gracefully — Phase 2 itself is allowed to crash.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_SAFE_REPO_SCRIPTS = _THIS_DIR.parent.parent / "safe-repo" / "scripts"
if str(_SAFE_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SAFE_REPO_SCRIPTS))

from public_repo_check import _slug  # type: ignore[import-not-found]  # noqa: E402

JUDGE_NAME = "sponsor-0g"

DEFAULT_PREFILTER_DIR = _THIS_DIR.parent / "artifacts" / "deterministic-prefilter"
DEFAULT_LLM_OUTPUT_DIR = _THIS_DIR.parent / "artifacts" / "llm-evaluation"
DEFAULT_RECORDS_DIR = _THIS_DIR.parent / "artifacts" / "llm-call-records"
DEFAULT_FINDINGS_DIR = _THIS_DIR.parent / "findings"

SAFE_REPO_FINDINGS_DIR = _THIS_DIR.parent.parent / "safe-repo" / "findings"
HACKATHON_FINDINGS_DIR = (
    _THIS_DIR.parent.parent / "hackathon-qualified" / "findings"
)

PREFILTER_SCRIPT = _THIS_DIR / "deterministic_prefilter.py"
LLM_EVALUATION_SCRIPT = _THIS_DIR / "llm_evaluation.py"

# Items that gate the rubric verdict. ``architecture-diagram`` is a soft
# item per SKILL.md — recorded but never gates.
SOFT_RUBRIC_ITEMS: frozenset[str] = frozenset({"architecture-diagram"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_declared_tracks(prefilter: dict) -> list[str]:
    """Map Phase 1's ``declared-tracks`` evidence to canonical track names.

    The match field is verbatim text like ``"framework track"`` or
    ``"Agents Track"``. Lowercase, strip the ``" track"`` suffix, drop any
    ``"inft"`` (not a top-level track), de-duplicate while preserving
    first-seen order.
    """
    items = prefilter.get("items", {}) or {}
    declared = (items.get("declared-tracks") or {}).get("evidence") or []
    seen: set[str] = set()
    out: list[str] = []
    for ev in declared:
        match = (ev.get("match") or "").lower().strip()
        if " track" not in match:
            continue
        name = match.split(" track", 1)[0].strip()
        if name in ("framework", "agents") and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _track_verdict(track: dict) -> str:
    """Compute a single-track verdict from a Call B result."""
    if track.get("integration_verdict") == "absent":
        return "fail-no-integration"
    rubric_items = track.get("rubric_items") or {}
    for item_id, value in rubric_items.items():
        if item_id in SOFT_RUBRIC_ITEMS:
            continue
        if value == "fail":
            return "fail-rubric"
    return "pass"


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _summary_skipped(repo_url: str, slug: str) -> dict:
    return {
        "judge": JUDGE_NAME,
        "repo": repo_url,
        "slug": slug,
        "passed": False,
        "stage_complete": True,
        "verdict": "skipped-upstream-failed",
        "declared_tracks": None,
        "inferred_tracks": None,
        "components_used": None,
        "tracks": None,
        "confidence": None,
        "llm_call_records_path": None,
        "completed_at": _now_iso(),
    }


def _summary_llm_failed(
    *,
    repo_url: str,
    slug: str,
    declared_tracks: list[str],
    records_dir: Path,
    failure_reason: str,
) -> dict:
    reason = (
        "Phase 2 LLM evaluation did not complete — track was not "
        f"classified. Reason: {failure_reason}"
    )
    return {
        "judge": JUDGE_NAME,
        "repo": repo_url,
        "slug": slug,
        "passed": False,
        "stage_complete": True,
        "verdict": "failed",
        "declared_tracks": declared_tracks,
        "inferred_tracks": [],
        "components_used": [],
        "tracks": {
            "framework": {
                "verdict": "not-classified",
                "reasoning": reason,
                "rubric_items": None,
            },
            "agents": {
                "verdict": "not-classified",
                "reasoning": reason,
                "rubric_items": None,
            },
        },
        "confidence": None,
        "llm_call_records_path": str(records_dir.resolve()),
        "completed_at": _now_iso(),
    }


def _summary_from_phase2(
    *,
    repo_url: str,
    slug: str,
    declared_tracks: list[str],
    phase2: dict,
    records_dir: Path,
) -> dict:
    classification = phase2.get("classification") or {}
    inferred: list[str] = []
    if classification.get("framework_applicable"):
        inferred.append("framework")
    if classification.get("agents_applicable"):
        inferred.append("agents")

    phase2_tracks = phase2.get("tracks") or {}
    tracks: dict[str, dict] = {}
    for name in ("framework", "agents"):
        track_result = phase2_tracks.get(name)
        if track_result is None:
            tracks[name] = {
                "verdict": "not-classified",
                "reasoning": (
                    f"Project does not fit the {name} track shape per "
                    "Call A; rubric was not applied."
                ),
                "rubric_items": None,
            }
            continue
        tracks[name] = {
            "verdict": _track_verdict(track_result),
            "reasoning": track_result.get("reasoning", ""),
            "rubric_items": track_result.get("rubric_items"),
        }

    passed = any(t["verdict"] == "pass" for t in tracks.values())
    return {
        "judge": JUDGE_NAME,
        "repo": repo_url,
        "slug": slug,
        "passed": passed,
        "stage_complete": True,
        "verdict": "passed" if passed else "failed",
        "declared_tracks": declared_tracks,
        "inferred_tracks": inferred,
        "components_used": list(classification.get("components_used") or []),
        "tracks": tracks,
        "confidence": classification.get("confidence"),
        "llm_call_records_path": str(records_dir.resolve()),
        "completed_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Subprocess invocation
# ---------------------------------------------------------------------------

def _run_phase1(repo_url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PREFILTER_SCRIPT), repo_url],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_phase2(repo_url: str, model: str | None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(LLM_EVALUATION_SCRIPT), repo_url]
    if model is not None:
        cmd += ["--model", model]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(
    repo_url: str,
    *,
    model: str | None = None,
    findings_dir: Path = DEFAULT_FINDINGS_DIR,
    no_write: bool = False,
    skip_upstream_check: bool = False,
) -> tuple[dict, int]:
    """Run the full sponsor-0g judge for ``repo_url``.

    Returns ``(summary, exit_code)``. ``exit_code`` is 1 only for misordered
    pipelines (missing upstream finding); transient LLM failures still write
    a well-formed summary and return 0.
    """
    slug = _slug(repo_url)
    summary_path = findings_dir / slug / "sponsor-0g.json"
    prefilter_path = DEFAULT_PREFILTER_DIR / f"{slug}.json"
    records_dir = DEFAULT_RECORDS_DIR / slug
    phase2_path = DEFAULT_LLM_OUTPUT_DIR / f"{slug}.json"

    safe_repo_finding_path = SAFE_REPO_FINDINGS_DIR / slug / "safe-repo.json"
    hackathon_finding_path = HACKATHON_FINDINGS_DIR / slug / "event-policy.json"

    if skip_upstream_check:
        print(
            f"WARNING: --skip-upstream-check is set (slug={slug}). This "
            "bypasses upstream gate checks and should only be used during "
            "calibration. Production runs must NOT use this flag.",
            file=sys.stderr,
        )

    # ---- Upstream gating ---------------------------------------------------
    if not safe_repo_finding_path.exists():
        print(
            f"upstream finding missing: {safe_repo_finding_path}\n"
            "Run safe-repo (judges/safe-repo/scripts/safe_repo_judge.py) first.",
            file=sys.stderr,
        )
        return ({}, 1)
    if not hackathon_finding_path.exists():
        print(
            f"upstream finding missing: {hackathon_finding_path}\n"
            "Run hackathon-qualified (judges/hackathon-qualified/event_policy_check.py) first.",
            file=sys.stderr,
        )
        return ({}, 1)

    safe_repo = _read_json(safe_repo_finding_path)
    hackathon = _read_json(hackathon_finding_path)
    if not skip_upstream_check and (
        not safe_repo.get("passed") or not hackathon.get("passed")
    ):
        summary = _summary_skipped(repo_url, slug)
        if not no_write:
            _atomic_write_json(summary_path, summary)
        return (summary, 0)

    # ---- Phase 1 (idempotent) ---------------------------------------------
    if not prefilter_path.exists():
        proc = _run_phase1(repo_url)
        if proc.returncode != 0:
            print(
                f"Phase 1 prefilter failed (exit {proc.returncode}):\n"
                f"{proc.stderr}",
                file=sys.stderr,
            )
            return ({}, 1)
    prefilter = _read_json(prefilter_path)
    declared_tracks = _extract_declared_tracks(prefilter)

    # ---- Phase 2 -----------------------------------------------------------
    proc = _run_phase2(repo_url, model)
    if proc.returncode != 0:
        failure_reason = (proc.stderr or "").strip() or (
            f"llm_evaluation.py exited {proc.returncode} with no stderr"
        )
        summary = _summary_llm_failed(
            repo_url=repo_url,
            slug=slug,
            declared_tracks=declared_tracks,
            records_dir=records_dir,
            failure_reason=failure_reason,
        )
        if skip_upstream_check:
            summary["upstream_check_skipped"] = True
        if not no_write:
            _atomic_write_json(summary_path, summary)
        return (summary, 0)

    if not phase2_path.exists():
        summary = _summary_llm_failed(
            repo_url=repo_url,
            slug=slug,
            declared_tracks=declared_tracks,
            records_dir=records_dir,
            failure_reason=f"Phase 2 output not found at {phase2_path}",
        )
        if skip_upstream_check:
            summary["upstream_check_skipped"] = True
        if not no_write:
            _atomic_write_json(summary_path, summary)
        return (summary, 0)

    phase2 = _read_json(phase2_path)
    summary = _summary_from_phase2(
        repo_url=repo_url,
        slug=slug,
        declared_tracks=declared_tracks,
        phase2=phase2,
        records_dir=records_dir,
    )
    if skip_upstream_check:
        summary["upstream_check_skipped"] = True
    if not no_write:
        _atomic_write_json(summary_path, summary)
    return (summary, 0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sponsor-0g judge wrapper")
    parser.add_argument("repo_url", help="Git repository URL to evaluate")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="model string forwarded to llm_evaluation.py",
    )
    parser.add_argument(
        "--findings-dir",
        type=Path,
        default=DEFAULT_FINDINGS_DIR,
        help=f"directory for the judge summary (default: {DEFAULT_FINDINGS_DIR})",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="suppress writing the summary finding (still printed to stdout)",
    )
    parser.add_argument(
        "--skip-upstream-check",
        action="store_true",
        default=False,
        help=(
            "bypass the upstream gate: proceed to Phase 1/2 even when the "
            "safe-repo or hackathon-qualified upstream finding has "
            "passed=false. Upstream finding files are still required to "
            "exist. CALIBRATION ONLY — production runs must not use this."
        ),
    )
    args = parser.parse_args(argv)

    summary, rc = run(
        args.repo_url,
        model=args.model,
        findings_dir=args.findings_dir,
        no_write=args.no_write,
        skip_upstream_check=args.skip_upstream_check,
    )
    if rc != 0:
        return rc
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
