from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard
    path('', views.inventory_dashboard, name='inventory_dashboard'),

    # Fabric Management
    path('fabrics/', views.fabric_list, name='fabric_list'),
    path('fabrics/add/', views.add_fabric, name='add_fabric'),
    path('fabrics/<int:pk>/edit/', views.edit_fabric, name='edit_fabric'),
    path('fabrics/<int:pk>/add-stock/', views.add_fabric_stock, name='add_fabric_stock'),
    path('fabrics/<int:pk>/remove-stock/', views.remove_fabric_stock, name='remove_fabric_stock'),
    path('fabrics/<int:pk>/ledger/', views.fabric_stock_ledger, name='fabric_stock_ledger'),

    # Trim Management
    path('trims/', views.trim_list, name='trim_list'),
    path('trims/add/', views.add_trim, name='add_trim'),
    path('trims/<int:pk>/edit/', views.edit_trim, name='edit_trim'),
    path('trims/<int:pk>/add-stock/', views.add_trim_stock, name='add_trim_stock'),
    path('trims/<int:pk>/remove-stock/', views.remove_trim_stock, name='remove_trim_stock'),
    path('trims/<int:pk>/ledger/', views.trim_stock_ledger, name='trim_stock_ledger'),

    # Goods Receipt (fabric) - legacy, kept for historical records/direct links only
    path('receipts/', views.goods_receipts, name='goods_receipts'),
    path('receipts/add/', views.add_goods_receipt, name='add_goods_receipt'),

    # Trim Receipt - legacy, kept for historical records/direct links only
    path('trim-receipts/', views.trim_receipts, name='trim_receipts'),
    path('trim-receipts/add/', views.add_trim_receipt, name='add_trim_receipt'),

    # Production Issues - legacy, kept for historical records/direct links only
    path('issues/', views.production_issues, name='production_issues'),
    path('issues/add/', views.add_production_issue, name='add_production_issue'),

    # Finished Goods
    path('finished-goods/', views.finished_goods_list, name='finished_goods_list'),
    path('finished-goods/add/', views.add_finished_goods, name='add_finished_goods'),
    path('finished-goods/<int:pk>/edit/', views.edit_finished_goods, name='edit_finished_goods'),
    path('finished-goods/<int:pk>/add-stock/', views.add_finished_goods_stock, name='add_finished_goods_stock'),
    path('finished-goods/<int:pk>/ledger/', views.finished_goods_stock_ledger, name='finished_goods_stock_ledger'),

    # Dispatches
    path('dispatches/', views.dispatches, name='dispatches'),
    path('dispatches/add/', views.add_dispatch, name='add_dispatch'),
    path('dispatches/<int:pk>/', views.dispatch_detail, name='dispatch_detail'),
    path('dispatches/<int:pk>/edit/', views.edit_dispatch, name='edit_dispatch'),
    path('dispatches/<int:pk>/delete/', views.delete_dispatch, name='delete_dispatch'),
    path('dispatches/<int:pk>/status/', views.update_dispatch_status, name='update_dispatch_status'),
    path('dispatches/<int:pk>/approve/', views.approve_dispatch, name='approve_dispatch'),
    path('dispatches/<int:pk>/reject/', views.reject_dispatch, name='reject_dispatch'),

    # Approvals (superuser)
    path('approvals/', views.pending_approvals, name='pending_approvals'),

    # Reports
    path('reports/', views.stock_report, name='stock_report'),
    path('reports/export/excel/', views.stock_report_export_excel, name='stock_report_export_excel'),
    path('reports/export/pdf/', views.stock_report_export_pdf, name='stock_report_export_pdf'),

    # Machines
    path('machines/', views.machine_list, name='machine_list'),
    path('machines/add/', views.add_machine, name='add_machine'),
    path('machines/<int:pk>/', views.machine_detail, name='machine_detail'),
    path('machines/<int:pk>/edit/', views.edit_machine, name='edit_machine'),
    path('machines/<int:pk>/events/add/', views.add_machine_event, name='add_machine_event'),
    path('machines/<int:pk>/events/<int:event_pk>/approve/', views.approve_machine_event, name='approve_machine_event'),
    path('machines/<int:pk>/events/<int:event_pk>/reject/', views.reject_machine_event, name='reject_machine_event'),

    # Spare Parts
    path('spare-parts/', views.spare_part_list, name='spare_part_list'),
    path('spare-parts/add/', views.add_spare_part, name='add_spare_part'),
    path('spare-parts/<int:pk>/edit/', views.edit_spare_part, name='edit_spare_part'),
    path('spare-parts/<int:pk>/ledger/', views.spare_part_stock_ledger, name='spare_part_stock_ledger'),
    path('spare-parts/<int:pk>/add-stock/', views.add_spare_part_stock, name='add_spare_part_stock'),
    path('spare-parts/<int:pk>/consume/', views.record_spare_part_consumption, name='record_spare_part_consumption'),

    # Stationery
    path('stationery/', views.stationery_list, name='stationery_list'),
    path('stationery/add/', views.add_stationery_item, name='add_stationery_item'),
    path('stationery/<int:pk>/edit/', views.edit_stationery_item, name='edit_stationery_item'),
    path('stationery/<int:pk>/ledger/', views.stationery_stock_ledger, name='stationery_stock_ledger'),
    path('stationery/<int:pk>/add-stock/', views.add_stationery_stock, name='add_stationery_stock'),
    path('stationery/<int:pk>/consume/', views.record_stationery_consumption, name='record_stationery_consumption'),

    # Supply Adjustments (Spare Parts + Stationery)
    path('supply-adjustments/', views.supply_adjustments, name='supply_adjustments'),
    path('supply-adjustments/add/', views.add_supply_adjustment, name='add_supply_adjustment'),
    path('supply-adjustments/<int:pk>/approve/', views.approve_supply_adjustment, name='approve_supply_adjustment'),
    path('supply-adjustments/<int:pk>/reject/', views.reject_supply_adjustment, name='reject_supply_adjustment'),
]
