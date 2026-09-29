from django.contrib import admin

from .models import (
    Fabric, FabricRoll, Trim, GoodsReceipt, GoodsReceiptDetail,
    TrimReceipt, TrimReceiptDetail,
    ProductionIssue, ProductionIssueDetail, FinishedGoods,
    FinishedGoodsProduction, Dispatch, DispatchDetail, StockMovement,
    Machine, MachineEvent, SparePart, SparePartConsumption,
    StationeryItem, StationeryConsumption, SupplyAdjustment,
)

admin.site.register(Fabric)
admin.site.register(FabricRoll)
admin.site.register(Trim)
admin.site.register(GoodsReceipt)
admin.site.register(GoodsReceiptDetail)
admin.site.register(TrimReceipt)
admin.site.register(TrimReceiptDetail)
admin.site.register(ProductionIssue)
admin.site.register(ProductionIssueDetail)
admin.site.register(FinishedGoods)
admin.site.register(FinishedGoodsProduction)
admin.site.register(Dispatch)
admin.site.register(DispatchDetail)
admin.site.register(StockMovement)

@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ('machine_code', 'machine_name', 'machine_type', 'status', 'department')
    list_filter = ('status', 'machine_type', 'department')
    search_fields = ('machine_code', 'machine_name', 'serial_number')

@admin.register(MachineEvent)
class MachineEventAdmin(admin.ModelAdmin):
    list_display = ('machine', 'event_type', 'status', 'event_date', 'created_by')
    list_filter = ('status', 'event_type')

@admin.register(SparePart)
class SparePartAdmin(admin.ModelAdmin):
    list_display = ('part_code', 'part_name', 'category', 'current_stock', 'stock_status')
    list_filter = ('category',)
    search_fields = ('part_name',)

admin.site.register(SparePartConsumption)

@admin.register(StationeryItem)
class StationeryItemAdmin(admin.ModelAdmin):
    list_display = ('item_code', 'item_name', 'category', 'current_stock', 'stock_status')
    list_filter = ('category',)
    search_fields = ('item_name',)

admin.site.register(StationeryConsumption)

@admin.register(SupplyAdjustment)
class SupplyAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_number', 'adjustment_type', 'direction', 'status', 'adjustment_date', 'created_by')
    list_filter = ('status', 'adjustment_type', 'direction')
