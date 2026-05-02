"""llm_evaluation.py — Phase 2 of the sponsor-0g judge.

Reads the Phase 1 deterministic prefilter JSON and the safe-repo gitingest
artifact, builds a single context pack, and makes one or two LLM calls:

* Call A — track classification (always runs).
* Call B — per-track rubric, runs once per track Call A judged applicable.

Writes a single JSON output combining both calls, plus per-call records on
disk via ``lib.llm.call_model_for_json``. No verdict computation; that's the
wrapper's job. This script is the inner layer — schema or LLM failures are
allowed to crash up to the wrapper, which is responsible for graceful
degradation.

The two prompt files in ``judges/sponsor-0g/prompts/`` are the source of
truth for what the LLM is asked. This module renders them, validates the
responses, and assembles the result; it does not make policy decisions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Repo root (two levels up from scripts/) hosts ``lib/llm.py``; make it
# importable. Also reuse the same sys.path shim deterministic_prefilter uses
# for ``public_repo_check._slug`` and ``_ingest_parsing``.
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent.parent
_SAFE_REPO_SCRIPTS = _THIS_DIR.parent.parent / "safe-repo" / "scripts"
for _p in (_REPO_ROOT, _SAFE_REPO_SCRIPTS, _THIS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.llm import call_model_for_json  # noqa: E402

from public_repo_check import _slug  # type: ignore[import-not-found]  # noqa: E402
from _ingest_parsing import ParsedRepo, load_repo  # noqa: E402
from deterministic_prefilter import MANIFEST_NAMES, REQUIREMENTS_RE  # noqa: E402

JUDGE_NAME = "sponsor-0g"
PHASE = "llm-evaluation"

DEFAULT_PREFILTER_DIR = _THIS_DIR.parent / "artifacts" / "deterministic-prefilter"
DEFAULT_INGEST_DIR = (
    _THIS_DIR.parent.parent / "safe-repo" / "artifacts" / "repo-ingest-dump"
)
DEFAULT_OUTPUT_DIR = _THIS_DIR.parent / "artifacts" / "llm-evaluation"
DEFAULT_RECORDS_DIR = _THIS_DIR.parent / "artifacts" / "llm-call-records"

PROMPT_DIR = _THIS_DIR.parent / "prompts"
TRACK_CLASSIFICATION_PROMPT = PROMPT_DIR / "track-classification.md"
TRACK_RUBRIC_PROMPT = PROMPT_DIR / "track-rubric.md"

CONTEXT_PACK_CHAR_CEILING = 32000


# ---------------------------------------------------------------------------
# Track + rubric constants (SKILL.md is the source of truth)
# ---------------------------------------------------------------------------

FRAMEWORK_DEFINITION = (
    "Framework-level work: modules, libraries, tooling, scaffolding, visual "
    "builders, agent-construction primitives that other developers build "
    "agents with. A framework submission ships things developers consume."
)
AGENTS_DEFINITION = (
    "End-user-facing work: single autonomous agents, swarms or collectives "
    "of agents, or iNFT (ERC-7857) projects — things end users interact "
    "with. An agents submission ships things end users consume."
)

# Per-track rubric items, in the order they appear in SKILL.md's Phase 2
# rubric table. The LLM is instructed to return exactly these keys.
FRAMEWORK_RUBRIC_ITEMS: tuple[str, ...] = (
    "project-name-and-description",
    "contract-deployment-addresses",
    "public-repo-with-setup",
    "demo-video-link",
    "live-demo-link",
    "protocol-features-explained",
    "team-contact-info",
    "working-example-agent",
    "architecture-diagram",
)
AGENTS_RUBRIC_ITEMS: tuple[str, ...] = (
    "project-name-and-description",
    "contract-deployment-addresses",
    "public-repo-with-setup",
    "demo-video-link",
    "live-demo-link",
    "protocol-features-explained",
    "team-contact-info",
    "agent-communication-explanation",
    "inft-link-and-proof",
)

# Verbatim from the Source column of SKILL.md's Phase 2 rubric table.
RUBRIC_ITEM_DESCRIPTIONS: dict[str, str] = {
    "project-name-and-description": "Common",
    "contract-deployment-addresses": "Common",
    "public-repo-with-setup": "Common",
    "demo-video-link": "Common",
    "live-demo-link": "Common",
    "protocol-features-explained": (
        "Common — README explains which 0G features/SDKs were used"
    ),
    "team-contact-info": "Common — Telegram/X handles",
    "working-example-agent": (
        "Framework-only — \"at least one working example agent built using "
        "your framework/tooling\""
    ),
    "architecture-diagram": (
        "Framework-only — \"optional but strongly recommended\"; contributes "
        "signal but never sets `fail-rubric` on its own. Treated as a soft "
        "item: reported, never gates."
    ),
    "agent-communication-explanation": (
        "Agents-only, conditional on the LLM judging the project is a "
        "swarm/multi-agent system; otherwise `n-a`."
    ),
    "inft-link-and-proof": (
        "Agents-only, conditional on the LLM judging the project is an iNFT "
        "submission; otherwise `n-a`. **Strict ERC-7857 reading:** the "
        "project must implement ERC-7857 (intelligence/memory embedded in "
        "the NFT itself) for this item to `pass`. ERC-721 NFTs used as "
        "access tokens or gating mechanisms do not satisfy this item — "
        "Phase 2 records `fail` on the item (not `n-a`) when a project "
        "makes an iNFT claim with a non-ERC-7857 contract, and surfaces "
        "the contract standard in its reasoning."
    ),
}

VALID_COMPONENTS: frozenset[str] = frozenset({"Storage", "DA", "Compute", "Chain"})
VALID_CONFIDENCE: frozenset[str] = frozenset({"low", "medium", "high"})
VALID_RUBRIC_VALUES: frozenset[str] = frozenset(
    {"pass", "fail", "needs-human-verification", "n-a"}
)
VALID_INTEGRATION_VERDICTS: frozenset[str] = frozenset({"present", "absent"})

# File-extension → fenced-code-block language tag. Anything not mapped is
# emitted with no language tag (still a valid fence).
EXTENSION_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".sol": "solidity",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".swift": "swift",
    ".php": "php",
    ".cs": "csharp",
    ".scala": "scala",
    ".vy": "python",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "bash",
    ".bash": "bash",
    ".md": "markdown",
}

EXAMPLE_TOP_DIRS: tuple[str, ...] = ("examples", "example", "demo", "samples", "agents")
SOURCE_EXTS: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    ".go", ".rs", ".sol", ".java", ".kt", ".kts", ".cpp", ".cc", ".c",
    ".h", ".hpp", ".rb", ".swift", ".php", ".cs", ".scala", ".vy",
})


class LLMSchemaError(Exception):
    """Raised when an LLM response is well-formed JSON of the wrong shape."""


# ---------------------------------------------------------------------------
# Context-pack assembly
# ---------------------------------------------------------------------------

def _ext(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    return ("." + base.rsplit(".", 1)[-1].lower()) if "." in base else ""


def _lang_for(path: str) -> str:
    return EXTENSION_LANG.get(_ext(path), "")


def _is_manifest(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return base in MANIFEST_NAMES or bool(REQUIREMENTS_RE.match(base))


def _excerpt_around(content: str, line_no: int, window: int) -> str:
    """Return ``window`` lines on either side of ``line_no`` (1-indexed)."""
    lines = content.splitlines()
    if not lines:
        return ""
    start = max(0, line_no - 1 - window)
    end = min(len(lines), line_no + window)
    return "\n".join(lines[start:end])


def _truncate_lines(content: str, max_lines: int) -> str:
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content
    return "\n".join(lines[:max_lines])


def _readme_section(parsed: ParsedRepo) -> str:
    if parsed.readme_content is None:
        return "## README\n\n_No README found in the repo._"
    return (
        "## README\n\n"
        "Below is the project's README in full.\n\n"
        + parsed.readme_content
    )


def _truncate_readme_middle(section: str, head_lines: int = 200, tail_lines: int = 200) -> str:
    """Replace the body's middle with a truncation marker, preserving head/tail."""
    head, _, body = section.partition("\n\n")  # "## README"
    description, _, content = body.partition("\n\n")  # one-line description
    if not content:
        return section
    lines = content.splitlines()
    if len(lines) <= head_lines + tail_lines:
        return section
    new_body = (
        "\n".join(lines[:head_lines])
        + "\n\n_[truncated for length]_\n\n"
        + "\n".join(lines[-tail_lines:])
    )
    return f"{head}\n\n{description}\n\n{new_body}"


