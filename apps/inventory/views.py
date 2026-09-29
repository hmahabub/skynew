from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q, F, Prefetch
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta, date
import json
import csv
from decimal import Decimal, InvalidOperation

from .models import (
    Fabric, FabricRoll, Trim, GoodsReceipt, GoodsReceiptDetail,
    TrimReceipt, TrimReceiptDetail,
    ProductionIssue, ProductionIssueDetail, FinishedGoods,
    FinishedGoodsProduction, Dispatch, DispatchDetail,
    StockMovement,
    Machine, MachineEvent, SparePart, SparePartConsumption,
    StationeryItem, StationeryConsumption, SupplyAdjustment,
)
from .forms import (
    FabricForm, FabricRollForm, FabricStockInForm, FabricStockOutForm,
    TrimForm, TrimStockInForm, TrimStockOutForm, GoodsReceiptForm,
    GoodsReceiptDetailForm, TrimReceiptForm, TrimReceiptDetailForm,
    ProductionIssueForm, ProductionIssueDetailForm,
    FinishedGoodsForm, FinishedGoodsStockInForm,
    DispatchForm, DispatchDetailForm,
    MachineForm, MachineEventForm, RejectMachineEventForm,
    SparePartForm, SparePartStockInForm, SparePartConsumptionForm,
    StationeryItemForm, StationeryStockInForm, StationeryConsumptionForm,
    SupplyAdjustmentForm, RejectSupplyAdjustmentForm,
)

def is_inventory_or_admin(user):
    return user.is_superuser or user.groups.filter(name='Inventory').exists()

@login_required
def inventory_dashboard(request):
    """Inventory Dashboard Overview"""
    context = {
        'active': 'inventory',
        'page_title': 'Inventory Dashboard',
    }

    # Summary Statistics
    context['total_fabrics'] = Fabric.objects.filter(is_active=True).count()
    context['total_trims'] = Trim.objects.filter(is_active=True).count()
    context['total_finished_goods'] = FinishedGoods.objects.filter(is_active=True).count()

    # Stock Status
    fabric_stock = Fabric.objects.aggregate(total=Sum('current_stock'))['total'] or 0
    trim_stock = Trim.objects.aggregate(total=Sum('current_stock'))['total'] or 0
    finished_stock = FinishedGoods.objects.aggregate(total=Sum('quantity_in_stock'))['total'] or 0

    context['total_fabric_stock'] = fabric_stock
    context['total_trim_stock'] = trim_stock
    context['total_finished_stock'] = finished_stock

    # Out of stock items
    context['out_of_stock_fabric_count'] = Fabric.objects.filter(
        current_stock__lte=0, is_active=True
    ).count()
    context['out_of_stock_trim_count'] = Trim.objects.filter(
        current_stock__lte=0, is_active=True
    ).count()
    context['pending_dispatch_count'] = Dispatch.objects.exclude(status='dispatched').count()

    # Assets & Supplies
    context['total_machines'] = Machine.objects.exclude(status__in=['sold', 'scrapped']).count()
    context['machines_needing_attention'] = Machine.objects.filter(
        status__in=['under_maintenance', 'broken_down']
    ).count()

    context['total_spare_parts'] = SparePart.objects.filter(is_active=True).count()
    context['spare_parts_stock'] = SparePart.objects.filter(is_active=True).aggregate(
        total=Sum('current_stock')
    )['total'] or 0
    context['low_spare_parts_count'] = SparePart.objects.filter(
        current_stock__lte=F('min_stock'), is_active=True
    ).count()

    context['total_stationery_items'] = StationeryItem.objects.filter(is_active=True).count()
    context['stationery_stock'] = StationeryItem.objects.filter(is_active=True).aggregate(
        total=Sum('current_stock')
    )['total'] or 0
    context['low_stationery_count'] = StationeryItem.objects.filter(
        current_stock__lte=F('min_stock'), is_active=True
    ).count()

    # Recent Receipts
    context['recent_receipts'] = GoodsReceipt.objects.select_related('supplier').order_by('-receipt_date')[:5]

    # Recent Dispatches
    context['recent_dispatches'] = Dispatch.objects.select_related('project').order_by('-dispatch_date')[:5]

    # Stock Movement Chart Data
    last_7_days = [date.today() - timedelta(days=x) for x in range(6, -1, -1)]
    movement_data = []

    for day in last_7_days:
        count = StockMovement.objects.filter(movement_date=day).count()
        movement_data.append(count)

    context['movement_labels'] = [day.strftime('%b %d') for day in last_7_days]
    context['movement_data'] = movement_data

    # Top Items by Stock Value
    top_fabrics = Fabric.objects.filter(is_active=True).order_by('-current_stock')[:5]
    top_trims = Trim.objects.filter(is_active=True).order_by('-current_stock')[:5]

    context['top_fabrics'] = top_fabrics
    context['top_trims'] = top_trims

    return render(request, 'inventory/dashboard.html', context)

def _redirect_back(request, fallback, *args, **kwargs):
    """
    Redirect to the POSTed `next` URL (the page a popup form was opened
    from) if it's a safe, same-site URL - otherwise to `fallback`.
    """
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect(fallback, *args, **kwargs)

def _form_errors_to_messages(request, form, prefix):
    """Popup forms can't re-render inline errors, so surface them as flash messages."""
    for field, errors in form.errors.items():
        label = '' if field == '__all__' else f"{form[field].label}: "
        for error in errors:
            messages.error(request, f"{prefix} - {label}{error}")

def _in_stock_lots_prefetch():
    return Prefetch(
        'rolls',
        queryset=FabricRoll.objects.filter(status='in_stock').order_by('received_date'),
        to_attr='in_stock_lots',
    )

def _fabric_lots_map(fabrics):
    """
    {fabric_id: [{id, lot, remaining}, ...]} for the "-" (Remove Stock)
    popup's lot dropdown. Fabrics must come from a queryset using
    _in_stock_lots_prefetch().
    """
    return {
        fabric.pk: [
            {'id': lot.pk, 'lot': lot.lot_number, 'remaining': str(lot.remaining_length)}
            for lot in fabric.in_stock_lots
        ]
        for fabric in fabrics
    }

def _next_lot_number(fabric):
    """Auto lot number for when the user leaves it blank, e.g. F-00012-L003."""
    n = fabric.rolls.count() + 1
    while FabricRoll.objects.filter(lot_number=f"{fabric.fabric_code}-L{n:03d}").exists():
        n += 1
    return f"{fabric.fabric_code}-L{n:03d}"

def _add_fabric_lot(fabric, quantity, user, lot_number='', location='Main Warehouse',
                    received_date=None, notes='', reference_number='', reference_id=None):
    """
    Create a new lot for `fabric` and add its quantity to stock. Every
    fabric stock-in goes through here, so a fabric's stock always equals
    what's left in its lots. Call inside transaction.atomic().
    """
    lot_number = lot_number or _next_lot_number(fabric)
    roll = FabricRoll.objects.create(
        roll_number=lot_number,
        lot_number=lot_number,
        fabric=fabric,
        length=quantity,
        location=location,
        received_date=received_date or date.today(),
        quality_status='passed',
    )
    Fabric.objects.filter(pk=fabric.pk).update(current_stock=F('current_stock') + quantity)
    StockMovement.objects.create(
        movement_type='receipt',
        reference_number=reference_number or f"LOT-{lot_number}",
        reference_id=reference_id or roll.pk,
        fabric=fabric,
        fabric_roll=roll,
        quantity=quantity,
        notes=notes,
        created_by=user,
    )
    return roll

