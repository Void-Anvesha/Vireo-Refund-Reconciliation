"""Optional API classification with validated JSON, durable cache and cost accounting."""
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
import pandas as pd
from load_clean import ROOT
from rules_baseline import LABELS, classify_text


def validate_result(result):
    if not isinstance(result, dict) or set(result) != {'reason', 'confidence', 'evidence'}:
        raise ValueError('Unexpected JSON schema')
    if result['reason'] not in LABELS:
        raise ValueError('Unknown code')
    score = result['confidence']
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('Invalid confidence')
    if not isinstance(result['evidence'], str) or len(result['evidence'].split()) > 15:
        raise ValueError('Evidence exceeds 15 words or is not a string')
    return result


def save_json(path, payload):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def classify(refunds, api_limit=None, force_rules=False):
    output = ROOT / 'output'
    output.mkdir(exist_ok=True)
    cache_dir = ROOT / '.cache'
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / 'classifications.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    prompt = (ROOT / 'prompts/v2.txt').read_text(encoding='utf-8')
    model = os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
    default_rates = model in ('claude-haiku-4-5-20251001', 'claude-haiku-4-5')
    input_rate = float(os.getenv('ANTHROPIC_INPUT_USD_PER_MILLION', '1' if default_rates else 'nan'))
    output_rate = float(os.getenv('ANTHROPIC_OUTPUT_USD_PER_MILLION', '5' if default_rates else 'nan'))
    key = os.getenv('ANTHROPIC_API_KEY')
    client = None
    error = None
    if key and not force_rules:
        if not all(math.isfinite(x) and x >= 0 for x in (input_rate, output_rate)):
            raise ValueError('Set input/output USD rates for the configured model')
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=key, max_retries=0, timeout=45)
        except ImportError:
            error = 'Anthropic package missing; install requirements.txt'
    costs = {'run_at_utc': datetime.now(timezone.utc).isoformat(), 'model': model, 'calls': 0,
             'successful_responses': 0, 'input_tokens': 0, 'output_tokens': 0, 'cache_hits': 0,
             'total_cost_usd': 0.0, 'errors': [], 'billing_uncertainty': False,
             'input_usd_per_million': input_rate if math.isfinite(input_rate) else None,
             'output_usd_per_million': output_rate if math.isfinite(output_rate) else None,
             'pricing_source': 'https://platform.claude.com/docs/en/about-claude/pricing',
             'api_limit': api_limit, 'key_configured': bool(key), 'force_rules': force_rules}
    if error:
        costs['errors'].append(error)
    started = time.perf_counter()
    predictions = []
    failures = 0
    for row in refunds.itertuples():
        message = '' if pd.isna(row.customer_message) else row.customer_message
        notes = '' if pd.isna(row.agent_notes) else row.agent_notes
        baseline = classify_text(message, notes)
        payload = json.dumps({'customer_message': message, 'agent_notes': notes}, ensure_ascii=False)
        fingerprint = hashlib.sha256((model + prompt + payload).encode()).hexdigest()
        cached = cache.get(row.ticket_id, {})
        result, source = baseline, 'rules'
        if not force_rules and cached.get('fingerprint') == fingerprint:
            try:
                result = validate_result(cached['result'])
                source = 'llm_cache'
                costs['cache_hits'] += 1
            except (ValueError, KeyError):
                pass
        if source == 'rules' and client is not None and failures < 3 and (api_limit is None or costs['calls'] < api_limit):
            costs['calls'] += 1
            received = False
            try:
                response = client.messages.create(model=model, max_tokens=180, temperature=0,
                                                  system=prompt, messages=[{'role': 'user', 'content': payload}])
                received = True
                costs['input_tokens'] += response.usage.input_tokens
                costs['output_tokens'] += response.usage.output_tokens
                costs['successful_responses'] += 1
                response_text = ''.join(block.text for block in response.content if block.type == 'text')
                result = validate_result(json.loads(response_text))
                source = 'llm'
                cache[row.ticket_id] = {'fingerprint': fingerprint, 'result': result}
                save_json(cache_path, cache)
                failures = 0
            except Exception as exc:
                # Never log exception text containing request payloads or credentials.
                costs['errors'].append({'ticket_id': row.ticket_id, 'error_type': type(exc).__name__})
                costs['billing_uncertainty'] |= not received
                failures += 1
                result, source = baseline, 'rules_api_fallback'
        predictions.append({'ticket_id': row.ticket_id, 'inferred_reason': result['reason'],
                            'confidence': result['confidence'], 'evidence': result['evidence'],
                            'classification_source': source, 'rules_reason': baseline['reason'],
                            'rules_confidence': baseline['confidence']})
    costs['total_cost_usd'] = (costs['input_tokens'] * (input_rate if math.isfinite(input_rate) else 0) + costs['output_tokens'] * (output_rate if math.isfinite(output_rate) else 0)) / 1e6
    costs['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    result = refunds.merge(pd.DataFrame(predictions), on='ticket_id', validate='one_to_one')
    result['needs_review'] = result.confidence.lt(.7)
    result['final_reason'] = result.inferred_reason.where(~result.needs_review, result.refund_reason_code.fillna('UNSPECIFIED'))
    costs['classification_counts'] = result.classification_source.value_counts().to_dict()
    costs['mode'] = 'rules-only' if not result.classification_source.str.startswith('llm').any() else ('llm' if result.classification_source.str.startswith('llm').all() else 'mixed')
    costs['pilot_status'] = 'not run: no key or forced rules' if not client else ('limited run' if api_limit is not None else 'full run')
    save_json(output / 'run_cost.json', costs)
    with (output / 'run_history.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(costs) + '\n')
    print(f"Classification: {costs['mode']}; calls={costs['calls']}; cost=${costs['total_cost_usd']:.6f}; review={result.needs_review.sum()}")
    return result, costs
