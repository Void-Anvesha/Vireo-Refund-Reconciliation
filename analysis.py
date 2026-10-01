"""Refund drivers and opportunity estimates; AI never writes financial conclusions."""
import math
import pandas as pd


def analyze(all_tickets, refunds):
    quarters = refunds.groupby('quarter').agg(refund_count=('ticket_id', 'size'), refund_minor=('refund_minor', 'sum'))
    quarters['average_inr'] = quarters.refund_minor / 100 / quarters.refund_count
    comparisons, contributions = [], []
    for start, end in [('2025Q2', '2025Q4'), ('2025Q4', '2026Q2'), ('2025Q2', '2026Q2')]:
        a, b = quarters.loc[start], quarters.loc[end]
        # Symmetric (Shapley) decomposition removes arbitrary ordering effects.
        volume = (b.refund_count - a.refund_count) * (a.average_inr + b.average_inr) / 2
        value = (b.average_inr - a.average_inr) * (a.refund_count + b.refund_count) / 2
        delta = (b.refund_minor - a.refund_minor) / 100
        assert math.isclose(volume + value, delta, abs_tol=.000001)
        comparisons.append({'comparison': f'{start} to {end}', 'start_count': int(a.refund_count), 'end_count': int(b.refund_count),
                            'start_average_inr': a.average_inr, 'end_average_inr': b.average_inr,
                            'change_inr': delta, 'volume_effect_inr': volume, 'average_effect_inr': value})
        for dimension in ['final_reason', 'team', 'channel']:
            grouped = refunds.groupby(['quarter', dimension]).agg(count=('ticket_id', 'size'), minor=('refund_minor', 'sum'))
            av, bv = grouped.loc[start], grouped.loc[end]
            joined = av.join(bv, how='outer', lsuffix='_start', rsuffix='_end').fillna(0)
            assert int((joined.minor_end - joined.minor_start).sum()) == int(b.refund_minor - a.refund_minor)
            for label, row in joined.iterrows():
                contributions.append({'comparison': f'{start} to {end}', 'dimension': dimension, 'group': label,
                                      'start_count': int(row.count_start), 'end_count': int(row.count_end),
                                      'start_minor': int(row.minor_start), 'end_minor': int(row.minor_end),
                                      'change_minor': int(row.minor_end - row.minor_start)})
    csat_rows = []
    frontline = all_tickets[all_tickets.team.isin(['Chat Frontline', 'Email Frontline', 'Voice Frontline'])]
    for population, frame in [('All tickets', all_tickets), ('Refund tickets', refunds), ('Resolving frontline teams', frontline)]:
        for quarter, group in frame.groupby('quarter'):
            eligible = group[group.status.isin(['resolved', 'closed'])]
            scores = eligible.csat_score.dropna()
            csat_rows.append({'population': population, 'quarter': quarter, 'completed_tickets': len(eligible),
                              'responses': len(scores), 'response_rate': len(scores) / len(eligible) if len(eligible) else 0,
                              'mean_csat': scores.mean()})
    claim = []
    for quarter, group in refunds.groupby('quarter'):
        claim.append({'quarter': quarter, 'refund_count': len(group), 'goodwill_like_count': int(group.final_reason.isin(['GW-OTHER', 'PRICE-ADJ']).sum()),
                      'doa_count': int(group.final_reason.eq('DOA-REPL').sum()), 'transit_count': int(group.final_reason.eq('LOST-TRANSIT').sum()),
                      'low_confidence_count': int(group.needs_review.sum())})
    opportunity = []
    for quarter, group in refunds.groupby('quarter'):
        both = group[group.refund_and_replacement]
        count = len(both)
        # Strictly below 1%, not <=1%.
        target_max = max(0, math.ceil(len(group) * .01) - 1)
        avoided = max(0, count - target_max)
        lower = float(both.replacement_cost_minor.mean() / 100 * avoided) if count else 0
        upper = float(both.refund_minor.mean() / 100 * avoided) if count else 0
        original = int(group.loc[group.refund_reason_code.eq('GW-OTHER'), 'refund_minor'].sum())
        final = int(group.loc[group.final_reason.eq('GW-OTHER'), 'refund_minor'].sum())
        opportunity.append({'quarter': quarter, 'refund_tickets': len(group), 'double_tickets': count,
                            'double_rate': count / len(group), 'target_max_tickets': target_max, 'avoided_tickets': avoided,
                            'replacement_exposure_minor': int(both.replacement_cost_minor.sum()), 'refund_exposure_minor': int(both.refund_minor.sum()),
                            'mean_replacement_inr': float(both.replacement_cost_minor.mean() / 100) if count else 0,
                            'mean_refund_inr': float(both.refund_minor.mean() / 100) if count else 0,
                            'saving_lower_inr': lower, 'saving_upper_inr': upper,
                            'original_gw_minor': original, 'final_gw_minor': final,
                            'original_gw_share': original / group.refund_minor.sum(), 'final_gw_share': final / group.refund_minor.sum()})
    separate = all_tickets.groupby('quarter').agg(replacement_cost_minor=('replacement_cost_minor', 'sum'), estimated_sla_credit_minor=('sla_credit_minor', 'sum'))
    return {'quarters': quarters.reset_index(), 'decomposition': pd.DataFrame(comparisons),
            'contributions': pd.DataFrame(contributions), 'csat': pd.DataFrame(csat_rows), 'claim': pd.DataFrame(claim),
            'opportunity': pd.DataFrame(opportunity), 'separate_costs': separate.reset_index()}
