from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal
from datetime import date, timedelta

class Fabric(models.Model):
    """Fabric master data"""
    FABRIC_TYPES = [
        ('shell', 'Shell'),
        ('lining', 'Lining'),
        ('interlining', 'Interlining'),
        ('inner-lining', 'Inner-lining'),
        ('pocket', 'Pocket'),
        ('cotton', 'Cotton'),
        ('polyester', 'Polyester'),
        ('denim', 'Denim'),
        ('silk', 'Silk'),
        ('wool', 'Wool'),
        ('linen', 'Linen'),
        ('blend', 'Blend'),
        ('other', 'Other'),
    ]

    UNIT_CHOICES = [
        ('meter', 'Meter'),
        ('kg', 'Kilogram'),
        ('yard', 'Yard'),
        ('roll', 'Roll'),
    ]

    fabric_name = models.CharField(max_length=200)
    fabric_type = models.CharField(max_length=20, choices=FABRIC_TYPES, default='cotton')
    color = models.CharField(max_length=50)
    gsm = models.IntegerField(help_text="Grams per square meter")
    width = models.DecimalField(max_digits=10, decimal_places=2, help_text="Width in inches")
    # Plain text instead of links to Accounts - so a fabric can be recorded
    # without first setting up the supplier/project/PO/buyer elsewhere.
    supplier = models.CharField(max_length=200, blank=True)
    project = models.CharField(max_length=200, blank=True)
    purchase_order = models.CharField(max_length=100, blank=True)
    buyer = models.CharField(max_length=200, blank=True)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='meter')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def fabric_code(self):
        return f"F-{self.pk:05d}"

    def __str__(self):
        return f"{self.fabric_code} - {self.fabric_name}"

    @property
    def stock_status(self):
        return 'in_stock' if self.current_stock > 0 else 'out_of_stock'

class FabricRoll(models.Model):
    """Individual fabric rolls with tracking"""
    STATUS_CHOICES = [
        ('in_stock', 'In Stock'),
        ('issued', 'Issued to Production'),
        ('finished', 'Fully Used'),
        ('damaged', 'Damaged'),
        ('returned', 'Returned to Supplier'),
    ]

    roll_number = models.CharField(max_length=50, unique=True)
    fabric = models.ForeignKey(Fabric, on_delete=models.CASCADE, related_name='rolls')
    lot_number = models.CharField(max_length=50, unique=True)
    length = models.DecimalField(max_digits=10, decimal_places=2)
    used_length = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_length = models.DecimalField(max_digits=10, decimal_places=2)
    location = models.CharField(max_length=100)
    rack_number = models.CharField(max_length=50, blank=True)
    bin_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_stock')
    received_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    quality_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending Inspection'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
    ], default='pending')
    inspector_name = models.CharField(max_length=100, blank=True)
    inspection_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.remaining_length = self.length - self.used_length
        if self.remaining_length <= 0:
            self.status = 'finished'
        elif self.status == 'finished' and self.remaining_length > 0:
            # A correction (e.g. an "increase" adjustment reducing used_length)
            # brought this lot back above zero - it's usable again.
            self.status = 'in_stock'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.roll_number} - {self.fabric.fabric_name} ({self.remaining_length} {self.fabric.unit})"

    @property
    def utilization_percentage(self):
        if self.length > 0:
            return (self.used_length / self.length) * 100
        return 0

    class Meta:
        ordering = ['-received_date']

