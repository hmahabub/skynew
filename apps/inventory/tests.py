from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Buyer, Project
from .models import Dispatch, DispatchDetail, Fabric, FabricRoll, FinishedGoods, StockMovement, StockTransfer, Trim


class InventoryTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client.force_login(self.admin)
        self.fabric = Fabric.objects.create(
            fabric_name='Cotton Poplin', color='Navy', gsm=150, width=Decimal('58'),
            supplier='ABC Textiles', buyer='H&M', project='Summer 26', purchase_order='PO-1',
            unit_price=Decimal('200'),
        )
        buyer = Buyer.objects.create(
            buyer_code='B1', buyer_name='Test Buyer', country='BD',
            email='b@example.com', phone='1', address='x',
        )
        self.project = Project.objects.create(
            project_number='PRJ-1', buyer=buyer, description='x', order_quantity=100,
            unit_price=Decimal('1'), total_value=Decimal('100'), cm_charge=Decimal('1'),
            order_date=date.today(), delivery_date=date.today(),
        )
        self.fg = FinishedGoods.objects.create(
            style='ST-1001', size='M', color='Red', quantity_in_stock=100,
            unit_price=Decimal('5'), warehouse_location='WH-A',
        )

    def add_stock(self, quantity, **extra):
        data = {'quantity': quantity, 'location': 'Main Warehouse', 'received_date': date.today().isoformat(),
                'next': reverse('inventory:fabric_list')}
        data.update(extra)
        return self.client.post(reverse('inventory:add_fabric_stock', args=[self.fabric.pk]), data)

    def transfer_stock(self, quantity, lot=None, reason='issue', issued_to=''):
        data = {'quantity': quantity, 'reason': reason, 'issued_to': issued_to, 'next': reverse('inventory:fabric_list')}
        if lot is not None:
            data['lot'] = lot.pk
        return self.client.post(reverse('inventory:transfer_fabric_stock', args=[self.fabric.pk]), data)

    def approve(self, transfer):
        return self.client.post(reverse('inventory:approve_stock_transfer', args=[transfer.pk]))

    def login_staff(self):
        """A non-admin Inventory user."""
        staff = User.objects.create_user('staff', password='pw')
        staff.groups.add(Group.objects.get_or_create(name='Inventory')[0])
        self.client.force_login(staff)
        return staff

    def create_dispatch(self, quantity, number='DSP-1'):
        return self.client.post(reverse('inventory:add_dispatch'), {
            'dispatch_number': number, 'project': self.project.pk,
            'dispatch_date': date.today().isoformat(), 'total_cartons': 1, 'shipping_line': 'MSC',
            'finished_goods_ids[]': [self.fg.pk], 'carton_numbers[]': ['CTN-1'], 'quantities[]': [quantity],
        })


