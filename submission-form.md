# Submission Form

## Project

Vireo Audio refund review - Set C.

## Deliverable

A runnable Python tool that cleans the helpdesk export, reconciles refund money, classifies refund reasons using a conservative rules baseline, applies policy checks, and creates:

- `output/vireo_refunds.xlsx`
- `MEMO.md`
- supporting audit CSV/JSON files in `output/`
- prompt notes in `prompts/`
- evaluation scripts and labels in `eval/`

The tool runs without a paid API key:

```powershell
python run.py --rules-only
```

## AI Use

The code includes an optional Anthropic classifier path, strict JSON validation, caching, and cost logging. No Anthropic key was available for this submission, so the delivered run is intentionally rules-only. No paid API calls were made and no fake AI accuracy claim is made.

Prompt drafts are included:

- `prompts/v1.txt`: first draft, not executed.
- `prompts/v2.txt`: improved production prompt for a later API-backed run.
- `prompts/CHANGELOG.md`: what changed and what was discarded.

## Business Goal

Reduce refund-plus-replacement cases below 1% of refund tickets.

In Q2 2026, there were 32 refund-plus-replacement cases out of 473 refund tickets, or 6.8%. A below-1% target allows at most 4 cases, so the current opportunity is about 28 avoided cases.

Estimated quarterly value at Q2 2026 volume:

- lower estimate: Rs 0.48 lakh, using observed replacement cost
- upper estimate: Rs 0.93 lakh, using observed refund value

This is a control opportunity, not guaranteed recovered cash.

## Validation

Accounting validation is covered by automated tests and reconciliation outputs.

Current checked facts:

- 638 duplicate ticket rows removed
- 2,340 refund tickets analyzed
- final reconciled refund total: Rs 67,09,932
- summary totals reconcile using integer paise accounting
- ambiguous order matches stay unresolved instead of being forced

Run:

```powershell
python -m unittest discover -s tests -v
python eval/score.py
```

The evaluation folder includes a small diagnostic human-label check and a larger sample for continued review. Current diagnostic result: 17 labeled tickets, rules accuracy 52.9%. This is not a population accuracy estimate; it is a transparent spot-check showing where the baseline is weak. Because the delivered run is rules-only, LLM accuracy is not applicable until someone runs the optional API path with a configured key.

## Cost

Application API cost for the submitted run: USD 0.

The latest cost log is in:

- `output/run_cost.json`
- `output/run_history.jsonl`

## Main Decisions

- Kept the current helpdesk copy of duplicate ticket IDs.
- Corrected legacy paise amounts only where source-unit evidence supports it.
- Reported by ticket created month in IST.
- Used integer paise for accounting.
- Joined agents using validity dates.
- Preserved ambiguous order matches as unresolved.
- Separated refund amount from replacement cost and estimated SLA credits.
- Avoided agent blame/ranking because resolving-agent attribution does not prove who approved each action.
- Treated weak text evidence as low-confidence and reviewable.

More detail is in `DECISIONS.md`.

## Left Out

- Interactive dashboard: static board pack was enough for the controller request.
- Live refund guardrail: recommended as an operational next step, not built.
- Agent ranking: not fair from this data.
- Chat interface: outside the useful scope.
- Full paid AI run: not affordable without an Anthropic key.

## Recording

The screen recording should follow `RECORDING_NOTES.md` and stay under three minutes.
