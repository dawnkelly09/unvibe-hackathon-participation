"""Parser for safe-repo's gitingest text artifact.

Extracted from the parsing logic in
``judges/safe-repo/scripts/dependency_safety_check.py``. Lives here for now
because sponsor-0g is the second consumer of the format; could be hoisted to
a shared ``judges/_lib/`` location once a third judge needs it.

The artifact format is:

    ============================================
    SAFE-REPO INGEST ARTIFACT
    ============================================
    Source URL: <url>
    Repository: <name>
    Commit: <sha>
    ...

    ============================================
    TREE
    ============================================
    <directory listing>

    ============================================
    CONTENTS
    ============================================
    ============================================
    FILE: <relative path>
    ============================================
    <file body>

    ============================================
    FILE: <next path>
    ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FILE_HEADER_RE = re.compile(
    r"^={3,}\s*\nFILE:\s*(?P<path>.+?)\s*\n={3,}\s*\n",
    re.MULTILINE,
)
_CONTENTS_HEADER_RE = re.compile(r"={3,}\s*\nCONTENTS\s*\n={3,}\s*\n")


@dataclass
class ParsedRepo:
    """Lightweight container for the inputs each item check needs."""

    metadata: dict
    files: dict[str, str]
    readme_path: str | None = None
    readme_content: str | None = None
    extras: dict = field(default_factory=dict)


def parse_ingest_artifact(text: str) -> tuple[dict, dict[str, str]]:
    """Return ``(metadata, files)`` parsed from a safe-repo ingest artifact.

    ``metadata`` carries best-effort source URL, repository, and commit. ``files``
    maps the relative path of each ingested file to its raw text body.

    Raises ``ValueError`` if the artifact has no ``CONTENTS`` section. An
    artifact that has the section but no ``FILE:`` blocks is returned as an
    empty ``files`` dict.
    """
    meta: dict = {"source_url": None, "repository": None, "commit": None}
    for line in text.splitlines():
        if line.startswith("Source URL:"):
            meta["source_url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Repository:"):
            meta["repository"] = line.split(":", 1)[1].strip()
        elif line.startswith("Commit:"):
            meta["commit"] = line.split(":", 1)[1].strip()

    contents = _CONTENTS_HEADER_RE.search(text)
    if not contents:
        raise ValueError("ingest artifact has no CONTENTS section")
    body = text[contents.end():]

    files: dict[str, str] = {}
    matches = list(_FILE_HEADER_RE.finditer(body))
    for i, m in enumerate(matches):
        path = m.group("path").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        files[path] = body[start:end].rstrip("\n")
    return meta, files


def find_top_level_readme(files: dict[str, str]) -> tuple[str | None, str | None]:
    """Locate the top-level README file.

    "Top-level" means the relative path has no directory component. Match is
    case-insensitive on the stem (``README``) and ignores extension. If both
    ``README.md`` and another README exist, ``README.md`` wins; otherwise the
    first match in sorted order is returned for determinism.
    """
    candidates: list[str] = []
    for path in files:
        if "/" in path:
            continue
        base = path.rsplit("/", 1)[-1]
        stem = base.split(".", 1)[0]
        if stem.upper() == "README":
            candidates.append(path)
    if not candidates:
        return None, None
    for c in candidates:
        if c.lower().endswith(".md"):
            return c, files[c]
    chosen = sorted(candidates)[0]
    return chosen, files[chosen]


def load_repo(text: str) -> ParsedRepo:
    """Parse the artifact and resolve the top-level README in one step."""
    meta, files = parse_ingest_artifact(text)
    readme_path, readme_content = find_top_level_readme(files)
    return ParsedRepo(
        metadata=meta,
        files=files,
        readme_path=readme_path,
        readme_content=readme_content,
    )
