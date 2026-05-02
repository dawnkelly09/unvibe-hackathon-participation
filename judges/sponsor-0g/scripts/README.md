# sponsor-0g scripts

Three tools used by the `sponsor-0g` judge, run in order. The first is the
LLM-free static prefilter that runs against the gitingest artifact written by
`safe-repo`. Its output is consumed by the Phase 2 LLM evaluation script and
ultimately surfaced in the judge's summary finding.

| Script                       | Role                   | Input                                       | Output                                                |
| ---------------------------- | ---------------------- | ------------------------------------------- | ----------------------------------------------------- |
| `deterministic_prefilter.py` | Phase 1, deterministic | repo URL (+ safe-repo gitingest artifact)   | prefilter JSON                                        |
| `llm_evaluation.py`          | Phase 2, LLM           | prefilter JSON + gitingest artifact         | LLM evaluation JSON + per-call records                |
| `sponsor_0g_judge.py`        | wrapper                | upstream findings + the two phase outputs   | summary finding JSON (`findings/<slug>/sponsor-0g.json`) |

The contract for each script lives in `judges/sponsor-0g/SKILL.md`. This
README documents the scripts themselves; if SKILL.md and this file disagree,
SKILL.md wins.

`llm_evaluation.py` and `sponsor_0g_judge.py` make LLM calls via
`lib/llm.py`. They require a model to be selected via either the `--model`
flag or the `MODEL` environment variable, in `<backend>:<name>` form (e.g.
`ollama:qwen2.5:7b` or `anthropic:claude-sonnet-4-6`). `deterministic_prefilter.py`
does no LLM work and ignores `MODEL`.

---

## `deterministic_prefilter.py`

### What It Checks

Every item from the SKILL.md Phase 1 table — no more, no less. Each item
produces a structured `present: bool` plus an `evidence: list[...]` of
locations where matches were found. Patterns are sourced from SKILL.md.

| Item                          | Source scope                             | Pattern summary                                                                       |
| ----------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------- |
| `readme-present`              | top-level                                | `README*` (case-insensitive); `README.md` preferred                                   |
| `setup-instructions-present`  | README headings                          | heading text matches `install\|setup\|getting started\|quickstart\|run`               |
| `contract-addresses`          | every file                               | `\b0x[a-fA-F0-9]{40}\b`                                                               |
| `demo-video-link`             | README only                              | URL on `youtube.com`, `youtu.be`, `loom.com`, `vimeo.com`                             |
| `live-demo-link`              | README only                              | "live demo" / "demo" / "try it" anchor, OR PaaS-host URL (vercel/fleek/netlify/...)   |
| `architecture-diagram`        | README only                              | image whose path or alt text matches `architecture\|diagram\|system`                  |
| `example-agent-presence`      | source files + README                    | source file under `examples?/`, `demo/`, `samples/`, `agents/`; or README mention     |
| `declared-tracks`             | README only                              | "framework track" / "agents track" / "iNFT track" — recorded **verbatim**, case-preserved |
| `0g-sdk-imports`              | package manifests                        | `@0glabs/*`, `0g-*`, `zerog-*` — manifests parsed as text, partial files tolerated    |
| `0g-component-mentions`       | README only                              | `0G Storage`, `0G DA` / `data availability`, `0G Compute`, `0G Chain` — paragraph snippet |
| `inft-mentions`               | README + `.sol` files                    | `iNFT` (case-insensitive) or `ERC-7857`                                               |
| `team-contact-info`           | README only                              | `telegram\|t\.me\|@[A-Za-z0-9_]+\|contact\|team` (deliberately generous)              |

The prefilter intentionally errs toward over-flagging — the Phase 2 LLM is
expected to reason about meaningful integration vs. mere mention. This script
produces **evidence**, not verdicts.

### Output schema

