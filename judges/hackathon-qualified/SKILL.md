---
name: hackathon-qualified
description: Second deterministic judge in the pipeline. Verifies a project meets the event's eligibility window — start date, submission deadline, and new-repo policy. The only judge after safe-repo that can gate a project out of the event entirely.
metadata:
  author: dawnkelly09
  version: 1.0
---

## Purpose

You are a hackathon judge whose goal is to confirm a project sits inside the event's eligibility window before it reaches any sponsor or quality evaluation. This judge runs second — after safe-repo proves the repo is reachable and safe — and is the last hard gate in the pipeline. Everything downstream is advisory; if a project fails here, it does not belong in the event.

A repo clears this stage when (a) its first commit falls on or after the event start date (when the event requires a fresh repo), and (b) its last commit falls on or before the submission deadline.

## Sub-checks

This judge runs three checks per repo against an event config. Two are hard gates; the third is signal for a human reviewer.

1. **`first-commit-in-window`** *(gating, conditional)* — first commit's author date must be on or after `event.start_date` if `event.new_repo_required` is true. When `new_repo_required` is false, this check passes automatically with a note explaining it was not enforced.
2. **`last-commit-before-deadline`** *(gating)* — last commit's author date must be on or before `event.submission_deadline`.
3. **`timeline-plausibility`** *(signal only, never gates)* — flags suspicious patterns in the commit timeline. None of these flip `passed` to false; they flow through as warnings for downstream human review.

The plausibility check raises one warning per pattern matched:

| Type | Trigger |
| ---- | ------- |
| `bulk-first-commit` | First commit changed > 5,000 lines (insertions + deletions) — may indicate a history dump from another repo. |
| `large-gap` | Two consecutive commits inside the event window are more than 30 days apart. |
| `midnight-proximity` | First commit timestamp is within 1 hour of midnight UTC of `start_date` — could indicate a backdated commit. |

These thresholds are constants at the top of `event_policy_check.py` (`BULK_COMMIT_LINE_THRESHOLD`, `LARGE_GAP_DAYS`, `MIDNIGHT_PROXIMITY_HOURS`) and can be tuned per event.

## Inputs

- **Repo URL** — positional CLI arg. Slug is derived via `_slug()` imported from `judges/safe-repo/scripts/public_repo_check.py`; the same slug convention used by safe-repo.
- **Event config** — `--event-config` flag, default `event.yaml` at the repo root. Required fields:
  - `start_date` — ISO 8601 date, inclusive.
  - `submission_deadline` — ISO 8601 datetime *with timezone offset*, inclusive.
  - `new_repo_required` — boolean.
  If the file is absent or malformed, the script exits non-zero with a clear stderr message. There are no defaults — the judge will not invent an eligibility window.
- **Upstream safe-repo finding** — `judges/safe-repo/findings/<slug>/safe-repo.json`. The judge refuses to run if this file does not exist; it must come after safe-repo. If safe-repo's `passed` is false, the event-policy judge writes a `verdict="skipped-upstream-failed"` finding and exits 0 — orchestrators should see a `stage_complete=true` file with a clear reason rather than an absent file.

The judge does **not** re-ingest the repo. It does perform a local `git clone --bare <url>` to a temp directory purely for commit metadata, then deletes the clone before exiting. This is the smallest operation that yields first-commit, last-commit, and `--shortstat` data without depending on a GitHub-specific API.

## Output contract

For a given input repo URL, the judge produces a single file on disk. The path uses the slug derived by `_slug()` (same convention as safe-repo).

| File | Path | Written when |
| ---- | ---- | ------------ |
| **Judge-level summary** | `judges/hackathon-qualified/findings/<slug>/event-policy.json` | always, once the judge finishes |

The summary is the single entry point for orchestrators and downstream judges. They should not need to consult event.yaml or the safe-repo finding to know whether this stage passed.

## Judge-level summary finding shape

`judges/hackathon-qualified/findings/<slug>/event-policy.json`:

