"""One-command workflow; optional pilot limits fresh API calls without truncating accounts."""
import argparse
import json
import time
from load_clean import ROOT, load_clean
from classify import classify
from policy_checks import apply_checks
from analysis import analyze
from report import build_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rules-only', action='store_true', help='Use only the rules baseline, including when a key exists')
    parser.add_argument('--pilot', type=int, help='Maximum fresh API calls (e.g. 50); remaining tickets use rules/cache')
    args = parser.parse_args()
    if args.pilot is not None and args.pilot < 0:
        parser.error('--pilot must be nonnegative')
    start = time.perf_counter()
    all_tickets, refunds, waterfall, audit = load_clean()
    refunds, costs = classify(refunds, api_limit=args.pilot, force_rules=args.rules_only)
    refunds = apply_checks(refunds)
    goodwill = refunds[refunds.refund_reason_code.eq('GW-OTHER')]
    both = refunds[refunds.refund_and_replacement]
    audit.update({'original_gw_tickets': len(goodwill), 'original_gw_inr': int(goodwill.refund_minor.sum()) / 100,
                  'original_gw_value_share': float(goodwill.refund_minor.sum() / refunds.refund_minor.sum()),
                  'missing_order_share': float(refunds.order_id.isna().mean()),
                  'double_compensation_rate': len(both) / len(refunds),
                  'double_compensation_refund_inr': int(both.refund_minor.sum()) / 100,
                  'double_compensation_replacement_inr': int(both.replacement_cost_minor.sum()) / 100,
                  'double_compensation_by_resolving_team': both.team.value_counts().to_dict(),
                  'double_compensation_by_initial_team': both.assigned_team.value_counts().to_dict()})
    analysis = analyze(all_tickets, refunds)
    sentences = build_report(all_tickets, refunds, waterfall, audit, analysis, costs)
    metadata = {'runtime_seconds': round(time.perf_counter() - start, 2), 'classification_mode': costs['mode'],
                'refund_tickets': len(refunds), 'total_inr': int(refunds.refund_minor.sum()) / 100,
                'policy_flags': refunds[['goodwill_original_over_cap', 'refund_and_replacement', 'missing_order', 'unresolved_order']].sum().astype(int).to_dict()}
    (ROOT / 'output/run_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('\n'.join(sentences))
    print(f"Saved output/vireo_refunds.xlsx in {metadata['runtime_seconds']:.2f}s")


if __name__ == '__main__':
    main()