```json
{
  "judge": "sponsor-0g",
  "phase": "deterministic-prefilter",
  "repo": "<source url>",
  "slug": "<repo slug>",
  "ingest_path": "<path that was read>",
  "items": {
    "<item-id>": {
      "present": true,
      "evidence": [
        {
          "file": "<relative path or 'README.md'>",
          "line": 42,
          "snippet": "<short surrounding context, max ~200 chars>",
          "value": "<matched URL or address — when applicable>",
          "match": "<verbatim match — when applicable>",
          "identifier": "<SDK identifier — for 0g-sdk-imports>",
          "component": "<component label — for 0g-component-mentions>"
        }
      ]
    }
  },
  "completed_at": "<ISO 8601 UTC>"
}
```

Every item from the SKILL table appears as a key in `items`, even when
`present` is `false` (with `evidence: []`). Consumers should not have to
handle missing keys.

If a single item check raises, that item is recorded as
`{"present": false, "evidence": [], "error": "<message>"}` and the rest of
the run continues. A complete prefilter result with one bad item is more
useful than a crashed run.

### Layout

```
judges/sponsor-0g/
├── scripts/
│   ├── deterministic_prefilter.py   # Phase 1
│   ├── _ingest_parsing.py           # shared parser for safe-repo artifacts
│   ├── llm_evaluation.py            # Phase 2
│   └── sponsor_0g_judge.py          # wrapper
├── prompts/
│   ├── track-classification.md      # Call A prompt
│   └── track-rubric.md              # Call B prompt (parameterized)
├── tests/
│   ├── fixtures/                    # synthetic gitingest artifacts
│   ├── test_deterministic_prefilter.py
│   └── test_llm_evaluation.py
├── artifacts/
│   ├── deterministic-prefilter/     # Phase 1 JSON, one per slug
│   ├── llm-evaluation/              # Phase 2 JSON, one per slug
│   └── llm-call-records/<slug>/     # per-call LLM records (audit trail)
└── findings/
    └── <slug>/sponsor-0g.json       # judge summary written by the wrapper
```

### Usage

```bash
# Default — reads the safe-repo ingest artifact under
# judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt and writes the JSON
# under judges/sponsor-0g/artifacts/deterministic-prefilter/<slug>.json:
uv run judges/sponsor-0g/scripts/deterministic_prefilter.py \
  https://github.com/dawnkelly09/eureka

# Explicit paths:
uv run judges/sponsor-0g/scripts/deterministic_prefilter.py \
  https://github.com/dawnkelly09/eureka \
  --ingest-path  judges/safe-repo/artifacts/repo-ingest-dump/github.com_dawnkelly09_eureka.txt \
  --output-path  /tmp/eureka-prefilter.json

# Dry run (still prints JSON to stdout):
uv run judges/sponsor-0g/scripts/deterministic_prefilter.py \
  https://github.com/dawnkelly09/eureka --no-write
```

stdout is reserved for the JSON output; status messages go to stderr. Output
is written via tempfile + `os.replace`, so a crash mid-write never leaves a
corrupt JSON behind. Exit status:

| Exit | Meaning                                                              |
| ---- | -------------------------------------------------------------------- |
| `0`  | Prefilter ran to completion (regardless of how many items matched).  |
| `1`  | Ingest artifact missing or unparseable. No output file written.      |

### Out of scope

- No network calls. The prefilter does not reach a live demo, watch a video,
  message a team, or check a contract address on-chain.
- No LLM calls. That's Phase 2.
- No verdict. The prefilter records evidence; Phase 2 reasons about it.

### Tests

```bash
uv run --group dev pytest judges/sponsor-0g/tests
```

Test fixtures live in `tests/fixtures/` as synthetic gitingest artifacts.
Each test loads a fixture, runs the prefilter, and asserts on specific items.

---

## `llm_evaluation.py`

### What It Does

Reads the Phase 1 prefilter JSON and the safe-repo gitingest artifact,
assembles a single context pack, and makes one or two LLM calls:

- **Call A — `track-classification`.** Always runs. Returns
  `framework_applicable`, `agents_applicable`, `components_used`,
  `reasoning`, `confidence`.
- **Call B — `framework-rubric` and/or `agents-rubric`.** Runs once per
  track Call A judged applicable. Returns `rubric_items`,
  `integration_verdict`, `reasoning`.