class FabricStockPopupTests(InventoryTestCase):
    def test_add_stock_auto_generates_lot_and_returns_to_list(self):
        response = self.add_stock('50')
        self.assertRedirects(response, reverse('inventory:fabric_list'))
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('50'))
        lot = self.fabric.rolls.get()
        self.assertEqual(lot.lot_number, f"{self.fabric.fabric_code}-L001")
        self.assertEqual(lot.remaining_length, Decimal('50'))

    def test_add_stock_rejects_duplicate_lot(self):
        self.add_stock('10', lot_number='LOT-A')
        self.add_stock('10', lot_number='LOT-A')
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('10'))

    def test_transfer_waits_for_approval_then_takes_from_lot(self):
        self.add_stock('50')
        lot = self.fabric.rolls.get()
        response = self.transfer_stock('20', lot=lot, reason='damage', issued_to='Cutting - Line 3')
        self.assertRedirects(response, reverse('inventory:fabric_list'))
        transfer = StockTransfer.objects.get()
        self.assertEqual(transfer.status, 'pending')
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('50'))  # nothing moved yet

        self.approve(transfer)
        transfer.refresh_from_db()
        self.fabric.refresh_from_db()
        lot.refresh_from_db()
        self.assertEqual(transfer.status, 'approved')
        self.assertEqual(self.fabric.current_stock, Decimal('30'))
        self.assertEqual(lot.remaining_length, Decimal('30'))
        movement = StockMovement.objects.filter(fabric=self.fabric).latest('created_at')
        self.assertEqual(movement.movement_type, 'transfer')
        self.assertEqual(movement.quantity, Decimal('-20'))
        self.assertEqual(movement.fabric_roll, lot)
        self.assertEqual(movement.issued_to, 'Cutting - Line 3')
        self.assertEqual(movement.reference_number, transfer.transfer_number)
        self.assertIn('Damaged', movement.notes)

    def test_reject_leaves_stock_alone(self):
        self.add_stock('50')
        self.transfer_stock('20', lot=self.fabric.rolls.get())
        transfer = StockTransfer.objects.get()
        self.client.post(reverse('inventory:reject_stock_transfer', args=[transfer.pk]))
        transfer.refresh_from_db()
        self.fabric.refresh_from_db()
        self.assertEqual(transfer.status, 'rejected')
        self.assertEqual(self.fabric.current_stock, Decimal('50'))
        self.approve(transfer)  # can't approve a rejected request
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('50'))

    def test_pending_transfers_count_against_available(self):
        self.add_stock('50')
        lot = self.fabric.rolls.get()
        self.transfer_stock('30', lot=lot)
        self.transfer_stock('30', lot=lot)  # only 20 left available
        self.assertEqual(StockTransfer.objects.count(), 1)

    def test_only_admin_can_approve(self):
        self.add_stock('50')
        self.transfer_stock('10', lot=self.fabric.rolls.get())
        transfer = StockTransfer.objects.get()
        self.login_staff()
        self.approve(transfer)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'pending')

    def test_ledger_has_separate_stock_in_and_out_tables(self):
        self.add_stock('50')
        self.transfer_stock('10', lot=self.fabric.rolls.get(), issued_to='Cutting - Line 3')
        self.approve(StockTransfer.objects.get())
        response = self.client.get(reverse('inventory:fabric_stock_ledger', args=[self.fabric.pk]))
        self.assertEqual(len(response.context['stock_in']), 1)
        self.assertEqual(len(response.context['stock_out']), 1)
        self.assertContains(response, 'Stock In')
        self.assertContains(response, 'Stock Out')
        self.assertContains(response, 'Cutting - Line 3')

    def test_ledger_lists_pending_transfer_requests(self):
        self.add_stock('50')
        self.transfer_stock('10', lot=self.fabric.rolls.get())
        response = self.client.get(reverse('inventory:fabric_stock_ledger', args=[self.fabric.pk]))
        self.assertContains(response, 'Awaiting Approval')
        self.assertContains(response, StockTransfer.objects.get().transfer_number)

    def test_transfer_more_than_lot_has_is_refused(self):
        self.add_stock('50')
        self.transfer_stock('60', lot=self.fabric.rolls.get())
        self.assertFalse(StockTransfer.objects.exists())

    def test_transfer_requires_lot_when_fabric_has_lots(self):
        self.add_stock('50')
        self.transfer_stock('10')
        self.assertFalse(StockTransfer.objects.exists())

    def test_transfer_without_lots_reduces_total(self):
        Fabric.objects.filter(pk=self.fabric.pk).update(current_stock=Decimal('40'))
        self.transfer_stock('15')
        self.approve(StockTransfer.objects.get())
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('25'))

    def test_using_up_a_lot_marks_it_finished(self):
        self.add_stock('10')
        lot = self.fabric.rolls.get()
        self.transfer_stock('10', lot=lot)
        self.approve(StockTransfer.objects.get())
        lot.refresh_from_db()
        self.assertEqual(lot.status, 'finished')

    def test_popup_endpoints_reject_get(self):
        response = self.client.get(reverse('inventory:add_fabric_stock', args=[self.fabric.pk]))
        self.assertEqual(response.status_code, 405)

    def test_next_url_must_be_same_site(self):
        response = self.add_stock('5', next='https://evil.example.com/')
        self.assertRedirects(response, reverse('inventory:fabric_list'))

    def test_fabric_list_shows_text_fields_and_popups(self):
        self.add_stock('50')
        response = self.client.get(reverse('inventory:fabric_list'))
        self.assertContains(response, 'ABC Textiles')
        self.assertContains(response, 'addFabricStockModal')
        self.assertContains(response, 'data-fabric-stock="transfer"')
        self.assertContains(response, 'Transfer Stock')

    def test_goods_receipt_creates_a_lot_per_line(self):
        from apps.accounts.models import Supplier
        supplier = Supplier.objects.create(
            supplier_code='S1', supplier_name='Sup', supplier_type=Supplier._meta.get_field('supplier_type').choices[0][0],
            email='s@example.com', phone='1',
        )
        self.client.post(reverse('inventory:add_goods_receipt'), {
            'supplier': supplier.pk, 'invoice_number': 'INV-1',
            'fabric_ids[]': [self.fabric.pk], 'quantities[]': ['75'], 'unit_prices[]': ['2'],
        })
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.current_stock, Decimal('75'))
        self.assertEqual(self.fabric.rolls.get().remaining_length, Decimal('75'))

    def test_add_fabric_with_opening_stock(self):
        response = self.client.post(reverse('inventory:add_fabric'), {
            'fabric_name': 'Denim', 'fabric_type': 'denim', 'color': 'Blue', 'gsm': 300, 'width': '60',
            'supplier': 'Any Supplier Ltd', 'project': '', 'purchase_order': 'PO-77', 'buyer': 'Zara',
            'unit': 'meter', 'unit_price': '5', 'initial_quantity': '120', 'lot_number': '',
        })
        self.assertRedirects(response, reverse('inventory:fabric_list'))
        fabric = Fabric.objects.get(fabric_name='Denim')
        self.assertEqual(fabric.supplier, 'Any Supplier Ltd')
        self.assertEqual(fabric.current_stock, Decimal('120'))
        self.assertEqual(fabric.rolls.count(), 1)


class TrimStockPopupTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.trim = Trim.objects.create(trim_name='Button', trim_type='button', unit='pcs', unit_price=Decimal('1'))

    def transfer(self, quantity, **extra):
        data = {'quantity': quantity, 'reason': 'issue', 'next': reverse('inventory:trim_list')}
        data.update(extra)
        return self.client.post(reverse('inventory:transfer_trim_stock', args=[self.trim.pk]), data)

    def test_add_and_transfer_trim_stock(self):
        list_url = reverse('inventory:trim_list')
        response = self.client.post(reverse('inventory:add_trim_stock', args=[self.trim.pk]),
                                    {'quantity': 100, 'next': list_url})
        self.assertRedirects(response, list_url)
        response = self.transfer(30, issued_to='Sewing - Line 2')
        self.assertRedirects(response, list_url)
        self.trim.refresh_from_db()
        self.assertEqual(self.trim.current_stock, 100)

        self.approve(StockTransfer.objects.get())
        self.trim.refresh_from_db()
        self.assertEqual(self.trim.current_stock, 70)
        movement = StockMovement.objects.filter(trim=self.trim).latest('created_at')
        self.assertEqual(movement.quantity, Decimal('-30'))
        self.assertEqual(movement.movement_type, 'transfer')
        self.assertEqual(movement.issued_to, 'Sewing - Line 2')

    def test_cannot_transfer_more_than_available(self):
        Trim.objects.filter(pk=self.trim.pk).update(current_stock=10)
        self.transfer(11)
        self.transfer(6)
        self.transfer(6)  # only 4 left once the first 6 is pending
        self.assertEqual(StockTransfer.objects.count(), 1)

    def test_approval_rechecks_stock(self):
        Trim.objects.filter(pk=self.trim.pk).update(current_stock=10)
        self.transfer(8)
        Trim.objects.filter(pk=self.trim.pk).update(current_stock=5)
        self.approve(StockTransfer.objects.get())
        self.assertEqual(StockTransfer.objects.get().status, 'pending')
        self.trim.refresh_from_db()
        self.assertEqual(self.trim.current_stock, 5)

    def test_trim_popups_on_list_and_ledger(self):
        for url in [reverse('inventory:trim_list'), reverse('inventory:trim_stock_ledger', args=[self.trim.pk])]:
            response = self.client.get(url)
            self.assertContains(response, 'transferTrimStockModal')
            self.assertContains(response, 'name="issued_to"')
            self.assertContains(response, 'Needs admin approval')

    def test_pending_approvals_page_lists_transfers(self):
        Trim.objects.filter(pk=self.trim.pk).update(current_stock=10)
        self.transfer(5, issued_to='Finishing Dept')
        response = self.client.get(reverse('inventory:pending_approvals'))
        self.assertContains(response, StockTransfer.objects.get().transfer_number)
        self.assertContains(response, 'Finishing Dept')


