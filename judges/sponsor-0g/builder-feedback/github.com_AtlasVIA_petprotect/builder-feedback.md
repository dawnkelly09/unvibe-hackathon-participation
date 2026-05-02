---
sponsor: 0G
repo: https://github.com/AtlasVIA/petprotect
slug: github.com_AtlasVIA_petprotect
classified_into: agents
verdict: pass
evaluated_on: 2026-05-02
0g_storage:
  network: galileo
  chain_id: 16602
  submission_seq: 73940
  root_hash: 0xdeceb19965cde26ebae7ef67be6c6574e0d1c6f09d172ffdc482b10982a75bd9
  tx_hash: 0xe99e57a7008fc90bfa12af08ff61633008eb74b9d14f7be8476e264b884d24e1
  file_size_bytes: 8079
  uploader: 0xCD8Bcd9A793a7381b3C66C763c3f463f70De4e12
  flow_contract: 0x22E03a6A89B950F1c82ec5e74F8eCa321a105296
  uploaded_at: 2026-05-02T21:34:21Z
  chain_explorer_tx: https://chainscan-galileo.0g.ai/tx/0xe99e57a7008fc90bfa12af08ff61633008eb74b9d14f7be8476e264b884d24e1
  storage_explorer: https://storagescan-galileo.0g.ai/submission/73940
---

# Builder Feedback: PetGuardian (petprotect)

**Sponsor:** 0G
**Repo:** https://github.com/AtlasVIA/petprotect
**Evaluated against:** ETHGlobal OpenAgents — 0G prize tracks
**Classified into:** `agents` (Best Autonomous Agents, Swarms & iNFT Innovations)
**Verdict:** pass
**Date evaluated:** 2026-05-02

---

