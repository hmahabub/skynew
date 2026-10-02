from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta, date
import json
import csv
from decimal import Decimal

from .models import (
    Buyer, Supplier, Project, PurchaseOrder, PurchaseOrderItem,
    SalesInvoice, SalesInvoiceItem, Payment,
    CostSheet, BankAccount, BankTransaction,
    LetterOfCredit, LCPayment, LCLoan, LCLoanRepayment, Cost, CostVoucher, CashBookEntry,
)
from .forms import (
    BuyerForm, SupplierForm, ProjectForm, OrderForm, PurchaseOrderForm,
    SalesInvoiceForm, PaymentForm,
    CostSheetForm, BankAccountForm, BankTransactionForm,
    LetterOfCreditForm, LCPaymentForm, LCReceiptForm, LCLoanForm, LCLoanRepaymentForm, LCCompleteForm,
    OrderCostForm, OverallCostForm, CostVoucherForm, CashBookEntryForm,
)
from . import services
from .amounts import format_taka, taka_in_words
from django.http import Http404
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

# Accounts is superuser-only, module-wide - no separate approver role.
is_superuser = user_passes_test(lambda u: u.is_superuser)

def merchandising_required(view):
    """
    Purchase Orders and Sales Invoices belong to the Merchandising module,
    which is switched off for now (settings.MERCHANDISING_ENABLED). Their
    pages send the user back to Accounting instead; no data is touched.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not settings.MERCHANDISING_ENABLED:
            messages.info(request, "Purchase Orders and Invoices are part of the Merchandising module, which is turned off for now.")
            return redirect('accounts:accounts_dashboard')
        return view(request, *args, **kwargs)
    return wrapper

def bank_book_hidden(view):
    """The separate bank book is switched off - the Cash Book covers bank payments too."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        messages.info(request, "The bank book isn't used for now - record bank payments in the Cash Book (choose 'Bank').")
        return redirect('accounts:cashbook')
    return wrapper

def _received_bdt(**date_filters):
    """BDT received from buyers: direct payments + LC receipts (what the bank credited)."""
    direct = Payment.objects.filter(payment_type='receivable', status='completed', **date_filters).aggregate(
        total=Sum('amount'))['total'] or Decimal('0')
    via_lc = LCPayment.objects.filter(**date_filters).aggregate(total=Sum('amount_bdt'))['total'] or Decimal('0')
    return direct + via_lc

def _order_form_class():
    return ProjectForm if settings.MERCHANDISING_ENABLED else OrderForm

def _save_order(form):
    """Save an Order from either form, keeping unit price and total value in step."""
    order = form.save(commit=False)
    if isinstance(form, OrderForm):
        order.unit_price = (order.total_value / order.order_quantity).quantize(Decimal('0.01'))
    else:
        order.total_value = order.unit_price * order.order_quantity
    order.save()
    order.calculate_profit()
    return order

@is_superuser
def accounts_dashboard(request):
    """Accounts Dashboard Overview"""
    context = {
        'active': 'accounts',
        'page_title': 'Accounts Dashboard',
    }

    # Financial Summary
    context['total_buyers'] = Buyer.objects.filter(is_active=True).count()
    context['total_suppliers'] = Supplier.objects.filter(is_active=True).count()
    open_orders = Project.objects.filter(is_active=True).exclude(status__in=['delivered', 'cancelled'])
    context['total_projects'] = open_orders.count()

    today = date.today()

    # Money received this month, BDT - direct payments and LC receipts alike
    context['monthly_sales'] = _received_bdt(
        payment_date__month=today.month, payment_date__year=today.year,
    )

    # Receivable, USD: per order, order value - what the buyer paid against it
    context['receivables'] = sum(
        (order.receivable_usd for order in Project.objects.filter(is_active=True).exclude(status='cancelled')),
        Decimal('0'),
    )
    context['orders_due'] = open_orders.filter(delivery_date__lte=today + timedelta(days=30)).count()

    # Loans against LCs still owed
    context['loans_outstanding'] = sum(
        (loan.outstanding for loan in LCLoan.objects.all()), Decimal('0')
    )
    context['open_loans'] = sum(1 for loan in LCLoan.objects.all() if not loan.is_settled)

    # Cash book balance (cash in hand + bank)
    context['cash_balance'] = CashBookEntry.balance()
    context['cash_in_hand'] = CashBookEntry.balance(mode='cash')
    context['bank_balance'] = CashBookEntry.balance(mode='bank')

    pending_vouchers = CostVoucher.objects.filter(status='pending')
    context['pending_vouchers'] = pending_vouchers.count()
    context['pending_vouchers_amount'] = pending_vouchers.aggregate(total=Sum('amount'))['total'] or 0

    # Recent Activity
    context['recent_orders'] = Project.objects.select_related('buyer').order_by('-created_at')[:5]
    context['recent_payments'] = Payment.objects.select_related('buyer', 'supplier').order_by('-created_at')[:5]

    # Chart Data - money received per month, last 6 months
    monthly_sales_data = []
    months = []
    for i in range(5, -1, -1):
        month = today.month - i
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        total = _received_bdt(payment_date__month=month, payment_date__year=year)
        monthly_sales_data.append(float(total))
        months.append(date(year, month, 1).strftime('%B'))

    context['monthly_sales_data'] = monthly_sales_data
    context['months'] = months

    return render(request, 'accounts/dashboard.html', context)

