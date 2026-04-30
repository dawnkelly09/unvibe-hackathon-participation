# Judges Needed

A look at which judges I need to build to complete this flow:

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

(for each sponsor with a prize)

- Reference library (Ghost RAG)
  - docs repo via gitingest
  - source code repos via gitingest
  - qualification & requirements for this hackathon
  - URLs to additional resources provided to builders (Notion pages, starter kits, etc.)
- Scoring Rubrics
  - Technical competency for the stack: tools used? correctly? does it do what it's supposed to?
  - Track requirements: how does project meet the qualifications outlined in each bounty/prize statement? If project clears minimum score, it is submitted to the prize track automatically for further consideration (devs don't have to pick the tracks they are applying for anymore -- share your project and the LLM judges determine where it fits)

## Prize Pool Coordinator

- Projects meeting technical competency for a sponsor track added to prize pool
- Stack rank against how well they meet track requirements
- Distribute micropayments to qualifying projects from prize pool

## Builder Feedback

- Collect outputs from Sponsor Check judges
- Synthesize into a builder feedback report
  - What was done well vs what could improve
  - Opportunities to continue project beyond hackathon
- Smart contract to encrypt feedback report, sign, and make magic link available to team via email for redemption

## LLM Council as Final Boss of Judges

Create an LLM Council to receive inputs from previous steps and evaluate project.

- Track evaluator: this judge evals how well the project meets a given track (rubric needed)
- Post-event opportunity evaluator: this judge evals if the project might be a good candidate for any identified post-hackathon accelerators, grants, or other opportunities to help builders continue with their project beyond the hackathon
- Stack ranker: synthesizes all preceding inputs to stack rank eligible projects so human judges see the most relevant projects first

The final output from the stack ranker is what goes to the human judges for their review.