def _prefilter_section(prefilter: dict) -> str:
    items = prefilter.get("items", {}) or {}
    body_lines: list[str] = [
        "## Phase 1 deterministic findings",
        "",
        "Below is what the deterministic prefilter found. Treat as ground "
        "truth — do not re-derive.",
        "",
    ]
    for item_id in sorted(items):
        item = items[item_id] or {}
        if item.get("error"):
            body_lines.append(f"**{item_id}:** check errored: {item['error']}.")
            continue
        if not item.get("present"):
            body_lines.append(f"**{item_id}:** not found.")
            continue

        evidence = item.get("evidence") or []
        if item_id == "0g-component-mentions":
            body_lines.append(f"**{item_id}:**")
            for ev in evidence:
                snippet = (ev.get("snippet") or "").strip()
                if len(snippet) > 300:
                    snippet = snippet[:297] + "..."
                component = ev.get("component", "")
                file = ev.get("file", "")
                line = ev.get("line", "")
                body_lines.append(
                    f"  - **{component}** ({file}:{line}): {snippet}"
                )
        elif item_id == "0g-sdk-imports":
            parts = []
            for ev in evidence:
                ident = ev.get("identifier") or ""
                file = ev.get("file") or ""
                parts.append(f"in `{file}` (`{ident}`)")
            body_lines.append(f"**{item_id}:** found " + ", ".join(parts))
        else:
            parts = []
            for ev in evidence:
                file = ev.get("file") or ""
                value = ev.get("value") or ev.get("match") or ev.get("identifier") or ""
                if value:
                    parts.append(f"{file} ({value})")
                else:
                    parts.append(file)
            body_lines.append(f"**{item_id}:** found at " + ", ".join(parts))
    return "\n".join(body_lines)


