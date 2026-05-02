# LLM-as-a-judge

"LLM-as-a-Judge or LLM-based evaluation is a conceptual framework in natural language processing (NLP) that employs large language models (LLMs) as evaluators to assess the performance of other language-based systems or outputs. Instead of relying solely on human annotators, the approach leverages the general language capabilities of advanced language models to serve at automated judges." [wikipedia](https://en.wikipedia.org/wiki/LLM-as-a-Judge)

## Exploring LLM-as-a-Judge

From Weights & Biases by Coreweave: (https://wandb.ai/site/articles/exploring-llm-as-a-judge/)

Input --> System LLM --> Judge --> Rubric

- Leverage large language model reasoning ability to make intelligent judgements
- Useful when human eval is too expensive (time/cost) but rules or metrics are too rigid to fit the shape of the problem
  - Common metrics based evals that are too rigid:
    - **BLEU(Bilingual Evaluation Understudy)**: quantifies the quality of AI-generated text by comparing it to one or more reference texts
    - **ROUGE(Recall Oriented Understudy for Gisting Evaluation)**: measure how closely machine-generated text aligns with human-written references
- Judge models assess correctness of answers & quality criteria

## Apply to Unvibe Hackathons

How can the concept of LLM-as-a-judge help improve the hackathon experience?

- Layered judges to filter projects before they make it to human judges:
  - Does project meet the minimum requirements of the hackathon (open source repo, etc.)?
  - Can the project be run locally for evaluation or is there a working demo site to interact with the project?
  - Does the project use target tools, libraries, or sponsor stack?
  - Does the project meet technical competency for the sponsor stack?

- Sponsor specific judge to evaluate technical aspects of implementation: does this work like it's supposed to?
- Judge report outputs to provide feedback to builders after the event
  - Identify any gaps in the project and explain
  - Opportunities for improvement
  - What the project does well
  - Any follow up info team wants to share with builder
- Pool Prize Judge: given a prize pool, can divide among qualifying projects not selected for track prizes
- LLM-Council type analysis as the "final boss" judge
  - Synthesize inputs from prior levels of judges
  - Compare against bounty or track statements
  - Stack rank according to perceived level of how well bounty or track statements are met
  - This is what is put in front of human judges for eval

## Example Conceptual Use

LLM answers the question: does the project have a public GitHub repo?

- This can be a fairly simple model as long as it can run a script and evaluate reponses
- Flow looks like:
  - Use gitingest CLI to fetch repo via GitHub URL, analyze repo, and create the text dump of contents
  - If the repo is public, this fetch should succeed (private repos need a PA token)
    - Fetch succeeds = yes repo is public
    - Fetch fails = repo may not be public but this check alone doesn't prove it
      - Consider a max number of tries (3?) to help account for other reasons fetch might fail
  - Repos confirmed as public move forward to next level of judging with their gitingest forwarded to the next judges
