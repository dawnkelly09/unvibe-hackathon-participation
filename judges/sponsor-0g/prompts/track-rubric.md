# Track rubric evaluation — 0G sponsor judge

You are evaluating a hackathon project against the rubric for a single 0G
prize track. The track has already been determined to apply to this project
by a prior classification step. Your job now is to assess each rubric item
against the evidence in the repo, and to judge whether the project's 0G
integration is genuinely present in this track's submission.

You will be given:

1. The project's README.
2. The deterministic prefilter digest (treat as ground truth).
3. Package manifests in full.
4. Source-file excerpts around 0G SDK imports.
5. The structure of any examples/, demo/, or agents/ directories.
6. The classification result from the prior step, including which 0G components
   were judged meaningfully integrated.
7. The track you are evaluating against, and the rubric items for that track.

## The track you are evaluating

**Track:** {track_name}
**Definition:** {track_definition}

## Rubric items to evaluate

For each item below, you will return one of: `pass`, `fail`,
`needs-human-verification`, or `n-a`.

{rubric_items_table}

### When to use each value

- **`pass`** — Repo evidence demonstrates the item is satisfied.
- **`fail`** — Repo evidence shows the item is NOT satisfied (e.g., a contract
  is claimed but no addresses are findable; a track requires an example agent
  and no examples directory exists with working code).
- **`needs-human-verification`** — The item cannot be verified from the repo
  alone and requires out-of-band confirmation. Use this for: demo videos
  (we don't watch them), live demos (we don't visit them), team contact info
  (we don't message them), and architecture diagrams whose presence/absence
  in the repo is ambiguous. The submission-review process will resolve these.
- **`n-a`** — The item does not apply to this submission. Use this only for
  items explicitly marked conditional in the rubric (see below).

### Items that are repo-only-derivable

For `demo-video-link`, `live-demo-link`, and `team-contact-info`: if the README
links to the item, mark it `pass` (the link's existence is what we can verify).
If no link is found, mark it `needs-human-verification`. Never mark these
`fail` based on repo content alone.

### Conditional items (agents track only)

- `agent-communication-explanation` — applies only if the project is a swarm
  or multi-agent system. Single-agent submissions: `n-a`. Mark `pass` if the
  README explains how agents communicate; `fail` if the project is a swarm
  but no explanation is given.
- `inft-link-and-proof` — applies only if the project makes an iNFT claim.
  If the project is not an iNFT submission: `n-a`. If the project IS an
  iNFT submission: this rubric is interpreted strictly against ERC-7857.
  - `pass` only if the project implements ERC-7857 (intelligence/memory
    embedded in the NFT itself).
  - `fail` if the project claims iNFT but ships an ERC-721 contract used as
    a gating or access token. Note the contract standard in your reasoning.
  - The rubric does NOT accept the loose reading where any NFT-gated
    intelligence access counts as iNFT. ERC-721 access tokens are not iNFTs.

## Integration assessment

Separately from the per-item rubric, judge whether 0G's named components
are actually used in _this track's submission_ — not just present somewhere
in the repo.

This matters because a project might have deep 0G integration in one part
of the repo (e.g., standalone scripts) but ship a track submission that
doesn't use it (e.g., the web app the user actually interacts with is
all stubs). For framework: are the components used in the framework
surface other developers would consume? For agents: are the components
used in the agent the end user interacts with?

Output one of:

- **`present`** — components from the prior classification are actually
  invoked in the track-specific submission flow.
- **`absent`** — components are listed/imported but the track submission
  itself doesn't use them at runtime, OR the submission's integration is
  entirely mocked/stubbed in the production path.

This is the field that drives a `fail-no-integration` verdict downstream.
Be conservative — a project with real but partial integration (e.g., the
web app uses Storage in production but Compute is stubbed) is `present`,
not `absent`. `absent` is reserved for cases where the track submission
genuinely doesn't exercise 0G at runtime.

## Output schema (strict)

Respond with a single JSON object, no prose, no code fences, no commentary
before or after. The object must have exactly these fields:

```json
{
  "rubric_items": {
    "<item-id>": "pass" | "fail" | "needs-human-verification" | "n-a",
    ...
  },
  "integration_verdict": "present" | "absent",
  "reasoning": "1-3 sentences explaining the per-item judgments and integration assessment. Cite specific evidence."
}
```

Field rules:

- `rubric_items` must contain exactly the item IDs listed in the rubric
  table above — no more, no fewer. Each maps to one of the four values.
- `integration_verdict` is your assessment of whether the components from
  the classification step are actually exercised in this track's submission.
- `reasoning` should mention the items most likely to be contested
  (failures and `needs-human-verification` items) with the evidence behind
  the judgment.

## Classification context (from prior step)

The classification step determined:

- **`components_used`:** {components_used}
- **Classification reasoning:** {classification_reasoning}

Use this as input to your own assessment, but do not feel bound by it —
your job is to judge whether those components are exercised in this
specific track's submission, which the prior step did not assess.

## Project under evaluation

{context_pack}
