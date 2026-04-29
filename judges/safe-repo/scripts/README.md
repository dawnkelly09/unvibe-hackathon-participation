# safe-repo scripts

Two judges. The first verifies a submission has a public repo and produces an
ingest artifact on disk. The second reads that artifact and triages dependency
manifests / install scripts for things that would harm a human judge running
the project locally.

| Script                       | Role         | Input           | Output                      |
| ---------------------------- | ------------ | --------------- | --------------------------- |
| `public_repo_check.py`       | first judge  | repo URL        | ingest artifact (text file) |
| `dependency_safety_check.py` | second judge | ingest artifact | JSON to stdout              |

---

## `dependency_safety_check.py`

### What It Checks

| Source                                                               | Checks                                                                                                                               |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `package.json` (npm)                                                 | `dependencies`, `devDependencies`, `optionalDependencies`, and the `preinstall` / `install` / `postinstall` / `prepare` script hooks |
| `requirements.txt`, `pyproject.toml`, `Pipfile` (Python)             | declared deps                                                                                                                        |
| `Cargo.toml` (Rust)                                                  | `dependencies`, `dev-dependencies`, `build-dependencies`                                                                             |
| `go.mod` (Go)                                                        | `require` block                                                                                                                      |
| `Gemfile` (Ruby)                                                     | `gem` lines                                                                                                                          |
| Setup shell scripts (`setup.sh`, `install.sh`, `bootstrap.sh`, etc.) | suspicious patterns                                                                                                                  |
| `Makefile`                                                           | the `install:` target body                                                                                                           |
| Any manifest                                                         | sibling lockfile presence                                                                                                            |

### Severity levels

| Level      | Meaning                                                                                                                                                                                                             | Routing                                |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `critical` | Unambiguous threat: known-malicious package, credential read on `~/.ssh` / `~/.aws` / `.env`, rc/cron/ssh-config modification, remote-binary download-and-execute, or an outbound POST/upload from an install hook. | Auto-reject. `passed=false`, exit `1`. |
| `warning`  | Sketchy-but-plausible: `curl \| bash` in a setup script, non-trivial postinstall, deps pinned to git/local paths, unjustified `sudo`.                                                                               | Flag for human review. `passed=true`.  |
| `info`     | Annotated only: missing lockfile, manifest parse error.                                                                                                                                                             | `passed=true`.                         |
| `pass`     | Nothing flagged.                                                                                                                                                                                                    | `passed=true`.                         |

### Output schema

```json
{
  "judge": "dependency-safety",
  "repo": "<source url from artifact>",
  "artifact_path": "<input path>",
  "severity": "critical | warning | info | pass",
  "passed": true,
  "finding": "<one-line summary>",
  "findings": [
    {
      "severity": "critical | warning | info",
      "category": "malicious-package | remote-exec | credential-read | persistence-mod | exfil-post | pipe-to-shell | postinstall-script | non-registry-dep | sudo-use | missing-lockfile | manifest-parse-error",
      "location": "<file path : line or section>",
      "detail": "<one-line explanation>",
      "evidence": "<triggering snippet>"
    }
  ]
}
```

Top-level `severity` is the highest severity in `findings[]`. Exit code is
`0` when `passed` is `true`, `1` otherwise.

### Usage

```bash
# Direct path:
python dependency_safety_check.py path/to/artifact.txt

# Or resolve under --artifact-dir (matches public_repo_check convention):
python dependency_safety_check.py \
  --artifact-dir judges/safe-repo/artifacts \
  --artifact-name github.com_dawnkelly09_BYTEBEAST-ARENA.txt
```

stdout is reserved for the JSON output. Status messages, if any, go to stderr.

### Extending

- **Malicious-package list** — edit `MALICIOUS_PACKAGES` near the top of the
  script. It's a `dict[str, set[str]]` keyed by ecosystem (`"npm"`, `"pypi"`,
  `"rubygems"`, `"crates"`, `"go"`). Add a name and a comment explaining why.
- **Suspicious patterns** — the module-level regexes are the knobs:
  `PIPE_TO_SHELL`, `DOWNLOAD_AND_EXEC`, `SECRET_READ`, `HTTP_POST`,
  `PERSISTENCE_MOD`, `SUDO_PATTERN`, `BENIGN_BUILD_TOKENS`. Add an alternative
  to the relevant pattern.
- **A new manifest type** — write `check_<thing>(file_path, content) -> list[dict]`
  and register it in `CHECKERS` with a path-matching regex.

### Scope

This is a triage tool. Outdated-but-not-known-vulnerable deps are info; CVE
matching is out of scope. The threat model is "what could silently hose a
judge's laptop during `npm install` or `./setup.sh`."

### Tests

```bash
uv run --group dev pytest judges/safe-repo/tests
```