# ------------------------------------------------------------------- buyers

@is_superuser
def buyers_list(request):
    """List all buyers"""
    buyers = Buyer.objects.filter(is_active=True)

    search = request.GET.get('search')
    if search:
        buyers = buyers.filter(
            Q(buyer_name__icontains=search) |
            Q(buyer_code__icontains=search) |
            Q(country__icontains=search)
        )

    context = {
        'active': 'accounts',
        'page_title': 'Buyers',
        'buyers': buyers,
        'search': search,
    }
    return render(request, 'accounts/buyers_list.html', context)

@is_superuser
def add_buyer(request):
    """Add new buyer"""
    if request.method == 'POST':
        form = BuyerForm(request.POST)
        if form.is_valid():
            buyer = form.save()
            messages.success(request, f'Buyer "{buyer.buyer_name}" added successfully!')
            return redirect('accounts:buyers_list')
    else:
        form = BuyerForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Buyer',
        'form': form,
    }
    return render(request, 'accounts/buyer_form.html', context)

@is_superuser
def edit_buyer(request, pk):
    """Edit buyer"""
    buyer = get_object_or_404(Buyer, pk=pk)
    if request.method == 'POST':
        form = BuyerForm(request.POST, instance=buyer)
        if form.is_valid():
            form.save()
            messages.success(request, f'Buyer "{buyer.buyer_name}" updated successfully!')
            return redirect('accounts:buyers_list')
    else:
        form = BuyerForm(instance=buyer)

    context = {
        'active': 'accounts',
        'page_title': 'Edit Buyer',
        'form': form,
        'buyer': buyer,
    }
    return render(request, 'accounts/buyer_form.html', context)

# ---------------------------------------------------------------- suppliers

@is_superuser
def suppliers_list(request):
    """List all suppliers"""
    suppliers = Supplier.objects.filter(is_active=True)

    search = request.GET.get('search')
    if search:
        suppliers = suppliers.filter(
            Q(supplier_name__icontains=search) |
            Q(supplier_code__icontains=search)
        )

    context = {
        'active': 'accounts',
        'page_title': 'Suppliers',
        'suppliers': suppliers,
        'search': search,
    }
    return render(request, 'accounts/suppliers_list.html', context)

@is_superuser
def add_supplier(request):
    """Add new supplier"""
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f'Supplier "{supplier.supplier_name}" added successfully!')
            return redirect('accounts:suppliers_list')
    else:
        form = SupplierForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Supplier',
        'form': form,
    }
    return render(request, 'accounts/supplier_form.html', context)

@is_superuser
def edit_supplier(request, pk):
    """Edit supplier"""
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f'Supplier "{supplier.supplier_name}" updated successfully!')
            return redirect('accounts:suppliers_list')
    else:
        form = SupplierForm(instance=supplier)

    context = {
        'active': 'accounts',
        'page_title': 'Edit Supplier',
        'form': form,
        'supplier': supplier,
    }
    return render(request, 'accounts/supplier_form.html', context)

# ----------------------------------------------------------------- projects

@is_superuser
def projects_list(request):
    """List all projects"""
    projects = Project.objects.select_related('buyer').all()

    status = request.GET.get('status')
    if status:
        projects = projects.filter(status=status)

    buyer = request.GET.get('buyer')
    if buyer:
        projects = projects.filter(buyer_id=buyer)

    context = {
        'active': 'accounts',
        'page_title': 'Orders',
        'projects': projects,
        'statuses': Project.STATUS_CHOICES,
        'buyers': Buyer.objects.filter(is_active=True),
        'current_status': status,
        'current_buyer': buyer,
    }
    return render(request, 'accounts/projects_list.html', context)

@is_superuser
def add_project(request):
    """Add new order"""
    form_class = _order_form_class()
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            project = _save_order(form)
            messages.success(request, f'Order "{project.project_number}" created successfully!')
            return redirect('accounts:projects_list')
    else:
        form = form_class()

    context = {
        'active': 'accounts',
        'page_title': 'Add Order',
        'form': form,
    }
    template = 'accounts/project_form.html' if form_class is ProjectForm else 'accounts/order_form.html'
    return render(request, template, context)

@is_superuser
def edit_project(request, pk):
    """Edit order"""
    project = get_object_or_404(Project, pk=pk)
    form_class = _order_form_class()
    if request.method == 'POST':
        form = form_class(request.POST, instance=project)
        if form.is_valid():
            project = _save_order(form)
            messages.success(request, f'Order "{project.project_number}" updated successfully!')
            return redirect('accounts:projects_list')
    else:
        form = form_class(instance=project)

    context = {
        'active': 'accounts',
        'page_title': 'Edit Order',
        'form': form,
        'project': project,
    }
    template = 'accounts/project_form.html' if form_class is ProjectForm else 'accounts/order_form.html'
    return render(request, template, context)

