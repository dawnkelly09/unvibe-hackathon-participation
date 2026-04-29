# Terminal commands

Quick reference for running things in this project. All commands assume you're at the repo root.

## Judges

### safe-repo

Verify a submitted project's repo is publicly ingestable. Exit code `0` on pass, `1` on fail. Writes the full ingest artifact to `judges/safe-repo/artifacts/<slug>.txt`.

```sh
uv run python judges/safe-repo/safe-repo.py <repo-url>
```

Example:

```sh
uv run python judges/safe-repo/safe-repo.py https://github.com/octocat/Hello-World
```

Override the artifact directory:

```sh
uv run python judges/safe-repo/safe-repo.py <repo-url> --artifact-dir /tmp/my-artifacts
```

## Environment

```sh
uv add <package>          # install a new dependency
uv run python <script>    # run a script inside the project venv
uv sync                   # reinstall everything from pyproject.toml + uv.lock
```