def _manifests_section(parsed: ParsedRepo) -> str:
    manifests = sorted(p for p in parsed.files if _is_manifest(p))
    head = (
        "## Package manifests\n\n"
        "Below are the project's package manifests in full."
    )
    if not manifests:
        return head + "\n\n_No package manifests found._"
    parts = [head, ""]
    for path in manifests:
        lang = _lang_for(path)
        fence = f"```{lang}" if lang else "```"
        parts.append(f"### {path}")
        parts.append(fence)
        parts.append(parsed.files[path])
        parts.append("```")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _sdk_imports_section(parsed: ParsedRepo, prefilter: dict, *, window: int) -> str | None:
    """Return None when the section should be omitted entirely."""
    items = prefilter.get("items", {}) or {}
    sdk = (items.get("0g-sdk-imports") or {}).get("evidence") or []
    if not sdk:
        return None
    parts = [
        "## SDK import sites",
        "",
        "Below are excerpts from source files that import or use 0G SDKs, "
        "based on Phase 1 findings.",
        "",
    ]
    for ev in sdk:
        path = ev.get("file") or ""
        line_no = ev.get("line")
        content = parsed.files.get(path)
        if content is None or line_no is None:
            continue
        excerpt = _excerpt_around(content, line_no, window)
        lang = _lang_for(path)
        fence = f"```{lang}" if lang else "```"
        parts.append(f"### {path} (line {line_no})")
        parts.append(fence)
        parts.append(excerpt)
        parts.append("```")
        parts.append("")
    if len(parts) <= 4:
        return None
    return "\n".join(parts).rstrip() + "\n"


