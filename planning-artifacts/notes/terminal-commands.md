# Terminal commands

Quick reference for running things in this project. All commands assume you're at the repo root and using `uv` for environment management.

## Pipeline

The orchestrator runs every wired-up judge in order and short-circuits on upstream failure. This is the common entrypoint.

```sh
# One repo:
uv run python run_pipeline.py https://github.com/octocat/Hello-World

# A batch from a file (one URL per line; '#' and blank lines ignored):
uv run python run_pipeline.py --repos-file judges/sponsor-0g/test-repos/calibration.txt

# Re-run even if a finding file already exists:
uv run python run_pipeline.py <repo-url> --force

# Run a subset of judges, in order:
uv run python run_pipeline.py <repo-url> --judges safe-repo,event-policy
```

The orchestrator currently runs `safe-repo` and `event-policy`. The `sponsor-0g` judge is wired end-to-end and runnable via its wrapper (see below); adding it to the orchestrator's judge list is a one-line change scheduled post-submission.

## Judges (run individually)

### safe-repo

Two-phase judge: `public_repo_check` ingests the repo and writes `judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt`; `dependency_safety_check` triages manifests and install scripts. The wrapper runs both and writes the summary finding to `judges/safe-repo/findings/<slug>/safe-repo.json`. Exit `0` on pass, `1` on fail.

```sh
# Wrapper (preferred):
uv run python judges/safe-repo/scripts/safe_repo_judge.py <repo-url>

# Phase 1 only — produces the ingest artifact downstream judges depend on:
uv run python judges/safe-repo/scripts/public_repo_check.py <repo-url>

# Phase 2 only — reads an existing artifact:
uv run python judges/safe-repo/scripts/dependency_safety_check.py \
  judges/safe-repo/artifacts/repo-ingest-dump/<slug>.txt
```

### hackathon-qualified

Checks event-policy compliance (commit-window dates, prior-deployment grace period). Reads `event.yaml` and the upstream safe-repo finding. Writes `judges/hackathon-qualified/findings/<slug>/event-policy.json`.

```sh
uv run python judges/hackathon-qualified/event_policy_check.py <repo-url>
```

### sponsor-0g

Two-phase sponsor judge for 0G's ETHGlobal OpenAgents prize tracks. Phase 1 is a deterministic prefilter over the safe-repo gitingest artifact; Phase 2 is the LLM evaluation (Call A — track classification; Call B — per-track rubric, runs once per applicable track). The wrapper runs both phases and writes the summary finding to `judges/sponsor-0g/findings/<slug>/sponsor-0g.json`. Full spec in `judges/sponsor-0g/SKILL.md`.

```sh
# Wrapper (preferred — runs Phase 1 + Phase 2 + writes summary finding):
uv run python judges/sponsor-0g/scripts/sponsor_0g_judge.py <repo-url>

# Skip the upstream-finding precondition check (useful when running
# sponsor-0g directly against a repo that hasn't been through the full
# pipeline yet — e.g., during calibration):
uv run python judges/sponsor-0g/scripts/sponsor_0g_judge.py \
  --skip-upstream-check <repo-url>

# Phase 1 only — deterministic prefilter, no LLM calls:
uv run python judges/sponsor-0g/scripts/deterministic_prefilter.py <repo-url>

# Phase 2 only — reads existing prefilter output, makes LLM calls:
uv run python judges/sponsor-0g/scripts/llm_evaluation.py <repo-url>
```

Phase 2 LLM evaluation defaults to a local Ollama model. Override with the `MODEL` environment variable (e.g., `MODEL=ollama:qwen2.5:14b`). Per-call records are written to `judges/sponsor-0g/artifacts/llm-call-records/<slug>/` for auditability.

## Tests

```sh
# Everything:
uv run --group dev pytest

# A single judge:
uv run --group dev pytest judges/safe-repo/tests
uv run --group dev pytest judges/sponsor-0g/tests

# A single test file with verbose output:
uv run --group dev pytest judges/sponsor-0g/tests/test_deterministic_prefilter.py -v

# Skip integration tests that require a live Ollama daemon:
uv run --group dev pytest -m "not integration"
```

## Environment

```sh
uv add <package>            # install a new runtime dependency
uv add --group dev <pkg>    # install a new dev-only dependency
uv run python <script>      # run a script inside the project venv
uv sync                     # reinstall everything from pyproject.toml + uv.lock
```
