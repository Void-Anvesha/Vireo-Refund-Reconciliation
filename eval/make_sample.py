"""Deterministic approximately balanced sample across code, channel and source."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from load_clean import ROOT, load_clean


def make_sample(refunds, n=120):
    # Round-robin within each joint stratum improves coverage without claiming population weighting.
    shuffled = refunds.sample(frac=1, random_state=42).copy()
    dims = ['refund_reason_code', 'channel', 'source_system']
    shuffled['_round'] = shuffled.groupby(dims, dropna=False).cumcount()
    selected = shuffled.sort_values('_round', kind='stable').head(n)
    output = selected[['ticket_id', 'customer_message', 'agent_notes']].rename(columns={'customer_message': 'message', 'agent_notes': 'notes'})
    output['human_reason'] = ''
    return output, selected[dims].value_counts().reset_index(name='sample_count')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Explicitly replace the existing labeling sample')
    args = parser.parse_args()
    target = ROOT / 'eval/to_label.csv'
    if target.exists() and not args.force:
        print('Existing eval/to_label.csv retained; labels are never overwritten by default.')
        return
    _, refunds, _, _ = load_clean()
    sample, strata = make_sample(refunds)
    sample.to_csv(target, index=False, encoding='utf-8-sig')
    strata.to_csv(ROOT / 'eval/sample_strata.csv', index=False)
    print(f'Wrote {len(sample)} tickets to eval/to_label.csv; add human_reason using policy codes.')


if __name__ == '__main__':
    main()