class UnitPriceTests(InventoryTestCase):
    def test_admin_sees_and_sets_price(self):
        response = self.client.get(reverse('inventory:add_trim'))
        self.assertIn('unit_price', response.context['form'].fields)
        self.assertContains(self.client.get(reverse('inventory:fabric_list')), 'Unit Price')

    def test_price_is_optional(self):
        self.client.post(reverse('inventory:add_fabric'), {
            'fabric_name': 'Twill', 'fabric_type': 'cotton', 'color': 'Red', 'gsm': 200, 'width': '58',
            'unit': 'meter', 'unit_price': '',
        })
        self.assertIsNone(Fabric.objects.get(fabric_name='Twill').unit_price)
        self.client.post(reverse('inventory:add_finished_goods'), {
            'style': 'ST-2', 'size': 'M', 'color': 'Red', 'unit_price': '', 'warehouse_location': 'WH',
        })
        self.assertIsNone(FinishedGoods.objects.get(style='ST-2').unit_price)

    def test_non_admin_cannot_see_or_change_price(self):
        self.login_staff()
        for url in [reverse('inventory:add_fabric'), reverse('inventory:add_trim'), reverse('inventory:add_finished_goods'),
                    reverse('inventory:edit_fabric', args=[self.fabric.pk])]:
            response = self.client.get(url)
            self.assertNotIn('unit_price', response.context['form'].fields, url)
            self.assertNotContains(response, 'name="unit_price"')
        for url in [reverse('inventory:fabric_list'), reverse('inventory:finished_goods_list')]:
            self.assertNotContains(self.client.get(url), 'Unit Price')

        # Posting a price anyway is ignored, and editing keeps the saved price.
        self.client.post(reverse('inventory:edit_fabric', args=[self.fabric.pk]), {
            'fabric_name': 'Cotton Poplin', 'fabric_type': 'cotton', 'color': 'Navy', 'gsm': 150, 'width': '58',
            'unit': 'meter', 'unit_price': '1',
        })
        self.fabric.refresh_from_db()
        self.assertEqual(self.fabric.unit_price, Decimal('200'))


class CopyAndOrderingTests(InventoryTestCase):
    def test_copy_fabric_prefills_form_but_not_stock(self):
        response = self.client.get(reverse('inventory:add_fabric'), {'copy_from': self.fabric.pk})
        form = response.context['form']
        self.assertEqual(form.initial['fabric_name'], 'Cotton Poplin')
        self.assertEqual(form.initial['supplier'], 'ABC Textiles')
        self.assertNotIn('current_stock', form.initial)
        self.assertContains(response, 'Copied from')
        self.assertContains(response, 'copyFromSelect')

    def test_copy_trim_and_finished_goods(self):
        trim = Trim.objects.create(trim_name='Button', trim_type='button', unit='pcs', color='Red')
        response = self.client.get(reverse('inventory:add_trim'), {'copy_from': trim.pk})
        self.assertEqual(response.context['form'].initial['color'], 'Red')
        response = self.client.get(reverse('inventory:add_finished_goods'), {'copy_from': self.fg.pk})
        self.assertEqual(response.context['form'].initial['style'], 'ST-1001')

    def test_non_admin_copy_does_not_leak_price(self):
        self.login_staff()
        response = self.client.get(reverse('inventory:add_fabric'), {'copy_from': self.fabric.pk})
        self.assertNotContains(response, '200.00')

    def test_lists_show_latest_first(self):
        newer_fabric = Fabric.objects.create(fabric_name='Newer', color='Red', gsm=1, width=1)
        newer_trim_old = Trim.objects.create(trim_name='Old Trim', trim_type='tag', unit='pcs')
        newer_trim = Trim.objects.create(trim_name='New Trim', trim_type='tag', unit='pcs')
        newer_fg = FinishedGoods.objects.create(style='ST-9', size='S', color='Red', warehouse_location='WH')
        self.assertEqual(self.client.get(reverse('inventory:fabric_list')).context['fabrics'][0], newer_fabric)
        self.assertEqual(list(self.client.get(reverse('inventory:trim_list')).context['trims'])[:2], [newer_trim, newer_trim_old])
        self.assertEqual(self.client.get(reverse('inventory:finished_goods_list')).context['finished_goods'][0], newer_fg)


