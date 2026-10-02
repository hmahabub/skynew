from django.conf import settings
from django import forms
from django.contrib.auth.models import User
from .models import (
    Buyer, Supplier, Project, PurchaseOrder, PurchaseOrderItem,
    SalesInvoice, SalesInvoiceItem, Payment,
    CostSheet, BankAccount, BankTransaction,
    LetterOfCredit, LCPayment, LCLoan, LCLoanRepayment, Cost, CostVoucher,
    CashBookEntry, ORDER_COST_TYPES, OVERALL_COST_TYPES, PAYMENT_MODE_CHOICES,
)
from datetime import date
from decimal import Decimal

class BuyerForm(forms.ModelForm):
    class Meta:
        model = Buyer
        fields = ['buyer_code', 'buyer_name', 'country', 'email', 'phone',
                 'address', 'credit_limit', 'credit_days']
        widgets = {
            'buyer_code': forms.TextInput(attrs={'class': 'form-control'}),
            'buyer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'credit_days': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['supplier_code', 'supplier_name', 'supplier_type', 'email',
                 'phone', 'address', 'bank_name', 'bank_account', 'credit_days']
        widgets = {
            'supplier_code': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_type': forms.Select(attrs={'class': 'form-select'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control'}),
            'credit_days': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['buyer_ref', 'buyer', 'description', 'order_quantity',
                 'unit_price', 'currency', 'cm_charge', 'agent_commission',
                 'order_date', 'delivery_date', 'status', 'remarks']
        widgets = {
            'buyer_ref': forms.TextInput(attrs={'class': 'form-control'}),
            'buyer': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'order_quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
            'cm_charge': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'agent_commission': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'delivery_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class OrderForm(forms.ModelForm):
    """
    Short Order form used while the Merchandising module is off - just what
    Accounting needs to hang Costs, LCs and Cost Sheets (and Dispatches) on.
    Unit price is worked out from the order value.
    """
    class Meta:
        model = Project
        fields = ['buyer', 'buyer_ref', 'order_quantity', 'total_value',
                  'delivery_date', 'status', 'remarks']
        labels = {
            'buyer_ref': 'Buyer Ref.',
            'total_value': 'Order Value',
            'remarks': 'Notes',
        }
        widgets = {
            'buyer_ref': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Buyer's order / PO no."}),
            'buyer': forms.Select(attrs={'class': 'form-select'}),
            'order_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'total_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'delivery_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_order_quantity(self):
        quantity = self.cleaned_data['order_quantity']
        if quantity <= 0:
            raise forms.ValidationError("Order quantity must be more than 0.")
        return quantity

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['po_number', 'supplier', 'style', 'order_date', 'delivery_date',
                 'total_amount', 'discount', 'tax', 'notes']
        widgets = {
            'po_number': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'style': forms.Select(attrs={'class': 'form-select'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'delivery_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class SalesInvoiceForm(forms.ModelForm):
    class Meta:
        model = SalesInvoice
        fields = ['invoice_number', 'style', 'buyer', 'invoice_date', 'due_date',
                 'amount', 'discount', 'tax', 'letter_of_credit', 'exchange_rate',
                 'currency', 'shipping_terms', 'shipping_cost', 'notes']
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'style': forms.Select(attrs={'class': 'form-select'}),
            'buyer': forms.Select(attrs={'class': 'form-select'}),
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'letter_of_credit': forms.Select(attrs={'class': 'form-select'}),
            'exchange_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
            'shipping_terms': forms.TextInput(attrs={'class': 'form-control'}),
            'shipping_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        # payment_number is generated on save (see Payment.save).
        fields = ['payment_type', 'payment_method', 'buyer', 'project',
                 'sales_invoice', 'supplier', 'purchase_order', 'amount', 'amount_usd',
                 'payment_date', 'reference_number', 'notes']
        labels = {
            'project': 'Order (optional)',
            'amount': 'Amount (BDT)',
            'amount_usd': 'USD equivalent (optional)',
        }
        help_texts = {
            'project': "Pick the order this pays for, so it counts against that order's receivable.",
            'amount_usd': "What this payment covers in USD - reduces the order's USD receivable.",
        }
        widgets = {
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'buyer': forms.Select(attrs={'class': 'form-select'}),
            'sales_invoice': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'project': forms.Select(attrs={'class': 'form-select'}),
            'amount_usd': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = Project.objects.filter(is_active=True).exclude(status='cancelled').select_related('buyer')
        if not settings.MERCHANDISING_ENABLED:
            # No invoices / POs yet, and every cost is recorded as already
            # paid - so a payment is only ever money received from a buyer
            # outside an LC. Money paid to suppliers is entered as a Cost.
            self.fields.pop('sales_invoice')
            self.fields.pop('purchase_order')
            self.fields.pop('supplier')
            self.fields['payment_type'].choices = [c for c in Payment.PAYMENT_TYPES if c[0] == 'receivable']
            self.fields['payment_type'].initial = 'receivable'
            self.fields['payment_type'].widget = forms.HiddenInput()
            self.fields['buyer'].required = True

    @property
    def receivable_only(self):
        return 'supplier' not in self.fields

    def clean(self):
        cleaned_data = super().clean()
        if self.receivable_only:
            cleaned_data['payment_type'] = 'receivable'
        payment_type = cleaned_data.get('payment_type')
        order, buyer = cleaned_data.get('project'), cleaned_data.get('buyer')
        if order and buyer and order.buyer_id != buyer.pk:
            self.add_error('project', f"Order {order.project_number} belongs to {order.buyer.buyer_name}, not {buyer.buyer_name}.")
        if cleaned_data.get('amount_usd') and not order:
            self.add_error('project', "Pick the order the USD equivalent counts against.")
        linked = 'sales_invoice' in self.fields

        if payment_type == 'receivable':
            if not cleaned_data.get('buyer') or (linked and not cleaned_data.get('sales_invoice')):
                raise forms.ValidationError(
                    'For receivable payments, both Buyer and Sales Invoice are required.' if linked
                    else 'Select the Buyer this payment was received from.'
                )
        elif payment_type == 'payable':
            if not cleaned_data.get('supplier') or (linked and not cleaned_data.get('purchase_order')):
                raise forms.ValidationError(
                    'For payable payments, both Supplier and Purchase Order are required.' if linked
                    else 'Select the Supplier this payment was made to.'
                )

        return cleaned_data

class CostSheetForm(forms.ModelForm):
    class Meta:
        model = CostSheet
        fields = ['style', 'cost_date', 'fabric_cost', 'trim_cost', 'packaging_cost',
                 'cutting_labor', 'stitching_labor', 'finishing_labor', 'qc_labor',
                 'factory_overhead', 'administrative_cost', 'selling_cost',
                 'selling_price', 'notes']
        widgets = {
            'style': forms.Select(attrs={'class': 'form-select'}),
            'cost_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fabric_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'trim_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'packaging_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'cutting_labor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stitching_labor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'finishing_labor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'qc_labor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'factory_overhead': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'administrative_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'selling_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['account_name', 'account_number', 'bank_name', 'branch_name',
                 'account_type', 'opening_balance', 'notes']
        widgets = {
            'account_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'branch_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class BankTransactionForm(forms.ModelForm):
    class Meta:
        model = BankTransaction
        fields = ['bank_account', 'transaction_type', 'amount', 'transaction_date',
                 'reference', 'description']
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'transaction_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class LetterOfCreditForm(forms.ModelForm):
    class Meta:
        model = LetterOfCredit
        fields = ['lc_number', 'project', 'lc_date', 'bank_name', 'lc_amount',
                 'currency', 'expiry_date', 'status', 'remarks']
        widgets = {
            'lc_number': forms.TextInput(attrs={'class': 'form-control'}),
            'project': forms.Select(attrs={'class': 'form-select'}),
            'lc_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'lc_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].choices = [
            c for c in LetterOfCredit.STATUS_CHOICES if c[0] != 'completed'
        ]

class LCPaymentForm(forms.ModelForm):
    """Money received under an LC: USD received + the bank's rate -> BDT credited."""
    class Meta:
        model = LCPayment
        fields = ['payment_date', 'amount', 'exchange_rate', 'amount_bdt', 'bank_name', 'reference', 'remarks']
        labels = {
            'amount': 'Amount received (USD)',
            'exchange_rate': 'Exchange rate (BDT per USD)',
            'amount_bdt': 'Amount credited (BDT)',
        }
        help_texts = {
            'exchange_rate': "From the bank's credit advice.",
            'amount_bdt': "Leave blank to use USD x rate, or type the exact BDT from the bank advice.",
        }
        widgets = {
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'exchange_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '0.0001'}),
            'amount_bdt': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['exchange_rate'].required = True

    def clean(self):
        cleaned_data = super().clean()
        amount, rate = cleaned_data.get('amount'), cleaned_data.get('exchange_rate')
        if amount is not None and amount <= 0:
            self.add_error('amount', "Amount must be more than 0.")
        if rate is not None and rate <= 0:
            self.add_error('exchange_rate', "Exchange rate must be more than 0.")
        if amount and rate and rate > 0 and cleaned_data.get('amount_bdt') is None:
            cleaned_data['amount_bdt'] = (amount * rate).quantize(Decimal('0.01'))
        return cleaned_data

class LCReceiptForm(LCPaymentForm):
    """Money received under an LC, recorded from the Payments page - pick the LC here."""
    class Meta(LCPaymentForm.Meta):
        fields = ['lc'] + LCPaymentForm.Meta.fields
        labels = {'lc': 'Letter of Credit'}
        widgets = dict(LCPaymentForm.Meta.widgets, lc=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lc'].queryset = LetterOfCredit.objects.filter(status='active').select_related('project', 'project__buyer')
        self.fields['lc'].help_text = "Only active LCs. To record the final amount, use Complete LC on the LC's page."
        self.fields['payment_date'].initial = date.today

class LCLoanForm(forms.ModelForm):
    """Take a loan against an LC - the amount goes into the cash book (bank)."""
    class Meta:
        model = LCLoan
        fields = ['loan_date', 'bank_name', 'loan_amount', 'interest', 'other_charges', 'remarks']
        labels = {'loan_amount': 'Loan amount (BDT)', 'interest': 'Interest (BDT)', 'other_charges': 'Other charges (BDT)'}
        widgets = {
            'loan_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'loan_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'interest': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'other_charges': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class LCLoanRepaymentForm(forms.ModelForm):
    """Pay an instalment on an LC loan."""
    class Meta:
        model = LCLoanRepayment
        fields = ['repayment_date', 'amount', 'mode', 'bank_name', 'reference', 'remarks']
        labels = {'mode': 'Paid by', 'amount': 'Amount (BDT)'}
        widgets = {
            'repayment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cheque / transaction no.'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, loan, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan
        if not self.is_bound:
            self.initial.setdefault('amount', loan.outstanding)
            self.initial.setdefault('bank_name', loan.bank_name)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Amount must be more than 0.")
        if amount > self.loan.outstanding:
            raise forms.ValidationError(f"Only {self.loan.outstanding:.2f} is still owed on this loan.")
        return amount

class LCCompleteForm(forms.Form):
    """Complete an LC: record the money realised. Open loans are adjusted from it first."""
    completion_date = forms.DateField(initial=date.today,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    realized_amount = forms.DecimalField(min_value=0, decimal_places=2, label='Amount realised (USD)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        help_text="USD received from the LC bank now.")
    exchange_rate = forms.DecimalField(min_value=Decimal('0.0001'), decimal_places=4, label='Exchange rate (BDT per USD)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '0.0001'}))
    realized_bdt = forms.DecimalField(required=False, min_value=0, decimal_places=2, label='Amount credited (BDT)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        help_text="Leave blank to use USD x rate.")
    bank_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    reference = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

class OrderCostForm(forms.ModelForm):
    """A cost against one Order. Saved as paid - it goes straight out of the cash book."""
    class Meta:
        model = Cost
        fields = ['project', 'purchase_order', 'cost_type', 'supplier', 'cost_date', 'description',
                  'amount', 'paid_by', 'bank_name', 'reference', 'remarks']
        labels = {'project': 'Order', 'supplier': 'Paid to Supplier', 'amount': 'Amount (BDT)'}
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'cost_type': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'cost_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'paid_by': forms.Select(attrs={'class': 'form-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bill / cheque / transaction no.'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].required = True
        self.fields['project'].queryset = Project.objects.filter(is_active=True)
        self.fields['cost_type'].choices = [('', '---------')] + ORDER_COST_TYPES
        self.fields['cost_date'].initial = date.today
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['supplier'].help_text = "Optional - if a supplier was paid."

        if not settings.MERCHANDISING_ENABLED:
            self.fields.pop('purchase_order')

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('paid_by') == 'cash':
            cleaned_data['bank_name'] = ''
        return cleaned_data

class OverallCostForm(forms.ModelForm):
    """A running cost of the business (rent, salaries...) - not tied to an order. Saved as paid."""
    class Meta:
        model = Cost
        fields = ['cost_type', 'supplier', 'cost_date', 'description', 'amount', 'paid_by', 'bank_name',
                  'reference', 'remarks']
        labels = {'supplier': 'Paid to Supplier', 'amount': 'Amount (BDT)'}
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'cost_type': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'cost_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'paid_by': forms.Select(attrs={'class': 'form-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bill / cheque / transaction no.'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cost_type'].choices = [('', '---------')] + OVERALL_COST_TYPES
        self.fields['cost_date'].initial = date.today
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['supplier'].help_text = "Optional - if a supplier was paid."


    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('paid_by') == 'cash':
            cleaned_data['bank_name'] = ''
        return cleaned_data

class CostVoucherForm(forms.ModelForm):
    """Ask for money to be spent. Becomes a Cost once an admin approves it."""
    class Meta:
        model = CostVoucher
        fields = ['project', 'cost_type', 'supplier', 'voucher_date', 'description', 'amount',
                  'paid_by', 'bank_name', 'remarks']
        labels = {'project': 'Order (optional)', 'paid_by': 'Pay by', 'supplier': 'Pay to Supplier (optional)',
                  'amount': 'Amount (BDT)'}
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'cost_type': forms.Select(attrs={'class': 'form-select'}),
            'voucher_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'What is the money for?'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'paid_by': forms.Select(attrs={'class': 'form-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = Project.objects.filter(is_active=True)
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['cost_type'].choices = [
            ('', '---------'),
            ('Order costs', ORDER_COST_TYPES),
            ('Overall costs', OVERALL_COST_TYPES),
        ]

    def clean(self):
        cleaned_data = super().clean()
        project, cost_type = cleaned_data.get('project'), cleaned_data.get('cost_type')
        order_types = {code for code, _ in ORDER_COST_TYPES}
        if cost_type and project and cost_type not in order_types:
            self.add_error('cost_type', "Pick an order cost type, or clear the Order for an overall cost.")
        if cost_type and not project and cost_type in order_types:
            self.add_error('project', "Pick the Order this cost belongs to, or choose an overall cost type.")
        if amount := cleaned_data.get('amount'):
            if amount <= 0:
                self.add_error('amount', "Amount must be more than 0.")
        return cleaned_data

class CashBookEntryForm(forms.Form):
    """Manual cash book line: other money in / out, or moving money between cash and bank."""
    ENTRY_TYPES = [
        ('in', 'Money In (e.g. opening balance, other income)'),
        ('out', 'Money Out (not a cost)'),
        ('to_bank', 'Deposit cash into bank'),
        ('to_cash', 'Withdraw cash from bank'),
    ]
    entry_type = forms.ChoiceField(choices=ENTRY_TYPES, widget=forms.Select(attrs={'class': 'form-select'}))
    entry_date = forms.DateField(initial=date.today,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, label='Amount (BDT)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}))
    mode = forms.ChoiceField(choices=PAYMENT_MODE_CHOICES, initial='cash', label='Cash or Bank',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Ignored for deposits / withdrawals - those always move between both.")
    bank_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    reference = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    description = forms.CharField(max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}))

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('entry_type') in ('in', 'out') and not cleaned_data.get('description'):
            self.add_error('description', "Say what this money is for.")
        return cleaned_data

