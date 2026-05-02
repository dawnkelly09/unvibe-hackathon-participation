# Judges Needed

**Scope narrowing note**: Friday May 1, 2026: decision was made to draw projects from the ETH Global Showcase tab to use as calibration examples for creating the judge for each sponsor track. Discovered Gensyn amd KeeperHub had no projects in the showcase. ENS and Uniswap had very general examples. Decision made to focus on a solid 0G judge as proof of concept and let sponsors expand out their own example judges using this structure.

Implementation for this proof of concept looks like:

safe_repo > event_policy > sponsor_0g > orchestrator > LLM-judge-council

## Safe Repo

(thanks for your input @bguiz!)

- repo is public: `public_repo_check.py`
- repo snapshot is captured (gitingest with hash) to protect against deleted repos or changes after hackathon has finished: output to `artifacts/repo-ingest-dump`
- repo is safe from malicious code or packages (npm installs, etc.): `dependency_safethy_check.py`
  - output JSON to `artifacts/deps-safety-check` with findings

## Hackathon Qualified Check

- Check against event policy: set once per event, stays static during judging
  - start date, submission deadline, new repo check

## Sponsor Check

(foucs on 0G for this PoC implementation)

- select example repos from ETH Global showcase for 0G
- judge needs to:
  - Classify: which tracks, if any, does this project apply to?
  - Evaluate: how well does it score against a rubric for the track?

- Reference library (Ghost RAG)
  - docs repo via gitingest
  - source code repos via gitingest
  - qualification & requirements for this hackathon
  - URLs to additional resources provided to builders (Notion pages, starter kits, etc.)
- Scoring Rubrics
  - Technical competency for the stack: tools used? correctly? does it do what it's supposed to?
  - Track requirements: how does project meet the qualifications outlined in each bounty/prize statement? If project clears minimum score, it is submitted to the prize track automatically for further consideration (devs don't have to pick the tracks they are applying for anymore -- share your project and the LLM judges determine where it fits)

Discovering the lack of example projects for a couple of the sponsors raised the issue that judgability is not uniform across sponsors. Long standing, open-source sponsors may have a rich ecosystem that can be leveraged to form a picture of what a good project for that sponsor looks like. Newer projects, or those stemming from closed-source ecosystems, will not have as rich a body of knowledge to draw against.

A widely usable version of a platform like this should consider some options like:

- newer projects use the safe-repo and hackathon-qualified checks for screening but BYO judging (via human or their own agents)
- a way for projects to configure their own judging agent prior to the event (the product team is where the expertise is, not the hackathon organizers)

## Prize Pool Coordinator (out of scope)

NOTE: I've determined I don't have enough time to implement this but, it is something I'd like to pursue to keep expanding on what this platform can do beyond the hackathon.

- Projects meeting technical competency for a sponsor track added to prize pool
- Stack rank against how well they meet track requirements
- Distribute micropayments to qualifying projects from prize pool

## Builder Feedback

- Collect outputs from Sponsor Check judge
- Synthesize into a builder feedback report
  - What was done well vs what could improve
  - Opportunities to continue project beyond hackathon
- Smart contract to encrypt feedback report, sign, and make magic link available to team via email for redemption

## LLM Council as Final Boss of Judges

Create an LLM Council to receive inputs from previous steps and evaluate project.

- Track evaluator: validate sponsor judge findings on how well the project meets a given track (rubric needed)
- Post-event opportunity evaluator: this judge evals if the project might be a good candidate for any identified post-hackathon accelerators, grants, or other opportunities to help builders continue with their project beyond the hackathon
- Stack ranker: synthesizes all preceding inputs to stack rank eligible projects so human judges see the most relevant projects first

The final output from the stack ranker is what goes to the human judges for their review.