@is_superuser
def project_detail(request, pk):
    """Project financial summary - PDF Section 10"""
    project = get_object_or_404(Project, pk=pk)

    context = {
        'active': 'accounts',
        'page_title': f'Order - {project.project_number}',
        'project': project,
        'letters_of_credit': project.letters_of_credit.all(),
        'purchase_orders': project.purchase_orders.all(),
        'costs': project.costs.select_related('purchase_order').all(),
        'invoices': project.invoices.all(),
    }
    return render(request, 'accounts/project_detail.html', context)

# ---------------------------------------------------------------- invoices

@is_superuser
def invoices_list(request):
    """List all invoices"""
    invoices = SalesInvoice.objects.select_related('buyer', 'style').all()

    status = request.GET.get('status')
    if status:
        invoices = invoices.filter(status=status)

    buyer = request.GET.get('buyer')
    if buyer:
        invoices = invoices.filter(buyer_id=buyer)

    context = {
        'active': 'accounts',
        'page_title': 'Sales Invoices',
        'invoices': invoices,
        'statuses': SalesInvoice.STATUS_CHOICES,
        'buyers': Buyer.objects.filter(is_active=True),
        'current_status': status,
        'current_buyer': buyer,
    }
    return render(request, 'accounts/invoices_list.html', context)

@is_superuser
def add_invoice(request):
    """Add new invoice"""
    if request.method == 'POST':
        form = SalesInvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()

            messages.success(request, f'Invoice "{invoice.invoice_number}" created successfully!')
            return redirect('accounts:invoice_detail', pk=invoice.pk)
    else:
        form = SalesInvoiceForm()

    context = {
        'active': 'accounts',
        'page_title': 'Create Invoice',
        'form': form,
    }
    return render(request, 'accounts/invoice_form.html', context)

@is_superuser
def invoice_detail(request, pk):
    """View invoice details"""
    invoice = get_object_or_404(SalesInvoice, pk=pk)

    context = {
        'active': 'accounts',
        'page_title': f'Invoice - {invoice.invoice_number}',
        'invoice': invoice,
        'balance': invoice.get_balance(),
    }
    return render(request, 'accounts/invoice_detail.html', context)

# ---------------------------------------------------------------- payments

@is_superuser
def payments_list(request):
    """
    Every payment received in one place: buyer payments made directly
    (advance, TT, cash...) and money received under an LC.
    """
    source = request.GET.get('source', '')
    buyer_id = request.GET.get('buyer', '')
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')

    direct = Payment.objects.select_related('buyer', 'supplier', 'project')
    if not settings.MERCHANDISING_ENABLED:
        direct = direct.filter(payment_type='receivable')
    lc_receipts = LCPayment.objects.select_related('lc', 'lc__project', 'lc__project__buyer')
    if buyer_id:
        direct = direct.filter(buyer_id=buyer_id)
        lc_receipts = lc_receipts.filter(lc__project__buyer_id=buyer_id)
    if date_from:
        direct = direct.filter(payment_date__gte=date_from)
        lc_receipts = lc_receipts.filter(payment_date__gte=date_from)
    if date_to:
        direct = direct.filter(payment_date__lte=date_to)
        lc_receipts = lc_receipts.filter(payment_date__lte=date_to)

    rows = []
    if source in ('', 'direct'):
        for p in direct:
            rows.append({
                'date': p.payment_date, 'created': p.created_at, 'number': p.payment_number, 'source': 'direct',
                'payment_type': p.payment_type,
                'party': (p.buyer.buyer_name if p.buyer else '-') if p.payment_type == 'receivable'
                         else (p.supplier.supplier_name if p.supplier else '-'),
                'order': p.project, 'via': p.get_payment_method_display(), 'bdt': p.amount,
                'usd': p.amount_usd, 'rate': None,
                'reference': p.reference_number, 'notes': p.notes, 'lc': None,
            })
    if source in ('', 'lc'):
        for r in lc_receipts:
            rows.append({
                'date': r.payment_date, 'created': r.created_at, 'number': r.receipt_number, 'source': 'lc',
                'payment_type': 'receivable', 'party': r.lc.project.buyer.buyer_name, 'order': r.lc.project,
                'via': f"LC {r.lc.lc_number}", 'bdt': r.amount_bdt, 'usd': r.amount, 'rate': r.exchange_rate,
                'reference': r.reference,
                'notes': r.remarks, 'lc': r.lc,
            })
    rows.sort(key=lambda row: (row['date'], row['created']), reverse=True)

    received = [row for row in rows if row['payment_type'] == 'receivable']
    context = {
        'active': 'accounts',
        'page_title': 'Payments',
        'rows': rows,
        'total_received': sum((row['bdt'] or 0 for row in received), Decimal('0')),
        'total_direct': sum((row['bdt'] or 0 for row in received if row['source'] == 'direct'), Decimal('0')),
        'total_lc': sum((row['bdt'] or 0 for row in received if row['source'] == 'lc'), Decimal('0')),
        'total_lc_usd': sum((row['usd'] or 0 for row in received if row['source'] == 'lc'), Decimal('0')),
        'buyers': Buyer.objects.filter(is_active=True),
        'current_source': source,
        'current_buyer': buyer_id,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'accounts/payments_list.html', context)

