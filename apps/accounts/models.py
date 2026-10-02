import uuid

from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date, timedelta

def save_with_number(instance, field, code, *args, **kwargs):
    """
    Save `instance`, giving it an auto number in `field` on first save:
    YY + code + id padded to 5 digits (e.g. 26ORD00012). The id only exists
    after the first insert, so a temporary unique value is used until then.
    """
    if getattr(instance, field):
        return super(type(instance), instance).save(*args, **kwargs)
    setattr(instance, field, f"TMP-{uuid.uuid4().hex[:20]}")
    super(type(instance), instance).save(*args, **kwargs)
    number = f"{instance.created_at:%y}{code}{instance.pk:05d}"
    setattr(instance, field, number)
    type(instance).objects.filter(pk=instance.pk).update(**{field: number})


class Buyer(models.Model):
    buyer_code = models.CharField(max_length=20, unique=True)
    buyer_name = models.CharField(max_length=200)
    country = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit_days = models.IntegerField(default=30)
    outstanding_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.buyer_code} - {self.buyer_name}"

    def get_outstanding(self):
        """Calculate outstanding balance from invoices"""
        total_invoiced = self.sales_invoices.filter(
            status__in=['pending', 'partial']
        ).aggregate(total=models.Sum('amount'))['total'] or 0

        total_paid = self.sales_invoices.filter(
            status='paid'
        ).aggregate(total=models.Sum('paid_amount'))['total'] or 0

        self.outstanding_balance = total_invoiced - total_paid
        self.save()
        return self.outstanding_balance

class Supplier(models.Model):
    SUPPLIER_TYPES = [
        ('fabric', 'Fabric Supplier'),
        ('trim', 'Trim Supplier'),
        ('both', 'Both'),
        ('service', 'Service Provider'),
    ]

    supplier_code = models.CharField(max_length=20, unique=True)
    supplier_name = models.CharField(max_length=200)
    supplier_type = models.CharField(max_length=20, choices=SUPPLIER_TYPES)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    bank_name = models.CharField(max_length=200, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    outstanding_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit_days = models.IntegerField(default=30)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.supplier_code} - {self.supplier_name}"

    def get_outstanding(self):
        """Calculate outstanding balance from bills"""
        total_bills = self.purchase_orders.filter(
            status__in=['approved', 'received']
        ).aggregate(total=models.Sum('total_amount'))['total'] or 0

        total_paid = self.purchase_orders.filter(
            status='completed'
        ).aggregate(total=models.Sum('advance_paid'))['total'] or 0

        self.outstanding_balance = total_bills - total_paid
        self.save()
        return self.outstanding_balance

