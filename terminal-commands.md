# Terminal commands

Quick reference for running things in this project. All commands assume you're at the repo root and using `uv` for environment management.

## Pipeline

The orchestrator runs every implemented judge in order and short-circuits on upstream failure. This is the common entrypoint.

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

### sponsor-0g (Phase 1 only — Phase 2 LLM evaluation not yet built)

Deterministic prefilter against the safe-repo gitingest artifact. Writes `judges/sponsor-0g/artifacts/deterministic-prefilter/<slug>.json`.

```sh
uv run python judges/sponsor-0g/scripts/deterministic_prefilter.py <repo-url>
```

## Tests

```sh
# Everything:
uv run --group dev pytest

# A single judge:
uv run --group dev pytest judges/safe-repo/tests
uv run --group dev pytest judges/sponsor-0g/tests

# A single test file with verbose output:
uv run --group dev pytest judges/sponsor-0g/tests/test_deterministic_prefilter.py -v
```

## Environment

```sh
uv add <package>            # install a new runtime dependency
uv add --group dev <pkg>    # install a new dev-only dependency
uv run python <script>      # run a script inside the project venv
uv sync                     # reinstall everything from pyproject.toml + uv.lock
```