@is_superuser
def add_lc_receipt(request):
    """Record money received under an LC, picking the LC on the form."""
    if request.method == 'POST':
        form = LCReceiptForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                receipt = services.record_lc_receipt(form.save(commit=False), user=request.user)
            messages.success(request, f'{receipt.receipt_number}: received {receipt.amount} under LC "{receipt.lc.lc_number}" - added to the cash book.')
            return redirect(f"{reverse('accounts:payments_list')}?source=lc")
    else:
        form = LCReceiptForm(initial={'lc': request.GET.get('lc'), 'exchange_rate': services.last_exchange_rate()})

    context = {
        'active': 'accounts',
        'page_title': 'Record LC Payment',
        'form': form,
    }
    return render(request, 'accounts/lc_receipt_form.html', context)

@is_superuser
def add_payment(request):
    """Add new payment"""
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.created_by = request.user
                payment.save()

                # Process the payment and post it to the cash book
                payment.process_payment()
                services.record_payment(payment, user=request.user)

            messages.success(request, f'Payment "{payment.payment_number}" processed successfully!')
            return redirect('accounts:payments_list')
    else:
        form = PaymentForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Payment',
        'form': form,
    }
    return render(request, 'accounts/payment_form.html', context)

# ------------------------------------------------------------ letters of credit

@is_superuser
def lc_list(request):
    """List all letters of credit"""
    lcs = LetterOfCredit.objects.select_related('project').all()

    status = request.GET.get('status')
    if status:
        lcs = lcs.filter(status=status)

    context = {
        'active': 'accounts',
        'page_title': 'Letters of Credit',
        'lcs': lcs,
        'statuses': LetterOfCredit.STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'accounts/lc_list.html', context)

@is_superuser
def add_lc(request):
    """Add new letter of credit"""
    if request.method == 'POST':
        form = LetterOfCreditForm(request.POST)
        if form.is_valid():
            lc = form.save(commit=False)
            lc.created_by = request.user
            lc.save()
            messages.success(request, f'Letter of Credit "{lc.lc_number}" created successfully!')
            return redirect('accounts:lc_detail', pk=lc.pk)
    else:
        form = LetterOfCreditForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Letter of Credit',
        'form': form,
    }
    return render(request, 'accounts/lc_form.html', context)

@is_superuser
def lc_detail(request, pk):
    """LC details: money received, loans taken against it and their repayments."""
    lc = get_object_or_404(LetterOfCredit.objects.select_related('project', 'project__buyer'), pk=pk)
    loans = lc.lc_loans.prefetch_related('repayments')

    context = {
        'active': 'accounts',
        'page_title': f'LC - {lc.lc_number}',
        'lc': lc,
        'payments': lc.lc_payments.all(),
        'loans': loans,
        'loans_outstanding': sum((loan.outstanding for loan in loans), Decimal('0')),
        'complete_form': LCCompleteForm(initial={
            'realized_amount': max(lc.lc_outstanding, Decimal('0')),
            'exchange_rate': services.last_exchange_rate(),
            'bank_name': lc.bank_name,
        }),
    }
    return render(request, 'accounts/lc_detail.html', context)

@is_superuser
def add_lc_payment(request, pk):
    """Record money received under an LC (a part payment) - goes into the cash book."""
    lc = get_object_or_404(LetterOfCredit, pk=pk)
    if request.method == 'POST':
        form = LCPaymentForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.lc = lc
                services.record_lc_receipt(payment, user=request.user)
            messages.success(request, f'Received {payment.amount} under "{lc.lc_number}" - added to the cash book.')
            return redirect('accounts:lc_detail', pk=lc.pk)
    else:
        form = LCPaymentForm(initial={'payment_date': date.today(), 'bank_name': lc.bank_name,
                                      'exchange_rate': services.last_exchange_rate()})

    context = {
        'active': 'accounts',
        'page_title': f'Add Payment - {lc.lc_number}',
        'form': form,
        'lc': lc,
    }
    return render(request, 'accounts/lc_payment_form.html', context)

@is_superuser
def add_lc_loan(request, pk):
    """Take a loan against an LC - the amount goes into the cash book (bank)."""
    lc = get_object_or_404(LetterOfCredit, pk=pk)
    if not lc.is_open:
        messages.error(request, f'LC "{lc.lc_number}" is {lc.get_status_display().lower()} - loans can only be taken against an active LC.')
        return redirect('accounts:lc_detail', pk=lc.pk)
    if request.method == 'POST':
        form = LCLoanForm(request.POST)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.lc = lc
            try:
                services.take_loan(loan, user=request.user)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Loan of {loan.loan_amount} taken against "{lc.lc_number}" - added to the cash book.')
            return redirect('accounts:lc_detail', pk=lc.pk)
    else:
        form = LCLoanForm(initial={'loan_date': date.today(), 'bank_name': lc.bank_name})

    context = {
        'active': 'accounts',
        'page_title': f'Take Loan - {lc.lc_number}',
        'form': form,
        'lc': lc,
    }
    return render(request, 'accounts/lc_loan_form.html', context)

