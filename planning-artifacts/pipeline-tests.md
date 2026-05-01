# Pipeline Tests

My notes as I run the pipeline test flows.

2026-05-01 Friday:

1. Ran `safe-repo` and `hackathon-qualified` on the calibration.txt repo set for the 0G judge. Findings were as expected -- all passed safe-repo and all failed hackathon-qualified because they are projects that are older than the current event defined in `event.yml`

Command to run:

```bash
uv run python run_pipeline.py --repos-file judges/sponsor-0g/test-repos/calibration.txt
```

Findings table:

Repo | safe-repo | event-policy | overall
----------------------------------------+-----------+---------------------+--------
https://github.com/AtlasVIA/petprotect | passed | failed-first-commit | failed
https://github.com/agoston0x/beepm | passed | failed-first-commit | failed
https://github.com/wszitenhelm/zenagent | passed | failed-first-commit | failed

2. Run `deterministic-prefilter.py` against each repo in the 0G calibration set. Commands to run:

```bash
uv run python judges/sponsor-0g/scripts/deterministic_prefilter.py https://github.com/AtlasVIA/petprotect
```

```bash
uv run python judges/sponsor-0g/scripts/deterministic_prefilter.py https://github.com/agoston0x/beepm
```

```bash
uv run python judges/sponsor-0g/scripts/deterministic_prefilter.py https://github.com/wszitenhelm/zenagent
```