class DispatchTests(InventoryTestCase):
    def test_dispatch_date_defaults_to_today(self):
        response = self.client.get(reverse('inventory:add_dispatch'))
        self.assertContains(response, f'value="{date.today().isoformat()}"')

    def test_only_three_statuses(self):
        self.assertEqual([code for code, _ in Dispatch.STATUS_CHOICES], ['pending', 'on_going', 'dispatched'])

    def test_new_dispatch_reserves_but_does_not_deduct_stock(self):
        response = self.create_dispatch(30)
        dispatch = Dispatch.objects.get()
        self.assertRedirects(response, reverse('inventory:dispatch_detail', args=[dispatch.pk]))
        self.fg.refresh_from_db()
        self.assertEqual(self.fg.quantity_in_stock, 100)
        self.assertEqual(self.fg.pending_dispatch_qty, 30)
        self.assertEqual(self.fg.available_stock, 70)
        annotated = FinishedGoods.with_pending_dispatch().get(pk=self.fg.pk)
        self.assertEqual(annotated.pending_dispatch_qty, 30)

    def test_cannot_dispatch_more_than_available(self):
        self.create_dispatch(80, number='DSP-1')
        self.create_dispatch(30, number='DSP-2')  # only 20 left available
        self.assertEqual(Dispatch.objects.count(), 1)

    def test_setting_dispatched_needs_approval_then_deducts_and_locks(self):
        self.create_dispatch(30)
        dispatch = Dispatch.objects.get()
        url = reverse('inventory:update_dispatch_status', args=[dispatch.pk])

        self.client.post(url, {'status': 'on_going'})
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status, 'on_going')

        self.client.post(url, {'status': 'dispatched'})
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status, 'on_going')
        self.assertEqual(dispatch.dispatch_approval, 'pending')

        self.client.post(reverse('inventory:approve_dispatch', args=[dispatch.pk]))
        dispatch.refresh_from_db()
        self.fg.refresh_from_db()
        self.assertEqual(dispatch.status, 'dispatched')
        self.assertTrue(dispatch.is_status_locked)
        self.assertEqual(self.fg.quantity_in_stock, 70)
        self.assertEqual(self.fg.quantity_dispatched, 30)
        self.assertEqual(self.fg.pending_dispatch_qty, 0)

        self.client.post(url, {'status': 'pending'})
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status, 'dispatched')

    def test_non_superuser_cannot_approve(self):
        self.create_dispatch(10)
        dispatch = Dispatch.objects.get()
        self.client.post(reverse('inventory:update_dispatch_status', args=[dispatch.pk]), {'status': 'dispatched'})
        self.login_staff()
        self.client.post(reverse('inventory:approve_dispatch', args=[dispatch.pk]))
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.dispatch_approval, 'pending')

    def test_reject_keeps_status(self):
        self.create_dispatch(10)
        dispatch = Dispatch.objects.get()
        self.client.post(reverse('inventory:update_dispatch_status', args=[dispatch.pk]), {'status': 'dispatched'})
        self.client.post(reverse('inventory:reject_dispatch', args=[dispatch.pk]))
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status, 'pending')
        self.assertEqual(dispatch.dispatch_approval, 'rejected')

    def test_delete_unapproved_dispatch_frees_reservation(self):
        self.create_dispatch(40)
        dispatch = Dispatch.objects.get()
        self.client.post(reverse('inventory:delete_dispatch', args=[dispatch.pk]))
        self.assertFalse(Dispatch.objects.exists())
        self.assertEqual(self.fg.pending_dispatch_qty, 0)

    def test_approved_dispatch_cannot_be_deleted(self):
        self.create_dispatch(10)
        dispatch = Dispatch.objects.get()
        self.client.post(reverse('inventory:update_dispatch_status', args=[dispatch.pk]), {'status': 'dispatched'})
        self.client.post(reverse('inventory:approve_dispatch', args=[dispatch.pk]))
        self.client.post(reverse('inventory:delete_dispatch', args=[dispatch.pk]))
        self.assertTrue(Dispatch.objects.exists())

    def test_product_dropdown_is_searchable_by_style(self):
        response = self.client.get(reverse('inventory:add_dispatch'))
        self.assertContains(response, 'js-style-search')
        self.assertContains(response, 'data-style="st-1001"')