@is_superuser
def repay_lc_loan(request, pk):
    """Pay an instalment on an LC loan - goes out of the cash book."""
    loan = get_object_or_404(LCLoan.objects.select_related('lc'), pk=pk)
    if loan.is_settled:
        messages.info(request, "This loan is already fully paid.")
        return redirect('accounts:lc_detail', pk=loan.lc_id)
    if request.method == 'POST':
        form = LCLoanRepaymentForm(request.POST, loan=loan)
        if form.is_valid():
            data = form.cleaned_data
            try:
                services.repay_loan(
                    loan, data['amount'], repayment_date=data['repayment_date'], mode=data['mode'],
                    bank_name=data['bank_name'] if data['mode'] == 'bank' else '',
                    reference=data['reference'], remarks=data['remarks'], user=request.user,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Repaid {data["amount"]} on the loan against "{loan.lc.lc_number}".')
                return redirect('accounts:lc_detail', pk=loan.lc_id)
    else:
        form = LCLoanRepaymentForm(loan=loan, initial={'repayment_date': date.today()})

    context = {
        'active': 'accounts',
        'page_title': f'Repay Loan - {loan.lc.lc_number}',
        'form': form,
        'loan': loan,
        'lc': loan.lc,
    }
    return render(request, 'accounts/lc_loan_repayment_form.html', context)

@is_superuser
@require_POST
def complete_lc(request, pk):
    """
    Complete an LC: record the money realised. Whatever is still owed on its
    loans is adjusted from that first; the rest goes into the cash book.
    """
    lc = get_object_or_404(LetterOfCredit, pk=pk)
    form = LCCompleteForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            messages.error(request, f"{form[field].label if field != '__all__' else ''}: {' '.join(errors)}")
        return redirect('accounts:lc_detail', pk=lc.pk)
    data = form.cleaned_data
    try:
        adjusted, net = services.complete_lc(
            lc, data['realized_amount'], data['exchange_rate'], realized_bdt=data['realized_bdt'],
            completion_date=data['completion_date'], bank_name=data['bank_name'],
            reference=data['reference'], user=request.user,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        msg = f'LC "{lc.lc_number}" completed. Realised USD {lc.realized_amount:,.2f} = BDT {lc.realized_bdt:,.2f}'
        if adjusted:
            msg += f', of which BDT {adjusted:,.2f} paid off its loan(s)'
        messages.success(request, msg + f'; BDT {net:,.2f} added to the cash book.')
        if lc.loans_outstanding > 0:
            messages.warning(request, f'BDT {lc.loans_outstanding:,.2f} is still owed on its loan(s) - repay it from the LC page.')
    return redirect('accounts:lc_detail', pk=lc.pk)

# -------------------------------------------------------------------- costs

@is_superuser
def costs_list(request):
    """
    All costs - every one already paid. Order costs and overall costs are
    entered separately (add_cost / add_overall_cost) and can be viewed
    together or apart.
    """
    costs = Cost.objects.select_related('project', 'project__buyer', 'supplier', 'purchase_order').all()

    scope = request.GET.get('scope', '')
    if scope == 'order':
        costs = costs.filter(project__isnull=False)
    elif scope == 'overall':
        costs = costs.filter(project__isnull=True)

    project = request.GET.get('project')
    if project:
        costs = costs.filter(project_id=project)

    cost_type = request.GET.get('cost_type')
    if cost_type:
        costs = costs.filter(cost_type=cost_type)

    supplier = request.GET.get('supplier')
    if supplier:
        costs = costs.filter(supplier_id=supplier)

    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    if date_from:
        costs = costs.filter(cost_date__gte=date_from)
    if date_to:
        costs = costs.filter(cost_date__lte=date_to)

    context = {
        'active': 'accounts',
        'page_title': 'Costs',
        'suppliers': Supplier.objects.filter(is_active=True),
        'current_supplier': supplier,
        'date_from': date_from,
        'date_to': date_to,
        'costs': costs,
        'total': costs.aggregate(total=Sum('amount'))['total'] or 0,
        'projects': Project.objects.filter(is_active=True),
        'cost_types': Cost.COST_TYPES,
        'current_scope': scope,
        'current_project': project,
        'current_cost_type': cost_type,
    }
    return render(request, 'accounts/costs_list.html', context)

def _add_cost(request, form_class, title, kind):
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            cost = services.record_cost(form.save(commit=False), user=request.user)
            target = f'Order "{cost.project.project_number}"' if cost.project_id else 'overall costs'
            messages.success(request, f'{cost.amount} {cost.get_cost_type_display()} recorded against {target} and paid from the cash book.')
            return redirect(f"{reverse('accounts:costs_list')}?scope={kind}")
    else:
        initial = {}
        if kind == 'order' and request.GET.get('order'):
            initial['project'] = request.GET['order']
        form = form_class(initial=initial)

    context = {
        'active': 'accounts',
        'page_title': title,
        'form': form,
        'kind': kind,
    }
    return render(request, 'accounts/cost_form.html', context)

@is_superuser
def add_cost(request):
    """Order cost - a cost against one order."""
    return _add_cost(request, OrderCostForm, 'Add Order Cost', 'order')

@is_superuser
def add_overall_cost(request):
    """Overall cost - a running cost of the business, not tied to an order."""
    return _add_cost(request, OverallCostForm, 'Add Overall Cost', 'overall')

# ------------------------------------------------------------------ vouchers

@login_required
def voucher_list(request):
    """Admins see every voucher (and approve them here); everyone else sees their own."""
    vouchers = CostVoucher.objects.select_related('project', 'supplier', 'requested_by', 'approved_by')
    if not request.user.is_superuser:
        vouchers = vouchers.filter(requested_by=request.user)

    status = request.GET.get('status', 'pending' if request.user.is_superuser else '')
    if status:
        vouchers = vouchers.filter(status=status)

    context = {
        'active': 'accounts' if request.user.is_superuser else 'vouchers',
        'page_title': 'Expense Vouchers',
        'vouchers': vouchers,
        'statuses': CostVoucher.STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'accounts/voucher_list.html', context)

@login_required
def add_voucher(request):
    """Anyone can raise a voucher; it becomes a cost once an admin approves it."""
    if request.method == 'POST':
        form = CostVoucherForm(request.POST)
        if form.is_valid():
            voucher = form.save(commit=False)
            voucher.requested_by = request.user
            if voucher.paid_by == 'cash':
                voucher.bank_name = ''
            voucher.save()
            messages.success(request, f'Voucher {voucher.voucher_number} for {voucher.amount} sent for approval. Use the print button to print it for signatures.')
            return redirect('accounts:voucher_list')
    else:
        form = CostVoucherForm()

    context = {
        'active': 'accounts' if request.user.is_superuser else 'vouchers',
        'page_title': 'New Expense Voucher',
        'form': form,
    }
    return render(request, 'accounts/voucher_form.html', context)

@login_required
def print_voucher(request, pk):
    """The voucher as a printable debit voucher (A5 landscape), for signatures."""
    voucher = get_object_or_404(
        CostVoucher.objects.select_related('project', 'project__buyer', 'supplier', 'requested_by', 'approved_by'),
        pk=pk,
    )
    if not request.user.is_superuser and voucher.requested_by_id != request.user.pk:
        raise Http404
    requester = voucher.requested_by
    requester_name = (requester.get_full_name() or requester.username) if requester else ''
    head = voucher.get_cost_type_display()
    if voucher.project:
        head += f" - Order {voucher.project.project_number}"
        if voucher.project.buyer_ref:
            head += f" ({voucher.project.buyer_ref})"
    particulars = []
    if voucher.remarks:
        particulars.append(voucher.remarks)
    if voucher.paid_by == 'bank':
        particulars.append(f"Paid by bank{' - ' + voucher.bank_name if voucher.bank_name else ''}")
    context = {
        'voucher': voucher,
        'head_of_account': head,
        'pay_to': voucher.supplier.supplier_name if voucher.supplier else requester_name,
        'particulars': (particulars + ['', '', ''])[:3],
        'amount': format_taka(voucher.amount),
    }
    # The form has two ruled lines for the amount in words; break at a word.
    words = taka_in_words(voucher.amount)
    first, rest = words, ''
    if len(words) > 60:
        cut = words.rfind(' ', 0, 60)
        first, rest = words[:cut], words[cut + 1:]
    context['words_line_1'], context['words_line_2'] = first, rest
    return render(request, 'accounts/voucher_print.html', context)

def _back(request, fallback):
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(fallback)

@is_superuser
@require_POST
def approve_voucher(request, pk):
    voucher = get_object_or_404(CostVoucher, pk=pk)
    try:
        cost = services.approve_voucher(voucher, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Voucher {voucher.voucher_number} approved - {cost.amount} recorded as a cost and paid from the cash book.')
    return _back(request, 'accounts:voucher_list')

@is_superuser
@require_POST
def reject_voucher(request, pk):
    voucher = get_object_or_404(CostVoucher, pk=pk)
    try:
        services.reject_voucher(voucher, request.user, request.POST.get('reason', '').strip())
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Voucher {voucher.voucher_number} rejected.')
    return _back(request, 'accounts:voucher_list')

# ----------------------------------------------------------------- cash book

@is_superuser
def cashbook(request):
    """
    The cash book: every money movement, newest first, with a running
    balance. Filter by Cash / Bank and by date range.
    """
    entries = CashBookEntry.objects.select_related('created_by')
    mode = request.GET.get('mode', '')
    if mode in ('cash', 'bank'):
        entries = entries.filter(mode=mode)
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')

    # Running balance over the (mode-filtered) book, oldest first.
    ordered = list(entries.order_by('entry_date', 'created_at'))
    balance = Decimal('0')
    for entry in ordered:
        balance += entry.signed_amount
        entry.balance_after = balance
    opening = Decimal('0')
    if date_from:
        opening = sum((e.signed_amount for e in ordered if str(e.entry_date) < date_from), Decimal('0'))
        ordered = [e for e in ordered if str(e.entry_date) >= date_from]
    if date_to:
        ordered = [e for e in ordered if str(e.entry_date) <= date_to]
    ordered.reverse()

    context = {
        'active': 'accounts',
        'page_title': 'Cash Book',
        'entries': ordered,
        'opening': opening,
        'money_in': sum((e.amount for e in ordered if e.direction == 'in'), Decimal('0')),
        'money_out': sum((e.amount for e in ordered if e.direction == 'out'), Decimal('0')),
        'cash_in_hand': CashBookEntry.balance(mode='cash'),
        'bank_balance': CashBookEntry.balance(mode='bank'),
        'total_balance': CashBookEntry.balance(),
        'current_mode': mode,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'accounts/cashbook.html', context)

@is_superuser
def add_cashbook_entry(request):
    """Manual cash book line (opening balance, other income/outgoings, cash <-> bank)."""
    if request.method == 'POST':
        form = CashBookEntryForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            entry_type = data['entry_type']
            if entry_type in ('to_bank', 'to_cash'):
                services.transfer_between_cash_and_bank(
                    data['amount'], 'bank' if entry_type == 'to_bank' else 'cash',
                    entry_date=data['entry_date'], bank_name=data['bank_name'],
                    reference=data['reference'], notes=data['description'], user=request.user,
                )
            else:
                services.post_cashbook(
                    entry_type, data['amount'], data['description'], entry_date=data['entry_date'],
                    mode=data['mode'], bank_name=data['bank_name'], reference=data['reference'],
                    user=request.user,
                )
            messages.success(request, "Cash book updated.")
            return redirect('accounts:cashbook')
    else:
        form = CashBookEntryForm()

    context = {
        'active': 'accounts',
        'page_title': 'Cash Book Entry',
        'form': form,
    }
    return render(request, 'accounts/cashbook_entry_form.html', context)

# ----------------------------------------------------------- purchase orders

@is_superuser
def purchase_orders_list(request):
    """List all purchase orders"""
    orders = PurchaseOrder.objects.select_related('supplier', 'style').all()

    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)

    context = {
        'active': 'accounts',
        'page_title': 'Purchase Orders',
        'orders': orders,
        'statuses': PurchaseOrder.STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'accounts/purchase_orders_list.html', context)

@is_superuser
def add_purchase_order(request):
    """Add new purchase order"""
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            po.calculate_net_amount()
            messages.success(request, f'Purchase Order "{po.po_number}" created successfully!')
            return redirect('accounts:purchase_order_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Purchase Order',
        'form': form,
    }
    return render(request, 'accounts/purchase_order_form.html', context)

@is_superuser
def edit_purchase_order(request, pk):
    """Edit purchase order"""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=po)
        if form.is_valid():
            po = form.save()
            po.calculate_net_amount()
            messages.success(request, f'Purchase Order "{po.po_number}" updated successfully!')
            return redirect('accounts:purchase_order_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm(instance=po)

    context = {
        'active': 'accounts',
        'page_title': 'Edit Purchase Order',
        'form': form,
        'po': po,
    }
    return render(request, 'accounts/purchase_order_form.html', context)

@is_superuser
def purchase_order_detail(request, pk):
    """View purchase order details - items and linked costs"""
    po = get_object_or_404(PurchaseOrder, pk=pk)

    context = {
        'active': 'accounts',
        'page_title': f'PO - {po.po_number}',
        'po': po,
        'items': po.items.all(),
        'costs': po.costs.all(),
    }
    return render(request, 'accounts/purchase_order_detail.html', context)

# ---------------------------------------------------------------- cost sheets

@is_superuser
def cost_sheets(request):
    """List all cost sheets"""
    cost_sheets = CostSheet.objects.select_related('style', 'created_by').all()

    style = request.GET.get('style')
    if style:
        cost_sheets = cost_sheets.filter(style_id=style)

    context = {
        'active': 'accounts',
        'page_title': 'Cost Sheets',
        'cost_sheets': cost_sheets,
        'styles': Project.objects.filter(is_active=True),
        'current_style': style,
    }
    return render(request, 'accounts/cost_sheets.html', context)

@is_superuser
def add_cost_sheet(request):
    """Add new cost sheet"""
    if request.method == 'POST':
        form = CostSheetForm(request.POST)
        if form.is_valid():
            cost_sheet = form.save(commit=False)
            cost_sheet.created_by = request.user
            cost_sheet.save()
            cost_sheet.calculate_totals()

            messages.success(request, f'Cost sheet for "{cost_sheet.style.project_number}" created successfully!')
            return redirect('accounts:cost_sheets')
    else:
        form = CostSheetForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Cost Sheet',
        'form': form,
    }
    return render(request, 'accounts/cost_sheet_form.html', context)

@is_superuser
def edit_cost_sheet(request, pk):
    """Edit cost sheet"""
    cost_sheet = get_object_or_404(CostSheet, pk=pk)
    if request.method == 'POST':
        form = CostSheetForm(request.POST, instance=cost_sheet)
        if form.is_valid():
            cost_sheet = form.save()
            cost_sheet.calculate_totals()
            messages.success(request, f'Cost sheet for "{cost_sheet.style.project_number}" updated successfully!')
            return redirect('accounts:cost_sheets')
    else:
        form = CostSheetForm(instance=cost_sheet)

    context = {
        'active': 'accounts',
        'page_title': 'Edit Cost Sheet',
        'form': form,
        'cost_sheet': cost_sheet,
    }
    return render(request, 'accounts/cost_sheet_form.html', context)

# -------------------------------------------------------------------- banks

@is_superuser
@bank_book_hidden
def banks_list(request):
    """List all bank accounts"""
    banks = BankAccount.objects.filter(is_active=True)

    context = {
        'active': 'accounts',
        'page_title': 'Bank Accounts',
        'banks': banks,
    }
    return render(request, 'accounts/banks_list.html', context)

@is_superuser
@bank_book_hidden
def add_bank(request):
    """Add new bank account"""
    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid():
            bank = form.save()
            messages.success(request, f'Bank account "{bank.account_name}" added successfully!')
            return redirect('accounts:banks_list')
    else:
        form = BankAccountForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Bank Account',
        'form': form,
    }
    return render(request, 'accounts/bank_form.html', context)

