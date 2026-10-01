# Prompt log

- v1: initial minimal draft; not executed. Desk review found missing label definitions, ambiguity handling, and protection against instructions embedded in ticket text. These are anticipated weaknesses, not measured failures.
- v2: added policy code definitions, conservative handling of weak evidence, Hinglish abbreviations, strict JSON contract and untrusted-text instructions. The agent dropdown is withheld to reduce anchoring. API execution requires a configured key; actual runs are logged in output/run_cost.json.
- No v3 or discarded API experiments are claimed: they have not occurred.
