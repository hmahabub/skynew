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
    LetterOfCredit, LCPayment, LCLoan, Cost,
)
from .forms import (
    BuyerForm, SupplierForm, ProjectForm, PurchaseOrderForm,
    SalesInvoiceForm, PaymentForm,
    CostSheetForm, BankAccountForm, BankTransactionForm,
    LetterOfCreditForm, LCPaymentForm, LCLoanForm, CostForm,
)

# Accounts is superuser-only, module-wide - no separate approver role.
is_superuser = user_passes_test(lambda u: u.is_superuser)

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
    context['total_projects'] = Project.objects.filter(is_active=True).count()

    # Sales Summary
    current_month = date.today().month
    current_year = date.today().year

    monthly_sales = SalesInvoice.objects.filter(
        invoice_date__month=current_month,
        invoice_date__year=current_year,
        status='paid'
    ).aggregate(total=Sum('net_amount'))['total'] or 0
    context['monthly_sales'] = monthly_sales

    # Receivables
    receivables = SalesInvoice.objects.filter(
        status__in=['pending', 'partial', 'overdue']
    ).aggregate(total=Sum('net_amount') - Sum('paid_amount'))['total'] or 0
    context['receivables'] = receivables

    # Payables
    payables = PurchaseOrder.objects.filter(
        status__in=['approved', 'received']
    ).aggregate(total=Sum('net_amount') - Sum('advance_paid'))['total'] or 0
    context['payables'] = payables

    # Cash Balance
    context['cash_balance'] = BankAccount.objects.aggregate(
        total=Sum('current_balance')
    )['total'] or 0

    # Recent Transactions
    context['recent_invoices'] = SalesInvoice.objects.select_related('buyer').order_by('-created_at')[:5]
    context['recent_payments'] = Payment.objects.select_related('buyer', 'supplier').order_by('-created_at')[:5]

    # Chart Data - Monthly Sales
    monthly_sales_data = []
    months = []
    for i in range(5, -1, -1):
        month = date.today().month - i
        year = date.today().year
        if month <= 0:
            month += 12
            year -= 1
        total = SalesInvoice.objects.filter(
            invoice_date__month=month,
            invoice_date__year=year,
            status='paid'
        ).aggregate(total=Sum('net_amount'))['total'] or 0
        monthly_sales_data.append(float(total))
        months.append(date(year, month, 1).strftime('%B'))

    context['monthly_sales_data'] = monthly_sales_data
    context['months'] = months

    # Overdue Invoices
    overdue_invoices = SalesInvoice.objects.filter(
        status='overdue'
    ).count()
    context['overdue_invoices'] = overdue_invoices

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
        'page_title': 'Projects',
        'projects': projects,
        'statuses': Project.STATUS_CHOICES,
        'buyers': Buyer.objects.filter(is_active=True),
        'current_status': status,
        'current_buyer': buyer,
    }
    return render(request, 'accounts/projects_list.html', context)

@is_superuser
def add_project(request):
    """Add new project"""
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.total_value = project.unit_price * project.order_quantity
            project.save()
            project.calculate_profit()
            messages.success(request, f'Project "{project.project_number}" created successfully!')
            return redirect('accounts:projects_list')
    else:
        form = ProjectForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Project',
        'form': form,
    }
    return render(request, 'accounts/project_form.html', context)

@is_superuser
def edit_project(request, pk):
    """Edit project"""
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            project = form.save(commit=False)
            project.total_value = project.unit_price * project.order_quantity
            project.save()
            project.calculate_profit()
            messages.success(request, f'Project "{project.project_number}" updated successfully!')
            return redirect('accounts:projects_list')
    else:
        form = ProjectForm(instance=project)

    context = {
        'active': 'accounts',
        'page_title': 'Edit Project',
        'form': form,
        'project': project,
    }
    return render(request, 'accounts/project_form.html', context)