@is_superuser
@bank_book_hidden
def edit_bank(request, pk):
    """Edit bank account"""
    bank = get_object_or_404(BankAccount, pk=pk)
    if request.method == 'POST':
        form = BankAccountForm(request.POST, instance=bank)
        if form.is_valid():
            form.save()
            messages.success(request, f'Bank account "{bank.account_name}" updated successfully!')
            return redirect('accounts:banks_list')
    else:
        form = BankAccountForm(instance=bank)

    context = {
        'active': 'accounts',
        'page_title': 'Edit Bank Account',
        'form': form,
        'bank': bank,
    }
    return render(request, 'accounts/bank_form.html', context)

@is_superuser
@bank_book_hidden
def bank_transactions_list(request):
    """List all bank transactions"""
    transactions = BankTransaction.objects.select_related('bank_account').all()

    bank = request.GET.get('bank')
    if bank:
        transactions = transactions.filter(bank_account_id=bank)

    context = {
        'active': 'accounts',
        'page_title': 'Bank Transactions',
        'transactions': transactions,
        'banks': BankAccount.objects.filter(is_active=True),
        'current_bank': bank,
    }
    return render(request, 'accounts/bank_transactions_list.html', context)

@is_superuser
@bank_book_hidden
def add_bank_transaction(request):
    """Add new bank transaction"""
    if request.method == 'POST':
        form = BankTransactionForm(request.POST)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.created_by = request.user
            txn.save()
            txn.process_transaction()
            messages.success(request, f'Transaction of {txn.amount} recorded successfully!')
            return redirect('accounts:bank_transactions_list')
    else:
        form = BankTransactionForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Bank Transaction',
        'form': form,
    }
    return render(request, 'accounts/bank_transaction_form.html', context)

