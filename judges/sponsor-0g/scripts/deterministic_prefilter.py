"""deterministic_prefilter.py — Phase 1 of the sponsor-0g judge.

Runs LLM-free static checks against a safe-repo gitingest artifact and emits
structured evidence per item from the SKILL.md Phase 1 table. Output is the
input to Phase 2 (LLM track classification + per-track rubric) and to the
judge's summary finding.

No network calls, no LLM calls, no link-following. Per-item failures are
caught and recorded so a single bad item never tanks the rest of the run.

Note: The current 0g-sdk-imports check only scans manifests. If the README is thin, it may be difficult to determine actual usage without a look at things like import statements inside the code itself.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# `_slug` is shared with safe-repo so the same URL → filename mapping is used
# everywhere. Importing requires putting safe-repo's scripts on sys.path.
_THIS_DIR = Path(__file__).resolve().parent
_SAFE_REPO_SCRIPTS = _THIS_DIR.parent.parent / "safe-repo" / "scripts"
if str(_SAFE_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SAFE_REPO_SCRIPTS))
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from public_repo_check import _slug  # type: ignore[import-not-found]  # noqa: E402
from _ingest_parsing import ParsedRepo, load_repo  # noqa: E402

JUDGE_NAME = "sponsor-0g"
PHASE = "deterministic-prefilter"

DEFAULT_INGEST_DIR = (
    _THIS_DIR.parent.parent / "safe-repo" / "artifacts" / "repo-ingest-dump"
)
DEFAULT_OUTPUT_DIR = _THIS_DIR.parent / "artifacts" / "deterministic-prefilter"


# ---------------------------------------------------------------------------
# Patterns (one source of truth; SKILL.md Phase 1 table is the spec)
# ---------------------------------------------------------------------------

# Markdown ATX heading: up to 3 leading spaces, 1–6 #, space, then text.
HEADING_LINE_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.*\S)\s*$")
# Setext heading underline (=== or ---), allows for RST-ish headings too.
SETEXT_UNDERLINE_RE = re.compile(r"^[=\-]{3,}\s*$")

SETUP_KEYWORD_RE = re.compile(
    r"install|setup|getting\s+started|quickstart|run",
    re.IGNORECASE,
)

ETH_ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")

DEMO_VIDEO_HOST_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|loom\.com|vimeo\.com)"
    r"/[^\s)>\"'`]*",
    re.IGNORECASE,
)

LIVE_DEMO_ANCHOR_RE = re.compile(
    r"\[(?P<text>[^\]]*?(?:live\s*demo|try\s*it|demo)[^\]]*?)\]"
    r"\((?P<url>[^)\s]+)\)",
    re.IGNORECASE,
)
PAAS_HOST_RE = re.compile(
    r"https?://[A-Za-z0-9.\-]*?"
    r"(?:vercel\.app|fleek\.[a-z]+|netlify\.app|fly\.dev|railway\.app|render\.com)"
    r"(?:/[^\s)>\"'`]*)?",
    re.IGNORECASE,
)

ARCH_KEYWORD_RE = re.compile(r"architecture|diagram|system", re.IGNORECASE)
MD_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)")
HTML_IMG_RE = re.compile(
    r"<img\b[^>]*?(?:src=[\"'](?P<src>[^\"']+)[\"'])"
    r"(?:[^>]*?alt=[\"'](?P<alt>[^\"']*)[\"'])?[^>]*/?>",
    re.IGNORECASE,
)

EXAMPLE_DIR_RE = re.compile(r"^(?P<dir>examples?|demo|samples|agents)/", re.IGNORECASE)
SOURCE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    ".go", ".rs", ".sol", ".java", ".kt", ".kts", ".cpp", ".cc", ".c",
    ".h", ".hpp", ".rb", ".swift", ".php", ".cs", ".scala", ".vy",
}
EXAMPLE_AGENT_PHRASE_RE = re.compile(r"example\s+agent", re.IGNORECASE)

TRACK_DECLARATION_RE = re.compile(r"\b(framework|agents|iNFT)\s+track\b", re.IGNORECASE)

SDK_IDENT_RE = re.compile(
    r"@0glabs/[A-Za-z0-9_.\-/]+|\b0g-[A-Za-z0-9_.\-]+|\bzerog-[A-Za-z0-9_.\-]+",
    re.IGNORECASE,
)
MANIFEST_NAMES = {
    "package.json", "package-lock.json", "pyproject.toml",
    "go.mod", "Cargo.toml",
}
REQUIREMENTS_RE = re.compile(r"^requirements[\w.\-]*\.txt$", re.IGNORECASE)

# 0G-DA/Storage/Compute/Chain are case-insensitive and tolerate hyphens or
# whitespace between "0G" and the component name.
COMPONENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("0G Storage", re.compile(r"\b0G[\s\-]*Storage\b", re.IGNORECASE)),
    ("0G DA", re.compile(r"\b0G[\s\-]*DA\b", re.IGNORECASE)),
    ("data availability", re.compile(r"\bdata\s+availability\b", re.IGNORECASE)),
    ("0G Compute", re.compile(r"\b0G[\s\-]*Compute\b", re.IGNORECASE)),
    ("0G Chain", re.compile(r"\b0G[\s\-]*Chain\b", re.IGNORECASE)),
]

INFT_RE = re.compile(r"\biNFT\b|ERC[-\s]*7857", re.IGNORECASE)

TEAM_CONTACT_RE = re.compile(
    r"telegram|t\.me|@[A-Za-z0-9_]+|contact|team",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _line_at(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _line_text(content: str, line_no: int, max_len: int = 200) -> str:
    lines = content.splitlines()
    if 1 <= line_no <= len(lines):
        return _truncate(lines[line_no - 1].strip(), max_len)
    return ""


def _truncate(s: str, max_len: int = 200) -> str:
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def _ext(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    return ("." + base.rsplit(".", 1)[-1].lower()) if "." in base else ""


def _evidence(file: str, line: int | None, snippet: str, **extra) -> dict:
    e: dict = {"file": file, "line": line, "snippet": _truncate(snippet)}
    e.update(extra)
    return e


def _paragraph_at(content: str, offset: int, max_len: int = 600) -> str:
    """Return the paragraph (text between blank lines) containing ``offset``."""
    prev = content.rfind("\n\n", 0, offset)
    start = 0 if prev == -1 else prev + 2
    nxt = content.find("\n\n", offset)
    end = len(content) if nxt == -1 else nxt
    return _truncate(content[start:end].strip(), max_len)


def _iter_headings(content: str):
    """Yield ``(line_no, heading_text)`` for ATX and setext-style headings."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        m = HEADING_LINE_RE.match(line)
        if m:
            yield i + 1, m.group("text")
            continue
        if (
            line.strip()
            and i + 1 < len(lines)
            and SETEXT_UNDERLINE_RE.match(lines[i + 1])
        ):
            yield i + 1, line.strip()


