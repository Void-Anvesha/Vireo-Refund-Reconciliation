"""Deterministic screening flags; flags are not findings of misconduct."""
import pandas as pd

FLAG_COLUMNS = ['goodwill_original_over_cap', 'goodwill_final_over_cap', 'refund_and_replacement', 'reason_mismatch', 'refund_over_order', 'tier1_warranty_replacement', 'missing_order', 'unresolved_order', 'roster_missing']


def apply_checks(refunds):
    d = refunds.copy()
    d['goodwill_original_over_cap'] = d.refund_reason_code.eq('GW-OTHER') & d.refund_minor.gt(50000)
    d['goodwill_final_over_cap'] = d.final_reason.eq('GW-OTHER') & d.refund_minor.gt(50000)
    d['refund_and_replacement'] = d.replacement_issued.eq('Y')
    d['reason_mismatch'] = d.refund_reason_code.ne(d.inferred_reason)
    d['refund_over_order'] = d.refund_amount_inr.gt(d.order_value_inr) & d.order_value_inr.notna()
    warranty_text = (d.customer_message.fillna('') + ' ' + d.agent_notes.fillna('')).str.contains(r'warranty|\brma\b|buy.?back', case=False, regex=True)
    d['tier1_warranty_replacement'] = d.tier.eq(1) & d.replacement_issued.eq('Y') & (warranty_text | d.category.fillna('').str.contains('warranty', case=False) | d.final_reason.eq('WTY-BUYBACK'))
    d['missing_order'] = d.order_id.isna()
    d['unresolved_order'] = d.matched_order_id.isna()
    d['policy_flag_count'] = d[FLAG_COLUMNS].sum(axis=1)
    d['policy_flags'] = d[FLAG_COLUMNS].apply(lambda row: '; '.join(row.index[row]), axis=1)
    return d