class Trim(models.Model):
    """Trim items like buttons, zippers, threads, etc."""
    TRIM_TYPES = [
        ('thread', 'Thread'),
        ('button', 'Button'),
        ('zipper', 'Zipper'),
        ('label', 'Label'),
        ('elastic', 'Elastic'),
        ('ribbon', 'Ribbon'),
        ('lace', 'Lace'),
        ('tag', 'Tag'),
        ('hook', 'Hook & Loop'),
        ('other', 'Other'),
    ]

    trim_name = models.CharField(max_length=200)
    trim_type = models.CharField(max_length=20, choices=TRIM_TYPES)
    supplier = models.ForeignKey('accounts.Supplier', on_delete=models.SET_NULL, null=True, related_name='trims')
    unit = models.CharField(max_length=20)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    current_stock = models.IntegerField(default=0)
    color = models.CharField(max_length=50, blank=True)
    size = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def trim_code(self):
        return f"T-{self.pk:05d}"

    def __str__(self):
        return f"{self.trim_code} - {self.trim_name}"

    @property
    def stock_status(self):
        return 'in_stock' if self.current_stock > 0 else 'out_of_stock'


class GoodsReceipt(models.Model):
    """
    Goods receipt from suppliers.

    A GR only ever ADDS to fabric stock - there's no accept/reject/QC split
    here. Fabric stock goes down through the Transfer Stock (-) action on the
    Fabric Management page instead.
    """
    supplier = models.ForeignKey('accounts.Supplier', on_delete=models.CASCADE, related_name='receipts')
    receipt_date = models.DateField(auto_now_add=True)
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField(null=True, blank=True)
    # Sum of this receipt's line-item quantities - recalculated whenever
    # items are added, so it always starts at 0 rather than being required
    # up front.
    total_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='received_goods')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.receipt_number} - {self.supplier.supplier_name}"

    @property
    def receipt_number(self):
        """
        Human-readable receipt reference, generated on the fly instead of
        stored in the DB - so it never needs a separate sequence/counter
        and can never go out of sync or collide.

        Format: GR-YYMMDD-00001
          - YYMMDD: the date the receipt was created (receipt_date)
          - 00001:  the receipt's own id, zero-padded to 5 digits
        """
        if not self.pk or not self.receipt_date:
            return "GR-PENDING"
        return f"GR-{self.receipt_date.strftime('%y%m%d')}-{self.pk:05d}"

    class Meta:
        ordering = ['-receipt_date']

class GoodsReceiptDetail(models.Model):
    """One fabric added to stock via a goods receipt."""
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='items')
    fabric = models.ForeignKey(Fabric, on_delete=models.CASCADE, related_name='receipt_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.goods_receipt.receipt_number} - {self.fabric.fabric_name}"

class TrimReceipt(models.Model):
    """
    Goods receipt from suppliers, for trims (buttons, zippers, thread, etc).
    Mirrors GoodsReceipt exactly - it only ever adds to trim stock.
    """
    supplier = models.ForeignKey('accounts.Supplier', on_delete=models.CASCADE, related_name='trim_receipts')
    receipt_date = models.DateField(auto_now_add=True)
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField(null=True, blank=True)
    # Sum of this receipt's line-item quantities - recalculated whenever
    # items are added, so it always starts at 0 rather than being required
    # up front.
    total_quantity = models.IntegerField(default=0)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='received_trims')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.receipt_number} - {self.supplier.supplier_name}"

    @property
    def receipt_number(self):
        """
        Human-readable receipt reference, generated on the fly instead of
        stored in the DB - same scheme as GoodsReceipt.receipt_number.

        Format: TR-YYMMDD-00001
          - YYMMDD: the date the receipt was created (receipt_date)
          - 00001:  the receipt's own id, zero-padded to 5 digits
        """
        if not self.pk or not self.receipt_date:
            return "TR-PENDING"
        return f"TR-{self.receipt_date.strftime('%y%m%d')}-{self.pk:05d}"

    class Meta:
        ordering = ['-receipt_date']

class TrimReceiptDetail(models.Model):
    """One trim added to stock via a trim receipt."""
    trim_receipt = models.ForeignKey(TrimReceipt, on_delete=models.CASCADE, related_name='items')
    trim = models.ForeignKey(Trim, on_delete=models.CASCADE, related_name='receipt_items')
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.trim_receipt.receipt_number} - {self.trim.trim_name}"