# ---------------------------------------------------------------------------
# Per-item checks
# ---------------------------------------------------------------------------

def check_readme_present(parsed: ParsedRepo) -> dict:
    """Top-level ``README*`` exists."""
    if parsed.readme_path is None:
        return {"present": False, "evidence": []}
    first = next(
        (line for line in (parsed.readme_content or "").splitlines() if line.strip()),
        "",
    )
    return {
        "present": True,
        "evidence": [
            _evidence(parsed.readme_path, 1 if first else None, first or parsed.readme_path)
        ],
    }


def check_setup_instructions_present(parsed: ParsedRepo) -> dict:
    """README has a heading matching install/setup/getting started/quickstart/run."""
    if parsed.readme_content is None:
        return {"present": False, "evidence": []}
    evidence: list[dict] = []
    for line_no, heading in _iter_headings(parsed.readme_content):
        m = SETUP_KEYWORD_RE.search(heading)
        if m:
            evidence.append(
                _evidence(
                    parsed.readme_path, line_no, heading,
                    match=m.group(0),
                )
            )
    return {"present": bool(evidence), "evidence": evidence}


def check_contract_addresses(parsed: ParsedRepo) -> dict:
    """Strings matching ``\\b0x[a-fA-F0-9]{40}\\b`` anywhere in the repo."""
    evidence: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for path, content in parsed.files.items():
        for m in ETH_ADDRESS_RE.finditer(content):
            line_no = _line_at(content, m.start())
            addr = m.group(0)
            key = (path, line_no, addr)
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                _evidence(path, line_no, _line_text(content, line_no), value=addr)
            )
    return {"present": bool(evidence), "evidence": evidence}