class Project(models.Model):
    """
    Project / Order - the central financial reference for a buyer order.
    Shown to users as an "Order". While the Merchandising module is off
    (settings.MERCHANDISING_ENABLED) it's entered with a short form - buyer,
    buyer's reference, quantity, value, delivery date - so the fields only
    the full form fills in have defaults.

    The Order No. (project_number) is generated automatically on first
    save: YY + "ORD" + id padded to 5 digits, e.g. 26ORD00012. The buyer's
    own order number goes in buyer_ref.
    Deliberately kept as one record (not split into separate Project and
    Order models) per the accounts module plan: a future Merchandising
    module can add order line items/detailed order info on top of this
    without changing this basic structure.
    """
    STATUS_CHOICES = [
        ('order', 'Order Confirmed'),
        ('production', 'In Production'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    project_number = models.CharField(max_length=50, unique=True, editable=False)
    buyer_ref = models.CharField(max_length=100, blank=True, help_text="The buyer's own order / PO number.")
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name='projects')
    description = models.TextField(blank=True, default='')
    order_quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_value = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    cm_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    agent_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Cost breakdown (estimate, feeds calculate_profit() - see also the
    # separate actual-cost ledger, the Cost model below)
    fabric_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    trim_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    overhead_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit_margin = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Dates
    order_date = models.DateField(default=date.today)
    delivery_date = models.DateField()
    shipped_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='order')
    remarks = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        ref = f" ({self.buyer_ref})" if self.buyer_ref else ""
        return f"{self.project_number}{ref} - {self.buyer.buyer_name}"

    def save(self, *args, **kwargs):
        save_with_number(self, 'project_number', 'ORD', *args, **kwargs)

    def calculate_profit(self):
        self.total_cost = self.fabric_cost + self.trim_cost + self.labor_cost + self.overhead_cost
        self.profit_margin = ((self.total_value - self.total_cost) / self.total_value) * 100 if self.total_value > 0 else 0
        self.save()
        return self.profit_margin

    @property
    def lc_amount_total(self):
        return self.letters_of_credit.aggregate(total=models.Sum('lc_amount'))['total'] or Decimal('0')

    @property
    def lc_paid_total(self):
        return LCPayment.objects.filter(lc__project=self).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def lc_outstanding_total(self):
        return self.lc_amount_total - self.lc_paid_total

    @property
    def loan_amount_total(self):
        return LCLoan.objects.filter(lc__project=self).aggregate(total=models.Sum('loan_amount'))['total'] or Decimal('0')

    @property
    def loan_repaid_total(self):
        return LCLoan.objects.filter(lc__project=self).aggregate(total=models.Sum('repaid_amount'))['total'] or Decimal('0')

    @property
    def loan_interest_total(self):
        return LCLoan.objects.filter(lc__project=self).aggregate(total=models.Sum('interest'))['total'] or Decimal('0')

    @property
    def loan_outstanding_total(self):
        loans = LCLoan.objects.filter(lc__project=self)
        total = Decimal('0')
        for loan in loans:
            total += loan.outstanding
        return total

    @property
    def po_cost_total(self):
        return self.costs.filter(purchase_order__isnull=False).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def other_cost_total(self):
        return self.costs.filter(purchase_order__isnull=True).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    # ----- Receivable (USD): order value minus what the buyer has paid against it
    @property
    def lc_received_usd(self):
        return self.lc_paid_total

    @property
    def direct_received_usd(self):
        return self.direct_payments.filter(payment_type='receivable', status='completed').aggregate(
            total=models.Sum('amount_usd'))['total'] or Decimal('0')

    @property
    def receivable_usd(self):
        return max(self.total_value - self.lc_received_usd - self.direct_received_usd, Decimal('0'))

    # ----- Money (BDT): what actually reached the bank / cash for this order
    @property
    def lc_received_bdt(self):
        return LCPayment.objects.filter(lc__project=self).aggregate(
            total=models.Sum('amount_bdt'))['total'] or Decimal('0')

    @property
    def direct_received_bdt(self):
        return self.direct_payments.filter(payment_type='receivable', status='completed').aggregate(
            total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def received_bdt(self):
        return self.lc_received_bdt + self.direct_received_bdt

    @property
    def loan_charges_total(self):
        """Interest + other charges on this order's LC loans (BDT)."""
        totals = LCLoan.objects.filter(lc__project=self).aggregate(
            interest=models.Sum('interest'), other=models.Sum('other_charges'))
        return (totals['interest'] or Decimal('0')) + (totals['other'] or Decimal('0'))

    @property
    def net_bdt(self):
        """Money received for this order minus its costs and loan charges, all in BDT."""
        return self.received_bdt - self.costs_total - self.loan_charges_total

    @property
    def costs_total(self):
        """All recorded costs, PO-linked or not."""
        return self.costs.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def actual_total_cost(self):
        """PO Cost + Other Cost + Loan Interest - the PDF's 'Total Cost' row."""
        return self.po_cost_total + self.other_cost_total + self.loan_interest_total


    class Meta:
        ordering = ['-created_at']
        verbose_name = 'order'

class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('received', 'Partially Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    po_number = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    style = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders')
    order_date = models.DateField()
    delivery_date = models.DateField()
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    advance_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_pos')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.po_number

    def calculate_net_amount(self):
        self.net_amount = self.total_amount - self.discount + self.tax
        self.save()
        return self.net_amount

    class Meta:
        ordering = ['-created_at']

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item_description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=15, decimal_places=2)
    received_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.item_description}"

class SalesInvoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('pending', 'Pending Payment'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    style = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invoices')
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name='sales_invoices')
    invoice_date = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    letter_of_credit = models.ForeignKey('LetterOfCredit', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    currency = models.CharField(max_length=3, default='USD')

    # Shipping
    shipping_terms = models.CharField(max_length=100, blank=True)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.invoice_number

    def calculate_net_amount(self):
        self.net_amount = self.amount - self.discount + self.tax
        self.save()
        return self.net_amount

    def is_overdue(self):
        if self.status not in ['paid', 'cancelled'] and date.today() > self.due_date:
            self.status = 'overdue'
            self.save()
            return True
        return False

    def get_balance(self):
        return self.net_amount - self.paid_amount

    class Meta:
        ordering = ['-created_at']

class SalesInvoiceItem(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='items')
    item_description = models.CharField(max_length=200)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=15, decimal_places=2)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.item_description}"