class ProductionIssue(models.Model):
    """Issue materials to production"""
    issue_number = models.CharField(max_length=50, unique=True)
    project = models.ForeignKey('accounts.Project', on_delete=models.CASCADE, related_name='issues')
    issue_date = models.DateField()
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_materials')
    department = models.ForeignKey('hr.Department', on_delete=models.SET_NULL, null=True, related_name='issues')
    production_line = models.CharField(max_length=50)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('partially_used', 'Partially Used'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.issue_number} - {self.project.project_number}"

    class Meta:
        ordering = ['-issue_date']

class ProductionIssueDetail(models.Model):
    """Items in production issue"""
    production_issue = models.ForeignKey(ProductionIssue, on_delete=models.CASCADE, related_name='items')
    fabric = models.ForeignKey(Fabric, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_items')
    fabric_roll = models.ForeignKey(FabricRoll, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_items')
    trim = models.ForeignKey(Trim, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_items')
    quantity_requested = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_issued = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity_returned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    waste_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    @property
    def is_completed(self):
        return self.quantity_issued <= (self.quantity_used + self.quantity_returned + self.waste_quantity)

    def __str__(self):
        item_name = self.fabric.fabric_name if self.fabric else self.trim.trim_name if self.trim else "Unknown"
        return f"{self.production_issue.issue_number} - {item_name}"

class FinishedGoods(models.Model):
    """Finished goods inventory - one row per style + size + color."""
    style = models.CharField(max_length=100)
    size = models.CharField(max_length=20)
    color = models.CharField(max_length=50)
    quantity_produced = models.IntegerField(default=0)
    quantity_in_stock = models.IntegerField(default=0)
    quantity_dispatched = models.IntegerField(default=0)
    quantity_defective = models.IntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    warehouse_location = models.CharField(max_length=100)
    rack_location = models.CharField(max_length=50, blank=True)
    bin_location = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.style} - ({self.size} - {self.color})"

    @property
    def pending_dispatch_qty(self):
        """
        Units already added to dispatches that haven't been approved as
        Dispatched yet. They're still physically in stock (and counted in
        quantity_in_stock) but promised to a buyer, so they can't be put on
        another dispatch. Uses the annotated value when the queryset came
        from with_pending_dispatch(), to avoid a query per row.
        """
        if hasattr(self, '_pending_dispatch_qty'):
            return self._pending_dispatch_qty or 0
        return self.dispatch_items.exclude(
            dispatch__status='dispatched'
        ).aggregate(total=models.Sum('quantity'))['total'] or 0

    @property
    def available_stock(self):
        """In stock and not already reserved by a pending/on-going dispatch."""
        return self.quantity_in_stock - self.pending_dispatch_qty

    @classmethod
    def with_pending_dispatch(cls, queryset=None):
        queryset = cls.objects.all() if queryset is None else queryset
        # Meta.ordering is ignored on aggregated querysets, so re-apply it.
        return queryset.annotate(_pending_dispatch_qty=models.Sum(
            'dispatch_items__quantity',
            filter=~models.Q(dispatch_items__dispatch__status='dispatched'),
        )).order_by(*cls._meta.ordering)

    class Meta:
        ordering = ['style', 'size', 'color']
        verbose_name_plural = 'Finished goods'
        constraints = [
            models.UniqueConstraint(fields=['style', 'size', 'color'], name='unique_finished_goods_style_size_color'),
        ]

class FinishedGoodsProduction(models.Model):
    """Production batch for finished goods"""
    batch_number = models.CharField(max_length=50, unique=True)
    project = models.ForeignKey('accounts.Project', on_delete=models.CASCADE, related_name='production_batches')
    finished_goods = models.ForeignKey(FinishedGoods, on_delete=models.CASCADE, related_name='production_batches')
    production_date = models.DateField()
    quantity_produced = models.IntegerField()
    quantity_defective = models.IntegerField(default=0)
    quantity_good = models.IntegerField()
    production_line = models.CharField(max_length=50)
    supervisor = models.CharField(max_length=100)
    quality_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending QC'),
        ('passed', 'Passed'),
        ('rejected', 'Rejected'),
        ('partial', 'Partially Passed'),
    ], default='pending')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='batches')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.quantity_good = self.quantity_produced - self.quantity_defective
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.batch_number} - {self.project.project_number}"

    @property
    def quality_rate(self):
        if self.quantity_produced > 0:
            return (self.quantity_good / self.quantity_produced) * 100
        return 0

    class Meta:
        ordering = ['-production_date']