def check_demo_video_link(parsed: ParsedRepo) -> dict:
    """README has a youtube/youtu.be/loom/vimeo URL."""
    if parsed.readme_content is None:
        return {"present": False, "evidence": []}
    evidence: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for m in DEMO_VIDEO_HOST_RE.finditer(parsed.readme_content):
        url = m.group(0).rstrip(".,);")
        line_no = _line_at(parsed.readme_content, m.start())
        key = (url, line_no)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            _evidence(
                parsed.readme_path, line_no,
                _line_text(parsed.readme_content, line_no),
                value=url,
            )
        )
    return {"present": bool(evidence), "evidence": evidence}


def check_live_demo_link(parsed: ParsedRepo) -> dict:
    """README has a 'live demo' / 'demo' / 'try it' anchor or a PaaS-host URL."""
    if parsed.readme_content is None:
        return {"present": False, "evidence": []}
    evidence: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    for m in LIVE_DEMO_ANCHOR_RE.finditer(parsed.readme_content):
        url = m.group("url")
        anchor = m.group("text").strip()
        line_no = _line_at(parsed.readme_content, m.start())
        key = ("anchor", url, line_no)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            _evidence(
                parsed.readme_path, line_no,
                _line_text(parsed.readme_content, line_no),
                value=url, anchor=anchor,
            )
        )
    for m in PAAS_HOST_RE.finditer(parsed.readme_content):
        url = m.group(0).rstrip(".,);")
        line_no = _line_at(parsed.readme_content, m.start())
        key = ("paas", url, line_no)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            _evidence(
                parsed.readme_path, line_no,
                _line_text(parsed.readme_content, line_no),
                value=url,
            )
        )
    return {"present": bool(evidence), "evidence": evidence}


def check_architecture_diagram(parsed: ParsedRepo) -> dict:
    """README image whose alt text or src path matches architecture/diagram/system."""
    if parsed.readme_content is None:
        return {"present": False, "evidence": []}
    evidence: list[dict] = []
    for m in MD_IMAGE_RE.finditer(parsed.readme_content):
        alt, src = m.group("alt"), m.group("src")
        if ARCH_KEYWORD_RE.search(alt) or ARCH_KEYWORD_RE.search(src):
            line_no = _line_at(parsed.readme_content, m.start())
            evidence.append(
                _evidence(parsed.readme_path, line_no, m.group(0), value=src, alt=alt)
            )
    for m in HTML_IMG_RE.finditer(parsed.readme_content):
        src = m.group("src") or ""
        alt = m.group("alt") or ""
        if ARCH_KEYWORD_RE.search(alt) or ARCH_KEYWORD_RE.search(src):
            line_no = _line_at(parsed.readme_content, m.start())
            evidence.append(
                _evidence(parsed.readme_path, line_no, m.group(0), value=src, alt=alt)
            )
    return {"present": bool(evidence), "evidence": evidence}