@login_required
def fabric_list(request):
    """List all fabrics, with +/- popups to add or remove stock in place."""
    fabrics = Fabric.objects.filter(is_active=True).prefetch_related(
        _in_stock_lots_prefetch()
    ).order_by('-created_at')

    # Search
    search = request.GET.get('search')
    if search:
        fabrics = fabrics.filter(
            Q(fabric_name__icontains=search) |
            Q(color__icontains=search) |
            Q(supplier__icontains=search) |
            Q(buyer__icontains=search) |
            Q(project__icontains=search) |
            Q(purchase_order__icontains=search)
        )

    # Filter by fabric type
    fabric_type = request.GET.get('type')
    if fabric_type:
        fabrics = fabrics.filter(fabric_type=fabric_type)

    # Filter by stock status
    stock_status = request.GET.get('stock_status')
    if stock_status == 'in_stock':
        fabrics = fabrics.filter(current_stock__gt=0)
    elif stock_status == 'out_of_stock':
        fabrics = fabrics.filter(current_stock__lte=0)

    # Pagination
    paginator = Paginator(fabrics, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active': 'inventory',
        'page_title': 'Fabric Management',
        'fabrics': page_obj,
        'fabric_lots': _fabric_lots_map(page_obj),
        'fabric_types': Fabric.FABRIC_TYPES,
        'search': search,
        'current_type': fabric_type,
        'current_stock_status': stock_status,
        'stock_in_form': FabricStockInForm(),
        'stock_out_reasons': FabricStockOutForm.REASON_CHOICES,
    }
    return render(request, 'inventory/fabric_list.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_fabric(request):
    """Add new fabric, optionally with its opening stock."""
    if request.method == 'POST':
        form = FabricForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                fabric = form.save()

                initial_quantity = form.cleaned_data.get('initial_quantity') or Decimal('0')
                if initial_quantity > 0:
                    lot_number = form.cleaned_data.get('lot_number')
                    _add_fabric_lot(
                        fabric, initial_quantity, request.user,
                        lot_number=lot_number,
                        notes="Opening stock",
                    )

            messages.success(request, f'Fabric "{fabric.fabric_name}" added successfully!')
            return redirect('inventory:fabric_list')
    else:
        form = FabricForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Fabric',
        'form': form,
    }
    return render(request, 'inventory/fabric_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def edit_fabric(request, pk):
    """Edit fabric"""
    fabric = get_object_or_404(Fabric, pk=pk)
    if request.method == 'POST':
        form = FabricForm(request.POST, instance=fabric)
        if form.is_valid():
            form.save()
            messages.success(request, f'Fabric "{fabric.fabric_name}" updated successfully!')
            return redirect('inventory:fabric_list')
    else:
        form = FabricForm(instance=fabric)

    context = {
        'active': 'inventory',
        'page_title': 'Edit Fabric',
        'form': form,
        'fabric': fabric,
    }
    return render(request, 'inventory/fabric_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
@require_POST
def add_fabric_stock(request, pk):
    """
    "+" popup: add a new lot to an existing fabric. Applies immediately,
    then returns to whichever page the popup was opened from.
    """
    fabric = get_object_or_404(Fabric, pk=pk)
    form = FabricStockInForm(request.POST)
    if not form.is_valid():
        _form_errors_to_messages(request, form, f'Add stock to "{fabric.fabric_name}"')
        return _redirect_back(request, 'inventory:fabric_list')

    quantity = form.cleaned_data['quantity']
    with transaction.atomic():
        roll = _add_fabric_lot(
            fabric, quantity, request.user,
            lot_number=form.cleaned_data['lot_number'],
            location=form.cleaned_data['location'],
            received_date=form.cleaned_data['received_date'],
            notes=form.cleaned_data['notes'],
        )
    messages.success(
        request,
        f'Added {quantity} {fabric.get_unit_display()} to "{fabric.fabric_name}" (lot {roll.lot_number}).'
    )
    return _redirect_back(request, 'inventory:fabric_list')

@login_required
@user_passes_test(is_inventory_or_admin)
@require_POST
def remove_fabric_stock(request, pk):
    """
    "-" popup: take stock out of one lot of a fabric (issued to
    production, damaged, returned...). Applies immediately - there's no
    approval step - and is logged in the fabric's stock history.
    """
    fabric = get_object_or_404(Fabric, pk=pk)
    form = FabricStockOutForm(request.POST, fabric=fabric)
    if not form.is_valid():
        _form_errors_to_messages(request, form, f'Remove stock from "{fabric.fabric_name}"')
        return _redirect_back(request, 'inventory:fabric_list')

    quantity = form.cleaned_data['quantity']
    reason = form.cleaned_data['reason']
    reason_label = dict(FabricStockOutForm.REASON_CHOICES)[reason]
    notes = form.cleaned_data['notes']
    try:
        with transaction.atomic():
            # Re-check against locked rows so two people removing stock at
            # the same moment can't take it below zero.
            fabric = Fabric.objects.select_for_update().get(pk=fabric.pk)
            if quantity > fabric.current_stock:
                raise ValueError(f"Only {fabric.current_stock} {fabric.unit} of this fabric is in stock.")

            lot = form.cleaned_data['lot']
            if lot is not None:
                lot = FabricRoll.objects.select_for_update().get(pk=lot.pk)
                if quantity > lot.remaining_length:
                    raise ValueError(f"Lot {lot.lot_number} only has {lot.remaining_length} {fabric.unit} left.")
                lot.used_length += quantity
                lot.save()

            fabric.current_stock -= quantity
            fabric.save(update_fields=['current_stock', 'updated_at'])

            movement = StockMovement.objects.create(
                movement_type='issue' if reason == 'issue' else 'adjustment',
                reference_number='',
                reference_id=fabric.pk,
                fabric=fabric,
                fabric_roll=lot,
                quantity=-quantity,
                issued_to=form.cleaned_data['issued_to'],
                notes=f"{reason_label} - {notes}" if notes else reason_label,
                created_by=request.user,
            )
            movement.reference_number = movement.movement_number
            movement.save(update_fields=['reference_number'])
    except ValueError as exc:
        messages.error(request, f'Remove stock from "{fabric.fabric_name}" - {exc}')
    else:
        lot_text = f" (lot {lot.lot_number})" if lot is not None else ""
        issued_to = form.cleaned_data['issued_to']
        to_text = f" (issued to {issued_to})" if issued_to else ""
        messages.success(
            request,
            f'Removed {quantity} {fabric.get_unit_display()} from "{fabric.fabric_name}"{lot_text} - {reason_label}{to_text}.'
        )
    return _redirect_back(request, 'inventory:fabric_list')

@login_required
def trim_list(request):
    """List all trims"""
    trims = Trim.objects.filter(is_active=True).select_related('supplier')

    # Search
    search = request.GET.get('search')
    if search:
        trims = trims.filter(
            Q(trim_name__icontains=search) |
            Q(color__icontains=search) |
            Q(size__icontains=search)
        )

    # Filter by trim type
    trim_type = request.GET.get('type')
    if trim_type:
        trims = trims.filter(trim_type=trim_type)

    context = {
        'active': 'inventory',
        'page_title': 'Trim Management',
        'trims': trims,
        'trim_types': Trim.TRIM_TYPES,
        'search': search,
        'current_type': trim_type,
        'trim_stock_in_form': TrimStockInForm(),
        'stock_out_reasons': TrimStockOutForm.REASON_CHOICES,
    }
    return render(request, 'inventory/trim_list.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_trim(request):
    """Add new trim"""
    if request.method == 'POST':
        form = TrimForm(request.POST)
        if form.is_valid():
            trim = form.save()
            messages.success(request, f'Trim "{trim.trim_name}" added successfully!')
            return redirect('inventory:trim_list')
    else:
        form = TrimForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Trim',
        'form': form,
    }
    return render(request, 'inventory/trim_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def edit_trim(request, pk):
    """Edit trim"""
    trim = get_object_or_404(Trim, pk=pk)
    if request.method == 'POST':
        form = TrimForm(request.POST, instance=trim)
        if form.is_valid():
            form.save()
            messages.success(request, f'Trim "{trim.trim_name}" updated successfully!')
            return redirect('inventory:trim_list')
    else:
        form = TrimForm(instance=trim)

    context = {
        'active': 'inventory',
        'page_title': 'Edit Trim',
        'form': form,
        'trim': trim,
    }
    return render(request, 'inventory/trim_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
@require_POST
def add_trim_stock(request, pk):
    """
    "+" popup: add stock to a trim. Applies immediately, then returns to
    whichever page the popup was opened from.
    """
    trim = get_object_or_404(Trim, pk=pk)
    form = TrimStockInForm(request.POST)
    if not form.is_valid():
        _form_errors_to_messages(request, form, f'Add stock to "{trim.trim_name}"')
        return _redirect_back(request, 'inventory:trim_list')

    quantity = form.cleaned_data['quantity']
    with transaction.atomic():
        Trim.objects.filter(pk=trim.pk).update(current_stock=F('current_stock') + quantity)
        movement = StockMovement.objects.create(
            movement_type='receipt',
            reference_number='',
            reference_id=trim.pk,
            trim=trim,
            quantity=quantity,
            notes=form.cleaned_data['notes'],
            created_by=request.user,
        )
        movement.reference_number = movement.movement_number
        movement.save(update_fields=['reference_number'])
    messages.success(request, f'Added {quantity} {trim.unit} to "{trim.trim_name}".')
    return _redirect_back(request, 'inventory:trim_list')

@login_required
@user_passes_test(is_inventory_or_admin)
@require_POST
def remove_trim_stock(request, pk):
    """
    "-" popup: take stock out of a trim (issued to production, damaged,
    returned...). Applies immediately and is logged in the stock history.
    """
    trim = get_object_or_404(Trim, pk=pk)
    form = TrimStockOutForm(request.POST, trim=trim)
    if not form.is_valid():
        _form_errors_to_messages(request, form, f'Remove stock from "{trim.trim_name}"')
        return _redirect_back(request, 'inventory:trim_list')

    quantity = form.cleaned_data['quantity']
    reason = form.cleaned_data['reason']
    reason_label = dict(TrimStockOutForm.REASON_CHOICES)[reason]
    issued_to = form.cleaned_data['issued_to']
    notes = form.cleaned_data['notes']
    try:
        with transaction.atomic():
            # Re-check against the locked row so two people removing stock
            # at the same moment can't take it below zero.
            trim = Trim.objects.select_for_update().get(pk=trim.pk)
            if quantity > trim.current_stock:
                raise ValueError(f"Only {trim.current_stock} {trim.unit} of this trim is in stock.")
            trim.current_stock -= quantity
            trim.save(update_fields=['current_stock', 'updated_at'])

            movement = StockMovement.objects.create(
                movement_type='issue' if reason == 'issue' else 'adjustment',
                reference_number='',
                reference_id=trim.pk,
                trim=trim,
                quantity=-quantity,
                issued_to=issued_to,
                notes=f"{reason_label} - {notes}" if notes else reason_label,
                created_by=request.user,
            )
            movement.reference_number = movement.movement_number
            movement.save(update_fields=['reference_number'])
    except ValueError as exc:
        messages.error(request, f'Remove stock from "{trim.trim_name}" - {exc}')
    else:
        to_text = f" (issued to {issued_to})" if issued_to else ""
        messages.success(request, f'Removed {quantity} {trim.unit} from "{trim.trim_name}" - {reason_label}{to_text}.')
    return _redirect_back(request, 'inventory:trim_list')

@login_required
def goods_receipts(request):
    """List all goods receipts"""
    receipts = GoodsReceipt.objects.select_related('supplier').all()

    context = {
        'active': 'inventory',
        'page_title': 'Goods Receipts',
        'receipts': receipts,
    }
    return render(request, 'inventory/goods_receipts.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_goods_receipt(request):
    """
    Create a Goods Receipt: adds one or more fabrics to stock.
    A GR only ever increases stock.
    """
    if request.method == 'POST':
        form = GoodsReceiptForm(request.POST)
        if form.is_valid():
            fabric_ids = request.POST.getlist('fabric_ids[]')
            quantities = request.POST.getlist('quantities[]')
            unit_prices = request.POST.getlist('unit_prices[]')

            row_errors = []
            rows = []

            for i in range(len(quantities)):
                if not quantities[i]:
                    continue

                fabric_id = fabric_ids[i] if i < len(fabric_ids) and fabric_ids[i] else None
                if not fabric_id:
                    row_errors.append(f"Row {i + 1}: select a fabric.")
                    continue

                try:
                    quantity = Decimal(quantities[i])
                    unit_price = Decimal(unit_prices[i] or 0)
                except InvalidOperation:
                    row_errors.append(f"Row {i + 1}: quantity and price must be valid numbers.")
                    continue

                if quantity <= 0:
                    row_errors.append(f"Row {i + 1}: quantity must be greater than 0.")
                    continue

                rows.append({
                    'fabric_id': fabric_id,
                    'quantity': quantity,
                    'unit_price': unit_price,
                })

            if not rows and not row_errors:
                row_errors.append("Add at least one fabric to the receipt.")

            if row_errors:
                for err in row_errors:
                    messages.error(request, err)
            else:
                with transaction.atomic():
                    receipt = form.save(commit=False)
                    receipt.received_by = request.user
                    receipt.save()

                    total_quantity = Decimal('0')

                    for row in rows:
                        detail = GoodsReceiptDetail.objects.create(
                            goods_receipt=receipt,
                            fabric_id=row['fabric_id'],
                            quantity=row['quantity'],
                            unit_price=row['unit_price'],
                        )

                        total_quantity += detail.quantity

                        # Each received line becomes its own lot, so it can
                        # later be taken out with the "-" (Remove Stock) popup.
                        _add_fabric_lot(
                            detail.fabric, detail.quantity, request.user,
                            notes=f"Goods receipt from {receipt.supplier.supplier_name}",
                            reference_number=receipt.receipt_number,
                            reference_id=receipt.pk,
                        )

                    receipt.total_quantity = total_quantity
                    receipt.save()

                messages.success(request, f'Goods receipt "{receipt.receipt_number}" created - stock updated!')
                return redirect('inventory:goods_receipts')
    else:
        form = GoodsReceiptForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Goods Receipt',
        'form': form,
        'fabrics': Fabric.objects.filter(is_active=True),
    }
    return render(request, 'inventory/goods_receipt_form.html', context)

@login_required
def fabric_stock_ledger(request, pk):
    """
    All stock-affecting activity (lot additions, issues/adjustments) for a
    single fabric, newest first, with a running balance - plus its current
    lot breakdown.
    """
    fabric = get_object_or_404(Fabric.objects.prefetch_related(_in_stock_lots_prefetch()), pk=pk)
    movements = list(
        StockMovement.objects.filter(fabric=fabric).select_related('fabric_roll', 'created_by')
        .order_by('movement_date', 'created_at')
    )

    # Work out a running balance ending at the fabric's current stock, so
    # the ledger reads naturally even though we're computing it after the
    # fact from a signed-quantity log.
    total_delta = sum((m.quantity for m in movements), Decimal('0'))
    running_balance = fabric.current_stock - total_delta
    for movement in movements:
        running_balance += movement.quantity
        movement.balance_after = running_balance

    movements.reverse()  # newest first for display

    lots = FabricRoll.objects.filter(fabric=fabric).order_by('-received_date')

    context = {
        'active': 'inventory',
        'page_title': f'Stock Ledger - {fabric.fabric_name}',
        'fabric': fabric,
        'movements': movements,
        'lots': lots,
        'fabric_lots': _fabric_lots_map([fabric]),
        'stock_in_form': FabricStockInForm(),
        'stock_out_reasons': FabricStockOutForm.REASON_CHOICES,
    }
    return render(request, 'inventory/fabric_stock_ledger.html', context)

@login_required
def trim_receipts(request):
    """List all trim receipts"""
    receipts = TrimReceipt.objects.select_related('supplier').all()

    context = {
        'active': 'inventory',
        'page_title': 'Trim Receipts',
        'receipts': receipts,
    }
    return render(request, 'inventory/trim_receipts.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_trim_receipt(request):
    """
    Create a Trim Receipt: adds one or more trims to stock.
    Mirrors add_goods_receipt exactly, just for trims. A TR only ever
    increases stock.
    """
    if request.method == 'POST':
        form = TrimReceiptForm(request.POST)
        if form.is_valid():
            trim_ids = request.POST.getlist('trim_ids[]')
            quantities = request.POST.getlist('quantities[]')
            unit_prices = request.POST.getlist('unit_prices[]')

            row_errors = []
            rows = []

            for i in range(len(quantities)):
                if not quantities[i]:
                    continue

                trim_id = trim_ids[i] if i < len(trim_ids) and trim_ids[i] else None
                if not trim_id:
                    row_errors.append(f"Row {i + 1}: select a trim.")
                    continue

                try:
                    quantity = int(quantities[i])
                    unit_price = Decimal(unit_prices[i] or 0)
                except (ValueError, InvalidOperation):
                    row_errors.append(f"Row {i + 1}: quantity must be a whole number and price must be valid.")
                    continue

                if quantity <= 0:
                    row_errors.append(f"Row {i + 1}: quantity must be greater than 0.")
                    continue

                rows.append({
                    'trim_id': trim_id,
                    'quantity': quantity,
                    'unit_price': unit_price,
                })

            if not rows and not row_errors:
                row_errors.append("Add at least one trim to the receipt.")

            if row_errors:
                for err in row_errors:
                    messages.error(request, err)
            else:
                with transaction.atomic():
                    receipt = form.save(commit=False)
                    receipt.received_by = request.user
                    receipt.save()

                    total_quantity = 0

                    for row in rows:
                        detail = TrimReceiptDetail.objects.create(
                            trim_receipt=receipt,
                            trim_id=row['trim_id'],
                            quantity=row['quantity'],
                            unit_price=row['unit_price'],
                        )

                        total_quantity += detail.quantity

                        # Update stock with an F() expression so concurrent
                        # receipts can't clobber each other's stock updates.
                        Trim.objects.filter(pk=detail.trim_id).update(
                            current_stock=F('current_stock') + detail.quantity
                        )

                        StockMovement.objects.create(
                            movement_type='receipt',
                            reference_number=receipt.receipt_number,
                            reference_id=receipt.pk,
                            trim_id=detail.trim_id,
                            quantity=detail.quantity,
                            notes=f"Trim receipt from {receipt.supplier.supplier_name}",
                            created_by=request.user,
                        )

                    receipt.total_quantity = total_quantity
                    receipt.save()

                messages.success(request, f'Trim receipt "{receipt.receipt_number}" created - stock updated!')
                return redirect('inventory:trim_receipts')
    else:
        form = TrimReceiptForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Trim Receipt',
        'form': form,
        'trims': Trim.objects.filter(is_active=True),
    }
    return render(request, 'inventory/trim_receipt_form.html', context)

@login_required
def trim_stock_ledger(request, pk):
    """
    All stock-affecting activity (stock added, Trim Receipts) for a single
    trim, newest first, with a running balance.
    """
    trim = get_object_or_404(Trim, pk=pk)
    movements = list(
        StockMovement.objects.filter(trim=trim).order_by('movement_date', 'created_at')
    )

    total_delta = sum((m.quantity for m in movements), Decimal('0'))
    running_balance = trim.current_stock - total_delta
    for movement in movements:
        running_balance += movement.quantity
        movement.balance_after = running_balance

    movements.reverse()  # newest first for display

    context = {
        'active': 'inventory',
        'page_title': f'Stock Ledger - {trim.trim_name}',
        'trim': trim,
        'movements': movements,
        'trim_stock_in_form': TrimStockInForm(),
        'stock_out_reasons': TrimStockOutForm.REASON_CHOICES,
    }
    return render(request, 'inventory/trim_stock_ledger.html', context)

@login_required
def production_issues(request):
    """List all production issues"""
    issues = ProductionIssue.objects.select_related('project', 'department', 'issued_by').all()

    context = {
        'active': 'inventory',
        'page_title': 'Production Issues',
        'issues': issues,
    }
    return render(request, 'inventory/production_issues.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_production_issue(request):
    """Add new production issue"""
    if request.method == 'POST':
        form = ProductionIssueForm(request.POST)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.issued_by = request.user
            issue.save()

            # Handle issue details
            fabric_ids = request.POST.getlist('fabric_ids[]')
            fabric_roll_ids = request.POST.getlist('fabric_roll_ids[]')
            trim_ids = request.POST.getlist('trim_ids[]')
            quantities_issued = request.POST.getlist('quantities_issued[]')

            for i in range(len(quantities_issued)):
                if quantities_issued[i]:
                    detail = ProductionIssueDetail.objects.create(
                        production_issue=issue,
                        fabric_id=fabric_ids[i] if i < len(fabric_ids) and fabric_ids[i] else None,
                        fabric_roll_id=fabric_roll_ids[i] if i < len(fabric_roll_ids) and fabric_roll_ids[i] else None,
                        trim_id=trim_ids[i] if i < len(trim_ids) and trim_ids[i] else None,
                        quantity_issued=Decimal(quantities_issued[i]),
                        quantity_requested=Decimal(quantities_issued[i])
                    )

                    # Update stock
                    if detail.fabric:
                        fabric = detail.fabric
                        fabric.current_stock -= detail.quantity_issued
                        fabric.save()
                        StockMovement.objects.create(
                            movement_type='issue',
                            reference_number=issue.issue_number,
                            reference_id=issue.pk,
                            fabric=fabric,
                            quantity=-detail.quantity_issued,
                            notes=f"Issued to production - {issue.project.project_number}",
                            created_by=request.user,
                        )
                    elif detail.trim:
                        trim = detail.trim
                        trim.current_stock -= int(detail.quantity_issued)
                        trim.save()
                        StockMovement.objects.create(
                            movement_type='issue',
                            reference_number=issue.issue_number,
                            reference_id=issue.pk,
                            trim=trim,
                            quantity=-detail.quantity_issued,
                            notes=f"Issued to production - {issue.project.project_number}",
                            created_by=request.user,
                        )

                    # Update fabric roll if used
                    if detail.fabric_roll:
                        roll = detail.fabric_roll
                        roll.used_length += detail.quantity_issued
                        roll.save()

            issue.status = 'issued'
            issue.save()

            messages.success(request, f'Production issue "{issue.issue_number}" created successfully!')
            return redirect('inventory:production_issues')
    else:
        form = ProductionIssueForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Production Issue',
        'form': form,
        'fabrics': Fabric.objects.filter(is_active=True),
        'fabric_rolls': FabricRoll.objects.filter(status='in_stock'),
        'trims': Trim.objects.filter(is_active=True),
    }
    return render(request, 'inventory/production_issue_form.html', context)

@login_required
def finished_goods_list(request):
    """List all finished goods, with how much of each is waiting on a pending dispatch."""
    finished_goods = FinishedGoods.with_pending_dispatch(
        FinishedGoods.objects.filter(is_active=True)
    )

    # Search
    search = request.GET.get('search')
    if search:
        finished_goods = finished_goods.filter(
            Q(style__icontains=search) |
            Q(size__icontains=search) |
            Q(color__icontains=search)
        )

    # Filter by stock status
    stock_status = request.GET.get('stock_status')
    if stock_status == 'in_stock':
        finished_goods = finished_goods.filter(quantity_in_stock__gt=0)
    elif stock_status == 'out':
        finished_goods = finished_goods.filter(quantity_in_stock__lte=0)
    elif stock_status == 'pending_dispatch':
        finished_goods = finished_goods.filter(_pending_dispatch_qty__gt=0)

    # Pagination
    paginator = Paginator(finished_goods, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active': 'inventory',
        'page_title': 'Finished Goods',
        'finished_goods': page_obj,
        'search': search,
        'current_stock_status': stock_status,
    }
    return render(request, 'inventory/finished_goods.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_finished_goods(request):
    """Add new finished goods"""
    if request.method == 'POST':
        form = FinishedGoodsForm(request.POST)
        if form.is_valid():
            finished = form.save()
            messages.success(request, f'Finished goods "{finished}" added successfully!')
            return redirect('inventory:finished_goods_list')
    else:
        form = FinishedGoodsForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Finished Goods',
        'form': form,
    }
    return render(request, 'inventory/finished_goods_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def edit_finished_goods(request, pk):
    """Edit finished goods"""
    finished = get_object_or_404(FinishedGoods, pk=pk)
    if request.method == 'POST':
        form = FinishedGoodsForm(request.POST, instance=finished)
        if form.is_valid():
            form.save()
            messages.success(request, f'Finished goods "{finished}" updated successfully!')
            return redirect('inventory:finished_goods_list')
    else:
        form = FinishedGoodsForm(instance=finished)

    context = {
        'active': 'inventory',
        'page_title': 'Edit Finished Goods',
        'form': form,
        'finished_goods': finished,
    }
    return render(request, 'inventory/finished_goods_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_finished_goods_stock(request, pk):
    """
    Add stock to a finished goods item - e.g. a production batch just came
    off the line. Deliberately self-contained within Inventory: no project,
    buyer or supplier from another module is required.
    """
    finished = get_object_or_404(FinishedGoods, pk=pk)
    if request.method == 'POST':
        form = FinishedGoodsStockInForm(request.POST)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            with transaction.atomic():
                FinishedGoods.objects.filter(pk=finished.pk).update(
                    quantity_in_stock=F('quantity_in_stock') + quantity,
                    quantity_produced=F('quantity_produced') + quantity,
                )
                movement = StockMovement.objects.create(
                    movement_type='production',
                    reference_number='',
                    reference_id=finished.pk,
                    finished_goods=finished,
                    quantity=quantity,
                    notes=form.cleaned_data['notes'],
                    created_by=request.user,
                )
                movement.reference_number = movement.movement_number
                movement.save(update_fields=['reference_number'])

            messages.success(request, f'Added {quantity} units to "{finished}" stock.')
            return redirect('inventory:finished_goods_stock_ledger', pk=finished.pk)
    else:
        form = FinishedGoodsStockInForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Stock',
        'form': form,
        'finished_goods': finished,
    }
    return render(request, 'inventory/finished_goods_stock_in_form.html', context)

@login_required
def finished_goods_stock_ledger(request, pk):
    """
    All stock-affecting activity (stock added, approved dispatches) for a
    single finished goods item, newest first, with a running balance.
    """
    finished = get_object_or_404(FinishedGoods, pk=pk)
    movements = list(
        StockMovement.objects.filter(finished_goods=finished).order_by('movement_date', 'created_at')
    )

    total_delta = sum((m.quantity for m in movements), Decimal('0'))
    running_balance = Decimal(finished.quantity_in_stock) - total_delta
    for movement in movements:
        running_balance += movement.quantity
        movement.balance_after = running_balance

    movements.reverse()  # newest first for display

    context = {
        'active': 'inventory',
        'page_title': f'Stock Ledger - {finished.style}',
        'finished_goods': finished,
        'movements': movements,
        'pending_dispatch_items': finished.dispatch_items.exclude(
            dispatch__status='dispatched'
        ).select_related('dispatch'),
    }
    return render(request, 'inventory/finished_goods_stock_ledger.html', context)

@login_required
def dispatches(request):
    """List all dispatches"""
    dispatches = Dispatch.objects.select_related('project', 'project__buyer', 'created_by').all()

    # Filter by status
    status = request.GET.get('status')
    if status:
        dispatches = dispatches.filter(status=status)

    context = {
        'active': 'inventory',
        'page_title': 'Dispatches',
        'dispatches': dispatches,
        'statuses': Dispatch.STATUS_CHOICES,
        'current_status': status,
    }
    return render(request, 'inventory/dispatches.html', context)

def _parse_dispatch_rows(request):
    """
    Read the dispatch item rows (finished_goods_ids[]/carton_numbers[]/
    quantities[]) from the POST data. Returns (rows, errors). Each product's
    total across all rows must fit in its available stock - i.e. what's in
    stock minus what other pending/on-going dispatches have already claimed.
    """
    finished_goods_ids = request.POST.getlist('finished_goods_ids[]')
    quantities = request.POST.getlist('quantities[]')
    carton_numbers = request.POST.getlist('carton_numbers[]')

    rows, errors = [], []
    for i, raw_qty in enumerate(quantities):
        fg_id = finished_goods_ids[i] if i < len(finished_goods_ids) else ''
        if not raw_qty and not fg_id:
            continue  # blank row
        if not fg_id:
            errors.append(f"Row {i + 1}: select a product.")
            continue
        try:
            quantity = int(raw_qty)
        except ValueError:
            errors.append(f"Row {i + 1}: quantity must be a whole number.")
            continue
        if quantity <= 0:
            errors.append(f"Row {i + 1}: quantity must be greater than 0.")
            continue
        carton = (carton_numbers[i] if i < len(carton_numbers) else '').strip()
        rows.append({
            'finished_goods_id': int(fg_id),
            'quantity': quantity,
            'carton_number': carton or f"CTN-{i + 1:04d}",
        })

    if not rows and not errors:
        errors.append("Add at least one product to the dispatch.")

    requested = {}
    for row in rows:
        requested[row['finished_goods_id']] = requested.get(row['finished_goods_id'], 0) + row['quantity']
    products = FinishedGoods.with_pending_dispatch().in_bulk(list(requested))
    for fg_id, quantity in requested.items():
        fg = products.get(fg_id)
        if fg is None:
            errors.append("One of the selected products no longer exists.")
        elif quantity > fg.available_stock:
            errors.append(
                f'"{fg}": only {fg.available_stock} available '
                f'({fg.quantity_in_stock} in stock, {fg.pending_dispatch_qty} already on pending dispatches).'
            )

    return rows, errors

def _dispatch_product_choices():
    """Products for the dispatch item dropdown - only ones with something available."""
    return [
        fg for fg in FinishedGoods.with_pending_dispatch(
            FinishedGoods.objects.filter(is_active=True, quantity_in_stock__gt=0)
        )
        if fg.available_stock > 0
    ]

@login_required
@user_passes_test(is_inventory_or_admin)
def add_dispatch(request):
    """
    Create a dispatch. Stock doesn't move yet - the quantities show as
    "Pending Dispatch" on Finished Goods until an admin approves the
    dispatch as Dispatched (see approve_dispatch).
    """
    rows = []
    if request.method == 'POST':
        form = DispatchForm(request.POST)
        rows, row_errors = _parse_dispatch_rows(request)
        if form.is_valid() and not row_errors:
            with transaction.atomic():
                dispatch = form.save(commit=False)
                dispatch.created_by = request.user
                dispatch.save()
                DispatchDetail.objects.bulk_create([
                    DispatchDetail(dispatch=dispatch, **row) for row in rows
                ])
                dispatch.total_quantity = sum(row['quantity'] for row in rows)
                dispatch.save(update_fields=['total_quantity'])

            messages.success(
                request,
                f'Dispatch "{dispatch.dispatch_number}" created. Its items show as Pending Dispatch '
                'on Finished Goods until it is approved as Dispatched.'
            )
            return redirect('inventory:dispatch_detail', pk=dispatch.pk)
        for err in row_errors:
            messages.error(request, err)
    else:
        form = DispatchForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Dispatch',
        'form': form,
        'finished_goods': _dispatch_product_choices(),
        'posted_rows': rows,
    }
    return render(request, 'inventory/dispatch_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def edit_dispatch(request, pk):
    """
    Edit a dispatch's header fields. Line items aren't editable here, and
    status changes go through update_dispatch_status instead, since
    'Dispatched' needs approval.
    """
    dispatch = get_object_or_404(Dispatch, pk=pk)
    if request.method == 'POST':
        form = DispatchForm(request.POST, instance=dispatch)
        if form.is_valid():
            form.save()
            messages.success(request, f'Dispatch "{dispatch.dispatch_number}" updated successfully!')
            return redirect('inventory:dispatch_detail', pk=dispatch.pk)
    else:
        form = DispatchForm(instance=dispatch)

    context = {
        'active': 'inventory',
        'page_title': 'Edit Dispatch',
        'form': form,
        'dispatch': dispatch,
    }
    return render(request, 'inventory/dispatch_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
@require_POST
def delete_dispatch(request, pk):
    """
    Delete a dispatch that hasn't been approved as Dispatched yet. Nothing
    to undo stock-wise - stock only moves at approval - so this simply
    frees its reserved (pending dispatch) quantities.
    """
    dispatch = get_object_or_404(Dispatch, pk=pk)
    if dispatch.is_status_locked:
        messages.error(request, "This dispatch has already been dispatched and can't be deleted.")
        return redirect('inventory:dispatch_detail', pk=dispatch.pk)
    number = dispatch.dispatch_number
    dispatch.delete()
    messages.success(request, f'Dispatch "{number}" deleted.')
    return redirect('inventory:dispatches')

@login_required
def dispatch_detail(request, pk):
    """Full view of a dispatch: header, line items, and status/approval controls."""
    dispatch = get_object_or_404(
        Dispatch.objects.select_related(
            'project', 'project__buyer', 'created_by',
            'approval_requested_by', 'approved_by',
        ),
        pk=pk,
    )
    context = {
        'active': 'inventory',
        'page_title': f'Dispatch {dispatch.dispatch_number}',
        'dispatch': dispatch,
        'items': dispatch.items.select_related('finished_goods'),
        'statuses': Dispatch.STATUS_CHOICES,
    }
    return render(request, 'inventory/dispatch_detail.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def update_dispatch_status(request, pk):
    """
    Update a dispatch's status. Pending and On-going apply right away.
    Setting it to 'Dispatched' creates a request that only a superuser can
    approve (approve_dispatch). Once approved, the status is locked and
    this view refuses all further changes.
    """
    dispatch = get_object_or_404(Dispatch, pk=pk)
    if request.method == 'POST':
        if dispatch.is_status_locked:
            messages.error(request, "This dispatch has been approved as Dispatched and its status can no longer be changed.")
        else:
            new_status = request.POST.get('status')
            valid_statuses = dict(Dispatch.STATUS_CHOICES)
            if new_status not in valid_statuses:
                messages.error(request, "Invalid status.")
            elif new_status == 'dispatched':
                dispatch.dispatch_approval = 'pending'
                dispatch.approval_requested_by = request.user
                dispatch.save(update_fields=['dispatch_approval', 'approval_requested_by'])
                messages.success(request, "Sent for approval - the status will change to Dispatched once an admin approves it.")
            else:
                dispatch.status = new_status
                dispatch.save(update_fields=['status'])
                messages.success(request, f'Status updated to "{valid_statuses[new_status]}".')
    return redirect('inventory:dispatch_detail', pk=dispatch.pk)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_dispatch(request, pk):
    """
    Approve a pending 'Dispatched' request. This is the moment finished
    goods stock is deducted, and the status is locked from then on.
    """
    dispatch = get_object_or_404(Dispatch.objects.select_related('project__buyer'), pk=pk)
    if request.method == 'POST' and dispatch.dispatch_approval == 'pending':
        try:
            with transaction.atomic():
                for item in dispatch.items.all():
                    fg = FinishedGoods.objects.select_for_update().get(pk=item.finished_goods_id)
                    if item.quantity > fg.quantity_in_stock:
                        raise ValueError(
                            f'Can\'t dispatch {item.quantity} of "{fg}": only {fg.quantity_in_stock} in stock.'
                        )
                    fg.quantity_in_stock -= item.quantity
                    fg.quantity_dispatched += item.quantity
                    fg.save(update_fields=['quantity_in_stock', 'quantity_dispatched', 'updated_at'])
                    StockMovement.objects.create(
                        movement_type='dispatch',
                        reference_number=dispatch.dispatch_number,
                        reference_id=dispatch.pk,
                        finished_goods=fg,
                        quantity=-item.quantity,
                        notes=f"Dispatched to {dispatch.project.buyer.buyer_name}",
                        created_by=request.user,
                    )
                dispatch.status = 'dispatched'
                dispatch.dispatch_approval = 'approved'
                dispatch.approved_by = request.user
                dispatch.approved_date = date.today()
                dispatch.save(update_fields=['status', 'dispatch_approval', 'approved_by', 'approved_date'])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Dispatch "{dispatch.dispatch_number}" approved as Dispatched - stock updated.')
    return _redirect_back(request, 'inventory:dispatch_detail', pk=dispatch.pk)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_dispatch(request, pk):
    """Reject a pending 'Dispatched' request - status stays as it was, and it can be requested again later."""
    dispatch = get_object_or_404(Dispatch, pk=pk)
    if request.method == 'POST' and dispatch.dispatch_approval == 'pending':
        dispatch.dispatch_approval = 'rejected'
        dispatch.approved_by = request.user
        dispatch.approved_date = date.today()
        dispatch.save(update_fields=['dispatch_approval', 'approved_by', 'approved_date'])
        messages.success(request, f'Dispatched request for "{dispatch.dispatch_number}" rejected.')
    return _redirect_back(request, 'inventory:dispatch_detail', pk=dispatch.pk)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def pending_approvals(request):
    """
    Everything awaiting superuser approval: Dispatches waiting to be marked
    Dispatched, Machine sold/scrapped requests, and Supply (Spare Part /
    Stationery) Adjustments - superuser only.
    """
    pending_dispatches = Dispatch.objects.filter(dispatch_approval='pending').select_related(
        'project', 'project__buyer', 'approval_requested_by'
    )

    machine_events = MachineEvent.objects.filter(status='pending').select_related(
        'machine', 'created_by'
    )

    supply_adjustments_pending = SupplyAdjustment.objects.filter(status='pending').select_related(
        'spare_part', 'stationery_item', 'created_by'
    )

    context = {
        'active': 'inventory',
        'page_title': 'Pending Approvals',
        'pending_dispatches': pending_dispatches,
        'machine_events': machine_events,
        'supply_adjustments_pending': supply_adjustments_pending,
    }
    return render(request, 'inventory/pending_approvals.html', context)

TOP_N = 10

STOCK_STATUS_LABELS = {'in_stock': 'In Stock', 'out_of_stock': 'Out of Stock'}

def _fabric_report_rows(queryset):
    return [{
        'code': fabric.fabric_code,
        'name': fabric.fabric_name,
        'color': fabric.color,
        'stock': fabric.current_stock,
        'unit': fabric.unit,
        'status': fabric.stock_status,
    } for fabric in queryset]

def _trim_report_rows(queryset):
    return [{
        'code': trim.trim_code,
        'name': trim.trim_name,
        'stock': trim.current_stock,
        'unit': trim.unit,
        'status': trim.stock_status,
    } for trim in queryset]

def _finished_goods_report_rows(queryset):
    return [{
        'style': fg.style,
        'size': fg.size,
        'color': fg.color,
        'in_stock': fg.quantity_in_stock,
        'pending_dispatch': fg.pending_dispatch_qty,
        'dispatched': fg.quantity_dispatched,
    } for fg in queryset]

@login_required
def stock_report(request):
    """
    Stock report overview - top 10 most recently updated items per
    category, with a 'View All' link to the full paginated/searchable
    list page and PDF/Excel export of the complete data.
    """
    fabrics = Fabric.objects.filter(is_active=True)
    trims = Trim.objects.filter(is_active=True)
    finished = FinishedGoods.with_pending_dispatch(FinishedGoods.objects.filter(is_active=True))

    context = {
        'active': 'inventory',
        'page_title': 'Stock Report',
        'fabric_data': _fabric_report_rows(fabrics.order_by('-updated_at')[:TOP_N]),
        'trim_data': _trim_report_rows(trims.order_by('-updated_at')[:TOP_N]),
        'finished_data': _finished_goods_report_rows(finished.order_by('-updated_at')[:TOP_N]),
        'fabric_total': fabrics.count(),
        'trim_total': trims.count(),
        'finished_total': finished.count(),
        'top_n': TOP_N,
    }
    return render(request, 'inventory/stock_report.html', context)

def _stock_report_sections():
    """(title, headers, rows) for each category of the full stock report exports."""
    finished = FinishedGoods.with_pending_dispatch(FinishedGoods.objects.filter(is_active=True))
    return [
        ('Fabrics',
         ['Code', 'Name', 'Color', 'Supplier', 'Buyer', 'Stock', 'Unit', 'Status'],
         [(f.fabric_code, f.fabric_name, f.color, f.supplier, f.buyer, float(f.current_stock), f.unit,
           STOCK_STATUS_LABELS[f.stock_status])
          for f in Fabric.objects.filter(is_active=True)]),
        ('Trims',
         ['Code', 'Name', 'Stock', 'Unit', 'Status'],
         [(t.trim_code, t.trim_name, t.current_stock, t.unit, STOCK_STATUS_LABELS[t.stock_status])
          for t in Trim.objects.filter(is_active=True)]),
        ('Finished Goods',
         ['Style', 'Size', 'Color', 'In Stock', 'Pending Dispatch', 'Dispatched'],
         [(fg.style, fg.size, fg.color, fg.quantity_in_stock, fg.pending_dispatch_qty, fg.quantity_dispatched)
          for fg in finished]),
    ]

@login_required
def stock_report_export_excel(request):
    """Full (untruncated) stock report as a 3-sheet Excel workbook."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', start_color='4472C4')
    header_align = Alignment(horizontal='center')

    for title, headers, rows in _stock_report_sections():
        ws = wb.create_sheet(title)
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            ws.column_dimensions[get_column_letter(col)].width = 18
        for row_idx, row in enumerate(rows, start=2):
            for col_idx, value in enumerate(row, start=1):
                ws.cell(row=row_idx, column=col_idx, value=value)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="stock_report_{date.today():%Y%m%d}.xlsx"'
    wb.save(response)
    return response

@login_required
def stock_report_export_pdf(request):
    """Full (untruncated) stock report as a landscape PDF, one table per category."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="stock_report_{date.today():%Y%m%d}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4),
                             leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    elements = [Paragraph('Stock Report', styles['Title']), Spacer(1, 0.5 * cm)]

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F2F2')]),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])

    for title, headers, rows in _stock_report_sections():
        elements.append(Paragraph(title, styles['Heading2']))
        table = Table([headers] + [[str(v) for v in row] for row in rows], repeatRows=1)
        table.setStyle(table_style)
        elements.append(table)
        elements.append(Spacer(1, 0.7 * cm))

    doc.build(elements)
    return response

# =============================================================== machines

@login_required
def machine_list(request):
    """List all machines"""
    machines = Machine.objects.select_related('department', 'supplier')

    search = request.GET.get('search')
    if search:
        machines = machines.filter(
            Q(machine_code__icontains=search) |
            Q(machine_name__icontains=search) |
            Q(brand__icontains=search) |
            Q(serial_number__icontains=search)
        )

    machine_type = request.GET.get('type')
    if machine_type:
        machines = machines.filter(machine_type=machine_type)

    status = request.GET.get('status')
    if status:
        machines = machines.filter(status=status)

    department_id = request.GET.get('department')
    if department_id:
        machines = machines.filter(department_id=department_id)

    paginator = Paginator(machines, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    from apps.hr.models import Department
    context = {
        'active': 'inventory',
        'page_title': 'Machines',
        'machines': page_obj,
        'machine_types': Machine.MACHINE_TYPES,
        'statuses': Machine.STATUS_CHOICES,
        'departments': Department.objects.all(),
        'search': search,
        'current_type': machine_type,
        'current_status': status,
        'current_department': department_id,
    }
    return render(request, 'inventory/machine_list.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_machine(request):
    """Add new machine"""
    if request.method == 'POST':
        form = MachineForm(request.POST)
        if form.is_valid():
            machine = form.save(commit=False)
            machine.created_by = request.user
            machine.save()
            messages.success(request, f'Machine "{machine.machine_code}" added successfully!')
            return redirect('inventory:machine_list')
    else:
        form = MachineForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Machine',
        'form': form,
    }
    return render(request, 'inventory/machine_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def edit_machine(request, pk):
    """Edit machine"""
    machine = get_object_or_404(Machine, pk=pk)
    if request.method == 'POST':
        form = MachineForm(request.POST, instance=machine)
        if form.is_valid():
            form.save()
            messages.success(request, f'Machine "{machine.machine_code}" updated successfully!')
            return redirect('inventory:machine_detail', pk=machine.pk)
    else:
        form = MachineForm(instance=machine)

    context = {
        'active': 'inventory',
        'page_title': 'Edit Machine',
        'form': form,
        'machine': machine,
    }
    return render(request, 'inventory/machine_form.html', context)

@login_required
def machine_detail(request, pk):
    """Machine detail: info + event timeline + recent spare-part consumption against it."""
    machine = get_object_or_404(Machine.objects.select_related('department', 'supplier'), pk=pk)
    context = {
        'active': 'inventory',
        'page_title': f'{machine.machine_code} - {machine.machine_name}',
        'machine': machine,
        'events': machine.events.select_related('created_by', 'approved_by'),
        'spare_part_consumptions': machine.spare_part_consumptions.select_related(
            'spare_part', 'department'
        ).order_by('-consumption_date')[:20],
    }
    return render(request, 'inventory/machine_detail.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_machine_event(request, pk):
    """
    Log an event against a machine. 'Sold'/'Scrapped' are created as
    pending and don't change Machine.status until a superuser approves
    them (approve_machine_event) - mirrors Dispatch.dispatch_approval.
    Every other event type applies immediately and updates Machine.status
    to match.
    """
    machine = get_object_or_404(Machine, pk=pk)
    if request.method == 'POST':
        form = MachineEventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.machine = machine
            event.created_by = request.user

            if event.event_type in ('sold', 'scrapped'):
                event.status = 'pending'
                event.save()
                messages.success(
                    request,
                    f'"{event.get_event_type_display()}" submitted for approval - '
                    'the machine stays active until an admin approves it.'
                )
            else:
                event.status = 'approved'
                event.approved_by = request.user
                event.approved_date = date.today()
                event.save()

                status_map = {
                    'breakdown': 'broken_down',
                    'repair_started': 'under_maintenance',
                    'repair_completed': 'active',
                    'maintenance': 'under_maintenance',
                }
                new_status = status_map.get(event.event_type)
                if new_status and new_status != machine.status:
                    machine.status = new_status
                    machine.save(update_fields=['status'])

                messages.success(request, f'"{event.get_event_type_display()}" logged for {machine.machine_code}.')

            return redirect('inventory:machine_detail', pk=machine.pk)
    else:
        form = MachineEventForm()

    context = {
        'active': 'inventory',
        'page_title': f'Log Event - {machine.machine_code}',
        'form': form,
        'machine': machine,
    }
    return render(request, 'inventory/machine_event_form.html', context)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_machine_event(request, pk, event_pk):
    """Approve a pending Sold/Scrapped request - this is the only place Machine.status becomes sold/scrapped."""
    machine = get_object_or_404(Machine, pk=pk)
    event = get_object_or_404(MachineEvent, pk=event_pk, machine=machine)
    if request.method == 'POST' and event.status == 'pending':
        event.status = 'approved'
        event.approved_by = request.user
        event.approved_date = date.today()
        event.save(update_fields=['status', 'approved_by', 'approved_date'])

        machine.status = event.event_type  # 'sold'/'scrapped' match Machine.STATUS_CHOICES exactly
        machine.save(update_fields=['status'])

        messages.success(request, f'"{event.get_event_type_display()}" approved for {machine.machine_code}.')
    return redirect('inventory:machine_detail', pk=machine.pk)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_machine_event(request, pk, event_pk):
    """Reject a pending Sold/Scrapped request - Machine.status is untouched."""
    machine = get_object_or_404(Machine, pk=pk)
    event = get_object_or_404(MachineEvent, pk=event_pk, machine=machine)
    if request.method == 'POST' and event.status == 'pending':
        form = RejectMachineEventForm(request.POST)
        if form.is_valid():
            event.status = 'rejected'
            event.rejection_reason = form.cleaned_data['rejection_reason']
            event.approved_by = request.user
            event.approved_date = date.today()
            event.save(update_fields=['status', 'rejection_reason', 'approved_by', 'approved_date'])
            messages.success(request, f'"{event.get_event_type_display()}" request rejected.')
        else:
            messages.error(request, "A rejection reason is required.")
    return redirect('inventory:machine_detail', pk=machine.pk)

# ============================================================= spare parts

@login_required
def spare_part_list(request):
    """List all spare parts"""
    parts = SparePart.objects.filter(is_active=True).select_related('supplier')

    search = request.GET.get('search')
    if search:
        parts = parts.filter(Q(part_name__icontains=search))

    category = request.GET.get('category')
    if category:
        parts = parts.filter(category=category)

    stock_status = request.GET.get('stock_status')
    if stock_status == 'low':
        parts = parts.filter(current_stock__lte=F('min_stock'))
    elif stock_status == 'normal':
        parts = parts.filter(current_stock__gt=F('min_stock'), current_stock__lt=F('max_stock'))
    elif stock_status == 'overstock':
        parts = parts.filter(current_stock__gte=F('max_stock'))

    paginator = Paginator(parts, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'active': 'inventory',
        'page_title': 'Spare Parts',
        'spare_parts': page_obj,
        'categories': SparePart.CATEGORY_CHOICES,
        'search': search,
        'current_category': category,
        'current_stock_status': stock_status,
    }
    return render(request, 'inventory/spare_part_list.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_spare_part(request):
    """Add new spare part"""
    if request.method == 'POST':
        form = SparePartForm(request.POST)
        if form.is_valid():
            part = form.save()
            messages.success(request, f'Spare part "{part.part_name}" added successfully!')
            return redirect('inventory:spare_part_list')
    else:
        form = SparePartForm()

    context = {'active': 'inventory', 'page_title': 'Add Spare Part', 'form': form}
    return render(request, 'inventory/spare_part_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def edit_spare_part(request, pk):
    """Edit spare part"""
    part = get_object_or_404(SparePart, pk=pk)
    if request.method == 'POST':
        form = SparePartForm(request.POST, instance=part)
        if form.is_valid():
            form.save()
            messages.success(request, f'Spare part "{part.part_name}" updated successfully!')
            return redirect('inventory:spare_part_list')
    else:
        form = SparePartForm(instance=part)

    context = {'active': 'inventory', 'page_title': 'Edit Spare Part', 'form': form, 'spare_part': part}
    return render(request, 'inventory/spare_part_form.html', context)

@login_required
def spare_part_stock_ledger(request, pk):
    """All stock-affecting activity for a single spare part, newest first, with a running balance."""
    part = get_object_or_404(SparePart, pk=pk)
    movements = list(StockMovement.objects.filter(spare_part=part).order_by('movement_date', 'created_at'))

    total_delta = sum((m.quantity for m in movements), Decimal('0'))
    running_balance = Decimal(part.current_stock) - total_delta
    for movement in movements:
        running_balance += movement.quantity
        movement.balance_after = running_balance
    movements.reverse()

    context = {
        'active': 'inventory',
        'page_title': f'Stock Ledger - {part.part_name}',
        'spare_part': part,
        'movements': movements,
        'consumptions': part.consumptions.select_related('department', 'machine').order_by('-consumption_date')[:20],
    }
    return render(request, 'inventory/spare_part_stock_ledger.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_spare_part_stock(request, pk):
    """Add stock to a spare part - immediate, no approval (mirrors add_trim_stock)."""
    part = get_object_or_404(SparePart, pk=pk)
    if request.method == 'POST':
        form = SparePartStockInForm(request.POST)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            with transaction.atomic():
                SparePart.objects.filter(pk=part.pk).update(current_stock=F('current_stock') + quantity)
                movement = StockMovement.objects.create(
                    movement_type='receipt', reference_number='', reference_id=part.pk,
                    spare_part=part, quantity=quantity,
                    notes=form.cleaned_data['notes'], created_by=request.user,
                )
                movement.reference_number = movement.movement_number
                movement.save(update_fields=['reference_number'])
            messages.success(request, f'Added {quantity} units to "{part.part_name}" stock.')
            return redirect('inventory:spare_part_stock_ledger', pk=part.pk)
    else:
        form = SparePartStockInForm()

    context = {'active': 'inventory', 'page_title': 'Add Stock', 'form': form, 'spare_part': part}
    return render(request, 'inventory/spare_part_stock_in_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def record_spare_part_consumption(request, pk):
    """
    Record a department's (optionally machine-linked) use of a spare part.
    Immediate - not approval-gated, this is routine maintenance logging,
    not a correction (see SupplyAdjustment for corrections).
    """
    part = get_object_or_404(SparePart, pk=pk)
    if request.method == 'POST':
        form = SparePartConsumptionForm(request.POST)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            if quantity > part.current_stock:
                messages.error(request, f"Can't consume {quantity}: only {part.current_stock} in stock.")
            else:
                department = form.cleaned_data['department']
                with transaction.atomic():
                    SparePartConsumption.objects.create(
                        spare_part=part,
                        department=department,
                        machine=form.cleaned_data['machine'],
                        quantity=quantity,
                        unit_price_at_consumption=part.unit_price,
                        consumption_date=form.cleaned_data['consumption_date'],
                        notes=form.cleaned_data['notes'],
                        issued_by=request.user,
                    )
                    SparePart.objects.filter(pk=part.pk).update(current_stock=F('current_stock') - quantity)
                    movement = StockMovement.objects.create(
                        movement_type='issue', reference_number='', reference_id=part.pk,
                        spare_part=part, quantity=-quantity,
                        notes=f"Issued to {department.name}", created_by=request.user,
                    )
                    movement.reference_number = movement.movement_number
                    movement.save(update_fields=['reference_number'])
                messages.success(request, f'Recorded consumption of {quantity} units of "{part.part_name}".')
                return redirect('inventory:spare_part_stock_ledger', pk=part.pk)
    else:
        form = SparePartConsumptionForm()

    context = {'active': 'inventory', 'page_title': 'Record Consumption', 'form': form, 'spare_part': part}
    return render(request, 'inventory/spare_part_consumption_form.html', context)

# ============================================================== stationery

@login_required
def stationery_list(request):
    """List all stationery items"""
    items = StationeryItem.objects.filter(is_active=True)

    search = request.GET.get('search')
    if search:
        items = items.filter(Q(item_name__icontains=search))

    category = request.GET.get('category')
    if category:
        items = items.filter(category=category)

    stock_status = request.GET.get('stock_status')
    if stock_status == 'low':
        items = items.filter(current_stock__lte=F('min_stock'))
    elif stock_status == 'normal':
        items = items.filter(current_stock__gt=F('min_stock'), current_stock__lt=F('max_stock'))
    elif stock_status == 'overstock':
        items = items.filter(current_stock__gte=F('max_stock'))

    paginator = Paginator(items, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'active': 'inventory',
        'page_title': 'Stationery',
        'stationery_items': page_obj,
        'categories': StationeryItem.CATEGORY_CHOICES,
        'search': search,
        'current_category': category,
        'current_stock_status': stock_status,
    }
    return render(request, 'inventory/stationery_list.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_stationery_item(request):
    """Add new stationery item"""
    if request.method == 'POST':
        form = StationeryItemForm(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, f'Stationery item "{item.item_name}" added successfully!')
            return redirect('inventory:stationery_list')
    else:
        form = StationeryItemForm()

    context = {'active': 'inventory', 'page_title': 'Add Stationery Item', 'form': form}
    return render(request, 'inventory/stationery_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def edit_stationery_item(request, pk):
    """Edit stationery item"""
    item = get_object_or_404(StationeryItem, pk=pk)
    if request.method == 'POST':
        form = StationeryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f'Stationery item "{item.item_name}" updated successfully!')
            return redirect('inventory:stationery_list')
    else:
        form = StationeryItemForm(instance=item)

    context = {'active': 'inventory', 'page_title': 'Edit Stationery Item', 'form': form, 'stationery_item': item}
    return render(request, 'inventory/stationery_form.html', context)

@login_required
def stationery_stock_ledger(request, pk):
    """All stock-affecting activity for a single stationery item, newest first, with a running balance."""
    item = get_object_or_404(StationeryItem, pk=pk)
    movements = list(StockMovement.objects.filter(stationery_item=item).order_by('movement_date', 'created_at'))

    total_delta = sum((m.quantity for m in movements), Decimal('0'))
    running_balance = Decimal(item.current_stock) - total_delta
    for movement in movements:
        running_balance += movement.quantity
        movement.balance_after = running_balance
    movements.reverse()

    context = {
        'active': 'inventory',
        'page_title': f'Stock Ledger - {item.item_name}',
        'stationery_item': item,
        'movements': movements,
        'consumptions': item.consumptions.select_related('department').order_by('-consumption_date')[:20],
    }
    return render(request, 'inventory/stationery_stock_ledger.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_stationery_stock(request, pk):
    """Add stock to a stationery item - immediate, no approval."""
    item = get_object_or_404(StationeryItem, pk=pk)
    if request.method == 'POST':
        form = StationeryStockInForm(request.POST)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            with transaction.atomic():
                StationeryItem.objects.filter(pk=item.pk).update(current_stock=F('current_stock') + quantity)
                movement = StockMovement.objects.create(
                    movement_type='receipt', reference_number='', reference_id=item.pk,
                    stationery_item=item, quantity=quantity,
                    notes=form.cleaned_data['notes'], created_by=request.user,
                )
                movement.reference_number = movement.movement_number
                movement.save(update_fields=['reference_number'])
            messages.success(request, f'Added {quantity} units to "{item.item_name}" stock.')
            return redirect('inventory:stationery_stock_ledger', pk=item.pk)
    else:
        form = StationeryStockInForm()

    context = {'active': 'inventory', 'page_title': 'Add Stock', 'form': form, 'stationery_item': item}
    return render(request, 'inventory/stationery_stock_in_form.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def record_stationery_consumption(request, pk):
    """Record a department's use of a stationery item - immediate, not approval-gated."""
    item = get_object_or_404(StationeryItem, pk=pk)
    if request.method == 'POST':
        form = StationeryConsumptionForm(request.POST)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            if quantity > item.current_stock:
                messages.error(request, f"Can't consume {quantity}: only {item.current_stock} in stock.")
            else:
                department = form.cleaned_data['department']
                with transaction.atomic():
                    StationeryConsumption.objects.create(
                        stationery_item=item,
                        department=department,
                        quantity=quantity,
                        unit_price_at_consumption=item.unit_price,
                        consumption_date=form.cleaned_data['consumption_date'],
                        notes=form.cleaned_data['notes'],
                        issued_by=request.user,
                    )
                    StationeryItem.objects.filter(pk=item.pk).update(current_stock=F('current_stock') - quantity)
                    movement = StockMovement.objects.create(
                        movement_type='issue', reference_number='', reference_id=item.pk,
                        stationery_item=item, quantity=-quantity,
                        notes=f"Issued to {department.name}", created_by=request.user,
                    )
                    movement.reference_number = movement.movement_number
                    movement.save(update_fields=['reference_number'])
                messages.success(request, f'Recorded consumption of {quantity} units of "{item.item_name}".')
                return redirect('inventory:stationery_stock_ledger', pk=item.pk)
    else:
        form = StationeryConsumptionForm()

    context = {'active': 'inventory', 'page_title': 'Record Consumption', 'form': form, 'stationery_item': item}
    return render(request, 'inventory/stationery_consumption_form.html', context)

# ========================================================= supply adjustments

@login_required
def supply_adjustments(request):
    """List all supply adjustments (Spare Parts + Stationery)"""
    adjustments = SupplyAdjustment.objects.select_related(
        'spare_part', 'stationery_item', 'created_by', 'approved_by'
    )
    context = {
        'active': 'inventory',
        'page_title': 'Supply Adjustments',
        'adjustments': adjustments,
    }
    return render(request, 'inventory/supply_adjustments.html', context)

@login_required
@user_passes_test(is_inventory_or_admin)
def add_supply_adjustment(request):
    """Request a correction for a Spare Part or Stationery Item - pending until a superuser approves it."""
    if request.method == 'POST':
        form = SupplyAdjustmentForm(request.POST)
        if form.is_valid():
            adjustment = form.save(commit=False)
            adjustment.status = 'pending'
            adjustment.created_by = request.user
            adjustment.save()
            messages.success(
                request,
                f'Adjustment "{adjustment.adjustment_number}" submitted for approval - '
                'stock will update once an admin approves it.'
            )
            return redirect('inventory:supply_adjustments')
    else:
        form = SupplyAdjustmentForm()

    context = {
        'active': 'inventory',
        'page_title': 'Add Supply Adjustment',
        'form': form,
    }
    return render(request, 'inventory/supply_adjustment_form.html', context)

def _apply_supply_adjustment(adjustment):
    """
    Apply an approved SupplyAdjustment's stock effect. Must be called
    inside a transaction.atomic() block by the caller.
    """
    quantity = adjustment.quantity
    signed_quantity = quantity if adjustment.direction == 'increase' else -quantity

    if adjustment.spare_part_id:
        part = SparePart.objects.select_for_update().get(pk=adjustment.spare_part_id)
        if adjustment.direction == 'decrease' and quantity > part.current_stock:
            raise ValueError(f"Can't decrease stock by {quantity}: only {part.current_stock} in stock.")
        part.current_stock += signed_quantity
        part.save(update_fields=['current_stock'])
    elif adjustment.stationery_item_id:
        item = StationeryItem.objects.select_for_update().get(pk=adjustment.stationery_item_id)
        if adjustment.direction == 'decrease' and quantity > item.current_stock:
            raise ValueError(f"Can't decrease stock by {quantity}: only {item.current_stock} in stock.")
        item.current_stock += signed_quantity
        item.save(update_fields=['current_stock'])

    StockMovement.objects.create(
        movement_type='adjustment',
        reference_number=adjustment.adjustment_number,
        reference_id=adjustment.pk,
        spare_part_id=adjustment.spare_part_id,
        stationery_item_id=adjustment.stationery_item_id,
        quantity=signed_quantity,
        notes=adjustment.reason,
        created_by=adjustment.approved_by,
    )

@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_supply_adjustment(request, pk):
    """Approve a pending supply adjustment - this is the only place stock actually changes."""
    adjustment = get_object_or_404(SupplyAdjustment, pk=pk)
    if request.method == 'POST' and adjustment.status == 'pending':
        try:
            with transaction.atomic():
                adjustment.approved_by = request.user
                adjustment.approved_date = date.today()
                _apply_supply_adjustment(adjustment)
                adjustment.status = 'approved'
                adjustment.save(update_fields=['status', 'approved_by', 'approved_date'])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Adjustment "{adjustment.adjustment_number}" approved - stock updated.')
    return redirect('inventory:supply_adjustments')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_supply_adjustment(request, pk):
    """Reject a pending supply adjustment - no stock change."""
    adjustment = get_object_or_404(SupplyAdjustment, pk=pk)
    if request.method == 'POST' and adjustment.status == 'pending':
        form = RejectSupplyAdjustmentForm(request.POST)
        if form.is_valid():
            adjustment.status = 'rejected'
            adjustment.rejection_reason = form.cleaned_data['rejection_reason']
            adjustment.approved_by = request.user
            adjustment.approved_date = date.today()
            adjustment.save(update_fields=['status', 'rejection_reason', 'approved_by', 'approved_date'])
            messages.success(request, f'Adjustment "{adjustment.adjustment_number}" rejected.')
        else:
            messages.error(request, "A rejection reason is required.")
    return redirect('inventory:supply_adjustments')