class FinishedGoodsTests(InventoryTestCase):
    def test_style_size_color_must_be_unique(self):
        response = self.client.post(reverse('inventory:add_finished_goods'), {
            'style': 'ST-1001', 'size': 'M', 'color': 'Red', 'unit_price': '5', 'warehouse_location': 'WH',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinishedGoods.objects.count(), 1)

    def test_same_style_other_size_is_allowed(self):
        self.client.post(reverse('inventory:add_finished_goods'), {
            'style': 'ST-1001', 'size': 'L', 'color': 'Red', 'unit_price': '5', 'warehouse_location': 'WH',
        })
        self.assertEqual(FinishedGoods.objects.filter(style='ST-1001').count(), 2)

    def test_list_shows_pending_dispatch_column_and_filter(self):
        self.create_dispatch(25)
        response = self.client.get(reverse('inventory:finished_goods_list'), {'stock_status': 'pending_dispatch'})
        self.assertContains(response, 'Pending Dispatch')
        self.assertContains(response, 'ST-1001')


class PageSmokeTests(InventoryTestCase):
    """Every inventory page renders for an admin (catches template/URL mistakes)."""

    def test_pages_render(self):
        self.add_stock('50')
        trim = Trim.objects.create(trim_name='Button', trim_type='button', unit='pcs', unit_price=Decimal('1'))
        self.create_dispatch(5)
        dispatch = Dispatch.objects.get()
        names = [
            ('inventory:inventory_dashboard', []),
            ('inventory:fabric_list', []),
            ('inventory:add_fabric', []),
            ('inventory:edit_fabric', [self.fabric.pk]),
            ('inventory:fabric_stock_ledger', [self.fabric.pk]),
            ('inventory:trim_list', []),
            ('inventory:add_trim', []),
            ('inventory:edit_trim', [trim.pk]),
            ('inventory:trim_stock_ledger', [trim.pk]),
            ('inventory:goods_receipts', []),
            ('inventory:add_goods_receipt', []),
            ('inventory:trim_receipts', []),
            ('inventory:add_trim_receipt', []),
            ('inventory:finished_goods_list', []),
            ('inventory:add_finished_goods', []),
            ('inventory:edit_finished_goods', [self.fg.pk]),
            ('inventory:add_finished_goods_stock', [self.fg.pk]),
            ('inventory:finished_goods_stock_ledger', [self.fg.pk]),
            ('inventory:dispatches', []),
            ('inventory:add_dispatch', []),
            ('inventory:dispatch_detail', [dispatch.pk]),
            ('inventory:edit_dispatch', [dispatch.pk]),
            ('inventory:pending_approvals', []),
            ('inventory:stock_report', []),
            ('inventory:stock_report_export_excel', []),
            ('inventory:stock_report_export_pdf', []),
            ('inventory:machine_list', []),
            ('inventory:spare_part_list', []),
            ('inventory:stationery_list', []),
            ('inventory:supply_adjustments', []),
        ]
        for name, args in names:
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200)


class WarehouseUserTests(InventoryTestCase):
    """A user in the Inventory group can use the warehouse and nothing else."""

    def test_can_use_warehouse_pages(self):
        self.login_staff()
        for name, args in [('inventory:inventory_dashboard', []), ('inventory:fabric_list', []),
                           ('inventory:add_fabric', []), ('inventory:trim_list', []),
                           ('inventory:finished_goods_list', []), ('inventory:dispatches', []),
                           ('inventory:add_dispatch', []), ('inventory:stock_report', [])]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_blocked_from_hr_accounts_admin_and_approvals(self):
        self.login_staff()
        for url in [reverse('hr:hr_dashboard'), reverse('hr:employee_list'), reverse('hr:payroll_list'),
                    reverse('accounts:accounts_dashboard'), reverse('accounts:buyers_list'),
                    reverse('inventory:pending_approvals'), '/admin/']:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn('login', response['Location'])

    def test_sidebar_hides_admin_only_links(self):
        self.login_staff()
        response = self.client.get(reverse('inventory:fabric_list'))
        self.assertNotContains(response, reverse('inventory:pending_approvals'))
        self.assertNotContains(response, f'href="{reverse("accounts:accounts_dashboard")}"')
        self.assertNotContains(response, reverse('accounts:cashbook'))
        # ...but they can raise expense vouchers.
        self.assertContains(response, reverse('accounts:voucher_list'))

    def test_create_warehouse_user_command(self):
        from unittest import mock
        from django.core.management import call_command
        with mock.patch('getpass.getpass', return_value='Wh-Strong-Pass-2026'):
            call_command('create_warehouse_user', 'store1', stdout=mock.MagicMock())
        user = User.objects.get(username='store1')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['Inventory'])
        self.assertTrue(user.check_password('Wh-Strong-Pass-2026'))