def check_example_agent_presence(parsed: ParsedRepo) -> dict:
    """Source file under examples?/demo/samples/agents, or 'example agent' in README."""
    evidence: list[dict] = []
    matched_paths: list[tuple[str, str]] = []
    for path in parsed.files:
        m = EXAMPLE_DIR_RE.match(path)
        if not m or _ext(path) not in SOURCE_EXTS:
            continue
        matched_paths.append((m.group("dir"), path))
    for top_dir, path in sorted(matched_paths, key=lambda p: p[1]):
        evidence.append(
            _evidence(
                path, None,
                "<source file under " + top_dir + "/>",
                directory=top_dir,
            )
        )
    if parsed.readme_content is not None:
        for m in EXAMPLE_AGENT_PHRASE_RE.finditer(parsed.readme_content):
            line_no = _line_at(parsed.readme_content, m.start())
            evidence.append(
                _evidence(
                    parsed.readme_path, line_no,
                    _line_text(parsed.readme_content, line_no),
                    match=m.group(0),
                )
            )
    return {"present": bool(evidence), "evidence": evidence}


def check_declared_tracks(parsed: ParsedRepo) -> dict:
    """README contains 'framework track' / 'agents track' / 'iNFT track'.

    Phrase recorded verbatim (case preserved) so reviewers see the literal text.
    """
    if parsed.readme_content is None:
        return {"present": False, "evidence": []}
    evidence: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for m in TRACK_DECLARATION_RE.finditer(parsed.readme_content):
        line_no = _line_at(parsed.readme_content, m.start())
        verbatim = m.group(0)
        key = (verbatim, line_no)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            _evidence(
                parsed.readme_path, line_no,
                _line_text(parsed.readme_content, line_no),
                match=verbatim,
            )
        )
    return {"present": bool(evidence), "evidence": evidence}


def check_0g_sdk_imports(parsed: ParsedRepo) -> dict:
    """Manifest references to ``@0glabs/*``, ``0g-*``, or ``zerog-*``.

    Manifests are scanned as plain text — partial / malformed JSON or TOML is
    tolerated, since real repos often ship those.
    """
    evidence: list[dict] = []
    for path, content in parsed.files.items():
        base = path.rsplit("/", 1)[-1]
        if base not in MANIFEST_NAMES and not REQUIREMENTS_RE.match(base):
            continue
        for m in SDK_IDENT_RE.finditer(content):
            line_no = _line_at(content, m.start())
            evidence.append(
                _evidence(
                    path, line_no, _line_text(content, line_no),
                    identifier=m.group(0),
                )
            )
    return {"present": bool(evidence), "evidence": evidence}


def check_0g_component_mentions(parsed: ParsedRepo) -> dict:
    """README mentions of 0G Storage / DA (or 'data availability') / Compute / Chain.

    Each match carries the surrounding paragraph as snippet.
    """
    if parsed.readme_content is None:
        return {"present": False, "evidence": []}
    evidence: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for label, pat in COMPONENT_PATTERNS:
        for m in pat.finditer(parsed.readme_content):
            line_no = _line_at(parsed.readme_content, m.start())
            key = (label, line_no)
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                {
                    "file": parsed.readme_path,
                    "line": line_no,
                    "snippet": _paragraph_at(parsed.readme_content, m.start()),
                    "component": label,
                    "match": m.group(0),
                }
            )
    return {"present": bool(evidence), "evidence": evidence}


def check_inft_mentions(parsed: ParsedRepo) -> dict:
    """README or .sol contracts referencing ``iNFT`` or ``ERC-7857``."""
    evidence: list[dict] = []
    targets: list[tuple[str, str]] = []
    if parsed.readme_path is not None and parsed.readme_content is not None:
        targets.append((parsed.readme_path, parsed.readme_content))
    for path, content in parsed.files.items():
        if path.lower().endswith(".sol"):
            targets.append((path, content))
    for path, content in targets:
        for m in INFT_RE.finditer(content):
            line_no = _line_at(content, m.start())
            evidence.append(
                _evidence(path, line_no, _line_text(content, line_no), match=m.group(0))
            )
    return {"present": bool(evidence), "evidence": evidence}