def _examples_section(
    parsed: ParsedRepo, *, include_file_bodies: bool, body_max_lines: int = 80
) -> str | None:
    by_dir: dict[str, list[str]] = {}
    for path in parsed.files:
        head = path.split("/", 1)[0] if "/" in path else ""
        if head.lower() not in EXAMPLE_TOP_DIRS:
            continue
        if _ext(path) not in SOURCE_EXTS:
            continue
        by_dir.setdefault(head, []).append(path)
    if not by_dir:
        return None
    parts = [
        "## Example directories",
        "",
        "Below are the structures of any examples/, demo/, samples/, or "
        "agents/ directories, plus the contents of the first source file "
        "from each.",
        "",
    ]
    for top in sorted(by_dir):
        files_in_dir = sorted(by_dir[top])
        parts.append(f"### {top}/")
        for path in files_in_dir:
            parts.append(f"- {path}")
        parts.append("")
        if include_file_bodies and files_in_dir:
            first = files_in_dir[0]
            content = _truncate_lines(parsed.files[first], body_max_lines)
            lang = _lang_for(first)
            fence = f"```{lang}" if lang else "```"
            parts.append(f"#### First source file: {first}")
            parts.append(fence)
            parts.append(content)
            parts.append("```")
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _assemble(parts: list[str | None]) -> str:
    return "\n\n---\n\n".join(p for p in parts if p is not None)


def _build_context_pack(parsed: ParsedRepo, prefilter: dict) -> str:
    """Build the LLM context pack from the parsed repo and the Phase 1 JSON.

    Sections are separated by ``\\n\\n---\\n\\n``; each starts with a markdown
    heading and a one-line description. If the assembled pack exceeds
    ``CONTEXT_PACK_CHAR_CEILING`` characters, it is trimmed in this order:
    (1) shorten SDK source-file excerpts; (2) drop example-directory file
    bodies; (3) truncate the README's middle. The README is never fully cut.
    """
    readme = _readme_section(parsed)
    findings = _prefilter_section(prefilter)
    manifests = _manifests_section(parsed)
    sdk = _sdk_imports_section(parsed, prefilter, window=15)
    examples = _examples_section(parsed, include_file_bodies=True)
    pack = _assemble([readme, findings, manifests, sdk, examples])

    if len(pack) <= CONTEXT_PACK_CHAR_CEILING:
        return pack

    sdk = _sdk_imports_section(parsed, prefilter, window=10)
    pack = _assemble([readme, findings, manifests, sdk, examples])
    if len(pack) <= CONTEXT_PACK_CHAR_CEILING:
        return pack

    examples = _examples_section(parsed, include_file_bodies=False)
    pack = _assemble([readme, findings, manifests, sdk, examples])
    if len(pack) <= CONTEXT_PACK_CHAR_CEILING:
        return pack

    readme = _truncate_readme_middle(readme)
    pack = _assemble([readme, findings, manifests, sdk, examples])
    return pack


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _read_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


def _rubric_table(item_ids: tuple[str, ...]) -> str:
    rows = ["| Item ID | Description |", "| --- | --- |"]
    for item_id in item_ids:
        desc = RUBRIC_ITEM_DESCRIPTIONS[item_id].replace("|", "\\|")
        rows.append(f"| `{item_id}` | {desc} |")
    return "\n".join(rows)


def _render_call_a(context_pack: str) -> str:
    template = _read_prompt(TRACK_CLASSIFICATION_PROMPT)
    return template.replace("{context_pack}", context_pack)


