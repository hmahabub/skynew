"""Taka amounts for printed documents: Bangladeshi digit grouping and amount in words."""
from decimal import Decimal, ROUND_HALF_UP

_ONES = [
    '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten',
    'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen',
]
_TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']


def _two_digits(n):
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (' ' + _ONES[n % 10] if n % 10 else '')).strip()


def _three_digits(n):
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if rest:
        parts.append(_two_digits(rest))
    return ' '.join(parts)


def _integer_in_words(n):
    """Words using the Bangladeshi system: Crore, Lakh, Thousand, Hundred."""
    if n == 0:
        return 'Zero'
    parts = []
    crore, n = divmod(n, 10_000_000)
    if crore:
        parts.append(f"{_integer_in_words(crore)} Crore")
    lakh, n = divmod(n, 100_000)
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    thousand, n = divmod(n, 1000)
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if n:
        parts.append(_three_digits(n))
    return ' '.join(parts)


def _to_decimal(amount):
    return Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def taka_in_words(amount):
    """e.g. 152340.50 -> 'One Lakh Fifty Two Thousand Three Hundred Forty Taka and Fifty Paisa Only'"""
    amount = _to_decimal(amount)
    taka = int(amount)
    paisa = int((amount - taka) * 100)
    words = f"{_integer_in_words(taka)} Taka"
    if paisa:
        words += f" and {_two_digits(paisa)} Paisa"
    return words + " Only"


def format_taka(amount):
    """Bangladeshi grouping: 1234567.5 -> '12,34,567.50'"""
    amount = _to_decimal(amount)
    sign = '-' if amount < 0 else ''
    whole, fraction = f"{abs(amount):.2f}".split('.')
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ','.join(groups + [tail])
    return f"{sign}{whole}.{fraction}"