The two prompt templates in `prompts/` are the source of truth for what the
LLM is asked. This script renders them, validates the JSON responses against
strict schemas, and writes one combined JSON output. It does no verdict
computation — that's the wrapper's job.

The context pack contains, in order:

1. The README in full.
2. A digest of the Phase 1 findings ("ground truth — do not re-derive").
3. Every package manifest, fenced as code.
4. ±15-line excerpts around each `0g-sdk-imports` evidence entry.
5. The structure of any `examples/`, `example/`, `demo/`, `samples/`, or
   `agents/` top-level directory, with the first source file's body.

If the assembled pack exceeds ~32k characters, sections are trimmed in this
order: SDK excerpts shrink to 10 lines; example file bodies are dropped
(listings preserved); the README's middle is replaced with `_[truncated for
length]_`. The README is never fully cut.

### Output schema

`judges/sponsor-0g/artifacts/llm-evaluation/<slug>.json`:

```json
{
  "judge": "sponsor-0g",
  "phase": "llm-evaluation",
  "repo": "<source url>",
  "slug": "<repo slug>",
  "model": "<resolved model string>",
  "classification": {
    "framework_applicable": true,
    "agents_applicable": false,
    "components_used": ["Storage", "Compute"],
    "reasoning": "...",
    "confidence": "high"
  },
  "tracks": {
    "framework": {
      "rubric_items": { "<item-id>": "pass | fail | needs-human-verification | n-a" },
      "integration_verdict": "present | absent",
      "reasoning": "..."
    },
    "agents": null
  },
  "records_dir": "<absolute path>",
  "completed_at": "<ISO 8601 UTC>"
}
```

A track marked not-applicable by Call A appears as `null` under `tracks`.
Both being `null` is valid and expected for many real projects.

Per-call records (one per LLM round-trip, including retries) are written
to `judges/sponsor-0g/artifacts/llm-call-records/<slug>/` for audit and
builder-feedback generation.

### Usage

```bash
# Default — reads
#   judges/sponsor-0g/artifacts/deterministic-prefilter/<slug>.json
#   judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt
# and writes
#   judges/sponsor-0g/artifacts/llm-evaluation/<slug>.json
#   judges/sponsor-0g/artifacts/llm-call-records/<slug>/<call>.json
MODEL=ollama:qwen2.5:7b \
uv run judges/sponsor-0g/scripts/llm_evaluation.py \
  https://github.com/dawnkelly09/eureka

# Or pass --model explicitly:
uv run judges/sponsor-0g/scripts/llm_evaluation.py \
  https://github.com/dawnkelly09/eureka \
  --model ollama:qwen2.5:7b
```

Exit status:

| Exit | Meaning                                                                        |
| ---- | ------------------------------------------------------------------------------ |
| `0`  | Phase 2 ran to completion. Output JSON is on disk (unless `--no-write`).       |
| `1`  | Prefilter JSON missing, ingest artifact missing, or prompt files missing.      |
| `>1` | Uncaught exception (e.g. `LLMSchemaError`, `LLMJSONParseError`, `LLMCallError`). The wrapper turns these into a `verdict="failed"` summary. |

Schema failures raise `LLMSchemaError` with a message naming the field and
what was wrong (e.g. `"Call A: components_used contains invalid entry
'storage' (expected one of Chain|Compute|DA|Storage)"`). They are NOT
retried — the LLM shim retries on JSON parse failure; a schema failure
means the model returned well-formed JSON of the wrong shape.

---

## `sponsor_0g_judge.py`

### What It Does

The judge wrapper. Reads upstream findings, runs the two phases, and
produces the single summary file the orchestrator and council stage read.

In order:

1. **Upstream gating.** Refuses to run if `judges/safe-repo/findings/<slug>/safe-repo.json`
   or `judges/hackathon-qualified/findings/<slug>/event-policy.json` is missing
   (exit `1`, no summary written — the pipeline is misordered). If either is
   present but `passed=false`, writes a summary with
   `verdict="skipped-upstream-failed"` and exits `0`.
