"""Accounting invariants and failure paths that could mislead the controller."""
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import classify as classifier
from load_clean import load_clean
from rules_baseline import classify_text
from policy_checks import apply_checks
from analysis import analyze


class AccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all_tickets, cls.refunds, cls.waterfall, cls.audit = load_clean()

    def test_rederived_reference_totals_and_unique_joins(self):
        self.assertEqual(self.audit['duplicate_ticket_ids'], 638)
        self.assertEqual(len(self.refunds), 2340)
        self.assertEqual(int(self.refunds.refund_minor.sum()), 670993200)
        self.assertTrue(self.all_tickets.ticket_id.is_unique)
        self.assertEqual(self.audit['legacy_rows_on_or_after_cutover'], 1)
        self.assertEqual(int(self.refunds.groupby('month').refund_minor.sum().sum()), 670993200)
        self.assertEqual(self.refunds.groupby('quarter').refund_minor.sum().tolist(), [60958300, 72742200, 120709100, 162757500, 125843800, 127982300])

    def test_ambiguous_orders_stay_unresolved(self):
        ambiguous = self.refunds[self.refunds.order_match.eq('ambiguous')]
        self.assertGreater(len(ambiguous), 0)
        self.assertTrue(ambiguous.order_value_inr.isna().all())
        self.assertTrue(ambiguous.order_candidates.gt(1).all())

    def test_flags_and_decomposition(self):
        r = self.refunds.copy()
        r['inferred_reason'] = r.refund_reason_code
        r['final_reason'] = r.refund_reason_code
        r['needs_review'] = False
        r = apply_checks(r)
        self.assertEqual(int(r.goodwill_original_over_cap.sum()), 879)
        self.assertEqual(int(r.refund_and_replacement.sum()), 166)
        self.assertEqual(int(r.loc[r.refund_and_replacement, 'replacement_cost_minor'].sum()), 29697000)
        a = analyze(self.all_tickets, r)
        for row in a['decomposition'].itertuples():
            self.assertAlmostEqual(row.change_inr, row.volume_effect_inr + row.average_effect_inr)
        for row in a['opportunity'].itertuples():
            self.assertLess(row.target_max_tickets / row.refund_tickets, .01)


class ClassifierTests(unittest.TestCase):
    def test_json_validation(self):
        for bad in [{'reason': 'OTHER', 'confidence': .9, 'evidence': 'x'},
                    {'reason': 'CANCEL', 'confidence': True, 'evidence': 'x'},
                    {'reason': 'CANCEL', 'confidence': float('nan'), 'evidence': 'x'},
                    {'reason': 'CANCEL', 'confidence': .9, 'evidence': 'word ' * 16}]:
            with self.assertRaises(ValueError):
                classifier.validate_result(bad)

    def test_empty_notes_low_confidence(self):
        self.assertLess(classify_text('', 'as discussed')['confidence'], .7)
        self.assertLess(classify_text('refund was promised 7 days ago', 'refund not credited')['confidence'], .7)

    def test_no_key_and_low_confidence_retention(self):
        frame = pd.DataFrame([{'ticket_id': 'T1', 'customer_message': '', 'agent_notes': 'cx ok', 'refund_reason_code': 'CANCEL'}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'prompts').mkdir()
            (root / 'prompts/v2.txt').write_text('test prompt', encoding='utf-8')
            with patch.object(classifier, 'ROOT', root), patch.dict('os.environ', {'ANTHROPIC_API_KEY': ''}):
                result, cost = classifier.classify(frame)
                self.assertEqual(cost['calls'], 0)
                self.assertEqual(cost['total_cost_usd'], 0)
                self.assertEqual(result.iloc[0].final_reason, 'CANCEL')
                self.assertTrue(result.iloc[0].needs_review)

    def test_api_cache_text_invalidation_and_failed_json_fallback(self):
        frame = pd.DataFrame([{'ticket_id': 'T1', 'customer_message': 'cancel order', 'agent_notes': '', 'refund_reason_code': 'GW-OTHER'}])
        response = SimpleNamespace(usage=SimpleNamespace(input_tokens=100, output_tokens=20),
                                   content=[SimpleNamespace(type='text', text=json.dumps({'reason': 'CANCEL', 'confidence': .9, 'evidence': 'cancel order'}))])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'prompts').mkdir()
            (root / 'prompts/v2.txt').write_text('test prompt', encoding='utf-8')
            with patch.object(classifier, 'ROOT', root), patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-only-not-a-key', 'ANTHROPIC_MODEL': 'claude-haiku-4-5-20251001'}), patch('anthropic.Anthropic') as client:
                client.return_value.messages.create.return_value = response
                first, cost = classifier.classify(frame)
                self.assertEqual(first.iloc[0].classification_source, 'llm')
                self.assertAlmostEqual(cost['total_cost_usd'], .0002)
                second, cost = classifier.classify(frame)
                self.assertEqual(second.iloc[0].classification_source, 'llm_cache')
                self.assertEqual(cost['calls'], 0)
                frame.loc[0, 'customer_message'] = 'changed text'
                response.content[0].text = '{invalid json'
                third, cost = classifier.classify(frame)
                self.assertEqual(cost['calls'], 1)
                self.assertEqual(third.iloc[0].classification_source, 'rules_api_fallback')
                self.assertTrue(third.iloc[0].needs_review)
                self.assertGreater(cost['total_cost_usd'], 0)


if __name__ == '__main__':
    unittest.main()
