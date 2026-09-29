from django.contrib import admin

from .models import (
    Buyer, Supplier, Project, PurchaseOrder, PurchaseOrderItem,
    SalesInvoice, SalesInvoiceItem, Payment,
    CostSheet, BankAccount, BankTransaction,
    LetterOfCredit, LCPayment, LCLoan, Cost,
)

admin.site.register(Buyer)
admin.site.register(Supplier)
admin.site.register(Project)
admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderItem)
admin.site.register(SalesInvoice)
admin.site.register(SalesInvoiceItem)
admin.site.register(Payment)
admin.site.register(CostSheet)
admin.site.register(BankAccount)
admin.site.register(BankTransaction)
admin.site.register(LetterOfCredit)
admin.site.register(LCPayment)
admin.site.register(LCLoan)
admin.site.register(Cost)
