# Evaluation

Status: scored. Labeled tickets: 17.

Rules accuracy on the small diagnostic reviewed subset is 52.9%. This is not a population-weighted accuracy estimate; it is a spot-check that makes the baseline's limits visible. LLM accuracy is not available unless API predictions exist. Likely weak cases include pickup delays versus QC-complete returns, ordinary faults versus DOA, warranty versus buy-back, conflicting notes, and short or misspelled Hinglish messages. Rules confidence is not calibrated. The five worst misses are ordered by confidence then refund value; explanations identify disagreements, not invented human rationales.
