# Vireo refund review

A small Python pipeline producing a reconciled Excel board pack and a generated, nontechnical memo. Current delivered run uses the rules baseline because no Anthropic API key was configured. Financial conclusions use code, not AI.

## Setup and run

Python 3.10+ (tested locally with Python 3.12.4).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

For the submitted no-key version shown in the recording, run:

```powershell
python run.py --rules-only
```

Put `tickets.csv`, `agents.csv`, `orders.csv`, `customers.csv`, `products.csv`, `support-policy.pdf`, `email-thread.txt`, `README.txt`, and the original `submission-form.md` in `data/`. Input lookup also accepts the supplied UUID-prefixed files in the project root and the `.txt.txt` filenames. There must be only one candidate for each input. Customers are supplied context; the refund analysis requires no additional customer attributes. Existing inputs are not modified.

`submission-form.md` records the submitted deliverable, validation, cost, business goal and scope choices.

## Optional AI classification

Configure `ANTHROPIC_API_KEY` in your local environment; never commit it. Only ticket messages and notes are sent to Anthropic, so they may contain customer information. The default model is `claude-haiku-4-5-20251001`; override with `ANTHROPIC_MODEL`.

```powershell
python run.py --pilot 50
python run.py
```

The pilot limits fresh API calls to 50 and still reports the full financial population; remaining tickets use rules or existing cache. Review `output/run_cost.json` before the full run. Without a key both commands use the rules fallback and record that the AI pilot did not run. `python run.py --rules-only` forces a baseline run even if a key or cached AI results exist.

API responses must pass the strict JSON schema and label checks. Failures use rules; three consecutive failures stop further API requests for that run. Local cache entries are keyed by ticket ID and validated against model, prompt and text hashes. Unchanged cached tickets incur no new API calls. Changing text, model or prompt invalidates that ticket's entry. Rules outputs are never cached as AI outputs.

Standard Haiku 4.5 rates are configured as USD 1/million input and USD 5/million output tokens, from [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing). These are estimates, not invoice reconciliation. Override `ANTHROPIC_INPUT_USD_PER_MILLION` and `ANTHROPIC_OUTPUT_USD_PER_MILLION` when prices change; custom models require explicit rates. Token usage, calls, failures, cache hits and estimated cost are logged per run. Transport failures can leave billed usage unknown and are flagged. No paid calls were made in the delivered run; full-run API cost/runtime remain unmeasured. Rules-mode runtime was under 15 seconds on this machine; inspect `output/run_metadata.json` for the latest measurement.

## Outputs

- `output/vireo_refunds.xlsx`: Summary, Trend chart, By Team, By Reason, By Agent, Why Refunds Rose, Policy Flags, Needs Review, Mismatch Matrix, Reconciliation, Assumptions.
- `output/monthly_refunds.png`: standalone monthly trend.
- `MEMO.md`: generated from the same calculations as the workbook.
- `output/reconciliation.csv`, `table_reconciliation.csv`, `audit.json`: exact accounting and join audit.
- `output/classifications.csv`: prediction audit for evaluation; not a board-pack raw dump.
- `output/quarters.csv`, `decomposition.csv`, `contributions.csv`, `csat.csv`, `claim.csv`, `opportunity.csv`, `separate_costs.csv`: machine-readable supporting figures.
- `output/run_cost.json`, `run_history.jsonl`, `run_metadata.json`: latest cost, run history and runtime.

Reruns replace the generated workbook, memo and CSVs; close the workbook in Excel first. They preserve human labels and append run-cost history. Workbook currency columns are explicitly in Rs lakh, with three decimal places; underlying accounting is integer paise. Display rounding is not used for reconciliation.

## Human evaluation

```powershell
python eval/make_sample.py
# Fill human_reason in eval/to_label.csv, using policy s.5 and reading message + notes.
python eval/score.py
```

The seeded 120-ticket sample improves coverage across joint agent-code/channel/source strata. The labeling file omits predictions and agent codes to reduce anchoring. Valid labels: `GW-OTHER`, `DOA-REPL`, `LOST-TRANSIT`, `DUP-PAYMENT`, `CANCEL`, `PRICE-ADJ`, `RETURN-QC-OK`, `WTY-BUYBACK`. Leave genuinely unadjudicated cases blank; document ambiguity during review. The sample generator preserves existing labels unless `--force` is supplied.

`output/evaluation/` contains accuracy, per-class precision/recall, confusion matrices, GW-OTHER accuracy, confidence buckets, cost metrics, five highest-confidence misses, and agent-code disagreement with human labels. The current submission includes 17 diagnostic human labels, with rules accuracy of 52.9% on that small reviewed subset. This is a transparent spot-check, not a population-weighted error-rate estimate. Partial labels are scored with the actual denominator. Empty labels produce explicit pending status and null metrics, never fabricated zero accuracy. LLM scoring excludes rules fallbacks.

Known weak cases include warranty versus buy-back, return delay versus QC completion, DOA timing, conflicting notes, and short/misspelled Hinglish. Rules confidence is heuristic. LLM accuracy cannot be stated until an API run occurs.

## Validation and boundaries

```powershell
python -m unittest discover -s tests -v
```

The pipeline asserts unique joins, expected source units, exact summary totals and decomposition arithmetic. Tests additionally lock the re-derived dataset totals and exercise missing-key behavior, uncertainty retention and JSON validation. See `DECISIONS.md` for attribution, ambiguous matches, policy applicability and filtered-sheet reconciliation. Refund plus replacement is a screening flag from the export; who approved each action cannot be established from the resolving agent alone.

The code does not build a dashboard, live refund guardrail, agent ranking, chat interface, or extra product/lot/repeat-customer analysis. `RECORDING_NOTES.md` and `prompts/CHANGELOG.md` document actual work and unexecuted experiments honestly.