# ------------------------------------------------------------------ reports

@is_superuser
def financial_reports(request):
    """
    Money in BDT (received, costs, loans, cash) kept apart from the USD side
    (order value, LCs, receivables) - the two are never added together.
    """
    today = date.today()
    this_month = {'payment_date__month': today.month, 'payment_date__year': today.year}

    order_costs = Cost.objects.filter(project__isnull=False)
    overall_costs = Cost.objects.filter(project__isnull=True)
    month_costs = {'cost_date__month': today.month, 'cost_date__year': today.year}
    loans = LCLoan.objects.aggregate(
        amount=Sum('loan_amount'), repaid=Sum('repaid_amount'), interest=Sum('interest'), other=Sum('other_charges'))
    loan_charges = (loans['interest'] or Decimal('0')) + (loans['other'] or Decimal('0'))

    def total(qs):
        return qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # ---- BDT
    month_received = _received_bdt(**this_month)
    month_costs_total = total(Cost.objects.filter(**month_costs))
    all_received = _received_bdt()
    all_order_costs = total(order_costs)
    all_overall_costs = total(overall_costs)

    # ---- USD
    orders = Project.objects.filter(is_active=True).exclude(status='cancelled')
    lc_amount = LetterOfCredit.objects.aggregate(total=Sum('lc_amount'))['total'] or Decimal('0')
    lc_received = LCPayment.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    context = {
        'active': 'accounts',
        'page_title': 'Financial Reports',
        'month_label': today.strftime('%B %Y'),
        # this month, BDT
        'month_received': month_received,
        'month_order_costs': total(order_costs.filter(**month_costs)),
        'month_overall_costs': total(overall_costs.filter(**month_costs)),
        'month_costs': month_costs_total,
        'month_net': month_received - month_costs_total,
        # all time, BDT
        'all_received': all_received,
        'all_order_costs': all_order_costs,
        'all_overall_costs': all_overall_costs,
        'loan_charges': loan_charges,
        'all_net': all_received - all_order_costs - all_overall_costs - loan_charges,
        'loans_taken': loans['amount'] or Decimal('0'),
        'loans_outstanding': (loans['amount'] or 0) + loan_charges - (loans['repaid'] or 0),
        'cash_balance': CashBookEntry.balance(),
        # orders & LCs, USD
        'total_order_value': orders.aggregate(total=Sum('total_value'))['total'] or Decimal('0'),
        'total_receivable': sum((o.receivable_usd for o in orders), Decimal('0')),
        'total_lc_amount': lc_amount,
        'total_lc_received': lc_received,
        'total_lc_outstanding': lc_amount - lc_received,
        'direct_received_usd': Payment.objects.filter(payment_type='receivable', status='completed').aggregate(
            total=Sum('amount_usd'))['total'] or Decimal('0'),
    }
    return render(request, 'accounts/financial_reports.html', context)