def _render_call_b(
    *,
    track_name: str,
    track_definition: str,
    rubric_items: tuple[str, ...],
    components_used: list[str],
    classification_reasoning: str,
    context_pack: str,
) -> str:
    template = _read_prompt(TRACK_RUBRIC_PROMPT)
    components = ", ".join(components_used) if components_used else "(none)"
    return (
        template
        .replace("{track_name}", track_name)
        .replace("{track_definition}", track_definition)
        .replace("{rubric_items_table}", _rubric_table(rubric_items))
        .replace("{components_used}", components)
        .replace("{classification_reasoning}", classification_reasoning)
        .replace("{context_pack}", context_pack)
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def _validate_call_a(data: object) -> dict:
    if not isinstance(data, dict):
        raise LLMSchemaError(
            f"Call A: expected JSON object, got {type(data).__name__}"
        )
    for field, expected in (
        ("framework_applicable", bool),
        ("agents_applicable", bool),
    ):
        if field not in data:
            raise LLMSchemaError(f"Call A: missing field '{field}'")
        if not isinstance(data[field], expected):
            raise LLMSchemaError(
                f"Call A: field '{field}' must be bool, got "
                f"{type(data[field]).__name__}"
            )
    if "components_used" not in data or not isinstance(data["components_used"], list):
        raise LLMSchemaError(
            "Call A: field 'components_used' must be a list of strings"
        )
    for entry in data["components_used"]:
        if not isinstance(entry, str):
            raise LLMSchemaError(
                f"Call A: components_used contains non-string entry "
                f"{entry!r}"
            )
        if entry not in VALID_COMPONENTS:
            raise LLMSchemaError(
                f"Call A: components_used contains invalid entry "
                f"'{entry}' (expected one of "
                f"{'|'.join(sorted(VALID_COMPONENTS))})"
            )
    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise LLMSchemaError("Call A: field 'reasoning' must be a non-empty string")
    confidence = data.get("confidence")
    if confidence not in VALID_CONFIDENCE:
        raise LLMSchemaError(
            f"Call A: field 'confidence' must be one of "
            f"{'|'.join(sorted(VALID_CONFIDENCE))}, got {confidence!r}"
        )
    return data


def _validate_call_b(data: object, *, track: str, expected_items: tuple[str, ...]) -> dict:
    if not isinstance(data, dict):
        raise LLMSchemaError(
            f"Call B ({track}): expected JSON object, got {type(data).__name__}"
        )
    rubric = data.get("rubric_items")
    if not isinstance(rubric, dict):
        raise LLMSchemaError(
            f"Call B ({track}): field 'rubric_items' must be an object"
        )
    expected = set(expected_items)
    actual = set(rubric.keys())
    missing = expected - actual
    extras = actual - expected
    if missing:
        raise LLMSchemaError(
            f"Call B ({track}): rubric_items missing required item(s): "
            f"{', '.join(sorted(missing))}"
        )
    if extras:
        raise LLMSchemaError(
            f"Call B ({track}): rubric_items has unexpected key(s): "
            f"{', '.join(sorted(extras))}"
        )
    for item_id, value in rubric.items():
        if value not in VALID_RUBRIC_VALUES:
            raise LLMSchemaError(
                f"Call B ({track}): rubric_items['{item_id}'] = {value!r} "
                f"(expected one of {'|'.join(sorted(VALID_RUBRIC_VALUES))})"
            )
    verdict = data.get("integration_verdict")
    if verdict not in VALID_INTEGRATION_VERDICTS:
        raise LLMSchemaError(
            f"Call B ({track}): integration_verdict must be one of "
            f"{'|'.join(sorted(VALID_INTEGRATION_VERDICTS))}, got "
            f"{verdict!r}"
        )
    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise LLMSchemaError(
            f"Call B ({track}): field 'reasoning' must be a non-empty string"
        )
    return data


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_TRACKS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("framework", "framework_applicable", "framework-rubric", FRAMEWORK_RUBRIC_ITEMS),
    ("agents", "agents_applicable", "agents-rubric", AGENTS_RUBRIC_ITEMS),
)

_TRACK_DEFINITIONS: dict[str, str] = {
    "framework": FRAMEWORK_DEFINITION,
    "agents": AGENTS_DEFINITION,
}


