# sponsor-0g scripts

Three tools used by the `sponsor-0g` judge, run in order. The first is the
LLM-free static prefilter that runs against the gitingest artifact written by
`safe-repo`. Its output is consumed by the Phase 2 LLM evaluation script and
ultimately surfaced in the judge's summary finding.

| Script                      | Role                  | Input                                       | Output                          |
| --------------------------- | --------------------- | ------------------------------------------- | ------------------------------- |
| `deterministic_prefilter.py`| Phase 1, deterministic| repo URL (+ safe-repo gitingest artifact)   | prefilter JSON                  |
| `llm_evaluation.py`         | Phase 2, LLM          | prefilter JSON + gitingest artifact         | per-call LLM records (JSON)     |
| `sponsor_og_judge.py`       | wrapper               | upstream findings + the two phase outputs   | summary finding (JSON)          |

The contract for each script lives in `judges/sponsor-0g/SKILL.md`. This
README documents the scripts themselves; if SKILL.md and this file disagree,
SKILL.md wins.

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
│   ├── deterministic_prefilter.py   # Phase 1 (this script)
│   ├── _ingest_parsing.py           # shared parser for safe-repo artifacts
│   ├── llm_evaluation.py            # Phase 2 (not in this README)
│   └── sponsor_og_judge.py          # wrapper (not in this README)
├── tests/
│   ├── fixtures/                    # synthetic gitingest artifacts
│   └── test_deterministic_prefilter.py
└── artifacts/
    └── deterministic-prefilter/     # JSON results, one per slug
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
