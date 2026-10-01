"""Conservative text-only baseline. Confidence scores require human calibration."""
import re

LABELS = ('GW-OTHER', 'DOA-REPL', 'LOST-TRANSIT', 'DUP-PAYMENT', 'CANCEL', 'PRICE-ADJ', 'RETURN-QC-OK', 'WTY-BUYBACK')
RULES = [
    ('DUP-PAYMENT', r'double.{0,15}(charg|debit)|duplicate.{0,15}(pay|charg)|charged twice|debited twice|payment.{0,30}(no order|no ordr|not showing)|money debited|payment was deducted|upi shows success|payment gateway|failed payment', .86),
    ('CANCEL', r'cancel|stop the shipment|ordered by mistake|change of mind', .86),
    ('PRICE-ADJ', r'coupon|price.{0,15}(drop|adjust|difference)|discount|cashback|promo', .82),
    ('LOST-TRANSIT', r'lost.{0,15}(transit|parcel|shipment)|not delivered|not received|undelivered|shipment not received|tracking.{0,20}(stuck|updat)|damaged.{0,15}(transit|box|parcel)|empty (box|package)|wrong (item|product).{0,15}deliver', .8),
    ('DOA-REPL', r'dead on arrival|\bdoa\b|out of (the )?box|arrived.{0,20}(dead|broken)|first (day|use)|day one|never (turned|switched|worked)', .83),
    ('RETURN-QC-OK', r'(qc|quality check).{0,20}(pass|ok|clear)', .82),
    ('RETURN-QC-OK', r'return received|received.{0,20}warehouse|picked up.{0,30}(money|refund)|refund not credited|refund was promised', .55),
    ('WTY-BUYBACK', r'buy.?back|warranty.{0,25}(refund|settlement)|out of stock.{0,30}(refund|warranty)|beyond repair', .8),
    ('GW-OTHER', r'goodwill|courtesy|gesture|pickup missed|pickup.{0,20}(pending|not happened)|courier.{0,20}(no.show|not showed)', .72),
]


def classify_text(message, notes):
    text = (str(message or '') + ' ' + str(notes or '')).lower().replace('\\n', ' ')
    text = re.sub(r'\brfnd\b|\brefnuded\b', 'refund', text)
    text = re.sub(r'\bpkp\b', 'pickup', text)
    text = text.replace('paisa kat', 'money debited').replace('paise kat', 'money debited').replace('band karo', 'cancel')
    matches = [(code, re.search(pattern, text), confidence) for code, pattern, confidence in RULES]
    matches = [(code, match, confidence) for code, match, confidence in matches if match]
    if not matches:
        return {'reason': 'GW-OTHER', 'confidence': .3, 'evidence': 'Insufficient specific evidence in text'}
    code, match, confidence = matches[0]
    if len({x[0] for x in matches}) > 1:
        confidence = .6
    return {'reason': code, 'confidence': confidence, 'evidence': ' '.join(match.group().split()[:15])}