def run_llm_evaluation(
    *,
    repo_url: str,
    prefilter: dict,
    parsed: ParsedRepo,
    records_dir: Path,
    model: str | None = None,
) -> dict:
    """Run Call A + (conditional) Call B per applicable track."""
    context_pack = _build_context_pack(parsed, prefilter)

    raw_a = call_model_for_json(
        _render_call_a(context_pack),
        record_dir=records_dir,
        record_label="track-classification",
        model=model,
    )
    classification = _validate_call_a(raw_a)

    tracks: dict[str, dict | None] = {"framework": None, "agents": None}
    for track_name, applicable_field, label, items in _TRACKS:
        if not classification[applicable_field]:
            continue
        prompt_b = _render_call_b(
            track_name=track_name,
            track_definition=_TRACK_DEFINITIONS[track_name],
            rubric_items=items,
            components_used=list(classification["components_used"]),
            classification_reasoning=classification["reasoning"],
            context_pack=context_pack,
        )
        raw_b = call_model_for_json(
            prompt_b,
            record_dir=records_dir,
            record_label=label,
            model=model,
        )
        tracks[track_name] = _validate_call_b(raw_b, track=track_name, expected_items=items)

    resolved_model = model if model is not None else os.environ.get("MODEL")
    return {
        "judge": JUDGE_NAME,
        "phase": PHASE,
        "repo": repo_url,
        "slug": _slug(repo_url),
        "model": resolved_model,
        "classification": classification,
        "tracks": tracks,
        "records_dir": str(records_dir.resolve()),
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

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


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    slug = _slug(args.repo_url)
    prefilter_path = (
        args.prefilter_path if args.prefilter_path is not None
        else DEFAULT_PREFILTER_DIR / f"{slug}.json"
    )
    ingest_path = (
        args.ingest_path if args.ingest_path is not None
        else DEFAULT_INGEST_DIR / f"{slug}.txt"
    )
    output_path = (
        args.output_path if args.output_path is not None
        else DEFAULT_OUTPUT_DIR / f"{slug}.json"
    )
    records_dir = (
        args.records_dir if args.records_dir is not None
        else DEFAULT_RECORDS_DIR / slug
    )
    return prefilter_path, ingest_path, output_path, records_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sponsor-0g Phase 2 LLM evaluation")
    parser.add_argument("repo_url", help="Git repository URL the artifacts correspond to")
    parser.add_argument(
        "--prefilter-path",
        type=Path,
        default=None,
        help=(
            "explicit path to the Phase 1 prefilter JSON "
            f"(default: {DEFAULT_PREFILTER_DIR}/<slug>.json)"
        ),
    )
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
            "explicit path for the LLM evaluation JSON "
            f"(default: {DEFAULT_OUTPUT_DIR}/<slug>.json)"
        ),
    )
    parser.add_argument(
        "--records-dir",
        type=Path,
        default=None,
        help=(
            "directory for individual LLM call records "
            f"(default: {DEFAULT_RECORDS_DIR}/<slug>/)"
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="model string passed to lib.llm; defaults to the MODEL env var",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="suppress writing the JSON result to disk (still printed to stdout)",
    )
    args = parser.parse_args(argv)

    prefilter_path, ingest_path, output_path, records_dir = _resolve_paths(args)

    if not prefilter_path.exists():
        print(
            f"prefilter JSON not found: {prefilter_path}\n"
            "Run sponsor-0g Phase 1 (deterministic_prefilter.py) first.",
            file=sys.stderr,
        )
        return 1
    if not ingest_path.exists():
        print(
            f"ingest artifact not found: {ingest_path}\n"
            "Run safe-repo (judges/safe-repo/scripts/public_repo_check.py) first.",
            file=sys.stderr,
        )
        return 1
    if not TRACK_CLASSIFICATION_PROMPT.exists() or not TRACK_RUBRIC_PROMPT.exists():
        print(
            f"prompt files missing in {PROMPT_DIR}; expected "
            "track-classification.md and track-rubric.md",
            file=sys.stderr,
        )
        return 1

    try:
        prefilter = json.loads(prefilter_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"could not parse prefilter JSON at {prefilter_path}: {exc}", file=sys.stderr)
        return 1
    try:
        parsed = load_repo(ingest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"could not parse ingest artifact at {ingest_path}: {exc}", file=sys.stderr)
        return 1

    result = run_llm_evaluation(
        repo_url=args.repo_url,
        prefilter=prefilter,
        parsed=parsed,
        records_dir=records_dir,
        model=args.model,
    )

    if not args.no_write:
        _atomic_write_json(output_path, result)
        print(f"wrote {output_path}", file=sys.stderr)

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