```json
{
  "judge": "event-policy",
  "repo": "<source url>",
  "slug": "<repo slug>",
  "passed": true,
  "stage_complete": true,
  "verdict": "passed",
  "sub_findings": {
    "first-commit-in-window": {
      "passed": true,
      "first_commit_date": "2026-04-15T09:00:00+00:00",
      "enforced": true,
      "note": null
    },
    "last-commit-before-deadline": {
      "passed": true,
      "last_commit_date": "2026-04-29T22:30:00+00:00",
      "note": null
    },
    "timeline-plausibility": {
      "severity": "pass",
      "warnings": []
    }
  },
  "event_config": {
    "start_date": "2026-04-15",
    "submission_deadline": "2026-04-30T23:59:59+00:00",
    "new_repo_required": true
  },
  "completed_at": "2026-04-30T12:00:00+00:00"
}
```

Field semantics:

- **`passed`** — `true` only when both gating sub-checks passed (`verdict == "passed"`). Plausibility warnings never affect this value.
- **`stage_complete`** — always `true` once this file is written. The file's existence means the judge ran; `passed` separately tells you the outcome. This lets an orchestrator distinguish "judge hasn't run" (no file) from "judge ran and the repo failed" (file exists, `passed=false`) without inspecting sub-findings.
- **`verdict`** — single human-readable label for routing:
  - `"passed"` — both gating checks passed.
  - `"failed-first-commit"` — first commit predates `start_date` and `new_repo_required` is true.
  - `"failed-last-commit"` — last commit is after `submission_deadline`.
  - `"failed-both"` — both gating checks failed.
  - `"skipped-upstream-failed"` — safe-repo did not pass; event-policy checks were not run. Sub-findings are `null`.
- **`sub_findings.first-commit-in-window`** — `enforced` is `false` when `new_repo_required` is false (in which case `passed` is always `true` and `note` explains why). When `enforced` is true, `note` carries a failure reason or is `null`.
- **`sub_findings.last-commit-before-deadline`** — `note` is `null` on pass, otherwise a short failure reason.
- **`sub_findings.timeline-plausibility`** — `severity` is `"pass"` when the warnings list is empty, `"warning"` otherwise. Each warning is `{type, message}`. This sub-finding never gates; downstream judges and human reviewers consume it as signal.
- **`event_config`** — the policy this project was evaluated against. Included so reviewers and downstream judges do not have to load `event.yaml` separately to interpret the result.
- **`completed_at`** — ISO 8601 UTC timestamp marking when the summary was written.

## Failure handling

The summary finding is always written when the judge finishes successfully — same invariant downstream consumers rely on for safe-repo. The five terminal states map to disk as follows:

| Outcome | `passed` | `stage_complete` | `verdict` |
| ------- | -------- | ---------------- | --------- |
| Both gating checks pass | `true` | `true` | `"passed"` |
| First-commit gate fails | `false` | `true` | `"failed-first-commit"` |
| Last-commit gate fails | `false` | `true` | `"failed-last-commit"` |
| Both gates fail | `false` | `true` | `"failed-both"` |
| Upstream safe-repo failed | `false` | `true` | `"skipped-upstream-failed"` |

Plausibility warnings flow through into `sub_findings.timeline-plausibility.warnings` regardless of the gating outcome. They never flip `passed` and never contribute to the verdict.

If the script crashes — git command fails, YAML is malformed, slug cannot be derived, ingest artifact referenced by safe-repo is missing — **no partial finding is written**. The script exits non-zero with a clear stderr message. A missing finding file means "the judge didn't finish"; a present one means "the judge finished, here's the result." That line is intentionally not blurred.

## Done condition

The event-policy judge is complete for a repo when `judges/hackathon-qualified/findings/<slug>/event-policy.json` exists.

## Out of scope

This judge intentionally does not:

- Check sponsor-specific qualification or bounty requirements — those live in the per-sponsor judges later in the pipeline.
- Assess README content, code quality, project completeness, or any judging criterion beyond eligibility.
- Detect backdated commits with cryptographic certainty. The `midnight-proximity` and `bulk-first-commit` warnings are heuristic signals for a human reviewer, not forensic findings.
- Re-clone or re-ingest the repo for content. The bare clone it performs is metadata-only and discarded immediately.
- Enforce a maximum project size, team size, or any policy not encoded in `event.yaml`.

The consensus-requirements check originally planned for this stage has been removed; sponsor-specific checks live in the per-sponsor judges. `consensus_requirements_check.py` in this directory is a deprecated stub being removed separately.
