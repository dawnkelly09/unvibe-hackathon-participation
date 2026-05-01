"""
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
"""