---
name: sponsor-0g
description: First sponsor judge in the pipeline. Classifies a project against 0G's two prize tracks (framework, agents), then evaluates rubric fit per applicable track. Repo-only evaluation; uses an LLM for classification and rubric narrative on top of a deterministic prefilter.
metadata:
  author: dawnkelly09
  version: 1.0
---

## Purpose

You are a hackathon judge whose goal is to determine whether a project qualifies for either of 0G's two ETHGlobal OpenAgents prize tracks, and — for each track it qualifies for — how well it satisfies that track's rubric. This judge runs after `safe-repo` and `hackathon-qualified` and is the first stage in the pipeline that requires LLM judgment.

A project may end up qualifying for zero, one, or both tracks. Builders are not asked to declare a track up front — track applicability is inferred by this judge from the repo. Where the project's README declares a track, the declaration is recorded as signal but does not constrain the judge.

The two tracks (per [the 0G prize page](https://ethglobal.com/events/openagents/prizes/0g)):

- **`framework`** — *Best Agent Framework, Tooling & Core Extensions.* Framework-level work: modules, tooling, libraries, scaffolding, visual builders, agent-construction primitives that other developers build agents *with*.
- **`agents`** — *Best Autonomous Agents, Swarms & iNFT Innovations.* End-user-facing work: single agents, swarms/collectives, iNFT (ERC-7857) projects — things end-users interact *with*.

The 0G prize page asserts the two tracks are "strictly" separate but does not define the boundary. This judge uses the working definition above: framework = built-with, agents = used-by. A project qualifies for both only if it includes both a reusable framework *and* a working example agent built on that framework (the framework track explicitly requires the latter, so any framework submission that ships a working example is eligible for both).

## Sub-checks

This judge runs as three scripts in order, one repo at a time:

1. `scripts/deterministic_prefilter.py` — runs the fully deterministic Phase 1 checks against the gitingest artifact and writes structured output to `artifacts/deterministic-prefilter/<slug>.json`.
2. `scripts/llm_evaluation.py` — reads the prefilter output, makes the Phase 2 LLM calls (track classification, per-track rubric evaluation), writes structured output to `artifacts/llm-evaluation/<slug>.json`. The LLM does not do work Phase 1 has already done.
3. `scripts/sponsor_0g_judge.py` — the wrapper. Reads upstream findings, invokes the two phases, writes the summary finding. 

### Phase 1 — Deterministic prefilter

Operates on the gitingest artifact written by `safe-repo` (`judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt`). No network calls, no LLM calls, no link-following. Each item below produces a structured boolean / list of evidence locations.

| Item | What it looks for |
| ---- | ----------------- |
| `readme-present` | Top-level `README*` exists. |
| `setup-instructions-present` | README contains a section heading matching `/install|setup|getting started|quickstart|run/i`. |
| `contract-addresses` | Strings matching `/\b0x[a-fA-F0-9]{40}\b/` anywhere in the repo, with file paths. |
| `demo-video-link` | Anchor or bare URL pointing at youtube.com / youtu.be / loom.com / vimeo.com inside README. |
| `live-demo-link` | Anchor labelled "live demo" / "demo" / "try it" in README, or a URL on a known PaaS host (vercel.app, fleek.\*, netlify.app, fly.dev, railway.app, render.com). |
| `architecture-diagram` | Image reference in README whose path or alt-text matches `/architecture|diagram|system/i`. |
| `example-agent-presence` | Directory named `examples/`, `example/`, `demo/`, `samples/`, or `agents/` containing at least one source file; or README section referencing an "example agent." |
| `declared-tracks` | README contains explicit phrases like "framework track", "agents track", "iNFT track" (case-insensitive). Recorded verbatim. |
| `0g-sdk-imports` | Package manifests (`package.json`, `package-lock.json`, `pyproject.toml`, `requirements.txt`, `go.mod`, `Cargo.toml`) referencing `@0glabs/*`, `0g-*`, or `zerog-*`. Each match recorded with file path and identifier. |
| `0g-component-mentions` | README mentions, case-insensitive, of `0G Storage`, `0G DA` / `data availability`, `0G Compute`, `0G Chain`. Each match recorded with surrounding context (one paragraph). |
| `inft-mentions` | README or contracts referencing `iNFT` or `ERC-7857`. |
| `team-contact-info` | README block matching `/telegram|t\.me|@[A-Za-z0-9_]+|contact|team/i`. |

Phase 1 results are written to `judges/sponsor-0g/artifacts/deterministic-prefilter/<slug>.json` regardless of Phase 2 outcome.

### Phase 2 — LLM judgments

Two kinds of model calls. Both consume the gitingest artifact and the Phase 1 JSON as context.

**Call A — track classification (always runs, exactly one call):**

- Inputs: gitingest text, Phase 1 JSON, the working definitions of `framework` and `agents` tracks given above, and 0G's four named components (`Storage`, `DA`, `Compute`, `Chain`).
- Output (strict JSON): `{ "framework_applicable": bool, "agents_applicable": bool, "components_used": [subset of Storage|DA|Compute|Chain], "reasoning": string (1–3 sentences), "confidence": "low"|"medium"|"high" }`.
- `components_used` is the LLM's assessment of which of the four named components are *meaningfully integrated* — that is, invoked at runtime in the project's primary flow, not merely listed in a manifest or namechecked in the README. Other 0G libraries not part of the four do not count, even if they're used; this is per the prize-track scope.
- A project may consume a named component via an OpenAI-compatible HTTP endpoint, a custom RPC, or another non-SDK path rather than via the official 0G SDK. This counts toward `components_used` when the operation is actually happening on 0G's infrastructure (or a node operator's 0G endpoint), regardless of the client-side library. Phase 2 should distinguish these in its reasoning ("Compute via HTTP proxy to a 0G endpoint" vs. "Compute via 0G SDK") because the integration depth differs, but neither pattern disqualifies a project from `components_used` membership.
- `confidence` reflects the LLM's certainty about classification, not about the project's quality. Low confidence is a signal for human review, not a fail.

**Call B — per-track rubric (runs once per applicable track):**

- Runs only for tracks where Call A returned `*_applicable: true`. For tracks marked not-applicable, the verdict is `not-classified` and the rubric is not applied.
- Inputs: gitingest text, Phase 1 JSON, Call A output, and the rubric items for the specific track (listed below).
- Output (strict JSON):
  ```json
  {
    "verdict": "pass" | "fail-rubric" | "fail-no-integration",
    "reasoning": "1–3 sentences",
    "rubric_items": { "<item-id>": "pass" | "fail" | "needs-human-verification" | "n-a" }
  }
  ```
- The verdict is determined as follows:
  - `fail-no-integration` if `components_used` from Call A is empty, or if Call B's own assessment concludes the named components are not actually used in this track's submission. This takes precedence over rubric failures because the failure mode is fundamental, not cosmetic.
  - `fail-rubric` if integration is present but one or more required (not `n-a`, not `needs-human-verification`) rubric items are `fail`.
  - `pass` otherwise. Items left as `needs-human-verification` do not block `pass` — see "Repo-only evaluation" below.

Per-track rubric items (derived directly from the prize page submission requirements):

| Item ID | Tracks | Source |
| ------- | ------ | ------ |
| `project-name-and-description` | framework, agents | Common |
| `contract-deployment-addresses` | framework, agents | Common |
| `public-repo-with-setup` | framework, agents | Common |
| `demo-video-link` | framework, agents | Common |
| `live-demo-link` | framework, agents | Common |
| `protocol-features-explained` | framework, agents | Common — README explains which 0G features/SDKs were used |
| `team-contact-info` | framework, agents | Common — Telegram/X handles |
| `working-example-agent` | framework | Framework-only — "at least one working example agent built using your framework/tooling" |
| `architecture-diagram` | framework | Framework-only — "optional but strongly recommended"; contributes signal but never sets `fail-rubric` on its own. Treated as a soft item: reported, never gates. |
| `agent-communication-explanation` | agents | Agents-only, conditional on the LLM judging the project is a swarm/multi-agent system; otherwise `n-a`. |
| `inft-link-and-proof` | agents | Agents-only, conditional on the LLM judging the project is an iNFT submission; otherwise `n-a`. **Strict ERC-7857 reading:** the project must implement ERC-7857 (intelligence/memory embedded in the NFT itself) for this item to `pass`. ERC-721 NFTs used as access tokens or gating mechanisms do not satisfy this item — Phase 2 records `fail` on the item (not `n-a`) when a project makes an iNFT claim with a non-ERC-7857 contract, and surfaces the contract standard in its reasoning. |

### Repo-only evaluation

Several rubric items can't be verified from a GitHub repo alone: the demo video itself (we don't watch it), the live demo (we don't visit it), team contact info (we don't message them). The judge's scope is repo-derivable evidence only. For these items:

