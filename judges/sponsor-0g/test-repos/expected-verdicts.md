# 0G — Expected Verdicts (Calibration Set)

This file captures my expected verdicts for each calibration repo _before_
the judge is built. The judge's job is to reproduce these intuitions on
its own. Disagreements between this file and the judge's output are the
signal that tells me whether the judge is working — so this file must be
written before I look at any judge output, and it must not be updated to
match the judge's verdicts after the fact.

If reading a repo causes me to change my mind about its expected verdict,
I update this file and note _why_ in the change log at the bottom. That's
legitimate. What's not legitimate is updating a verdict because the judge
disagreed and the judge's reasoning sounded convincing — that's the judge
training me, not me validating the judge.

Meta observations: I seriously underestimated the quality of integration
for all three of these example projects when conducting my manual review.
The deterministic filter produced enough evidence programmatically to
change my mind on my initial assessment. LLM as judge closing the gaps
in real time.

---

## Sponsor

**Name:** 0G
**Tracks:**

- `framework` — Best Agent Framework, Tooling & Core Extensions
- `agents` — Best Autonomous Agents, Swarms & iNFT Innovations

A project can qualify for zero, one, or both tracks.

---

## Repo: AtlasVIA/petprotect

**URL:** https://github.com/AtlasVIA/petprotect
**Date reviewed:** 2026-05-01
**Time spent reviewing:** ~5 minutes

### What the project appears to be

Creates a health history for your pet that owners an veterinarians can interact with via chat. Basically the existing pet microchip system with an ENS identity and crypto rails. Claims to use 0G for "document analysis."

### 0G integration

- **Components used:** Compute
- **Evidence:** `@0glabs/0g-serving-broker` declared in `package.json`; `createZGComputeNetworkBroker` imported and invoked in source code; 0G testnet RPC hardcoded as the AI compute endpoint
- **Depth:** meaningful

Note: `@0glabs/0g-serving-broker` is 0G's Compute SDK. The project actively
calls into it at runtime for AI inference, not just listed as a dependency.

### Submission artifacts present

Track which qualification items I can verify from the repo alone. Items
not verifiable from the repo (demo video, contact info) get "n/a — not
in repo."

- [ x ] Project name and short description (in README)
- [ n/a ] Contract deployment addresses
- [ x ] Public GitHub repo with README + setup instructions
- [ n/a ] Demo video & live demo link (n/a from repo alone)
- [ x ] Explanation of which protocol features/SDKs were used
- [ n/a ] Team member names and contact info (n/a from repo alone)
- [ n/a ] (Framework only) At least one working example agent
- [ n/a ] (Agents/swarms only) Explanation of agent communication
- [ n/a ] (Agents/iNFT only) Link to minted iNFT + intelligence/memory proof

### Expected track classification

- **Framework:** no
  - Doesn't seem to use a framework for agentic development
- **Agents:** no
  - Reasoning: no evidence of use of agents inside this project.

### Expected verdicts

For each track the project is classified into, what verdict do I expect?

- **Framework verdict:** not-applicable
  - If fail, primary reason: [missing rubric items / shallow integration
    / off-topic / etc.]
  - Confidence: high
- **Agents verdict:** not-applicable
  - If fail, primary reason: [...]
  - Confidence: high

### Things I'm uncertain about

I think this project uses AI but doesn't use anything recognizable as the shape of an agent.

### Notes for the rubric

## I believe this will be a good example of "uses some sponsor tech but not the specific tools in the ways we want for this bounty."

## Repo: agoston0x/beepm

**URL:** https://github.com/agoston0x/beepm
**Date reviewed:** 2026-05-01
**Time spent reviewing:** ~5 minutes

### What the project appears to be

Personal health data tracking and insights integrated with ZeroClaw and a Telegram mini app.

### 0G integration

