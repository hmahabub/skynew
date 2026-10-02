"""
Money display: {{ amount|bdt }} -> "৳ 1,52,340.50" (Bangladeshi grouping),
{{ amount|usd }} -> "$ 30,900.00". Payments, costs, loans and the cash book
are BDT; orders, LCs and cost sheets are USD.
"""
from decimal import Decimal, InvalidOperation

from django import template

from apps.accounts.amounts import format_taka

register = template.Library()


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def bdt(value):
    amount = _decimal(value)
    return '-' if amount is None else f"৳ {format_taka(amount)}"


@register.filter
def usd(value):
    amount = _decimal(value)
    if amount is None:
        return '-'
    sign = '-' if amount < 0 else ''
    return f"{sign}$ {abs(amount):,.2f}"