class Dispatch(models.Model):
    """
    Dispatch finished goods to buyers.

    Flow: Pending -> On-going -> Dispatched. Pending and On-going can be
    set freely. Dispatched needs superuser approval; finished-goods stock is
    only deducted at the moment of approval, and after that the status is
    locked. Until then the dispatch's quantities show up as "Pending
    Dispatch" on the Finished Goods page.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('on_going', 'On-going'),
        ('dispatched', 'Dispatched'),
    ]

    APPROVAL_CHOICES = [
        ('none', 'Not Requested'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    dispatch_number = models.CharField(max_length=50, unique=True)
    project = models.ForeignKey('accounts.Project', on_delete=models.CASCADE, related_name='dispatches')
    dispatch_date = models.DateField(default=date.today)
    total_cartons = models.IntegerField()
    # Computed from line items after they're added (see add_dispatch), so it
    # isn't known at the header's initial save() - needs a default like
    # GoodsReceipt/TrimReceipt.total_quantity, not left NOT NULL with none.
    total_quantity = models.IntegerField(default=0)
    shipping_line = models.CharField(max_length=200)
    vessel_name = models.CharField(max_length=200, blank=True)
    vessel_number = models.CharField(max_length=100, blank=True)
    container_number = models.CharField(max_length=50, blank=True)
    container_size = models.CharField(max_length=20, blank=True)
    bl_number = models.CharField(max_length=100, blank=True)
    bl_date = models.DateField(null=True, blank=True)
    ex_factory_date = models.DateField(null=True, blank=True)
    shipping_agent = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # Marking a dispatch 'Dispatched' needs admin approval and, once
    # approved, the status is permanently locked (see is_status_locked) -
    # these fields track that request independently of `status` itself,
    # which is only ever set to 'dispatched' at the moment of approval.
    dispatch_approval = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='none')
    approval_requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='requested_dispatch_approvals')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_dispatches')
    approved_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='dispatches')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.dispatch_number} - {self.project.buyer.buyer_name}"

    @property
    def is_status_locked(self):
        """Once a Dispatched request is approved, status can never change again."""
        return self.dispatch_approval == 'approved'

    class Meta:
        ordering = ['-dispatch_date']

class DispatchDetail(models.Model):
    """Items in dispatch"""
    dispatch = models.ForeignKey(Dispatch, on_delete=models.CASCADE, related_name='items')
    finished_goods = models.ForeignKey(FinishedGoods, on_delete=models.CASCADE, related_name='dispatch_items')
    carton_number = models.CharField(max_length=50)
    quantity = models.IntegerField()
    carton_weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    carton_dimensions = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.dispatch.dispatch_number} - {self.finished_goods.style}"

class StockMovement(models.Model):
    """
    Ledger of every event that changes a fabric's (or other item's) stock
    quantity - one row per stock added, removed, received or dispatched.
    This is what powers the "stock history" page for a fabric.
    """
    MOVEMENT_TYPES = [
        ('receipt', 'Goods Receipt'),
        ('production', 'Production / Stock In'),
        ('issue', 'Production Issue'),
        ('return', 'Return to Store'),
        ('adjustment', 'Stock Removed'),
        ('transfer', 'Stock Transfer'),
        ('dispatch', 'Dispatch to Buyer'),
    ]

    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    reference_number = models.CharField(max_length=100)
    reference_id = models.IntegerField()
    fabric = models.ForeignKey(Fabric, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    fabric_roll = models.ForeignKey(FabricRoll, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    trim = models.ForeignKey(Trim, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    finished_goods = models.ForeignKey(FinishedGoods, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    spare_part = models.ForeignKey('SparePart', on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    stationery_item = models.ForeignKey('StationeryItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    # Signed: positive = added to stock, negative = removed from stock.
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    from_location = models.CharField(max_length=100, blank=True)
    to_location = models.CharField(max_length=100, blank=True)
    # Who/where stock was handed to when it's removed (e.g. "Cutting - Line 3").
    issued_to = models.CharField(max_length=200, blank=True)
    movement_date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def movement_number(self):
        if not self.pk:
            return "SM-PENDING"
        return f"SM-{self.movement_date.strftime('%y%m%d')}-{self.pk:05d}"

    def __str__(self):
        return f"{self.movement_number} - {self.movement_type}"

    class Meta:
        ordering = ['-movement_date', '-created_at']

class StockTransfer(models.Model):
    """
    A request to take stock out of a fabric (from one lot) or a trim - the
    "Transfer Stock" popup. Nothing moves until a superuser approves it
    (see approve_stock_transfer); then the stock is deducted and logged as
    a StockMovement. Pending requests still count against what's available,
    so the same stock can't be requested twice.
    """
    REASON_CHOICES = [
        ('issue', 'Issued to Production'),
        ('damage', 'Damaged'),
        ('return', 'Returned to Supplier'),
        ('recount', 'Recount Correction'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    fabric = models.ForeignKey(Fabric, on_delete=models.CASCADE, null=True, blank=True, related_name='transfers')
    fabric_roll = models.ForeignKey(FabricRoll, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers')
    trim = models.ForeignKey(Trim, on_delete=models.CASCADE, null=True, blank=True, related_name='transfers')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default='issue')
    issued_to = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_stock_transfers')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_stock_transfers')
    approved_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def transfer_number(self):
        if not self.pk:
            return "TRF-PENDING"
        return f"TRF-{self.created_at:%y%m%d}-{self.pk:05d}"

    @property
    def item_name(self):
        if self.fabric_id:
            return f"{self.fabric.fabric_code} - {self.fabric.fabric_name}"
        return f"{self.trim.trim_code} - {self.trim.trim_name}" if self.trim_id else "-"

    @property
    def unit(self):
        if self.fabric_id:
            return self.fabric.unit
        return self.trim.unit if self.trim_id else ''

    @classmethod
    def pending_qty(cls, **filters):
        """Total quantity of pending transfers matching filters (e.g. fabric_roll=lot)."""
        return cls.objects.filter(status='pending', **filters).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

    def __str__(self):
        return f"{self.transfer_number} - {self.item_name} ({self.quantity})"

    class Meta:
        ordering = ['-created_at']

class Machine(models.Model):
    """Garment-factory machinery asset register."""
    MACHINE_TYPES = [
        ('sewing_single_needle', 'Sewing - Single Needle Lockstitch'),
        ('sewing_overlock', 'Sewing - Overlock / Serger'),
        ('sewing_flatlock', 'Sewing - Flatlock / Interlock'),
        ('sewing_bartack', 'Sewing - Bartack'),
        ('sewing_buttonhole', 'Sewing - Buttonhole'),
        ('sewing_button_attach', 'Sewing - Button Attach'),
        ('sewing_kansai', 'Sewing - Kansai (Multi-needle)'),
        ('cutting_straight_knife', 'Cutting - Straight Knife'),
        ('cutting_band_knife', 'Cutting - Band Knife'),
        ('fusing_press', 'Fusing Press'),
        ('embroidery', 'Embroidery'),
        ('washing', 'Washing Machine'),
        ('dryer', 'Dryer'),
        ('boiler', 'Boiler'),
        ('generator', 'Generator'),
        ('compressor', 'Air Compressor'),
        ('iron_press', 'Iron / Steam Press'),
        ('needle_detector', 'Needle Detector'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('idle', 'Idle'),
        ('under_maintenance', 'Under Maintenance'),
        ('broken_down', 'Broken Down'),
        ('sold', 'Sold'),
        ('scrapped', 'Scrapped'),
        ('transferred', 'Transferred'),
    ]

    machine_code = models.CharField(max_length=50, unique=True)
    machine_name = models.CharField(max_length=200)
    machine_type = models.CharField(max_length=30, choices=MACHINE_TYPES, default='other')
    brand = models.CharField(max_length=100, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    supplier = models.ForeignKey('accounts.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='machines')
    department = models.ForeignKey('hr.Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='machines')
    line_number = models.CharField(max_length=50, blank=True, help_text="e.g. Line-3")
    location = models.CharField(max_length=200, blank=True, help_text="e.g. Floor 2, Line 3, Station 12")
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='machines_added')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.machine_code} - {self.machine_name}"

    @property
    def is_disposed(self):
        return self.status in ('sold', 'scrapped')

    class Meta:
        ordering = ['machine_code']

class MachineEvent(models.Model):
    """
    Status-change ledger for a Machine - the equivalent of StockMovement,
    but for a discrete asset instead of a fungible quantity. Sold/Scrapped
    events need superuser approval before Machine.status actually changes
    (mirrors Dispatch.dispatch_approval); every other event type
    applies immediately.
    """
    EVENT_TYPES = [
        ('breakdown', 'Breakdown Reported'),
        ('repair_started', 'Repair Started'),
        ('repair_completed', 'Repair Completed'),
        ('maintenance', 'Routine Maintenance'),
        ('relocated', 'Relocated'),
        ('sold', 'Sold'),
        ('scrapped', 'Scrapped'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    event_date = models.DateField()
    description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Repair cost or sale price, if applicable")
    counterparty = models.CharField(max_length=200, blank=True, help_text="Buyer, vendor or technician name")
    # Only 'sold'/'scrapped' events are ever created as 'pending' - every
    # other event type is created straight as 'approved' since it doesn't
    # gate anything (see add_machine_event).
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='approved')
    rejection_reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_machine_events')
    approved_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='machine_events_logged')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.machine.machine_code} - {self.get_event_type_display()} ({self.event_date})"

    class Meta:
        ordering = ['-event_date', '-created_at']

class SparePart(models.Model):
    """Machine spare parts inventory (needles, motors, belts, etc.)."""
    CATEGORY_CHOICES = [
        ('needle', 'Needle'),
        ('motor', 'Motor'),
        ('belt', 'Belt'),
        ('bobbin', 'Bobbin'),
        ('presser_foot', 'Presser Foot'),
        ('bearing', 'Bearing'),
        ('gear', 'Gear'),
        ('electronic_board', 'Electronic Board / PCB'),
        ('blade', 'Blade / Knife'),
        ('other', 'Other'),
    ]

    part_name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    compatible_machine_type = models.CharField(max_length=30, choices=Machine.MACHINE_TYPES, blank=True)
    supplier = models.ForeignKey('accounts.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='spare_parts')
    unit = models.CharField(max_length=20, default='pcs')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    current_stock = models.IntegerField(default=0)
    min_stock = models.IntegerField(default=0)
    max_stock = models.IntegerField(default=99999)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def part_code(self):
        return f"SP-{self.pk:05d}"

    def __str__(self):
        return f"{self.part_code} - {self.part_name}"

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock

    @property
    def stock_status(self):
        if self.current_stock <= self.min_stock:
            return 'low'
        elif self.current_stock >= self.max_stock:
            return 'overstock'
        else:
            return 'normal'

    class Meta:
        ordering = ['part_name']

class SparePartConsumption(models.Model):
    """
    One department's use of a spare part, optionally against a specific
    Machine/MachineEvent (repair). unit_price_at_consumption is snapshotted
    at issue time so a later costing report doesn't need historical price
    lookups.
    """
    spare_part = models.ForeignKey(SparePart, on_delete=models.CASCADE, related_name='consumptions')
    department = models.ForeignKey('hr.Department', on_delete=models.PROTECT, related_name='spare_part_consumptions')
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True, related_name='spare_part_consumptions')
    machine_event = models.ForeignKey(MachineEvent, on_delete=models.SET_NULL, null=True, blank=True, related_name='spare_part_consumptions')
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_price_at_consumption = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    consumption_date = models.DateField()
    notes = models.TextField(blank=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='spare_part_consumptions')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_cost(self):
        return self.quantity * self.unit_price_at_consumption

    def __str__(self):
        return f"{self.spare_part.part_name} x{self.quantity} - {self.department.name}"

    class Meta:
        ordering = ['-consumption_date']

class StationeryItem(models.Model):
    """Office/stationery supplies inventory."""
    CATEGORY_CHOICES = [
        ('paper', 'Paper'),
        ('writing', 'Writing Materials'),
        ('printing', 'Printing / Toner'),
        ('filing', 'Filing & Organization'),
        ('cleaning', 'Cleaning Supplies'),
        ('other', 'Other'),
    ]

    item_name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    unit = models.CharField(max_length=20, default='pcs')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    current_stock = models.IntegerField(default=0)
    min_stock = models.IntegerField(default=0)
    max_stock = models.IntegerField(default=99999)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def item_code(self):
        return f"ST-{self.pk:05d}"

    def __str__(self):
        return f"{self.item_code} - {self.item_name}"

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock

    @property
    def stock_status(self):
        if self.current_stock <= self.min_stock:
            return 'low'
        elif self.current_stock >= self.max_stock:
            return 'overstock'
        else:
            return 'normal'

    class Meta:
        ordering = ['item_name']

class StationeryConsumption(models.Model):
    """One department's use of a stationery item - mirrors SparePartConsumption."""
    stationery_item = models.ForeignKey(StationeryItem, on_delete=models.CASCADE, related_name='consumptions')
    department = models.ForeignKey('hr.Department', on_delete=models.PROTECT, related_name='stationery_consumptions')
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_price_at_consumption = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    consumption_date = models.DateField()
    notes = models.TextField(blank=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stationery_consumptions')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_cost(self):
        return self.quantity * self.unit_price_at_consumption

    def __str__(self):
        return f"{self.stationery_item.item_name} x{self.quantity} - {self.department.name}"

    class Meta:
        ordering = ['-consumption_date']

class SupplyAdjustment(models.Model):
    """
    Stock correction for a SparePart or StationeryItem, with a
    pending/approved/rejected approval gate.
    """
    ADJUSTMENT_TYPES = [
        ('damage', 'Damage Write-off'),
        ('expired_obsolete', 'Expired / Obsolete'),
        ('recount', 'Recount Adjustment'),
        ('other', 'Other'),
    ]

    DIRECTION_CHOICES = [
        ('increase', 'Increase Stock'),
        ('decrease', 'Decrease Stock'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='decrease')
    spare_part = models.ForeignKey(SparePart, on_delete=models.SET_NULL, null=True, blank=True, related_name='adjustments')
    stationery_item = models.ForeignKey(StationeryItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='adjustments')
    adjustment_date = models.DateField()
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_supply_adjustments')
    approved_date = models.DateField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_supply_adjustments')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def adjustment_number(self):
        if not self.pk:
            return "SUA-PENDING"
        return f"SUA-{self.adjustment_date.strftime('%y%m%d')}-{self.pk:05d}"

    def clean(self):
        from django.core.exceptions import ValidationError
        targets = [t for t in [self.spare_part_id, self.stationery_item_id] if t]
        if len(targets) != 1:
            raise ValidationError("Select exactly one of Spare Part or Stationery Item.")

    def __str__(self):
        return f"{self.adjustment_number} - {self.adjustment_type}"

    class Meta:
        ordering = ['-adjustment_date']
