"""
Every money movement in Accounting goes through here, so the cash book is
always posted the same way no matter which screen (or the seed command)
recorded it. Call these inside transaction.atomic() when combining several.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction

from .models import CashBookEntry, Cost, LCLoanRepayment, LCPayment

TWO_PLACES = Decimal('0.01')


def last_exchange_rate():
    """The most recent BDT-per-USD rate used on an LC receipt - suggested on the next one."""
    last = LCPayment.objects.exclude(exchange_rate__isnull=True).order_by('-payment_date', '-pk').first()
    return last.exchange_rate if last else None


def to_bdt(amount_usd, exchange_rate):
    return (Decimal(amount_usd) * Decimal(exchange_rate)).quantize(TWO_PLACES)


def _mode_for_payment_method(method):
    return 'cash' if method == 'cash' else 'bank'


def post_cashbook(direction, amount, description, *, entry_date=None, mode='cash', bank_name='',
                  reference='', source='manual', source_id=None, user=None):
    return CashBookEntry.objects.create(
        entry_date=entry_date or date.today(),
        direction=direction,
        amount=amount,
        mode=mode,
        bank_name=bank_name if mode == 'bank' else '',
        reference=reference,
        description=description[:255],
        source=source,
        source_id=source_id,
        created_by=user,
    )


def record_payment(payment, user=None):
    """A buyer / supplier payment: money in for receivables, out for payables."""
    party = payment.buyer if payment.payment_type == 'receivable' else payment.supplier
    party_name = (party.buyer_name if payment.payment_type == 'receivable' else party.supplier_name) if party else '-'
    verb = 'Received from' if payment.payment_type == 'receivable' else 'Paid to'
    return post_cashbook(
        'in' if payment.payment_type == 'receivable' else 'out',
        payment.amount,
        f"{verb} {party_name} ({payment.payment_number})",
        entry_date=payment.payment_date,
        mode=_mode_for_payment_method(payment.payment_method),
        reference=payment.reference_number,
        source='payment', source_id=payment.pk, user=user,
    )


def record_cost(cost, user=None):
    """Save a cost - every cost counts as paid, so it also goes out of the cash book."""
    if cost.paid_by == 'cash':
        cost.bank_name = ''
    with transaction.atomic():
        cost.created_by = cost.created_by or user
        cost.save()
        scope = f"Order {cost.project.project_number}" if cost.project_id else "Overall"
        detail = f" - {cost.description}" if cost.description else ""
        paid_to = f" (paid to {cost.supplier.supplier_name})" if cost.supplier_id else ""
        post_cashbook(
            'out', cost.amount,
            f"{scope}: {cost.get_cost_type_display()}{detail}{paid_to}",
            entry_date=cost.cost_date, mode=cost.paid_by, bank_name=cost.bank_name,
            reference=cost.reference, source='cost', source_id=cost.pk, user=user,
        )
    return cost


def approve_voucher(voucher, approver):
    """Approve a pending voucher: it becomes a (paid) Cost straight away."""
    if voucher.status != 'pending':
        raise ValueError(f"{voucher.voucher_number} has already been {voucher.get_status_display().lower()}.")
    with transaction.atomic():
        cost = record_cost(Cost(
            project=voucher.project,
            supplier=voucher.supplier,
            cost_type=voucher.cost_type,
            cost_date=voucher.voucher_date,
            description=voucher.description,
            amount=voucher.amount,
            paid_by=voucher.paid_by,
            bank_name=voucher.bank_name,
            reference=voucher.voucher_number,
            remarks=voucher.remarks,
            created_by=voucher.requested_by,
        ), user=approver)
        voucher.status = 'approved'
        voucher.approved_by = approver
        voucher.approved_date = date.today()
        voucher.cost = cost
        voucher.save(update_fields=['status', 'approved_by', 'approved_date', 'cost'])
    return cost


def reject_voucher(voucher, approver, reason=''):
    if voucher.status != 'pending':
        raise ValueError(f"{voucher.voucher_number} has already been {voucher.get_status_display().lower()}.")
    voucher.status = 'rejected'
    voucher.approved_by = approver
    voucher.approved_date = date.today()
    voucher.rejection_reason = reason
    voucher.save(update_fields=['status', 'approved_by', 'approved_date', 'rejection_reason'])


def take_loan(loan, user=None):
    """Save a new LC loan - the money arrives in the bank."""
    if not loan.lc.is_open:
        raise ValueError(f"LC {loan.lc.lc_number} is {loan.lc.get_status_display().lower()} - loans can only be taken against an active LC.")
    with transaction.atomic():
        loan.created_by = loan.created_by or user
        loan.save()
        post_cashbook(
            'in', loan.loan_amount, f"Loan against LC {loan.lc.lc_number}",
            entry_date=loan.loan_date, mode='bank', bank_name=loan.bank_name or loan.lc.bank_name,
            source='loan', source_id=loan.pk, user=user,
        )
    return loan


def _add_repayment(loan, amount, kind, *, repayment_date, mode='bank', bank_name='', reference='', remarks='', user=None):
    repayment = LCLoanRepayment.objects.create(
        loan=loan, kind=kind, amount=amount, repayment_date=repayment_date, mode=mode,
        bank_name=bank_name, reference=reference, remarks=remarks, created_by=user,
    )
    loan.repaid_amount += amount
    loan.save(update_fields=['repaid_amount'])
    return repayment


def repay_loan(loan, amount, *, repayment_date=None, mode='bank', bank_name='', reference='', remarks='', user=None):
    """The user pays an instalment on an LC loan - money goes out of the cash book."""
    if amount <= 0:
        raise ValueError("Repayment amount must be more than 0.")
    if amount > loan.outstanding:
        raise ValueError(f"Only {loan.outstanding:.2f} is still owed on this loan.")
    with transaction.atomic():
        repayment = _add_repayment(
            loan, amount, 'payment', repayment_date=repayment_date or date.today(), mode=mode,
            bank_name=bank_name, reference=reference, remarks=remarks, user=user,
        )
        post_cashbook(
            'out', amount, f"Loan repayment - LC {loan.lc.lc_number}",
            entry_date=repayment.repayment_date, mode=mode, bank_name=bank_name, reference=reference,
            source='loan_repayment', source_id=repayment.pk, user=user,
        )
    return repayment


def record_lc_receipt(lc_payment, user=None):
    """
    A part payment received under an LC before it's completed. amount is
    USD; the BDT the bank credited (amount_bdt, or USD x rate) goes into the
    cash book.
    """
    if lc_payment.amount_bdt is None:
        if not lc_payment.exchange_rate:
            raise ValueError("An exchange rate (or the BDT amount credited) is needed.")
        lc_payment.amount_bdt = to_bdt(lc_payment.amount, lc_payment.exchange_rate)
    lc_payment.created_by = lc_payment.created_by or user
    lc_payment.save()
    post_cashbook(
        'in', lc_payment.amount_bdt,
        f"Received under LC {lc_payment.lc.lc_number} (USD {lc_payment.amount:,.2f})",
        entry_date=lc_payment.payment_date, mode='bank', bank_name=lc_payment.bank_name,
        reference=lc_payment.reference, source='lc_receipt', source_id=lc_payment.pk, user=user,
    )
    return lc_payment


def complete_lc(lc, realized_usd, exchange_rate=None, *, realized_bdt=None, completion_date=None,
                bank_name='', reference='', user=None):
    """
    Complete an LC. realized_usd is what the LC paid (USD); the bank credits
    realized_bdt (or USD x exchange_rate). That BDT first pays off whatever is
    still owed on the LC's loans (loans are BDT, oldest first); only the rest
    reaches the cash book. Returns (loan_adjusted, net_received), both BDT.
    """
    if not lc.is_open:
        raise ValueError(f"LC {lc.lc_number} is already {lc.get_status_display().lower()}.")
    if realized_usd < 0:
        raise ValueError("Realised amount can't be negative.")
    if realized_bdt is None:
        if realized_usd and not exchange_rate:
            raise ValueError("An exchange rate (or the BDT amount credited) is needed.")
        realized_bdt = to_bdt(realized_usd, exchange_rate) if realized_usd else Decimal('0')
    completion_date = completion_date or date.today()
    bank_name = bank_name or lc.bank_name

    with transaction.atomic():
        receipt = LCPayment.objects.create(
            lc=lc, payment_date=completion_date, amount=realized_usd, exchange_rate=exchange_rate,
            amount_bdt=realized_bdt, bank_name=bank_name, reference=reference,
            remarks="LC completed", created_by=user,
        ) if realized_usd else None

        remaining = realized_bdt
        adjusted = Decimal('0')
        for loan in lc.lc_loans.order_by('loan_date', 'pk'):
            if remaining <= 0:
                break
            take = min(loan.outstanding, remaining)
            if take <= 0:
                continue
            _add_repayment(
                loan, take, 'lc_adjustment', repayment_date=completion_date, bank_name=bank_name,
                reference=reference, remarks=f"Adjusted from LC {lc.lc_number} on completion", user=user,
            )
            adjusted += take
            remaining -= take

        net = realized_bdt - adjusted
        if net > 0:
            note = f", after BDT {adjusted:,.2f} loan adjusted" if adjusted else ""
            post_cashbook(
                'in', net, f"LC {lc.lc_number} realised (USD {realized_usd:,.2f}{note})",
                entry_date=completion_date, mode='bank', bank_name=bank_name, reference=reference,
                source='lc_receipt', source_id=receipt.pk if receipt else None, user=user,
            )

        lc.status = 'completed'
        lc.completed_date = completion_date
        lc.realized_amount = realized_usd
        lc.exchange_rate = exchange_rate
        lc.realized_bdt = realized_bdt
        lc.loan_adjusted = adjusted
        lc.save(update_fields=['status', 'completed_date', 'realized_amount', 'exchange_rate',
                               'realized_bdt', 'loan_adjusted'])
    return adjusted, net


def transfer_between_cash_and_bank(amount, to_mode, *, entry_date=None, bank_name='', reference='', notes='', user=None):
    """Move money between cash in hand and bank: one 'out' line and one 'in' line."""
    from_mode = 'cash' if to_mode == 'bank' else 'bank'
    label = "Cash deposited to bank" if to_mode == 'bank' else "Cash withdrawn from bank"
    description = f"{label} - {notes}" if notes else label
    with transaction.atomic():
        post_cashbook('out', amount, description, entry_date=entry_date, mode=from_mode, bank_name=bank_name,
                      reference=reference, source='transfer', user=user)
        post_cashbook('in', amount, description, entry_date=entry_date, mode=to_mode, bank_name=bank_name,
                      reference=reference, source='transfer', user=user)
