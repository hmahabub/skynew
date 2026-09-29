from django import forms
from django.contrib.auth.models import User
from .models import (
    Buyer, Supplier, Project, PurchaseOrder, PurchaseOrderItem,
    SalesInvoice, SalesInvoiceItem, Payment,
    CostSheet, BankAccount, BankTransaction,
    LetterOfCredit, LCPayment, LCLoan, Cost,
)
from datetime import date

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
        fields = ['project_number', 'buyer', 'description', 'order_quantity',
                 'unit_price', 'currency', 'cm_charge', 'agent_commission',
                 'order_date', 'delivery_date', 'status', 'remarks']
        widgets = {
            'project_number': forms.TextInput(attrs={'class': 'form-control'}),
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
        fields = ['payment_number', 'payment_type', 'payment_method', 'buyer',
                 'sales_invoice', 'supplier', 'purchase_order', 'amount',
                 'payment_date', 'reference_number', 'notes']
        widgets = {
            'payment_number': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'buyer': forms.Select(attrs={'class': 'form-select'}),
            'sales_invoice': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        payment_type = cleaned_data.get('payment_type')
        
        if payment_type == 'receivable':
            if not cleaned_data.get('buyer') or not cleaned_data.get('sales_invoice'):
                raise forms.ValidationError('For receivable payments, both Buyer and Sales Invoice are required.')
        elif payment_type == 'payable':
            if not cleaned_data.get('supplier') or not cleaned_data.get('purchase_order'):
                raise forms.ValidationError('For payable payments, both Supplier and Purchase Order are required.')
        
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

class LCPaymentForm(forms.ModelForm):
    class Meta:
        model = LCPayment
        fields = ['payment_date', 'amount', 'bank_name', 'reference', 'remarks']
        widgets = {
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class LCLoanForm(forms.ModelForm):
    class Meta:
        model = LCLoan
        fields = ['loan_date', 'bank_name', 'loan_amount', 'interest',
                 'other_charges', 'repaid_amount', 'remarks']
        widgets = {
            'loan_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'loan_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'interest': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'other_charges': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'repaid_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class CostForm(forms.ModelForm):
    class Meta:
        model = Cost
        fields = ['project', 'purchase_order', 'cost_type', 'cost_date', 'description',
                 'amount', 'currency', 'payment_status', 'remarks']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'cost_type': forms.Select(attrs={'class': 'form-select'}),
            'cost_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_status': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }