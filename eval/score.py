"""Honest evaluation: absent human labels or API predictions are reported as unavailable."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from load_clean import ROOT
from rules_baseline import LABELS


def metrics(frame, prediction):
    confusion = pd.crosstab(frame.human_reason, frame[prediction]).reindex(index=LABELS, columns=LABELS, fill_value=0)
    rows = []
    for label in LABELS:
        tp = int(((frame.human_reason == label) & (frame[prediction] == label)).sum())
        predicted = int(frame[prediction].eq(label).sum())
        support = int(frame.human_reason.eq(label).sum())
        rows.append({'label': label, 'support': support, 'precision': tp / predicted if predicted else None, 'recall': tp / support if support else None})
    gw = frame[frame.refund_reason_code.eq('GW-OTHER')]
    return {'n': len(frame), 'accuracy': float(frame.human_reason.eq(frame[prediction]).mean()) if len(frame) else None,
            'gw_other_n': len(gw), 'gw_other_accuracy': float(gw.human_reason.eq(gw[prediction]).mean()) if len(gw) else None,
            'per_class': rows}, confusion


def score():
    target = ROOT / 'output/evaluation'
    target.mkdir(exist_ok=True)
    labels = pd.read_csv(ROOT / 'eval/to_label.csv', keep_default_na=False)
    if not labels.ticket_id.is_unique:
        raise ValueError('Duplicate human-label ticket IDs')
    labels['human_reason'] = labels.human_reason.str.strip()
    invalid = set(labels.human_reason) - set(LABELS) - {''}
    if invalid:
        raise ValueError(f'Invalid human labels: {sorted(invalid)}')
    labels = labels[labels.human_reason.ne('')]
    predictions = pd.read_csv(ROOT / 'output/classifications.csv')
    if not predictions.ticket_id.is_unique:
        raise ValueError('Duplicate prediction ticket IDs')
    merged = labels.merge(predictions, on='ticket_id', validate='one_to_one', how='left', indicator=True)
    if merged._merge.ne('both').any():
        raise ValueError('Human labels contain tickets absent from current predictions')
    results = {'status': 'pending human labels' if not len(merged) else 'scored', 'labeled_tickets': len(merged),
               'sample_note': 'Stratified diagnostic sample; unweighted accuracy is not a population error-rate estimate.',
               'agent_disagreement_rate': float(merged.human_reason.ne(merged.refund_reason_code).mean()) if len(merged) else None}
    misses = []
    buckets = []
    for name, pred, confidence, frame in [('rules', 'rules_reason', 'rules_confidence', merged),
                                            ('llm', 'inferred_reason', 'confidence', merged[merged.classification_source.fillna('').str.startswith('llm')])]:
        result, matrix = metrics(frame, pred)
        result['status'] = 'scored' if len(frame) else ('pending human labels' if not len(merged) else 'no LLM predictions available')
        results[name] = result
        matrix.to_csv(target / f'{name}_confusion.csv')
        pd.DataFrame(result['per_class']).to_csv(target / f'{name}_per_class.csv', index=False)
        frame = frame.copy()
        frame['confidence_bucket'] = pd.cut(frame[confidence], bins=[-1, .4, .7, .9, 1.01], right=False, labels=['<0.4', '0.4-<0.7', '0.7-<0.9', '0.9-1.0'])
        for bucket, group in frame.groupby('confidence_bucket', observed=True):
            buckets.append({'classifier': name, 'bucket': str(bucket), 'n': len(group), 'accuracy': float(group.human_reason.eq(group[pred]).mean())})
        worst = frame[frame.human_reason.ne(frame[pred])].sort_values([confidence, 'refund_minor'], ascending=False).head(5)
        for row in worst.to_dict('records'):
            misses.append({'classifier': name, 'ticket_id': row['ticket_id'], 'human_reason': row['human_reason'], 'prediction': row[pred],
                           'confidence': row[confidence], 'message': row['message'], 'notes': row['notes'],
                           'why': f"Predicted {row[pred]} versus human {row['human_reason']}; inspect ambiguity and missing policy conditions. Root cause requires reviewer judgment."})
    history_path = ROOT / 'output/run_history.jsonl'
    history = [json.loads(line) for line in history_path.read_text(encoding='utf-8').splitlines()] if history_path.exists() else []
    total_cost = sum(run['total_cost_usd'] for run in history)
    responses = sum(run['successful_responses'] for run in history)
    results['cost'] = {'historical_api_cost_usd': total_cost, 'api_responses': responses,
                       'cost_per_api_response_usd': total_cost / responses if responses else None,
                       'cost_per_current_llm_ticket_usd': total_cost / int(predictions.classification_source.str.startswith('llm').sum()) if predictions.classification_source.str.startswith('llm').any() else None,
                       'note': 'History may include failed JSON responses and reclassifications; cached reruns have zero new cost.'}
    (target / 'metrics.json').write_text(json.dumps(results, indent=2, allow_nan=False), encoding='utf-8')
    pd.DataFrame(buckets, columns=['classifier', 'bucket', 'n', 'accuracy']).to_csv(target / 'confidence_buckets.csv', index=False)
    pd.DataFrame(misses, columns=['classifier', 'ticket_id', 'human_reason', 'prediction', 'confidence', 'message', 'notes', 'why']).to_csv(target / 'worst_misses.csv', index=False)
    if len(merged):
        accuracy_line = (
            f"Rules accuracy on the small diagnostic reviewed subset is {results['rules']['accuracy']:.1%}. "
            "This is not a population-weighted accuracy estimate; it is a spot-check that makes the baseline's limits visible. "
        )
    else:
        accuracy_line = "No accuracy is claimed without human labels. "
    (target / 'README.md').write_text(f"# Evaluation\n\nStatus: {results['status']}. Labeled tickets: {len(merged)}.\n\n"
        f"{accuracy_line}"
        'LLM accuracy is not available unless API predictions exist. '
        'Likely weak cases include pickup delays versus QC-complete returns, ordinary faults versus DOA, warranty versus buy-back, '
        'conflicting notes, and short or misspelled Hinglish messages. Rules confidence is not calibrated. '
        'The five worst misses are ordered by confidence then refund value; explanations identify disagreements, not invented human rationales.\n', encoding='utf-8')
    print(json.dumps({'status': results['status'], 'labeled_tickets': len(merged), 'agent_disagreement_rate': results['agent_disagreement_rate']}))


if __name__ == '__main__':
    score()
