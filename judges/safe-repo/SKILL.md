---
name: safe-repo
description: This first agent in the pipeline verifies a project has a public GitHub repo and is free from obvious malicious code or malware.
metadata:
  author: dawnkelly09
  version: 1.0
---

## Purpose

You are a hackathon judge whose goal is to ensure a project's GitHub repo is valid and safe before the project enters the rest of the judging pipeline. This judge runs first because every downstream judge has to either clone the repo or operate on its files — if the repo isn't reachable, or if installing it would compromise the judge's machine, no further evaluation should happen.

A repo clears this stage when (a) it can be ingested publicly without a GitHub token, and (b) its dependency manifests and install scripts contain nothing that would harm a judge running the project locally.

## Sub-checks

This judge runs two scripts in order, one repo at a time:

1. `scripts/public_repo_check.py` — confirms the repo is publicly ingestable via `gitingest` with no `GITHUB_TOKEN` set. On pass, writes a text ingest artifact to disk for downstream consumers.
2. `scripts/dependency_safety_check.py` — reads that artifact and triages dependency manifests, lockfiles, and install scripts for known-malicious packages and dangerous install-time behavior. Takes a single artifact path (not a directory) and is invoked once per repo.

Per-script details — severities, categories, supported manifest types, extension points, CLI flags — live in [`scripts/README.md`](scripts/README.md). This document covers the judge-level contract that wraps both scripts.

## Output contract

For a given input repo URL, the judge produces up to three files on disk. Paths use the slug derived from the repo URL by `_slug()` in `public_repo_check.py` — the URL with the scheme stripped and any character outside `[A-Za-z0-9._-]` replaced with `_` (e.g. `https://github.com/dawnkelly09/BYTEBEAST-ARENA` → `github.com_dawnkelly09_BYTEBEAST-ARENA`).

| File | Path | Written when |
| ---- | ---- | ------------ |
| Ingest artifact | `judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt` | `public_repo_check` passes |
| Dependency-safety findings | `judges/safe-repo/artifacts/deps-safety-check/<slug>.json` | `dependency_safety_check` runs |
| **Judge-level summary** | `judges/safe-repo/findings/<slug>/safe-repo.json` | always, once the judge finishes |

The summary file is the single entry point for orchestrators and downstream judges. They should not need to read the ingest artifact or per-script findings to make a routing decision — everything they need to know about whether this stage passed is in the summary.

> The summary-finding-writing logic is not yet implemented; this section defines the contract that a follow-up task will satisfy.

## Judge-level summary finding shape

`judges/safe-repo/findings/<slug>/safe-repo.json`:

```json
{
  "judge": "safe-repo",
  "repo": "<source url>",
  "slug": "<repo slug>",
  "passed": true,
  "stage_complete": true,
  "verdict": "passed",
  "sub_findings": {
    "public-repo-check": {
      "passed": true,
      "artifact_path": "judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt",
      "error": null
    },
    "dependency-safety-check": {
      "passed": true,
      "severity": "pass",
      "findings_path": "judges/safe-repo/artifacts/deps-safety-check/<slug>.json"
    }
  },
  "completed_at": "2026-04-29T17:30:00+00:00"
}
```

Field semantics:

- **`passed`** — `true` only if both sub-checks passed. If either failed, `false`.
- **`stage_complete`** — always `true` once this file is written. The file's existence means the judge ran; `passed` separately tells you the outcome. This lets an orchestrator distinguish "judge hasn't run yet" (no file) from "judge ran and the repo failed" (file exists, `passed=false`) without inspecting either sub-finding.
- **`verdict`** — single human-readable label for routing:
  - `"passed"` — both sub-checks passed
  - `"failed-public-repo"` — `public_repo_check` failed; dependency check was skipped
  - `"failed-dependency-safety"` — ingest succeeded but dependency check returned `severity=critical`
- **`sub_findings.public-repo-check`** — mirrors what `public_repo_check.py` returns. `artifact_path` is `null` when the check failed; `error` is the exception message in that case, otherwise `null`.
- **`sub_findings.dependency-safety-check`** — mirrors the top-level fields of the dependency-safety judge result. `severity` is one of `critical | warning | info | pass | skipped`; `skipped` is used when the public-repo check failed and the dependency check did not run, in which case `findings_path` is `null`.
- **`completed_at`** — ISO 8601 UTC timestamp marking when the summary was written.

## Failure handling

The summary finding is always written when the judge finishes — that is the invariant downstream consumers rely on. The three terminal states map to disk as follows:

| Outcome | Ingest artifact | Dependency findings | Summary finding |
| ------- | --------------- | ------------------- | --------------- |
| `public-repo-check` fails | not written | not written (check skipped) | written; `passed=false`, `verdict=failed-public-repo`, `dependency-safety-check.severity="skipped"` |
| `dependency-safety-check` returns `critical` | written | written; `passed=false` | written; `passed=false`, `verdict=failed-dependency-safety` |
| both pass | written | written; `passed=true` | written; `passed=true`, `verdict=passed` |

`warning` and `info` severities from the dependency check do **not** fail the stage — they flow through into `sub_findings.dependency-safety-check.severity` so a downstream human-review judge can surface them, but `passed` stays `true` and `verdict` stays `passed`.

## Done condition

The safe-repo judge is complete for a repo when `judges/safe-repo/findings/<slug>/safe-repo.json` exists.

## Out of scope

This judge intentionally does not:

- Check whether the project was created during the hackathon submission window — that's the `hackathon-qualified` judge.
- Assess code quality, README substance, sponsor integration, or any judging criterion beyond "is this safe to run."
- Function as a comprehensive security or SAST scanner. The dependency-safety check is triage-grade with a narrow threat model — see the Scope section of [`scripts/README.md`](scripts/README.md).
- Run the project's install scripts or build commands. Everything is static analysis on the ingest artifact.