class Payment(models.Model):
    PAYMENT_TYPES = [
        ('receivable', 'Accounts Receivable'),
        ('payable', 'Accounts Payable'),
    ]

    # Money received under an LC is recorded on the LC (LCPayment), not here.
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('online', 'Online Payment'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    # Generated on first save: YY + PAY + id, e.g. 26PAY00012.
    payment_number = models.CharField(max_length=50, unique=True, editable=False)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)

    # For Receivables (from buyers)
    buyer = models.ForeignKey(Buyer, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_received')
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')

    # For Payables (to suppliers)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_made')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')

    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="BDT")
    # Optional: which order this pays for and what it's worth in USD - this
    # is what lets each order's receivable be worked out in USD.
    project = models.ForeignKey('Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='direct_payments')
    amount_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    payment_date = models.DateField()
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.payment_number} - {self.amount}"

    def save(self, *args, **kwargs):
        save_with_number(self, 'payment_number', 'PAY', *args, **kwargs)

    def process_payment(self):
        """Process the payment and update related records"""
        if self.status == 'completed':
            return False

        if self.payment_type == 'receivable' and self.sales_invoice:
            self.sales_invoice.paid_amount += self.amount
            if self.sales_invoice.paid_amount >= self.sales_invoice.net_amount:
                self.sales_invoice.status = 'paid'
            else:
                self.sales_invoice.status = 'partial'
            self.sales_invoice.save()

            # Update buyer outstanding
            self.buyer.outstanding_balance -= self.amount
            self.buyer.save()

        elif self.payment_type == 'payable' and self.purchase_order:
            self.purchase_order.advance_paid += self.amount
            if self.purchase_order.advance_paid >= self.purchase_order.net_amount:
                self.purchase_order.status = 'completed'
            self.purchase_order.save()

            # Update supplier outstanding
            self.supplier.outstanding_balance -= self.amount
            self.supplier.save()

        self.status = 'completed'
        self.save()
        return True

    class Meta:
        ordering = ['-created_at']

class CostSheet(models.Model):
    """
    Pre-production cost ESTIMATE/budget worksheet - one per project, fixed
    cost buckets, used for planning/quoting. Distinct from Cost below,
    which is the actual transactional cost ledger recorded as spend
    happens.
    """
    style = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='cost_sheets')
    cost_date = models.DateField()

    # Raw Materials
    fabric_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    trim_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    packaging_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Labor
    cutting_labor = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    stitching_labor = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    finishing_labor = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    qc_labor = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Overhead
    factory_overhead = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    administrative_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    selling_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Total
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    profit_margin = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cost_sheets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cost Sheet - {self.style.project_number} - {self.cost_date}"

    def calculate_totals(self):
        material_cost = self.fabric_cost + self.trim_cost + self.packaging_cost
        labor_cost = self.cutting_labor + self.stitching_labor + self.finishing_labor + self.qc_labor
        overhead_cost = self.factory_overhead + self.administrative_cost + self.selling_cost

        self.total_cost = material_cost + labor_cost + overhead_cost
        self.profit = self.selling_price - self.total_cost
        self.profit_margin = (self.profit / self.selling_price) * 100 if self.selling_price > 0 else 0
        self.save()
        return self.total_cost

    class Meta:
        ordering = ['-created_at']

class BankAccount(models.Model):
    ACCOUNT_TYPES = [
        ('savings', 'Savings Account'),
        ('current', 'Current Account'),
        ('fixed', 'Fixed Deposit'),
    ]

    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50, unique=True)
    bank_name = models.CharField(max_length=200)
    branch_name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.account_name} - {self.account_number}"

class BankTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
    ]

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    is_reconciled = models.BooleanField(default=False)
    reconciliation_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bank_account.account_name} - {self.transaction_type} - {self.amount}"

    def process_transaction(self):
        """Update bank account balance"""
        if self.transaction_type in ['deposit', 'receipt']:
            self.bank_account.current_balance += self.amount
        else:
            self.bank_account.current_balance -= self.amount
        self.bank_account.save()