> 📦 **This report is content-addressed and persisted on 0G Storage (Galileo testnet).**
> Root hash `0xdeceb1…2a75bd9`. View on the [storage explorer](https://storagescan-galileo.0g.ai/submission/73940) or the [chain explorer](https://chainscan-galileo.0g.ai/tx/0xe99e57a7008fc90bfa12af08ff61633008eb74b9d14f7be8476e264b884d24e1).

## Summary

PetGuardian was evaluated against 0G's two prize tracks and classified into the `agents` track. The judge found a clear fit: a single end-user-facing agent that uses 0G's infrastructure for AI inference, with the supporting artifacts a hackathon submission needs (named project description, deployed contracts, public repo with setup instructions, protocol features explained). The verdict is **pass**, with three rubric items flagged for human verification at the next review stage.

This is a genuine _pass_ — not a "passed by the skin of its teeth" pass. The judge surfaced the 0G integration, recognized the agent shape, and correctly identified which rubric items don't apply to a single-agent submission.

## What worked

The judge's own words on what it saw:

> "The project uses the @0glabs/0g-serving-broker package, as evidenced by the `package.json` file. The README provides a clear description of the tech stack and usage of 0G for document analysis."

Specifically:

- **Project name and description** — Clearly named in the README, with a concrete description of what PetGuardian does (pet health history with chat-based interaction for owners and veterinarians).
- **Contract deployment addresses** — Found in `backend/ens.ts`. The deterministic prefilter pulled them automatically.
- **Public repo with setup instructions** — README has a `Quickstart` section and `Install dependencies` instructions; the prefilter detected both.
- **Protocol features explained** — The README explains 0G's role in the project (AI inference for document analysis) rather than just listing it as a dependency.
- **Correct track classification** — The judge identified this as a single end-user agent (not a framework, not a swarm), which is exactly what the agents track is for.

The deterministic prefilter found `@0glabs/0g-serving-broker ^0.7.4` declared in `package.json` — this is 0G's Compute SDK, used for AI inference via 0G's decentralized compute network. Solid, real integration.

## Items flagged for human verification

These aren't failures. They're items the automated pass can't confirm from the repo alone, flagged for the human reviewer at the final-review stage. Each one is a small thing you can address before final review to remove the ambiguity:

- **Demo video link.** The prefilter looked for YouTube, Loom, or Vimeo URLs in the README and didn't find one. If you have a demo video, link it from the README. A 60–90 second walkthrough of the chat flow with a sample pet would do it.
- **Live demo link.** Looked for "live demo" / "try it" anchors or URLs on common PaaS hosts (Vercel, Fleek, Netlify, Fly, Railway, Render). If you have a deployment, add it to the README. If not, that's also fine — many strong submissions don't.
- **Team contact info.** Looked for Telegram links, `t.me`, `@username` patterns, or "Contact" / "Team" sections. If your team has Telegram handles or other contact info you're comfortable sharing, a short "Team" section helps reviewers reach you with questions.

## A flag worth your attention

The judge classified your 0G component usage as **`Chain`**. Based on the `@0glabs/0g-serving-broker` import, this is almost certainly **`Compute`** — `0g-serving-broker` is the SDK for 0G's decentralized inference network. The judge's _rubric_ reasoning correctly cited the serving-broker package; the _classification_ step in an earlier call attached the wrong component label.

This is an honest mistake on the judge's part, and it doesn't affect your `pass` verdict. We're surfacing it because you should know what the judge thought it saw, and because clarifying which 0G component you're using in your README's protocol-features section would remove the ambiguity for human reviewers.

A README addition like this would help:

> "PetGuardian uses 0G Compute via the `@0glabs/0g-serving-broker` SDK to call 0G's decentralized AI inference network for document analysis."

Specific component names map to specific tracks and rubric expectations, and explicit naming protects you from misclassification.

## Areas to strengthen for next time

For the current submission, these are nice-to-haves rather than blockers:

- **Architecture diagram.** The prefilter looked for an image referenced in the README with `architecture` / `diagram` / `system` in the path or alt-text and didn't find one. A simple sequence diagram (user → agent → 0G Compute → response) would help reviewers understand the integration shape at a glance. Mermaid in the README works.
- **Explicit track declaration.** Your README doesn't declare a track. The judge inferred `agents` correctly from project shape, but stating it explicitly ("This project is submitted to the 0G **agents** track") removes ambiguity and is a freebie.
- **Component naming.** Per the flag above — name the specific 0G components used (Compute, Chain, Storage, DA), not just "0G." This is the single highest-leverage README change for any 0G-track submission.

These are pattern-level observations from one repo. Treat them as suggestions, not requirements.

## What the prefilter found (verbatim)

For your reference, here's the deterministic evidence the judge had to work with before any LLM call:

| Item                            | Found? | Evidence                                             |
| ------------------------------- | ------ | ---------------------------------------------------- |
| README present                  | ✅     | `README.md`                                          |
| Setup instructions              | ✅     | `Quickstart`, `Install dependencies`                 |
| Contract addresses              | ✅     | ENS registry + resolver in `backend/ens.ts`          |
| 0G SDK imports                  | ✅     | `@0glabs/0g-serving-broker ^0.7.4` in `package.json` |
| Demo video link                 | ❌     | —                                                    |
| Live demo link                  | ❌     | —                                                    |
| Architecture diagram            | ❌     | —                                                    |
| Example agent directory         | ❌     | —                                                    |
| Declared tracks                 | ❌     | —                                                    |
| 0G component mentions in README | ❌     | —                                                    |
| iNFT mentions                   | ❌     | —                                                    |
| Team contact info               | ❌     | —                                                    |

The full prefilter JSON and per-call LLM records are available on request; this report draws from both.

## A note on the verdict

The 0G judge evaluates _fit against the prize tracks_, not project quality. A `pass` here means the project's shape and integration line up with what the agents track asks for — it doesn't compare your project to other submissions, and final track ranking happens at the human review stage.

If you have questions about any specific call the judge made, the per-call LLM records (with full prompts and responses) are kept on disk for auditability. Reasonable people can disagree with a model's call; this report exists in part to make those disagreements legible.

---

_Generated by the Unvibe Hackathons sponsor-0g judge. See https://github.com/dawnkelly09/unvibe-hackathon-participation for the source._