2. **Phase 1.** Runs `deterministic_prefilter.py` as a subprocess, only if
   the prefilter JSON isn't already on disk (idempotent).
3. **Phase 2.** Runs `llm_evaluation.py` as a subprocess (`--model`
   forwarded). On non-zero exit, writes a `verdict="failed"` summary with
   both tracks set to `not-classified`, reasoning string lifted from the
   subprocess stderr, and exits `0`. A transient LLM outage produces a
   well-formed finding rather than crashing the pipeline.
4. **Summary.** Reads the Phase 2 JSON, computes per-track verdicts and the
   overall `passed` boolean, and atomically writes
   `judges/sponsor-0g/findings/<slug>/sponsor-0g.json`.

Per-track verdict logic (per `SKILL.md`):

```
if track was not applicable per Call A:
  verdict = "not-classified", rubric_items = null
elif Call B integration_verdict == "absent":
  verdict = "fail-no-integration"
elif any required rubric item is "fail":
  verdict = "fail-rubric"
else:
  verdict = "pass"
```

`architecture-diagram` is a soft item — recorded but never gates a verdict.
Top-level `passed` is `true` iff at least one track has `verdict == "pass"`;
top-level `verdict` is `"passed"` or `"failed"` accordingly.

### Output schema

See `SKILL.md`'s "Judge-level summary finding shape" section for the
authoritative spec. The wrapper is strict about which fields are populated
in each terminal state:

| Outcome                          | `passed` | `verdict`                  | `tracks`                                 |
| -------------------------------- | -------- | -------------------------- | ---------------------------------------- |
| ≥1 track passes                  | `true`   | `"passed"`                 | both keys present, ≥1 with `"pass"`      |
| no track passes (after Phase 2)  | `false`  | `"failed"`                 | both keys present, none with `"pass"`    |
| Phase 2 LLM call failed          | `false`  | `"failed"`                 | both tracks `"not-classified"`; reasoning explains LLM failure |
| Upstream `passed=false`          | `false`  | `"skipped-upstream-failed"`| `null`                                   |

### Usage

```bash
# Default — runs Phase 1 + Phase 2 and writes the summary.
MODEL=ollama:qwen2.5:7b \
uv run judges/sponsor-0g/scripts/sponsor_0g_judge.py \
  https://github.com/dawnkelly09/eureka

# Suppress the disk write (still prints to stdout):
MODEL=ollama:qwen2.5:7b \
uv run judges/sponsor-0g/scripts/sponsor_0g_judge.py \
  https://github.com/dawnkelly09/eureka --no-write
```

Exit status:

| Exit | Meaning                                                                    |
| ---- | -------------------------------------------------------------------------- |
| `0`  | Summary finding written (or printed). Includes the LLM-failed branch.      |
| `1`  | Misordered pipeline (upstream finding missing) or Phase 1 crashed. No summary written. |

---

## End-to-end usage

Run the three scripts manually on one repo:

```bash
# Phase 1 — deterministic prefilter (no LLM):
uv run judges/sponsor-0g/scripts/deterministic_prefilter.py \
  https://github.com/dawnkelly09/eureka

# Phase 2 — LLM evaluation:
MODEL=ollama:qwen2.5:7b \
uv run judges/sponsor-0g/scripts/llm_evaluation.py \
  https://github.com/dawnkelly09/eureka

# Summary — read upstream findings, both phase outputs, and write the
# judge-level summary at judges/sponsor-0g/findings/<slug>/sponsor-0g.json:
MODEL=ollama:qwen2.5:7b \
uv run judges/sponsor-0g/scripts/sponsor_0g_judge.py \
  https://github.com/dawnkelly09/eureka
```

Or just run the wrapper — it does Phase 1 + Phase 2 itself:

```bash
MODEL=ollama:qwen2.5:7b \
uv run judges/sponsor-0g/scripts/sponsor_0g_judge.py \
  https://github.com/dawnkelly09/eureka
```
