"""Input normalization. All accounting uses integer paise after source conversion."""
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

ROOT = Path(__file__).resolve().parent


def find_input(name):
    for directory in (ROOT / 'data', ROOT):
        matches = sorted(directory.glob('*' + name)) if directory.exists() else []
        if not matches:
            matches = sorted(directory.glob('*' + name + '.txt')) if directory.exists() else []
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f'Ambiguous input {name}: {matches}')
    raise FileNotFoundError(f'Place {name} in data/')


def money(value):
    if pd.isna(value) or value == '':
        return 0
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def load_clean():
    raw = pd.read_csv(find_input('tickets.csv'))
    raw['raw_minor'] = raw.refund_amount_inr.map(money)
    raw_sum = int(raw.raw_minor.sum())
    raw['_priority'] = raw.source_system.map({'legacy_fd': 0, 'helpdesk': 1})
    assert raw._priority.notna().all(), 'Unknown source system'
    duplicate_ids = int(raw.loc[raw.ticket_id.duplicated(False), 'ticket_id'].nunique())
    d = raw.sort_values('_priority', kind='stable').drop_duplicates('ticket_id', keep='last').copy()
    dedup_sum = int(d.raw_minor.sum())
    for col in ['created_at', 'first_response_at']:
        d[col] = pd.to_datetime(d[col], errors='raise').dt.tz_localize('Asia/Kolkata')
    resolved = pd.to_datetime(d.resolved_at, errors='raise')
    d['resolved_at'] = resolved.dt.tz_localize('Asia/Kolkata')
    legacy = d.source_system.eq('legacy_fd')
    legacy_count = int(legacy.sum())
    d.loc[legacy, 'resolved_at'] = resolved[legacy].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
    cutoff = pd.Timestamp('2025-09-14', tz='Asia/Kolkata')
    late_legacy_count = int((legacy & d.created_at.ge(cutoff)).sum())
    assert not (legacy & d.created_at.ge(cutoff) & d.raw_minor.ne(0)).any(), 'Unexpected monetary legacy row after migration'
    d['refund_minor'] = d.raw_minor
    assert (d.loc[legacy, 'raw_minor'] % 100 == 0).all(), 'Fractional paise in source'
    d.loc[legacy, 'refund_minor'] = d.loc[legacy, 'raw_minor'] // 100
    d['refund_amount_inr'] = d.refund_minor / 100
    d['month'] = d.created_at.dt.strftime('%Y-%m')
    d['quarter'] = d.created_at.dt.tz_localize(None).dt.to_period('Q').astype(str)
    roster = pd.read_csv(find_input('agents.csv')).rename(columns={'name': 'agent_name'})
    roster['from_date'] = pd.to_datetime(roster.from_date)
    roster['to_date'] = pd.to_datetime(roster.to_date).fillna(pd.Timestamp('2100-01-01'))
    # Resolving agent is attributed at resolution, or creation for unfinished tickets.
    d['assignment_date'] = d.resolved_at.fillna(d.created_at).dt.tz_localize(None).dt.normalize()
    candidates = d[['ticket_id', 'agent_id', 'assignment_date']].merge(roster, on='agent_id', how='left')
    valid = candidates[candidates.assignment_date.between(candidates.from_date, candidates.to_date)]
    assert not valid.ticket_id.duplicated().any(), 'Overlapping roster validity dates'
    d = d.merge(valid[['ticket_id', 'agent_name', 'site', 'team', 'tier', 'shift']], on='ticket_id', how='left', validate='one_to_one')
    d['roster_missing'] = d.team.isna()
    for col in ['team', 'agent_name', 'site', 'shift']:
        d[col] = d[col].fillna('Unknown')
    d['tier'] = d.tier.fillna(0).astype(int)
    products = pd.read_csv(find_input('products.csv'))
    d = d.merge(products[['sku', 'unit_cost_inr', 'product_name']], left_on='product_sku', right_on='sku', how='left', validate='many_to_one').drop(columns='sku')
    assert d.unit_cost_inr.notna().all(), 'Missing product costs'
    orders = pd.read_csv(find_input('orders.csv'))
    assert orders.order_id.is_unique, 'Duplicate order IDs'
    orders['order_date'] = pd.to_datetime(orders.order_date)
    by_id = orders.set_index('order_id')
    fallback = {key: group for key, group in orders.groupby(['customer_id', 'sku'])}
    attachments = []
    for row in d.itertuples():
        match, method, count = None, 'unmatched', 0
        if pd.notna(row.order_id):
            if row.order_id in by_id.index:
                candidate = by_id.loc[row.order_id]
                if candidate.customer_id == row.customer_id and candidate.sku == row.product_sku and candidate.order_date <= row.created_at.tz_localize(None):
                    match, method, count = candidate, 'order_id', 1
                else:
                    method = 'order_conflict'
        else:
            options = fallback.get((row.customer_id, row.product_sku))
            if options is not None:
                options = options[options.order_date <= row.created_at.tz_localize(None)]
                count = len(options)
                if count == 1:
                    match, method = options.iloc[0], 'customer_sku'
                elif count > 1:
                    method = 'ambiguous'
        attachments.append({'ticket_id': row.ticket_id, 'order_match': method, 'order_candidates': count,
                            'matched_order_id': (row.order_id if method == 'order_id' else match.order_id) if match is not None else None,
                            'order_value_inr': match.order_value_inr if match is not None else None,
                            'lot_code': match.lot_code if match is not None else None})
    d = d.merge(pd.DataFrame(attachments), on='ticket_id', validate='one_to_one')
    d['replacement_cost_minor'] = (d.unit_cost_inr.map(money) + 34000).where(d.replacement_issued.eq('Y'), 0)
    targets = d.channel.map({'chat': 15, 'email': 480, 'voice': 120, 'social': 240})
    d['sla_breach'] = (d.first_response_at - d.created_at).dt.total_seconds().div(60).gt(targets)
    d['sla_credit_minor'] = (d.sla_breach & d.status.isin(['resolved', 'closed'])).astype(int) * 35000
    final = int(d.refund_minor.sum())
    waterfall = pd.DataFrame([
        ['Raw export (mixed units)', raw_sum, 0],
        ['After duplicate removal', dedup_sum, dedup_sum - raw_sum],
        ['After paise correction', final, final - dedup_sum],
        ['Final reconciled refunds', final, 0]], columns=['stage', 'balance_minor', 'change_minor'])
    refunds = d[d.refund_minor > 0].copy()
    assert d.ticket_id.is_unique and final == int(refunds.refund_minor.sum())
    audit = {'raw_rows': len(raw), 'clean_rows': len(d), 'duplicate_ticket_ids': duplicate_ids,
             'removed_rows': len(raw) - len(d), 'refund_tickets': len(refunds), 'refund_minor': final,
             'legacy_rows_converted': legacy_count, 'legacy_rows_on_or_after_cutover': late_legacy_count, 'missing_roster_rows': int(d.roster_missing.sum()),
             'raw_quarters_inr': raw.assign(quarter=pd.to_datetime(raw.created_at).dt.to_period('Q').astype(str)).groupby('quarter').raw_minor.sum().div(100).to_dict()}
    print(waterfall.assign(balance_inr=waterfall.balance_minor / 100).to_string(index=False))
    print('Refunds by quarter (INR):', refunds.groupby('quarter').refund_amount_inr.sum().to_dict())
    print('Audit:', audit)
    return d, refunds, waterfall, audit


if __name__ == '__main__':
    load_clean()