class LetterOfCredit(models.Model):
    """
    An Order can have one or more LCs. Loans can be taken against an
    active LC and repaid in instalments. Completing the LC (see
    services.complete_lc) records the money realised; whatever is still
    owed on its loans is adjusted (paid off) from that first, and only the
    rest reaches the cash book.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    lc_number = models.CharField(max_length=100, unique=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='letters_of_credit')
    lc_date = models.DateField()
    bank_name = models.CharField(max_length=200)
    lc_amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    expiry_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    remarks = models.TextField(blank=True)
    # Filled in when the LC is completed.
    completed_date = models.DateField(null=True, blank=True)
    realized_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="BDT per USD")
    realized_bdt = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    loan_adjusted = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="BDT")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='letters_of_credit')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.lc_number} - {self.project.project_number}"

    @property
    def total_paid(self):
        return self.lc_payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    @property
    def lc_outstanding(self):
        return self.lc_amount - self.total_paid

    @property
    def loans_outstanding(self):
        return sum((loan.outstanding for loan in self.lc_loans.all()), Decimal('0'))

    @property
    def is_open(self):
        return self.status == 'active'

    class Meta:
        ordering = ['-lc_date']

class LCPayment(models.Model):
    """
    Money received under an LC (part payments, and the final realisation on
    completion). `amount` is in the LC's currency (USD); amount_bdt is what
    the bank actually credited - that's what goes into the cash book.
    """
    lc = models.ForeignKey(LetterOfCredit, on_delete=models.CASCADE, related_name='lc_payments')
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="BDT per USD")
    amount_bdt = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    bank_name = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lc_payments')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.lc.lc_number} - {self.amount} ({self.payment_date})"

    @property
    def receipt_number(self):
        """Shown alongside Payment numbers on the Payments page, e.g. 26LCP00003."""
        if not self.pk:
            return "LCP-PENDING"
        return f"{self.created_at:%y}LCP{self.pk:05d}"

    class Meta:
        ordering = ['-payment_date']

class LCLoan(models.Model):
    """
    Loan Against LC. The loan amount goes into the cash book when taken.
    It's paid off by LCLoanRepayment rows - instalments the user pays, or
    the automatic adjustment when the LC completes. repaid_amount is the
    running total of those. Interest / other charges are flat one-time
    amounts owed on top of the loan.
    """
    lc = models.ForeignKey(LetterOfCredit, on_delete=models.CASCADE, related_name='lc_loans')
    loan_date = models.DateField()
    bank_name = models.CharField(max_length=200, blank=True)
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    other_charges = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    repaid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lc_loans')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.lc.lc_number} - Loan {self.loan_amount} ({self.loan_date})"

    @property
    def total_due(self):
        return self.loan_amount + self.interest + self.other_charges

    @property
    def outstanding(self):
        return self.total_due - self.repaid_amount

    @property
    def is_settled(self):
        return self.outstanding <= 0

    class Meta:
        ordering = ['-loan_date']


class LCLoanRepayment(models.Model):
    """One payment towards an LC loan - by the user, or adjusted from the LC on completion."""
    KIND_CHOICES = [
        ('payment', 'Repayment'),
        ('lc_adjustment', 'Adjusted from LC'),
    ]

    loan = models.ForeignKey(LCLoan, on_delete=models.CASCADE, related_name='repayments')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='payment')
    repayment_date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    mode = models.CharField(max_length=10, choices=[('cash', 'Cash'), ('bank', 'Bank')], default='bank')
    bank_name = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lc_loan_repayments')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.loan} - {self.get_kind_display()} {self.amount}"

    class Meta:
        ordering = ['-repayment_date', '-created_at']

PAYMENT_MODE_CHOICES = [
    ('cash', 'Cash'),
    ('bank', 'Bank'),
]

# Costs recorded against one order...
ORDER_COST_TYPES = [
    ('fabric', 'Fabric'),
    ('accessories', 'Accessories'),
    ('production', 'Production'),
    ('washing', 'Washing'),
    ('printing', 'Printing'),
    ('embroidery', 'Embroidery'),
    ('transport', 'Transport'),
    ('inspection', 'Inspection'),
    ('lc_charges', 'LC Charges'),
    ('commission', 'Commission'),
    ('documentation', 'Documentation'),
    ('courier', 'Courier'),
    ('other', 'Other'),
]

# ...and running costs of the business as a whole.
OVERALL_COST_TYPES = [
    ('rent', 'Rent'),
    ('utilities', 'Utilities (power, gas, water)'),
    ('salaries', 'Salaries & Wages'),
    ('office', 'Office Expenses'),
    ('maintenance', 'Repair & Maintenance'),
    ('bank_charges', 'Bank Charges'),
    ('travel', 'Travel & Conveyance'),
    ('entertainment', 'Entertainment'),
    ('taxes', 'Taxes & Fees'),
    ('miscellaneous', 'Miscellaneous'),
    ('overall_other', 'Other'),
]

class Cost(models.Model):
    """
    Actual cost ledger. Every cost is treated as already paid, so saving one
    (services.record_cost) also takes the money out of the cash book.

    Two kinds, entered separately:
    - Order cost: linked to an Order (project set), ORDER_COST_TYPES.
    - Overall cost: the business's running costs (project blank),
      OVERALL_COST_TYPES.
    Distinct from CostSheet, which is a pre-production estimate.
    """
    COST_TYPES = ORDER_COST_TYPES + OVERALL_COST_TYPES

    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='costs')
    # Who was paid, if it was a supplier - this is how money paid to
    # suppliers is tracked (there are no separate supplier payments).
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='costs')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='costs')
    cost_type = models.CharField(max_length=20, choices=COST_TYPES)
    cost_date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="BDT")
    currency = models.CharField(max_length=3, default='BDT')
    paid_by = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, default='cash')
    bank_name = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='costs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        scope = self.project.project_number if self.project_id else "Overall"
        return f"{scope} - {self.get_cost_type_display()} - {self.amount}"

    @property
    def is_order_cost(self):
        return self.project_id is not None

    @property
    def is_po_cost(self):
        return self.purchase_order_id is not None

    class Meta:
        ordering = ['-cost_date']


class CostVoucher(models.Model):
    """
    A request to spend money, raised by any user. Nothing is recorded until
    an admin approves it; approval creates the Cost (and so the cash book
    entry) straight away - see services.approve_voucher.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='vouchers',
                                help_text="Leave blank for an overall (non-order) cost.")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='cost_vouchers')
    cost_type = models.CharField(max_length=20, choices=Cost.COST_TYPES)
    voucher_date = models.DateField(default=date.today)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    paid_by = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, default='cash')
    bank_name = models.CharField(max_length=200, blank=True)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cost_vouchers')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_cost_vouchers')
    approved_date = models.DateField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=200, blank=True)
    cost = models.OneToOneField(Cost, on_delete=models.SET_NULL, null=True, blank=True, related_name='voucher')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def voucher_number(self):
        if not self.pk:
            return "VCH-PENDING"
        return f"VCH-{self.created_at:%y%m%d}-{self.pk:05d}"

    def __str__(self):
        return f"{self.voucher_number} - {self.amount}"

    class Meta:
        ordering = ['-created_at']


