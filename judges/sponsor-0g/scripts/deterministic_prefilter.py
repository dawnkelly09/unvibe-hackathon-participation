"""
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
"""