- If the README links to the item, the rubric item is `pass` (the link's existence is what we can verify).
- If no link is found, the item is `needs-human-verification`. This does **not** flip the verdict to `fail-rubric` on its own. It is surfaced in the finding so a human reviewer can confirm at submission-review time.

A judge that hard-failed projects for missing items it couldn't verify from a repo would produce false negatives, which is worse than producing findings that need human follow-up. The downstream submission-review process is expected to handle the verification of these items.

## Output contract

For a given input repo URL, this judge produces up to three artifacts on disk. Slugs use the same `_slug()` convention as `safe-repo` (the URL with the scheme stripped and any character outside `[A-Za-z0-9._-]` replaced with `_`).

| File | Path | Written when |
| ---- | ---- | ------------ |
| Phase 1 prefilter results | `judges/sponsor-0g/artifacts/deterministic-prefilter/<slug>.json` | Phase 1 runs |
| LLM call records | `judges/sponsor-0g/artifacts/llm-call-records/<slug>/<call>.json` | Each LLM call (Call A: `track-classification.json`; Call B: `framework-rubric.json` and/or `agents-rubric.json`) |
| **Judge-level summary** | `judges/sponsor-0g/findings/<slug>/sponsor-0g.json` | always, once the judge finishes |

The summary file is the single entry point for the orchestrator and the LLM judge council. Downstream consumers should not need to read the prefilter or per-call records to make a routing decision — everything they need is in the summary. The per-call records exist for auditability and for builder-feedback generation, which may want the LLM's prose reasoning verbatim.

## Judge-level summary finding shape

`judges/sponsor-0g/findings/<slug>/sponsor-0g.json`:

```json
{
  "judge": "sponsor-0g",
  "repo": "<source url>",
  "slug": "<repo slug>",
  "passed": true,
  "stage_complete": true,
  "verdict": "passed",
  "declared_tracks": ["framework"],
  "inferred_tracks": ["framework"],
  "components_used": ["Storage", "Compute"],
  "tracks": {
    "framework": {
      "verdict": "pass",
      "reasoning": "Project ships a reusable agent-construction toolkit with one example agent under examples/. README explains 0G Storage and 0G Compute usage and links to deployed contracts.",
      "rubric_items": {
        "project-name-and-description": "pass",
        "contract-deployment-addresses": "pass",
        "public-repo-with-setup": "pass",
        "demo-video-link": "pass",
        "live-demo-link": "needs-human-verification",
        "protocol-features-explained": "pass",
        "team-contact-info": "pass",
        "working-example-agent": "pass",
        "architecture-diagram": "needs-human-verification"
      }
    },
    "agents": {
      "verdict": "not-classified",
      "reasoning": "Project is a framework with a single example agent; the example exists to demonstrate the framework, not as a standalone agents-track submission.",
      "rubric_items": null
    }
  },
  "confidence": "high",
  "llm_call_records_path": "judges/sponsor-0g/artifacts/llm-call-records/<slug>/",
  "completed_at": "2026-05-01T17:30:00+00:00"
}
```

Field semantics:

- **`passed`** — `true` when at least one track in `tracks` has `verdict == "pass"`. Otherwise `false`. The orchestrator uses this single boolean to decide whether to forward the project to the prize-pool coordinator.
- **`stage_complete`** — always `true` once this file is written. Same invariant as upstream judges: file's existence means the judge ran; `passed` separately tells you the outcome.
- **`verdict`** — single human-readable label for routing:
  - `"passed"` — at least one track has `verdict == "pass"`.
  - `"failed"` — no track has `verdict == "pass"`. Per-track verdicts give the why.
  - `"skipped-upstream-failed"` — `safe-repo` or `hackathon-qualified` did not pass; sponsor-0g checks were not run. `tracks`, `declared_tracks`, `inferred_tracks`, `components_used`, and `confidence` are `null`.
- **`declared_tracks`** — list of track ids the README explicitly claims (`["framework"]`, `["agents"]`, `["framework", "agents"]`, or `[]`). Comes from Phase 1; not used to constrain classification. A mismatch between `declared_tracks` and `inferred_tracks` is allowed and surfaced for human review, not treated as an error.
- **`inferred_tracks`** — list of track ids Call A judged applicable. The set of keys in `tracks` whose verdict is not `not-classified`.
- **`components_used`** — subset of `["Storage", "DA", "Compute", "Chain"]` that Call A judged are meaningfully integrated. Project-level (not per-track) because component use is a property of the project, not the rubric.
- **`tracks`** — exactly two keys, `"framework"` and `"agents"`. Each value carries a per-track verdict from `{ "pass", "fail-rubric", "fail-no-integration", "not-classified" }`, the LLM's 1–3 sentence reasoning, and the rubric-item map. `rubric_items` is `null` when verdict is `not-classified`. The four-value verdict vocabulary distinguishes:
  - `pass` — track shape matches and rubric is satisfied (modulo `needs-human-verification` items).
  - `fail-rubric` — track shape matches but one or more required rubric items failed. Builder feedback should focus on the missing items.
  - `fail-no-integration` — track shape matches but the project doesn't use 0G's named components in the way this track requires. Builder feedback should focus on the integration gap, which is more fundamental than a polish issue.
  - `not-classified` — project does not fit this track's shape; the rubric was not applied.
- **`confidence`** — Call A's self-reported confidence in its classification: `"low" | "medium" | "high"`. A `"low"` value here is a signal for human review at the council stage, not a reason to fail the project.
- **`llm_call_records_path`** — directory where the individual LLM call records live. Always present when at least one LLM call ran. `null` only when `verdict == "skipped-upstream-failed"`.
- **`completed_at`** — ISO 8601 UTC timestamp marking when the summary was written.

## Failure handling

The summary finding is always written when the judge finishes successfully — same invariant downstream consumers rely on for `safe-repo` and `hackathon-qualified`. Terminal states map to disk as follows:

| Outcome | `passed` | `stage_complete` | `verdict` | `tracks` |
| ------- | -------- | ---------------- | --------- | -------- |
| At least one track passes | `true` | `true` | `"passed"` | populated |
| No track passes (any combination of `fail-rubric`, `fail-no-integration`, `not-classified`) | `false` | `true` | `"failed"` | populated; per-track verdicts give the why |
| Upstream `safe-repo` or `hackathon-qualified` did not pass | `false` | `true` | `"skipped-upstream-failed"` | `null` |

Specific failure modes inside the judge's run:

- **Ingest artifact missing.** If `judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt` does not exist, the judge refuses to run and exits non-zero. This should not happen in a well-formed pipeline (safe-repo's `passed=true` implies the artifact exists), but the check is defensive.
- **Upstream finding missing.** If either `judges/safe-repo/findings/<slug>/safe-repo.json` or `judges/hackathon-qualified/findings/<slug>/event-policy.json` is missing, the judge exits non-zero with a clear stderr message. A summary finding is **not** written. A missing upstream finding means the pipeline is misordered, not that the project failed.
- **Upstream finding present but `passed=false`.** Judge writes the summary with `verdict="skipped-upstream-failed"` and exits 0. No LLM calls are made; no Phase 1 prefilter is run.
- **LLM call fails (network error, timeout, malformed response after retries).** The judge retries Call A or Call B up to a fixed bound (set in the implementation). If retries exhaust, the judge writes the summary with `passed=false`, `verdict="failed"`, and the affected track's verdict set to `"not-classified"` with `reasoning` explaining the LLM failure. The other track's result is preserved if it succeeded. The per-call record on disk reflects the failure for auditability. This conservative behavior is preferred over raising — a transient LLM outage should not stall the pipeline, and the council stage can re-run individual sponsor judges from their summaries if needed.
- **LLM returns non-JSON or schema-invalid output after retries.** Same handling as a network failure: the affected track is `not-classified` with a reasoning string explaining the parse failure.
- **Phase 1 prefilter crashes.** Judge exits non-zero; no summary is written. Phase 1 is deterministic file parsing — a crash indicates a code bug, not a project-level signal.

A missing summary finding file means "the judge didn't finish"; a present one means "the judge finished, here's the result." That line is intentionally not blurred.

## Done condition

The sponsor-0g judge is complete for a repo when `judges/sponsor-0g/findings/<slug>/sponsor-0g.json` exists.

## Out of scope

This judge intentionally does not:

- Evaluate code quality, architectural soundness, or technical sophistication beyond what's required to assess rubric fit. A future judge in the council stage handles technical-merit evaluation.
- Check sponsor requirements *outside* of 0G. Each sponsor has its own judge; this one is 0G-specific. Other 0G libraries that aren't part of the four named components do not count toward integration depth, even if their use is meaningful elsewhere.
- Watch demo videos, visit live demos, or message team members. Repo-derivable evidence only; non-derivable items are flagged `needs-human-verification` for the submission-review stage.
- Make a final prize-pool ranking decision. Stack-ranking against other qualifying projects is the prize-pool coordinator's job. This judge produces the per-project per-track verdict the coordinator stack-ranks on.
- Re-ingest or re-clone the repo. It consumes the gitingest artifact written by `safe-repo` and does not touch the network for repo data.
- Generate builder feedback prose. The per-track reasoning strings and per-call LLM records are inputs to a downstream builder-feedback judge, not the feedback itself.
- Resolve ambiguity in the 0G prize page beyond the two interpretations stated above (strict ERC-7857 for iNFT, HTTP-proxy use counts toward `components_used`). Other interpretive questions that arise during operation should be raised back to the rubric, not decided ad hoc by Phase 2.
