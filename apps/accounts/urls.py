from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Dashboard
    path('', views.accounts_dashboard, name='accounts_dashboard'),

    # Buyers
    path('buyers/', views.buyers_list, name='buyers_list'),
    path('buyers/add/', views.add_buyer, name='add_buyer'),
    path('buyers/<int:pk>/edit/', views.edit_buyer, name='edit_buyer'),

    # Suppliers
    path('suppliers/', views.suppliers_list, name='suppliers_list'),
    path('suppliers/add/', views.add_supplier, name='add_supplier'),
    path('suppliers/<int:pk>/edit/', views.edit_supplier, name='edit_supplier'),

    # Projects
    path('projects/', views.projects_list, name='projects_list'),
    path('projects/add/', views.add_project, name='add_project'),
    path('projects/<int:pk>/', views.project_detail, name='project_detail'),
    path('projects/<int:pk>/edit/', views.edit_project, name='edit_project'),

    # Purchase Orders
    path('purchase-orders/', views.purchase_orders_list, name='purchase_orders_list'),
    path('purchase-orders/add/', views.add_purchase_order, name='add_purchase_order'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/edit/', views.edit_purchase_order, name='edit_purchase_order'),

    # Sales Invoices
    path('invoices/', views.invoices_list, name='invoices_list'),
    path('invoices/add/', views.add_invoice, name='add_invoice'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),

    # Payments
    path('payments/', views.payments_list, name='payments_list'),
    path('payments/add/', views.add_payment, name='add_payment'),

    # Letters of Credit
    path('lc/', views.lc_list, name='lc_list'),
    path('lc/add/', views.add_lc, name='add_lc'),
    path('lc/<int:pk>/', views.lc_detail, name='lc_detail'),
    path('lc/<int:pk>/payments/add/', views.add_lc_payment, name='add_lc_payment'),
    path('lc/<int:pk>/loans/add/', views.add_lc_loan, name='add_lc_loan'),

    # Costs (actual PO-cost + other-cost ledger)
    path('costs/', views.costs_list, name='costs_list'),
    path('costs/add/', views.add_cost, name='add_cost'),

    # Cost Sheets (pre-production estimate)
    path('cost-sheets/', views.cost_sheets, name='cost_sheets'),
    path('cost-sheets/add/', views.add_cost_sheet, name='add_cost_sheet'),
    path('cost-sheets/<int:pk>/edit/', views.edit_cost_sheet, name='edit_cost_sheet'),

    # Bank Accounts
    path('banks/', views.banks_list, name='banks_list'),
    path('banks/add/', views.add_bank, name='add_bank'),
    path('banks/<int:pk>/edit/', views.edit_bank, name='edit_bank'),
    path('banks/transactions/', views.bank_transactions_list, name='bank_transactions_list'),
    path('banks/transactions/add/', views.add_bank_transaction, name='add_bank_transaction'),

    # Reports
    path('reports/', views.financial_reports, name='financial_reports'),
]