- **Components used:** Compute, Chain
- **Evidence:** README claims 0G Compute and 0G Chain integration; gateway/server.js confirms ethers.js calls to 0G Newton testnet RPC (https://evmrpc-testnet.0g.ai) for INFT contract reads/writes; Compute calls go via HTTP through an OpenAI-compatible proxy at compute-network-6.integratenetwork.work, not via a 0G SDK; deployed contract addresses on 0G Newton (chain 16602) and Base Sepolia
- **Depth:** meaningful

Note: 0G Compute is consumed via HTTP proxy, not via the 0G Compute SDK.
0G Storage appears in the README but only in a v2/post-hackathon roadmap
section; current storage is local JSON files plus browser localStorage.

### Submission artifacts present

- [x] Project name and short description (in README)
- [x] Contract deployment addresses
- [x] Public GitHub repo with README + setup instructions
- [n/a] Demo video & live demo link (n/a from repo alone)
- [x] Explanation of which protocol features/SDKs were used
- [n/a] Team member names and contact info (n/a from repo alone)
- [n/a] (Framework only) At least one working example agent — project is not a framework submission
- [n/a] (Agents/swarms only) Explanation of agent communication — single agent, not a swarm
- [x] (Agents/iNFT only) Link to minted iNFT + intelligence/memory proof — INFT contract address is in the README and gateway code, but the contract is ERC-721 not ERC-7857; whether this satisfies the rubric item is a judgment call

### Expected track classification

- **Framework:** no
  - Reasoning: Single end-user agent (Telegram mini app + gateway + INFT-gated inference). No framework surface — nothing other developers would build agents _with_. No `examples/` directory, no library structure, no scaffolding for third-party use.
- **Agents:** yes
  - Reasoning: Exactly the agents-track shape. End users interact with a Telegram mini app; the agent runs OCR locally and calls 0G Compute via gateway for evaluation; access is gated by NFT ownership.

### Expected verdicts

- **Framework verdict:** not-classified
  - Reason: Project does not fit the framework track shape. The framework rubric is not applied.
  - Confidence: high
- **Agents verdict:** fail-rubric
  - Primary reason: The project makes an iNFT claim, but the contract is ERC-721 (per the README's own description), not ERC-7857. The agents-track rubric item "Link to minted iNFT + intelligence/memory proof" is interpreted strictly against the prize page's named standard, which this project does not implement. The intelligence/memory is in the gateway-mediated 0G Compute call, not embedded in the NFT.
  - Confidence: medium — strict-vs-loose iNFT interpretation is a standing rubric question (see Things I'm Uncertain About).

### Things I'm uncertain about

- **Strict vs. loose iNFT reading.** The prize page names ERC-7857 specifically. This project's "INFT" is an ERC-721 used as a gating token. Strict read: doesn't qualify as an iNFT submission. Loose read: NFT-gated agent access fits the spirit. This question will recur on other projects, so it's worth resolving in the rubric, not just per-project.
- **HTTP proxy vs. SDK as "uses 0G Compute."** This project hits an OpenAI-compatible HTTP endpoint that claims to be 0G Compute, not the 0G Compute SDK directly. Does that count as "uses 0G Compute" for the integration-depth assessment? Probably yes (the inference is happening on 0G's infrastructure either way), but Phase 2 should be explicit about how it judges this.

### Notes for the rubric

- The framework-vs-agents distinction got clearer with closer reading: presence/absence of an `examples/` directory and library-shaped surface area is a strong signal. Frameworks ship things other developers consume; agents ship things end users consume. Phase 1's `example-agent-presence` check is the cheapest indicator.
- The iNFT rubric item needs an explicit position on strict (ERC-7857) vs. loose (any NFT-gated intelligence access). Without one, the verdict on this item is non-deterministic across reviewers.
- "Uses 0G Compute" needs to distinguish "via the 0G Compute SDK" from "via HTTP to a 0G-claimed endpoint." Both are real integrations; they're just different shapes.

---

## Repo: wszitenhelm/zenagent

**URL:** https://github.com/wszitenhelm/zenagent
**Date reviewed:** 2026-05-01
**Time spent reviewing:** ~5 minutes

### What the project appears to be

Crypto-native wellness companion built for ETHGlobal Cannes 2026.

### 0G integration

- **Components used:** Storage, Compute
- **Evidence:** Real working integration: `apps/world-web/lib/0g.ts` uses `@0gfoundation/0g-ts-sdk` `Indexer` to upload AES-256-encrypted journal data to 0G Storage; `/api/0g/upload-journal` route is wired to the check-in UI flow; standalone scripts in `apps/0g-tools/` (`journal-upload.ts`, `journal-download.ts`, `compute-quotes.ts`) demonstrate full SDK integration including `createZGComputeNetworkBroker` for 0G Compute. Both 0G SDKs are declared and used: `@0gfoundation/0g-ts-sdk` and `@0glabs/0g-serving-broker`.
- **Depth:** deep for 0G Storage (production path in the web app), meaningful for 0G Compute (demonstrated in standalone tools, stubbed in the web app)

Note: The web app's 0G Compute integration is explicitly stubbed (`/api/0g/manifestation` and `/api/0g/compute/init` return mock responses with comments noting "full integration available"). The standalone scripts in `apps/0g-tools/` show the team can do the real integration; they just didn't wire Compute through to the web app for this submission. The README is honest about this: "Mock 0G responses (full SDK integration available)."

Note: The README targets the "0G Wildcard ($3K Track)" from a different ETHGlobal event (likely Cannes 2026), not the OpenAgents framework/agents track structure. The integration is real, but this project was not designed against the OpenAgents prize tracks specifically.

### Submission artifacts present

- [x] Project name and short description (in README)
- [x] Contract deployment addresses
- [x] Public GitHub repo with README + setup instructions
- [n/a] Demo video & live demo link (not in repo)
- [x] Explanation of which protocol features/SDKs were used
- [n/a] Team member names and contact info (n/a from repo alone — README has a "Team" section header but no actual handles or contact info)
- [n/a] (Framework only) At least one working example agent — project is not a framework submission
- [n/a] (Agents/swarms only) Explanation of agent communication — not a swarm
- [n/a] (Agents/iNFT only) Link to minted iNFT + intelligence/memory proof — not an iNFT submission

### Expected track classification

- **Framework:** no
  - Reasoning: No framework surface. The `0g-tools` package contains standalone demo scripts, not a reusable library other developers would build agents with. The web app is a Next.js wellness check-in application, not a framework. No `examples/` directory in the framework sense.
- **Agents:** no
  - Reasoning: Despite the project name and the use of `@worldcoin/agentkit`, this is not an autonomous agent. The AgentKit usage is explicitly a "demonstration" with mock hooks. The user-facing surface is a wellness check-in app that uploads encrypted journals to 0G Storage and displays charts. There's no autonomous behavior, no swarm, no iNFT-embedded intelligence.

### Expected verdicts

- **Framework verdict:** not-classified
  - Reason: Project does not fit the framework track shape. The framework rubric is not applied.
  - Confidence: high
- **Agents verdict:** not-classified
  - Reason: Project does not fit the agents track shape (autonomous agents, swarms, or iNFT projects). The agents rubric is not applied.
  - Confidence: high

Note: Both verdicts being not-classified does NOT mean the project is low-quality or that 0G integration is shallow — quite the opposite. ZenAgent has the deepest 0G Storage integration of the three calibration repos. It just doesn't happen to fit the OpenAgents-specific track shapes. This is an important calibration data point: a project can have genuine, deep 0G integration and still be `not-classified` because the prize tracks are about project shape, not about whether 0G is used.

### Things I'm uncertain about

### Things I'm uncertain about

- **Originally I thought this project barely used 0G.** Closer reading shows the opposite: 0G Storage is a production path in the check-in flow, and the team has working 0G Compute scripts demonstrating SDK fluency. My five-minute manual read missed this entirely. This is a useful data point for the project's thesis — five-minute reads systematically miss integration depth.

### Notes for the rubric

### Notes for the rubric

- **Project shape and integration depth are orthogonal axes.** ZenAgent is the cleanest example: deep 0G integration, but neither framework-shaped nor agent-shaped. The rubric's `not-classified` verdict is the right call here, and it's not a failure verdict — it just means the project belongs in a different track (e.g., the 0G Wildcard track this project actually targeted).
- **The README's stated tracks are signal worth surfacing.** ZenAgent explicitly says "0G Wildcard ($3K Track)" — that's a declared track from a different event, and Phase 2 should notice when a project's declared track doesn't map onto the OpenAgents tracks. Mismatch isn't failure; it's information.
- **"Honest about stubs" is a positive signal.** ZenAgent's README discloses which integrations are mocked. That's a maturity marker. The rubric might want a way to credit this kind of honesty rather than penalize it.

---

## Change log

Track every change to expected verdicts after initial write, with reason.

| Date       | Repo       | Field changed                    | Old → New                                                                                                                                                                                            | Reason                                                                                                                                                                                                                                                                                                           |
| ---------- | ---------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-05-01 | petprotect | Components used                  | none -> Compute                                                                                                                                                                                      | Project uses `@0glabs/0g-serving-broker` which is 0G's compute SDK. Without knowing the expected package name, I could not predict this.                                                                                                                                                                         |
| 2026-05-01 | petprotect | Evidence                         | package-lock.json -> `@0glabs/0g-serving-broker` declared in `package.json`; `createZGComputeNetworkBroker` imported and invoked in source code; 0G testnet RPC hardcoded as the AI compute endpoint | Calibration run surfaced more evidence than my initial manual review of the project.                                                                                                                                                                                                                             |
| 2026-05-01 | beepm      | Components used                  | Chain / Compute → Compute, Chain                                                                                                                                                                     | Closer reading of gateway/server.js confirmed Compute is via OpenAI-compatible HTTP proxy (compute-network-6.integratenetwork.work), not via a 0G SDK. Chain is via ethers.js to 0G Newton RPC. Reordering and explicit "via HTTP proxy" note added.                                                             |
| 2026-05-01 | beepm      | Components used (Storage)        | listed as v2 → confirmed not used                                                                                                                                                                    | Closer reading confirmed README's "Multi-device sync via 0G Storage" is in a post-hackathon roadmap section. Current storage is local JSON files and browser localStorage. Storage stays out of components_used.                                                                                                 |
| 2026-05-01 | beepm      | iNFT rubric item                 | n/a → applicable                                                                                                                                                                                     | Project makes an explicit iNFT claim throughout the README and ships an INFT contract on 0G Newton testnet. Item is no longer n/a. Resolution to pass/fail depends on strict (ERC-7857) vs. loose (any NFT-gated intelligence access) interpretation — see Things I'm Uncertain About.                           |
| 2026-05-01 | beepm      | Framework classification         | borderline → no                                                                                                                                                                                      | Closer reading clarified the framework-vs-agents distinction: project is a single end-user agent, no library surface, no examples/ directory, nothing other developers would build agents _with_. Confidence raised from medium to high.                                                                         |
| 2026-05-01 | beepm      | Agents classification confidence | medium → high                                                                                                                                                                                        | Closer reading confirmed exactly the agents-track shape (end-user Telegram mini app, gateway-mediated inference, INFT gating).                                                                                                                                                                                   |
| 2026-05-01 | beepm      | Framework verdict                | fail → not-classified                                                                                                                                                                                | Per the SKILL.md verdict vocabulary, projects that don't fit the track shape are not-classified rather than fail. Framework rubric is not applied to non-framework projects.                                                                                                                                     |
| 2026-05-01 | beepm      | Agents verdict                   | pass → fail-rubric (or pass — version dependent)                                                                                                                                                     | If strict ERC-7857 interpretation: project's INFT is ERC-721, fails the iNFT rubric item. If loose interpretation: passes. Choosing strict for now, with the standing question logged. Confidence dropped from high to medium because the verdict hinges on an unresolved rubric question, not on project facts. |
| 2026-05-01 | zenagent   | Components used                  | none → Storage, Compute                                                                                                                                                                              | Closer reading found real 0G Storage integration in the web app's check-in flow (lib/0g.ts uses @0gfoundation/0g-ts-sdk Indexer for production uploads) and full SDK demonstration in apps/0g-tools/ standalone scripts. Both 0G SDKs are imported and used in real code paths.                                  |
| 2026-05-01 | zenagent   | Depth                            | meaningful → deep (Storage) / meaningful (Compute)                                                                                                                                                   | Storage is a production path in the primary user flow. Compute is real in standalone tools, stubbed in the web app — README is explicit about which is which.                                                                                                                                                    |
| 2026-05-01 | zenagent   | Framework verdict                | not-applicable → not-classified                                                                                                                                                                      | Aligning with the SKILL.md verdict vocabulary; "not-classified" is the right term for projects that don't fit a track's shape.                                                                                                                                                                                   |
| 2026-05-01 | zenagent   | Agents verdict                   | not-applicable → not-classified                                                                                                                                                                      | Same. AgentKit usage is a demo with mock hooks, not an autonomous agent. Project shape is a Next.js wellness app, not an agents-track submission.                                                                                                                                                                |
| 2026-05-01 | zenagent   | Confidence on classifications    | medium → high                                                                                                                                                                                        | Closer reading clarified what the project actually is (wellness check-in app with deep 0G Storage integration) and what it isn't (framework, autonomous agent). Confidence raised on both classifications.                                                                                                       |
| 2026-05-01 | zenagent   | Declared track                   | (not noted) → "0G Wildcard ($3K Track)"                                                                                                                                                              | README explicitly declares this track, which is from a different event (likely Cannes 2026). Worth surfacing as a mismatch with OpenAgents tracks rather than ignoring.                                                                                                                                          |

[A change with reason "judge disagreed and convinced me" is a red flag.
Reasons should be things like "I missed that the README has a section
on X" or "I misclassified Storage as Compute on first read."]