@is_superuser
def project_detail(request, pk):
    """Project financial summary - PDF Section 10"""
    project = get_object_or_404(Project, pk=pk)

    context = {
        'active': 'accounts',
        'page_title': f'Project - {project.project_number}',
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
    """List all payments"""
    payments = Payment.objects.select_related('buyer', 'supplier').all()

    payment_type = request.GET.get('type')
    if payment_type:
        payments = payments.filter(payment_type=payment_type)

    context = {
        'active': 'accounts',
        'page_title': 'Payments',
        'payments': payments,
        'payment_types': Payment.PAYMENT_TYPES,
        'current_type': payment_type,
    }
    return render(request, 'accounts/payments_list.html', context)

@is_superuser
def add_payment(request):
    """Add new payment"""
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.created_by = request.user
            payment.save()

            # Process the payment
            payment.process_payment()

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
    """View LC details - payments, loans, outstanding"""
    lc = get_object_or_404(LetterOfCredit, pk=pk)

    context = {
        'active': 'accounts',
        'page_title': f'LC - {lc.lc_number}',
        'lc': lc,
        'payments': lc.lc_payments.all(),
        'loans': lc.lc_loans.all(),
    }
    return render(request, 'accounts/lc_detail.html', context)

@is_superuser
def add_lc_payment(request, pk):
    """Record a payment against an LC"""
    lc = get_object_or_404(LetterOfCredit, pk=pk)
    if request.method == 'POST':
        form = LCPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.lc = lc
            payment.created_by = request.user
            payment.save()
            messages.success(request, f'Payment of {payment.amount} recorded against "{lc.lc_number}"!')
            return redirect('accounts:lc_detail', pk=lc.pk)
    else:
        form = LCPaymentForm()

    context = {
        'active': 'accounts',
        'page_title': f'Add Payment - {lc.lc_number}',
        'form': form,
        'lc': lc,
    }
    return render(request, 'accounts/lc_payment_form.html', context)

@is_superuser
def add_lc_loan(request, pk):
    """Record a loan against an LC"""
    lc = get_object_or_404(LetterOfCredit, pk=pk)
    if request.method == 'POST':
        form = LCLoanForm(request.POST)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.lc = lc
            loan.created_by = request.user
            loan.save()
            messages.success(request, f'Loan of {loan.loan_amount} recorded against "{lc.lc_number}"!')
            return redirect('accounts:lc_detail', pk=lc.pk)
    else:
        form = LCLoanForm()

    context = {
        'active': 'accounts',
        'page_title': f'Add Loan - {lc.lc_number}',
        'form': form,
        'lc': lc,
    }
    return render(request, 'accounts/lc_loan_form.html', context)

# -------------------------------------------------------------------- costs

@is_superuser
def costs_list(request):
    """List all actual costs (PO cost + other cost)"""
    costs = Cost.objects.select_related('project', 'purchase_order').all()

    project = request.GET.get('project')
    if project:
        costs = costs.filter(project_id=project)

    cost_type = request.GET.get('cost_type')
    if cost_type:
        costs = costs.filter(cost_type=cost_type)

    context = {
        'active': 'accounts',
        'page_title': 'Costs',
        'costs': costs,
        'projects': Project.objects.filter(is_active=True),
        'cost_types': Cost.COST_TYPES,
        'current_project': project,
        'current_cost_type': cost_type,
    }
    return render(request, 'accounts/costs_list.html', context)

@is_superuser
def add_cost(request):
    """Add new cost entry"""
    if request.method == 'POST':
        form = CostForm(request.POST)
        if form.is_valid():
            cost = form.save(commit=False)
            cost.created_by = request.user
            cost.save()
            messages.success(request, f'Cost entry for "{cost.project.project_number}" added successfully!')
            return redirect('accounts:costs_list')
    else:
        form = CostForm()

    context = {
        'active': 'accounts',
        'page_title': 'Add Cost',
        'form': form,
    }
    return render(request, 'accounts/cost_form.html', context)

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
    """Financial reports dashboard - direct aggregation, no GL"""
    context = {
        'active': 'accounts',
        'page_title': 'Financial Reports',
    }

    current_month = date.today().month
    current_year = date.today().year

    # Revenue
    total_revenue = SalesInvoice.objects.filter(
        status='paid',
        invoice_date__month=current_month,
        invoice_date__year=current_year
    ).aggregate(total=Sum('net_amount'))['total'] or 0

    # Cost of Goods Sold (estimated, from cost sheets)
    total_cogs = CostSheet.objects.filter(
        cost_date__month=current_month,
        cost_date__year=current_year
    ).aggregate(total=Sum('total_cost'))['total'] or 0

    gross_profit = total_revenue - total_cogs
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    context['total_revenue'] = total_revenue
    context['total_cogs'] = total_cogs
    context['gross_profit'] = gross_profit
    context['gross_margin'] = gross_margin

    # Company-wide rollup across all active projects (PDF Section 10, aggregated)
    projects = Project.objects.filter(is_active=True)

    context['total_order_value'] = projects.aggregate(total=Sum('total_value'))['total'] or Decimal('0')

    context['total_lc_amount'] = LetterOfCredit.objects.aggregate(total=Sum('lc_amount'))['total'] or Decimal('0')
    total_lc_paid = LCPayment.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    context['total_lc_paid'] = total_lc_paid
    context['total_lc_outstanding'] = context['total_lc_amount'] - total_lc_paid

    total_loan_amount = LCLoan.objects.aggregate(total=Sum('loan_amount'))['total'] or Decimal('0')
    total_loan_repaid = LCLoan.objects.aggregate(total=Sum('repaid_amount'))['total'] or Decimal('0')
    total_loan_interest = LCLoan.objects.aggregate(total=Sum('interest'))['total'] or Decimal('0')
    total_loan_other = LCLoan.objects.aggregate(total=Sum('other_charges'))['total'] or Decimal('0')
    context['total_loan_amount'] = total_loan_amount
    context['total_loan_repaid'] = total_loan_repaid
    context['total_loan_interest'] = total_loan_interest
    context['total_loan_outstanding'] = total_loan_amount + total_loan_interest + total_loan_other - total_loan_repaid

    total_po_cost = Cost.objects.filter(purchase_order__isnull=False).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_other_cost = Cost.objects.filter(purchase_order__isnull=True).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    context['total_po_cost'] = total_po_cost
    context['total_other_cost'] = total_other_cost

    total_costs = total_po_cost + total_other_cost + total_loan_interest
    context['total_costs'] = total_costs

    total_paid_invoices = SalesInvoice.objects.filter(status='paid').aggregate(total=Sum('net_amount'))['total'] or Decimal('0')
    context['total_revenue_all_time'] = total_paid_invoices

    context['overall_estimated_profit'] = context['total_order_value'] - total_costs

    return render(request, 'accounts/financial_reports.html', context)