def check_team_contact_info(parsed: ParsedRepo) -> dict:
    """README block matching telegram / t.me / @handle / contact / team.

    Generous by design — the phase-2 LLM decides whether real contact info
    is actually present.
    """
    if parsed.readme_content is None:
        return {"present": False, "evidence": []}
    evidence: list[dict] = []
    seen_lines: set[int] = set()
    for m in TEAM_CONTACT_RE.finditer(parsed.readme_content):
        line_no = _line_at(parsed.readme_content, m.start())
        if line_no in seen_lines:
            continue
        seen_lines.add(line_no)
        evidence.append(
            _evidence(
                parsed.readme_path, line_no,
                _line_text(parsed.readme_content, line_no),
                match=m.group(0),
            )
        )
    return {"present": bool(evidence), "evidence": evidence}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ITEM_CHECKERS: list[tuple[str, callable]] = [
    ("readme-present", check_readme_present),
    ("setup-instructions-present", check_setup_instructions_present),
    ("contract-addresses", check_contract_addresses),
    ("demo-video-link", check_demo_video_link),
    ("live-demo-link", check_live_demo_link),
    ("architecture-diagram", check_architecture_diagram),
    ("example-agent-presence", check_example_agent_presence),
    ("declared-tracks", check_declared_tracks),
    ("0g-sdk-imports", check_0g_sdk_imports),
    ("0g-component-mentions", check_0g_component_mentions),
    ("inft-mentions", check_inft_mentions),
    ("team-contact-info", check_team_contact_info),
]


def run_prefilter(parsed: ParsedRepo) -> dict:
    """Run every item check, isolating failures so one bad item never kills the rest."""
    items: dict[str, dict] = {}
    for item_id, fn in ITEM_CHECKERS:
        try:
            items[item_id] = fn(parsed)
        except Exception as exc:  # pragma: no cover — defensive
            items[item_id] = {
                "present": False,
                "evidence": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
    return items


def build_result(repo_url: str, ingest_path: Path, parsed: ParsedRepo) -> dict:
    return {
        "judge": JUDGE_NAME,
        "phase": PHASE,
        "repo": repo_url,
        "slug": _slug(repo_url),
        "ingest_path": str(ingest_path),
        "items": run_prefilter(parsed),
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: dict) -> None:
    """Write ``data`` to ``path`` atomically (tempfile + os.replace)."""
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


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    slug = _slug(args.repo_url)
    ingest_path = (
        args.ingest_path if args.ingest_path is not None
        else DEFAULT_INGEST_DIR / f"{slug}.txt"
    )
    output_path = (
        args.output_path if args.output_path is not None
        else DEFAULT_OUTPUT_DIR / f"{slug}.json"
    )
    return ingest_path, output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sponsor-0g Phase 1 deterministic prefilter")
    parser.add_argument("repo_url", help="Git repository URL the artifact corresponds to")
    parser.add_argument(
        "--ingest-path",
        type=Path,
        default=None,
        help=(
            "explicit path to the safe-repo gitingest artifact "
            f"(default: {DEFAULT_INGEST_DIR}/<slug>.txt)"
        ),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help=(
            "explicit path for the prefilter JSON "
            f"(default: {DEFAULT_OUTPUT_DIR}/<slug>.json)"
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="suppress writing the JSON result to disk (still printed to stdout)",
    )
    args = parser.parse_args(argv)

    ingest_path, output_path = _resolve_paths(args)
    if not ingest_path.exists():
        print(
            f"ingest artifact not found: {ingest_path}\n"
            "Run safe-repo (judges/safe-repo/scripts/public_repo_check.py) first.",
            file=sys.stderr,
        )
        return 1

    text = ingest_path.read_text(encoding="utf-8")
    try:
        parsed = load_repo(text)
    except ValueError as exc:
        print(f"could not parse ingest artifact at {ingest_path}: {exc}", file=sys.stderr)
        return 1

    result = build_result(args.repo_url, ingest_path, parsed)

    if not args.no_write:
        _atomic_write_json(output_path, result)
        print(f"wrote {output_path}", file=sys.stderr)

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
