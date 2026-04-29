"""dependency_safety_check.py — second judge in the safe-repo stage.

Reads the ingest artifact produced by `public_repo_check.py` and scans dependency manifests and install scripts for things that would harm a human judge running the project locally. Emits JSON to stdout.

Scope: triage, not a SAST scanner. Threat model is "what could silently hose a judge's laptop during ``npm install`` or ``./setup.sh``."
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

JUDGE_NAME = "dependency-safety"
_ARTIFACTS_ROOT = Path(__file__).parent.parent / "artifacts"
DEFAULT_ARTIFACT_DIR = _ARTIFACTS_ROOT / "repo-ingest-dump"
DEFAULT_OUTPUT_DIR = _ARTIFACTS_ROOT / "deps-safety-check"


# ---------------------------------------------------------------------------
# Severity routing
# ---------------------------------------------------------------------------

SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3}


def _max_severity(findings: list[dict]) -> str:
    if not findings:
        return "pass"
    return max(
        (f["severity"] for f in findings),
        key=lambda s: SEVERITY_RANK[s],
    )


# ---------------------------------------------------------------------------
# Known-malicious package list (extend by appending)
# ---------------------------------------------------------------------------

MALICIOUS_PACKAGES: dict[str, set[str]] = {
    "npm": {
        "crossenv",            # typosquat of cross-env
        "discord.dll",         # known malware drop
        "event-stream",        # compromised at v3.3.6
        "flatmap-stream",      # malware injected via event-stream
        "eslint-scope",        # 3.7.2 was compromised
        "eslint-config-eslint",
        "electorn",            # typosquat of electron
        "fallguys",
        "loadyaml",
        "ua-parser-js",        # compromised versions
        "coa",                 # compromised
        "rc",                  # compromised versions
        "node-ipc",            # protestware
        "colors",              # protestware infinite-loop versions
        "faker",               # author-sabotaged versions
    },
    "pypi": {
        "urlib3",              # typosquat of urllib3
        "python3-dateutil",    # typosquat
        "jeIlyfish",           # typosquat (capital I as l)
        "requesys",            # typosquat
        "easyinstall",         # typosquat
        "colourama",           # typosquat of colorama
    },
    "rubygems": {
        "rest-client",         # specific compromised versions
    },
    "crates": set(),
    "go": set(),
}


# ---------------------------------------------------------------------------
# Suspicious pattern regexes (extend by appending)
# ---------------------------------------------------------------------------

# Pipe-to-shell: ``curl <url> | sh`` / ``bash <(curl ...)``.
PIPE_TO_SHELL = re.compile(
    r"(?:\b(?:curl|wget|fetch)\b[^|;\n]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|ksh)\b"
    r"|\b(?:bash|sh|zsh|ksh)\s+<\(\s*(?:curl|wget|fetch)\b)",
    re.IGNORECASE,
)

# Download → chmod +x → execute. Stronger signal than a pipe.
DOWNLOAD_AND_EXEC = re.compile(
    r"\b(?:curl|wget)\b[^\n]*?(?:-O\b|-o\s+\S+|--output\s+\S+|>\s*\S+)"
    r"[\s\S]{0,200}?chmod\s+\+x[\s\S]{0,200}?(?:\./|\bexec\b)",
    re.IGNORECASE,
)

# Read from a credential / secrets path.
SECRET_READ = re.compile(
    r"\b(?:cat|less|tail|head|cp|mv|tar|zip|gzip|base64|curl|wget|scp|rsync|nc)\b"
    r"[^\n]*"
    r"(?:~/\.ssh|\$HOME/\.ssh|~/\.aws|\$HOME/\.aws|~/\.config|\$HOME/\.config"
    r"|\.env\b|/etc/passwd|/etc/shadow)",
    re.IGNORECASE,
)

# Outbound HTTP POST / upload.
HTTP_POST = re.compile(
    r"(?:\bcurl\b[^\n]*?(?:--data\b|--data-binary\b|--upload-file\b|-X\s*POST\b|-d\s)"
    r"|\bwget\b[^\n]*?--post-data\b"
    r"|\baxios\.post\b|\brequests\.post\b"
    r"|\bfetch\([^)]*method:\s*['\"]POST['\"])",
    re.IGNORECASE,
)

# Persistence: rc files, ssh config, cron entries.
PERSISTENCE_MOD = re.compile(
    r"(?:>>?\s*~?/?\.(?:bashrc|zshrc|profile|bash_profile|bash_login|zprofile)\b"
    r"|>>?\s*~?/?\.ssh/(?:config|authorized_keys|known_hosts)\b"
    r"|\bcrontab\s+(?:-|<)"
    r"|>>?\s*/etc/cron|/var/spool/cron"
    r"|\bschtasks\s+/create\b)",
    re.IGNORECASE,
)

# ``sudo`` invocation at the start of a line.
SUDO_PATTERN = re.compile(r"^\s*sudo\b", re.MULTILINE)

# Tokens that suggest a script is just building the project (benign).
BENIGN_BUILD_TOKENS = re.compile(
    r"\b(?:tsc|webpack|rollup|vite|esbuild|babel|prebuild|node-gyp(?:\s+rebuild)?|"
    r"npm\s+(?:install|run|ci)|yarn\s+(?:install|build)|pnpm\s+(?:install|build)|bun\s+install|"
    r"python\s+-?m?\s*build|setup\.py\s+build|cargo\s+build|go\s+build|make\b|"
    r"apt(?:-get)?\s+install|brew\s+install|yum\s+install|dnf\s+install|pacman\s+-S\b)",
    re.IGNORECASE,
)

# Non-registry dependency reference.
GIT_OR_LOCAL_DEP = re.compile(r"^(git\+|git://|git@|file:|\.{1,2}/|/)", re.IGNORECASE)

# Setup-script filenames.
SETUP_SCRIPT_PATTERN = re.compile(
    r"(?:^|/)(?:setup|install|bootstrap|init|configure|deploy)"
    r"(?:[-_][A-Za-z0-9]+)?\.(?:sh|bash|zsh)$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Artifact parsing
# ---------------------------------------------------------------------------

_FILE_HEADER_RE = re.compile(
    r"^={3,}\s*\nFILE:\s*(?P<path>.+?)\s*\n={3,}\s*\n",
    re.MULTILINE,
)
_CONTENTS_HEADER_RE = re.compile(r"={3,}\s*\nCONTENTS\s*\n={3,}\s*\n")


def parse_artifact(text: str) -> tuple[dict, dict[str, str]]:
    """Return (metadata, files) parsed from a public_repo_check artifact."""
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
        return meta, {}
    body = text[contents.end():]

    files: dict[str, str] = {}
    matches = list(_FILE_HEADER_RE.finditer(body))
    for i, m in enumerate(matches):
        path = m.group("path").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        files[path] = body[start:end].rstrip("\n")
    return meta, files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_at(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _line_text(content: str, line_no: int, max_len: int = 200) -> str:
    lines = content.splitlines()
    if 1 <= line_no <= len(lines):
        text = lines[line_no - 1].strip()
        return text[:max_len] + ("..." if len(text) > max_len else "")
    return ""


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _flag_packages(
    names: list[tuple[str, str | None, int | None]],
    ecosystem: str,
    file_path: str,
    section: str,
) -> list[dict]:
    """Match package names against the malicious list."""
    bad = MALICIOUS_PACKAGES.get(ecosystem, set())
    findings: list[dict] = []
    for name, version, line_no in names:
        if name.lower() in bad:
            location = f"{file_path}:{line_no}" if line_no else f"{file_path}:{section}"
            findings.append(
                {
                    "severity": "critical",
                    "category": "malicious-package",
                    "location": location,
                    "detail": (
                        f"Package '{name}' is on the known-malicious "
                        f"list for {ecosystem}."
                    ),
                    "evidence": f"{name}=={version}" if version else name,
                }
            )
    return findings


def _scan_install_script(
    file_path: str,
    content: str,
    section_label: str,
    *,
    treat_as_install_hook: bool,
) -> list[dict]:
    """Scan a script body for dangerous patterns.

    ``treat_as_install_hook=True`` raises certain patterns to critical because
    they auto-execute during install (npm hook, ``make install``, etc.).
    """
    findings: list[dict] = []
    location_suffix = f" ({section_label})" if section_label else ""

    def add(severity: str, category: str, line_no: int, detail: str, evidence: str):
        findings.append(
            {
                "severity": severity,
                "category": category,
                "location": f"{file_path}:{line_no}{location_suffix}",
                "detail": detail,
                "evidence": evidence,
            }
        )

    for m in DOWNLOAD_AND_EXEC.finditer(content):
        line_no = _line_at(content, m.start())
        add(
            "critical",
            "remote-exec",
            line_no,
            "Script downloads a file, marks it executable, and runs it.",
            _line_text(content, line_no) or m.group(0)[:200],
        )

    for m in SECRET_READ.finditer(content):
        line_no = _line_at(content, m.start())
        add(
            "critical",
            "credential-read",
            line_no,
            "Script reads from a credential or secrets path.",
            _line_text(content, line_no) or m.group(0)[:200],
        )

    for m in PERSISTENCE_MOD.finditer(content):
        line_no = _line_at(content, m.start())
        add(
            "critical",
            "persistence-mod",
            line_no,
            "Script modifies shell rc, ssh config, or cron entries.",
            _line_text(content, line_no) or m.group(0)[:200],
        )

    for m in HTTP_POST.finditer(content):
        line_no = _line_at(content, m.start())
        add(
            "critical" if treat_as_install_hook else "warning",
            "exfil-post",
            line_no,
            "Script issues an outbound POST/upload.",
            _line_text(content, line_no) or m.group(0)[:200],
        )

    for m in PIPE_TO_SHELL.finditer(content):
        line_no = _line_at(content, m.start())
        add(
            "critical" if treat_as_install_hook else "warning",
            "pipe-to-shell",
            line_no,
            "Pipes the output of a network fetch directly into a shell.",
            _line_text(content, line_no) or m.group(0)[:200],
        )

    for m in SUDO_PATTERN.finditer(content):
        line_no = _line_at(content, m.start())
        line = _line_text(content, line_no)
        if not line or BENIGN_BUILD_TOKENS.search(line):
            continue
        add(
            "warning",
            "sudo-use",
            line_no,
            "Script invokes sudo without an obvious build/install justification.",
            line,
        )

    return findings


# ---------------------------------------------------------------------------
# npm
# ---------------------------------------------------------------------------

NPM_INSTALL_HOOKS = ("preinstall", "install", "postinstall", "prepare")


def check_package_json(file_path: str, content: str) -> list[dict]:
    findings: list[dict] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return [
            {
                "severity": "info",
                "category": "manifest-parse-error",
                "location": file_path,
                "detail": f"Could not parse package.json: {exc}",
                "evidence": "",
            }
        ]
    if not isinstance(data, dict):
        return findings

    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        deps = data.get(section) or {}
        if not isinstance(deps, dict):
            continue
        package_list: list[tuple[str, str | None, int | None]] = []
        for name, version in deps.items():
            package_list.append((name, str(version), None))
            if isinstance(version, str) and GIT_OR_LOCAL_DEP.match(version):
                findings.append(
                    {
                        "severity": "warning",
                        "category": "non-registry-dep",
                        "location": f"{file_path}:{section}",
                        "detail": (
                            f"Dependency '{name}' is pinned to a "
                            f"non-registry source ({version})."
                        ),
                        "evidence": f'"{name}": "{version}"',
                    }
                )
        findings.extend(_flag_packages(package_list, "npm", file_path, section))

    scripts = data.get("scripts") or {}
    if isinstance(scripts, dict):
        for hook in NPM_INSTALL_HOOKS:
            body = scripts.get(hook)
            if not isinstance(body, str) or not body.strip():
                continue
            hook_findings = _scan_install_script(
                file_path,
                body,
                section_label=f"scripts.{hook}",
                treat_as_install_hook=True,
            )
            findings.extend(hook_findings)
            if (
                hook == "postinstall"
                and not BENIGN_BUILD_TOKENS.search(body)
                and not any(f["severity"] == "critical" for f in hook_findings)
            ):
                findings.append(
                    {
                        "severity": "warning",
                        "category": "postinstall-script",
                        "location": f"{file_path}:scripts.{hook}",
                        "detail": (
                            "postinstall script does non-trivial work — "
                            "review before installing."
                        ),
                        "evidence": body[:200],
                    }
                )

    return findings


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*"
    r"(?:(?:[<>=!~]=?|==|>=|<=)\s*([^\s#;]*))?"
)


def check_requirements_txt(file_path: str, content: str) -> list[dict]:
    findings: list[dict] = []
    package_list: list[tuple[str, str | None, int]] = []
    for line_no, raw in enumerate(content.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith(("-e ", "-e\t")) or line.startswith("git+"):
            findings.append(
                {
                    "severity": "warning",
                    "category": "non-registry-dep",
                    "location": f"{file_path}:{line_no}",
                    "detail": "Editable or git-URL pip dependency.",
                    "evidence": raw.strip(),
                }
            )
            continue
        if line.startswith("-"):
            continue
        m = _REQ_LINE.match(line)
        if not m:
            continue
        package_list.append((m.group(1), m.group(2) or None, line_no))
    findings.extend(_flag_packages(package_list, "pypi", file_path, "deps"))
    return findings


def _flatten_python_deps(data: dict) -> list[str]:
    names: list[str] = []
    project = data.get("project") or {}
    for dep in project.get("dependencies") or []:
        if isinstance(dep, str):
            names.append(dep)
    optional = project.get("optional-dependencies") or {}
    if isinstance(optional, dict):
        for group in optional.values():
            if isinstance(group, list):
                names.extend(d for d in group if isinstance(d, str))
    poetry = (data.get("tool") or {}).get("poetry") or {}
    for section in ("dependencies", "dev-dependencies"):
        deps = poetry.get(section) or {}
        if isinstance(deps, dict):
            names.extend(deps.keys())
    return names


def check_pyproject(file_path: str, content: str) -> list[dict]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        return [
            {
                "severity": "info",
                "category": "manifest-parse-error",
                "location": file_path,
                "detail": f"Could not parse pyproject.toml: {exc}",
                "evidence": "",
            }
        ]
    package_list: list[tuple[str, str | None, int | None]] = []
    for raw in _flatten_python_deps(data):
        m = re.match(r"^([A-Za-z0-9_.\-]+)", raw)
        if m:
            package_list.append((m.group(1), None, None))
    return _flag_packages(package_list, "pypi", file_path, "deps")


def check_pipfile(file_path: str, content: str) -> list[dict]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        return [
            {
                "severity": "info",
                "category": "manifest-parse-error",
                "location": file_path,
                "detail": f"Could not parse Pipfile: {exc}",
                "evidence": "",
            }
        ]
    package_list: list[tuple[str, str | None, int | None]] = []
    for section in ("packages", "dev-packages"):
        deps = data.get(section) or {}
        if isinstance(deps, dict):
            package_list.extend((name, None, None) for name in deps)
    return _flag_packages(package_list, "pypi", file_path, "packages")


# ---------------------------------------------------------------------------
# Cargo / Go / Ruby
# ---------------------------------------------------------------------------

def check_cargo_toml(file_path: str, content: str) -> list[dict]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        return [
            {
                "severity": "info",
                "category": "manifest-parse-error",
                "location": file_path,
                "detail": f"Could not parse Cargo.toml: {exc}",
                "evidence": "",
            }
        ]
    package_list: list[tuple[str, str | None, int | None]] = []
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        deps = data.get(section) or {}
        if isinstance(deps, dict):
            package_list.extend((name, None, None) for name in deps)
    return _flag_packages(package_list, "crates", file_path, "deps")


def check_go_mod(file_path: str, content: str) -> list[dict]:
    package_list: list[tuple[str, str | None, int]] = []
    in_block = False
    for line_no, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if in_block or line.startswith("require "):
            stripped = line.removeprefix("require ").strip()
            parts = stripped.split()
            if parts:
                package_list.append((parts[0], None, line_no))
    return _flag_packages(package_list, "go", file_path, "require")


def check_gemfile(file_path: str, content: str) -> list[dict]:
    package_list: list[tuple[str, str | None, int]] = []
    gem_re = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"]")
    for line_no, raw in enumerate(content.splitlines(), 1):
        m = gem_re.match(raw)
        if m:
            package_list.append((m.group(1), None, line_no))
    return _flag_packages(package_list, "rubygems", file_path, "gem")


# ---------------------------------------------------------------------------
# Setup scripts / Makefile
# ---------------------------------------------------------------------------

def check_shell_script(file_path: str, content: str) -> list[dict]:
    return _scan_install_script(
        file_path,
        content,
        section_label=_basename(file_path),
        treat_as_install_hook=False,
    )


_MAKE_TARGET = re.compile(r"^([A-Za-z0-9_./\-]+)\s*:", re.MULTILINE)


def check_makefile(file_path: str, content: str) -> list[dict]:
    findings: list[dict] = []
    matches = list(_MAKE_TARGET.finditer(content))
    for i, m in enumerate(matches):
        if m.group(1).strip() != "install":
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end]
        findings.extend(
            _scan_install_script(
                file_path,
                body,
                section_label="install target",
                treat_as_install_hook=True,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Lockfile presence (info)
# ---------------------------------------------------------------------------

LOCKFILES: dict[str, tuple[str, ...]] = {
    "package.json": ("package-lock.json", "yarn.lock", "pnpm-lock.yaml"),
    "requirements.txt": ("requirements.lock", "uv.lock", "pip-tools.lock"),
    "pyproject.toml": ("uv.lock", "poetry.lock", "pdm.lock"),
    "Pipfile": ("Pipfile.lock",),
    "Cargo.toml": ("Cargo.lock",),
    "Gemfile": ("Gemfile.lock",),
}


def check_lockfile_presence(files: dict[str, str]) -> list[dict]:
    findings: list[dict] = []
    basenames = {_basename(p): p for p in files}
    for manifest, lockfiles in LOCKFILES.items():
        if manifest not in basenames:
            continue
        if any(lf in basenames for lf in lockfiles):
            continue
        findings.append(
            {
                "severity": "info",
                "category": "missing-lockfile",
                "location": basenames[manifest],
                "detail": (
                    f"{manifest} present but no lockfile "
                    f"({', '.join(lockfiles)}) found."
                ),
                "evidence": "",
            }
        )
    return findings


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

CHECKERS = [
    (re.compile(r"(?:^|/)package\.json$"), check_package_json),
    (re.compile(r"(?:^|/)requirements[\w.\-]*\.txt$"), check_requirements_txt),
    (re.compile(r"(?:^|/)pyproject\.toml$"), check_pyproject),
    (re.compile(r"(?:^|/)Pipfile$"), check_pipfile),
    (re.compile(r"(?:^|/)Cargo\.toml$"), check_cargo_toml),
    (re.compile(r"(?:^|/)go\.mod$"), check_go_mod),
    (re.compile(r"(?:^|/)Gemfile$"), check_gemfile),
    (re.compile(r"(?:^|/)Makefile$"), check_makefile),
    (SETUP_SCRIPT_PATTERN, check_shell_script),
]


def analyze(files: dict[str, str]) -> list[dict]:
    findings: list[dict] = []
    for path, body in files.items():
        for pattern, checker in CHECKERS:
            if pattern.search(path):
                findings.extend(checker(path, body))
                break
    findings.extend(check_lockfile_presence(files))
    return findings


# ---------------------------------------------------------------------------
# Top-level summary
# ---------------------------------------------------------------------------

def _summary(severity: str, findings: list[dict]) -> str:
    if severity == "pass":
        return "no dependency-safety issues found"
    counts = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    parts = [f"{counts[k]} {k}" for k in ("critical", "warning", "info") if counts[k]]
    return "dependency-safety findings: " + ", ".join(parts)


def judge(artifact_path: Path) -> dict:
    text = artifact_path.read_text(encoding="utf-8")
    meta, files = parse_artifact(text)
    findings = analyze(files)
    severity = _max_severity(findings)
    return {
        "judge": JUDGE_NAME,
        "repo": meta.get("source_url"),
        "artifact_path": str(artifact_path),
        "severity": severity,
        "passed": severity != "critical",
        "finding": _summary(severity, findings),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="dependency-safety judge")
    parser.add_argument(
        "artifact_path",
        type=Path,
        nargs="?",
        help="path to the public_repo_check ingest artifact",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help=f"directory containing ingest artifacts (default: {DEFAULT_ARTIFACT_DIR})",
    )
    parser.add_argument(
        "--artifact-name",
        type=str,
        help="resolve artifact relative to --artifact-dir",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"directory for judge JSON output (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="suppress writing the JSON result to --output-dir",
    )
    args = parser.parse_args()

    artifact_path = args.artifact_path
    if artifact_path is None:
        if args.artifact_name is None:
            parser.error("provide artifact_path or --artifact-name")
        artifact_path = args.artifact_dir / args.artifact_name
    if not artifact_path.exists():
        print(f"artifact not found: {artifact_path}", file=sys.stderr)
        return 2

    result = judge(artifact_path)

    if not args.no_write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = args.output_dir / f"{artifact_path.stem}.json"
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path}", file=sys.stderr)

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
