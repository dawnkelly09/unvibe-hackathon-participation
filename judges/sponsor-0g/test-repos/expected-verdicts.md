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

- **Components used:** none
- **Evidence:** package-lock.json
- **Depth:** meaningful

Note: uses other 0g libraries not featured for this hackathon

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

- **Components used:** Chain / Compute
- **Evidence:** README mention
- **Depth:** meaningful

### Submission artifacts present

Track which qualification items I can verify from the repo alone. Items
not verifiable from the repo (demo video, contact info) get "n/a — not
in repo."

- [ x ] Project name and short description (in README)
- [ x ] Contract deployment addresses
- [ x ] Public GitHub repo with README + setup instructions
- [ n/a ] Demo video & live demo link (n/a from repo alone)
- [ x ] Explanation of which protocol features/SDKs were used
- [ n/a ] Team member names and contact info (n/a from repo alone)
- [ x ] (Framework only) At least one working example agent
- [ n/a ] (Agents/swarms only) Explanation of agent communication
- [ n/a ] (Agents/iNFT only) Link to minted iNFT + intelligence/memory proof

### Expected track classification

- **Framework:** borderline
  - Reasoning: Unsure what actually constitutes a framework but this seems to be a single agent.
- **Agents:** yes
  - Reasoning: Uses a zeroclaw agent

### Expected verdicts

For each track the project is classified into, what verdict do I expect?

- **Framework verdict:** not-applicable
  - If fail, primary reason: [missing rubric items / shallow integration
    / off-topic / etc.]
  - Confidence: medium
- **Agents verdict:** pass
  - If fail, primary reason: [...]
  - Confidence: medium

### Things I'm uncertain about

I'm finding myself a bit confused as to what constitutes agent work versus framework work now that I'm looking at these examples.

### Notes for the rubric

The rubric will need to do a decent job of describing a framework qualifying project vs an agent one because I don't have a firm definition of that right now.

---

## Repo: wszitenhelm/zenagent

**URL:** https://github.com/wszitenhelm/zenagent
**Date reviewed:** 2026-05-01
**Time spent reviewing:** ~5 minutes

### What the project appears to be

Crypto-native wellness companion built for ETHGlobal Cannes 2026.

### 0G integration

- **Components used:** Storage / Compute
- **Evidence:** README mention, links to usage
- **Depth:** meaningful

### Submission artifacts present

Track which qualification items I can verify from the repo alone. Items
not verifiable from the repo (demo video, contact info) get "n/a — not
in repo."

- [ x ] Project name and short description (in README)
- [ x ] Contract deployment addresses
- [ x ] Public GitHub repo with README + setup instructions
- [ na/ ] Demo video & live demo link (n/a from repo alone)
- [ x ] Explanation of which protocol features/SDKs were used
- [ n/a ] Team member names and contact info (n/a from repo alone)
- [ n/a ] (Framework only) At least one working example agent
- [ n/a ] (Agents/swarms only) Explanation of agent communication
- [ n/a ] (Agents/iNFT only) Link to minted iNFT + intelligence/memory proof

### Expected track classification

- **Framework:** no
  - Reasoning: No use of agents in this project
- **Agents:** no
  - Reasoning: No use of agents in this project

### Expected verdicts

For each track the project is classified into, what verdict do I expect?

- **Framework verdict:** not-applicable
  - If fail, primary reason: [missing rubric items / shallow integration
    / off-topic / etc.]
  - Confidence: medium
- **Agents verdict:** not-applicable
  - If fail, primary reason: [...]
  - Confidence: medium

### Things I'm uncertain about

I don't think this uses any actual agents but I'm prepared to be wrong about that.

### Notes for the rubric

I think this will be a good example of "lightly integrates 0G but doesn't do agent things with it."

---

---

## Change log

Track every change to expected verdicts after initial write, with reason.

| Date | Repo | Field changed | Old → New | Reason |
| ---- | ---- | ------------- | --------- | ------ |

[A change with reason "judge disagreed and convinced me" is a red flag.
Reasons should be things like "I missed that the README has a section
on X" or "I misclassified Storage as Compute on first read."]
