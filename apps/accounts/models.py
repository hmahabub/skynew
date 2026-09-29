from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date, timedelta

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
    Deliberately kept as one record (not split into separate Project and
    Order models) per the accounts module plan: a future Merchandising
    module can add order line items/detailed order info on top of this
    without changing this basic structure.
    """
    STATUS_CHOICES = [
        ('quotation', 'Quotation'),
        ('order', 'Order Confirmed'),
        ('production', 'In Production'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    project_number = models.CharField(max_length=50, unique=True)
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name='projects')
    description = models.TextField()
    order_quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_value = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    cm_charge = models.DecimalField(max_digits=10, decimal_places=2)
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
    order_date = models.DateField()
    delivery_date = models.DateField()
    shipped_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='quotation')
    remarks = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project_number} - {self.buyer.buyer_name}"

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

    @property
    def actual_total_cost(self):
        """PO Cost + Other Cost + Loan Interest - the PDF's 'Total Cost' row."""
        return self.po_cost_total + self.other_cost_total + self.loan_interest_total

    @property
    def estimated_profit(self):
        return self.total_value - self.actual_total_cost

    class Meta:
        ordering = ['-created_at']

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

    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('lc', 'Letter of Credit'),
        ('online', 'Online Payment'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    payment_number = models.CharField(max_length=50, unique=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)

    # For Receivables (from buyers)
    buyer = models.ForeignKey(Buyer, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_received')
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')

    # For Payables (to suppliers)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_made')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.payment_number} - {self.amount}"

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
    """A Project/Order can have one or more LCs."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('utilized', 'Utilized'),
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

    class Meta:
        ordering = ['-lc_date']

class LCPayment(models.Model):
    """LC payments are linked directly to the LC."""
    lc = models.ForeignKey(LetterOfCredit, on_delete=models.CASCADE, related_name='lc_payments')
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    bank_name = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lc_payments')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.lc.lc_number} - {self.amount} ({self.payment_date})"

    class Meta:
        ordering = ['-payment_date']

class LCLoan(models.Model):
    """
    Loan Against LC - linked directly to the LC. This is the only way
    loan_outstanding is reduced (via repaid_amount); interest/other_charges
    are flat one-time charges, not an accruing schedule.
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
    def outstanding(self):
        return self.loan_amount + self.interest + self.other_charges - self.repaid_amount

    class Meta:
        ordering = ['-loan_date']

class Cost(models.Model):
    """
    Actual transactional cost ledger - PO Cost (purchase_order set) or
    Other Cost (purchase_order blank), always linked to a Project. Distinct
    from CostSheet, which is a pre-production estimate/budget worksheet.
    """
    COST_TYPES = [
        ('fabric', 'Fabric'),
        ('accessories', 'Accessories'),
        ('production', 'Production'),
        ('washing', 'Washing'),
        ('printing', 'Printing'),
        ('embroidery', 'Embroidery'),
        ('transport', 'Transport'),
        ('inspection', 'Inspection'),
        ('lc_charges', 'LC Charges'),
        ('bank_charges', 'Bank Charges'),
        ('commission', 'Commission'),
        ('documentation', 'Documentation'),
        ('courier', 'Courier'),
        ('travel', 'Travel'),
        ('miscellaneous', 'Miscellaneous'),
        ('other', 'Other'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='costs')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='costs')
    cost_type = models.CharField(max_length=20, choices=COST_TYPES)
    cost_date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='costs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.project_number} - {self.get_cost_type_display()} - {self.amount}"

    @property
    def is_po_cost(self):
        return self.purchase_order_id is not None

    class Meta:
        ordering = ['-cost_date']