class CashBookEntry(models.Model):
    """
    One line in the cash book: money in or out, by cash or through a bank.
    Most lines are posted automatically (see services.py) when a payment,
    cost, approved voucher, LC loan / repayment or LC receipt is recorded;
    the rest are manual entries (opening balance, other income, moving money
    between cash in hand and bank).
    """
    DIRECTION_CHOICES = [
        ('in', 'Money In'),
        ('out', 'Money Out'),
    ]

    SOURCE_CHOICES = [
        ('manual', 'Manual Entry'),
        ('payment', 'Payment'),
        ('cost', 'Cost'),
        ('loan', 'LC Loan Taken'),
        ('loan_repayment', 'LC Loan Repayment'),
        ('lc_receipt', 'LC Receipt'),
        ('transfer', 'Cash / Bank Transfer'),
    ]

    entry_date = models.DateField(default=date.today)
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, default='cash')
    bank_name = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    source_id = models.IntegerField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cashbook_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def signed_amount(self):
        return self.amount if self.direction == 'in' else -self.amount

    @classmethod
    def balance(cls, **filters):
        totals = cls.objects.filter(**filters).aggregate(
            money_in=models.Sum('amount', filter=models.Q(direction='in')),
            money_out=models.Sum('amount', filter=models.Q(direction='out')),
        )
        return (totals['money_in'] or Decimal('0')) - (totals['money_out'] or Decimal('0'))

    def __str__(self):
        return f"{self.entry_date} {self.get_direction_display()} {self.amount} ({self.get_mode_display()})"

    class Meta:
        ordering = ['-entry_date', '-created_at']
        verbose_name_plural = 'cash book entries'
