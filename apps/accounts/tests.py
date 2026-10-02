from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from . import services
from .models import (
    Buyer, CashBookEntry, Cost, CostVoucher, LCLoan, LCPayment, LetterOfCredit, Payment, Project, Supplier,
)


class AccountingTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client.force_login(self.admin)
        self.buyer = Buyer.objects.create(
            buyer_code='B1', buyer_name='Test Buyer', country='BD', email='b@example.com', phone='1', address='x',
        )
        self.supplier = Supplier.objects.create(
            supplier_code='S1', supplier_name='Test Supplier',
            supplier_type=Supplier.SUPPLIER_TYPES[0][0], email='s@example.com', phone='1',
        )

    def add_order(self, buyer_ref='PO-77', value='5000', quantity=1000):
        return self.client.post(reverse('accounts:add_project'), {
            'buyer': self.buyer.pk, 'buyer_ref': buyer_ref, 'order_quantity': quantity,
            'total_value': value, 'delivery_date': (date.today() + timedelta(days=10)).isoformat(),
            'status': 'order', 'remarks': '',
        })

    def make_order(self):
        self.add_order()
        return Project.objects.latest('pk')

    def make_lc(self, amount='10000'):
        order = self.make_order()
        return LetterOfCredit.objects.create(
            lc_number='LC-1', project=order, lc_date=date.today(), bank_name='Prime Bank',
            lc_amount=Decimal(amount), expiry_date=date.today() + timedelta(days=60),
        )

    def warehouse_user(self):
        user = User.objects.create_user('store1', password='pw')
        user.groups.add(Group.objects.get_or_create(name='Inventory')[0])
        return user


@override_settings(MERCHANDISING_ENABLED=False)
class OrderTests(AccountingTestCase):
    def test_order_number_is_generated_and_buyer_ref_kept(self):
        response = self.add_order(buyer_ref='H&M-4411')
        self.assertRedirects(response, reverse('accounts:projects_list'))
        order = Project.objects.get()
        self.assertEqual(order.project_number, f"{order.created_at:%y}ORD{order.pk:05d}")
        self.assertEqual(order.buyer_ref, 'H&M-4411')
        self.assertEqual(order.unit_price, Decimal('5.00'))
        self.assertIn('H&M-4411', str(order))

    def test_numbers_follow_ids(self):
        self.add_order(buyer_ref='A')
        self.add_order(buyer_ref='B')
        first, second = Project.objects.order_by('pk')
        self.assertEqual(int(second.project_number[-5:]), int(first.project_number[-5:]) + 1)

    def test_order_number_cant_be_changed_on_edit(self):
        order = self.make_order()
        number = order.project_number
        self.client.post(reverse('accounts:edit_project', args=[order.pk]), {
            'project_number': 'HACKED', 'buyer': self.buyer.pk, 'buyer_ref': 'NEW', 'order_quantity': 10,
            'total_value': '100', 'delivery_date': date.today().isoformat(), 'status': 'order',
        })
        order.refresh_from_db()
        self.assertEqual(order.project_number, number)
        self.assertEqual(order.buyer_ref, 'NEW')

    def test_no_quotation_status(self):
        self.assertNotIn('quotation', dict(Project.STATUS_CHOICES))
        response = self.client.get(reverse('accounts:add_project'))
        self.assertNotContains(response, 'Quotation')


@override_settings(MERCHANDISING_ENABLED=False)
class LCLoanTests(AccountingTestCase):
    def take_loan(self, lc, amount='4000', interest='100', charges='50'):
        return self.client.post(reverse('accounts:add_lc_loan', args=[lc.pk]), {
            'loan_date': date.today().isoformat(), 'bank_name': 'Prime Bank',
            'loan_amount': amount, 'interest': interest, 'other_charges': charges,
        })

    def test_take_loan_adds_to_cash_book(self):
        lc = self.make_lc()
        self.take_loan(lc)
        loan = LCLoan.objects.get()
        self.assertEqual(loan.outstanding, Decimal('4150'))
        entry = CashBookEntry.objects.get(source='loan')
        self.assertEqual((entry.direction, entry.amount, entry.mode), ('in', Decimal('4000'), 'bank'))

    def test_repay_loan_in_instalments(self):
        lc = self.make_lc()
        self.take_loan(lc)
        loan = LCLoan.objects.get()
        url = reverse('accounts:repay_lc_loan', args=[loan.pk])
        self.client.post(url, {'repayment_date': date.today().isoformat(), 'amount': '1000', 'mode': 'cash'})
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding, Decimal('3150'))
        out = CashBookEntry.objects.get(source='loan_repayment')
        self.assertEqual((out.direction, out.amount, out.mode), ('out', Decimal('1000'), 'cash'))

        # Can't pay more than is owed.
        self.client.post(url, {'repayment_date': date.today().isoformat(), 'amount': '5000', 'mode': 'bank'})
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding, Decimal('3150'))

    def test_completing_lc_adjusts_loan_first(self):
        lc = self.make_lc('10000')                     # USD
        self.take_loan(lc)                             # owes BDT 4150
        loan = LCLoan.objects.get()
        services.repay_loan(loan, Decimal('150'), user=self.admin)  # owes BDT 4000
        self.client.post(reverse('accounts:complete_lc', args=[lc.pk]), {
            'completion_date': date.today().isoformat(), 'realized_amount': '10000', 'exchange_rate': '120',
            'bank_name': 'Prime Bank',
        })
        lc.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(lc.status, 'completed')
        self.assertEqual(lc.realized_bdt, Decimal('1200000'))
        self.assertEqual(lc.loan_adjusted, Decimal('4000'))
        self.assertTrue(loan.is_settled)
        self.assertEqual(loan.repayments.filter(kind='lc_adjustment').get().amount, Decimal('4000'))
        # Only the remainder (BDT) reaches the cash book; the LC's receipt is tracked in USD.
        self.assertEqual(CashBookEntry.objects.get(source='lc_receipt').amount, Decimal('1196000'))
        self.assertEqual(lc.total_paid, Decimal('10000'))

    def test_completion_bdt_can_be_typed_from_bank_advice(self):
        lc = self.make_lc('1000')
        services.complete_lc(lc, Decimal('1000'), Decimal('121.5'), realized_bdt=Decimal('121480'), user=self.admin)
        self.assertEqual(CashBookEntry.objects.get(source='lc_receipt').amount, Decimal('121480'))
    def test_completion_smaller_than_loan_leaves_rest_owed(self):
        lc = self.make_lc('10000')
        self.take_loan(lc, amount='5000', interest='0', charges='0')
        services.complete_lc(lc, Decimal('30'), Decimal('100'), user=self.admin)   # BDT 3000
        loan = LCLoan.objects.get()
        self.assertEqual(loan.outstanding, Decimal('2000'))
        self.assertFalse(CashBookEntry.objects.filter(source='lc_receipt').exists())
    def test_no_new_loans_on_completed_lc(self):
        lc = self.make_lc()
        services.complete_lc(lc, Decimal('10000'), Decimal('120'), user=self.admin)
        self.take_loan(lc)
        self.assertFalse(LCLoan.objects.exists())

    def test_lc_page_shows_loans_and_complete_form(self):
        lc = self.make_lc()
        self.take_loan(lc)
        response = self.client.get(reverse('accounts:lc_detail', args=[lc.pk]))
        self.assertContains(response, 'Make Payment')
        self.assertContains(response, 'Complete LC')


@override_settings(MERCHANDISING_ENABLED=False)
class CostTests(AccountingTestCase):
    def test_order_cost_is_paid_from_cash_book(self):
        order = self.make_order()
        response = self.client.post(reverse('accounts:add_cost'), {
            'project': order.pk, 'cost_type': 'fabric', 'cost_date': date.today().isoformat(),
            'description': 'Fabric', 'amount': '800', 'paid_by': 'bank', 'bank_name': 'Prime Bank',
        })
        self.assertRedirects(response, reverse('accounts:costs_list') + '?scope=order')
        cost = Cost.objects.get()
        self.assertTrue(cost.is_order_cost)
        entry = CashBookEntry.objects.get(source='cost')
        self.assertEqual((entry.direction, entry.amount, entry.mode, entry.bank_name), ('out', Decimal('800'), 'bank', 'Prime Bank'))

    def test_order_cost_needs_an_order(self):
        self.client.post(reverse('accounts:add_cost'), {
            'cost_type': 'fabric', 'cost_date': date.today().isoformat(), 'amount': '800', 'paid_by': 'cash',
        })
        self.assertFalse(Cost.objects.exists())

    def test_overall_cost_has_no_order(self):
        response = self.client.get(reverse('accounts:add_overall_cost'))
        self.assertNotIn('project', response.context['form'].fields)
        self.client.post(reverse('accounts:add_overall_cost'), {
            'cost_type': 'rent', 'cost_date': date.today().isoformat(), 'description': 'Factory rent',
            'amount': '60000', 'paid_by': 'cash', 'bank_name': 'ignored',
        })
        cost = Cost.objects.get()
        self.assertIsNone(cost.project)
        self.assertEqual(cost.bank_name, '')
        self.assertEqual(CashBookEntry.balance(mode='cash'), Decimal('-60000'))

    def test_cost_can_record_supplier_paid(self):
        self.client.post(reverse('accounts:add_overall_cost'), {
            'cost_type': 'maintenance', 'supplier': self.supplier.pk, 'cost_date': date.today().isoformat(),
            'description': 'Generator service', 'amount': '900', 'paid_by': 'cash',
        })
        cost = Cost.objects.get()
        self.assertEqual(cost.supplier, self.supplier)
        self.assertIn('paid to Test Supplier', CashBookEntry.objects.get(source='cost').description)
        response = self.client.get(reverse('accounts:costs_list'), {'supplier': self.supplier.pk})
        self.assertEqual(list(response.context['costs']), [cost])

    def test_costs_date_range_filter(self):
        services.record_cost(Cost(cost_type='rent', cost_date=date(2026, 8, 31), amount=Decimal('100')))
        services.record_cost(Cost(cost_type='rent', cost_date=date(2026, 9, 15), amount=Decimal('200')))
        services.record_cost(Cost(cost_type='rent', cost_date=date(2026, 10, 1), amount=Decimal('400')))
        response = self.client.get(reverse('accounts:costs_list'), {'from': '2026-09-01', 'to': '2026-09-30'})
        self.assertEqual(response.context['total'], Decimal('200'))
        self.assertEqual(self.client.get(reverse('accounts:costs_list'), {'from': '2026-09-01'}).context['total'], Decimal('600'))

    def test_payments_date_range_filter(self):
        for day, amount in [(date(2026, 8, 31), '100'), (date(2026, 9, 15), '200')]:
            self.client.post(reverse('accounts:add_payment'), {
                'payment_type': 'receivable', 'payment_method': 'bank', 'buyer': self.buyer.pk,
                'amount': amount, 'payment_date': day.isoformat(),
            })
        response = self.client.get(reverse('accounts:payments_list'), {'from': '2026-09-01', 'to': '2026-09-30'})
        self.assertEqual(response.context['total_received'], Decimal('200'))

    def test_costs_list_tabs(self):
        order = self.make_order()
        services.record_cost(Cost(project=order, cost_type='fabric', cost_date=date.today(), amount=Decimal('10')))
        services.record_cost(Cost(cost_type='rent', cost_date=date.today(), amount=Decimal('20')))
        self.assertEqual(len(self.client.get(reverse('accounts:costs_list'), {'scope': 'order'}).context['costs']), 1)
        self.assertEqual(len(self.client.get(reverse('accounts:costs_list'), {'scope': 'overall'}).context['costs']), 1)
        self.assertEqual(self.client.get(reverse('accounts:costs_list')).context['total'], Decimal('30'))


@override_settings(MERCHANDISING_ENABLED=False)
class VoucherTests(AccountingTestCase):
    def raise_voucher(self, **extra):
        data = {'cost_type': 'office', 'voucher_date': date.today().isoformat(), 'description': 'Printer ink',
                'amount': '1500', 'paid_by': 'cash'}
        data.update(extra)
        return self.client.post(reverse('accounts:add_voucher'), data)

    def test_any_user_can_raise_a_voucher(self):
        self.client.force_login(self.warehouse_user())
        response = self.raise_voucher()
        self.assertRedirects(response, reverse('accounts:voucher_list'))
        voucher = CostVoucher.objects.get()
        self.assertEqual(voucher.status, 'pending')
        self.assertFalse(Cost.objects.exists())
        # ...sees only their own vouchers, and can't approve.
        self.assertContains(self.client.get(reverse('accounts:voucher_list')), voucher.voucher_number)
        self.client.post(reverse('accounts:approve_voucher', args=[voucher.pk]))
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'pending')
        self.assertContains(self.client.get(reverse('inventory:fabric_list')), 'Expense Vouchers')

    def test_approval_creates_paid_cost(self):
        self.raise_voucher()
        voucher = CostVoucher.objects.get()
        self.client.post(reverse('accounts:approve_voucher', args=[voucher.pk]))
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'approved')
        self.assertEqual(voucher.cost.amount, Decimal('1500'))
        self.assertIsNone(voucher.cost.project)
        self.assertEqual(CashBookEntry.objects.get(source='cost').amount, Decimal('1500'))
        # Approving twice does nothing more.
        self.client.post(reverse('accounts:approve_voucher', args=[voucher.pk]))
        self.assertEqual(Cost.objects.count(), 1)

    def test_voucher_supplier_carries_to_cost(self):
        self.raise_voucher(supplier=self.supplier.pk)
        voucher = CostVoucher.objects.get()
        self.client.post(reverse('accounts:approve_voucher', args=[voucher.pk]))
        voucher.refresh_from_db()
        self.assertEqual(voucher.cost.supplier, self.supplier)

    def test_reject_records_nothing(self):
        self.raise_voucher()
        voucher = CostVoucher.objects.get()
        self.client.post(reverse('accounts:reject_voucher', args=[voucher.pk]), {'reason': 'Not needed'})
        voucher.refresh_from_db()
        self.assertEqual((voucher.status, voucher.rejection_reason), ('rejected', 'Not needed'))
        self.assertFalse(Cost.objects.exists())

    def test_order_voucher_types_must_match(self):
        order = self.make_order()
        self.raise_voucher(project=order.pk, cost_type='rent')        # overall type with an order
        self.raise_voucher(cost_type='fabric')                         # order type without an order
        self.assertFalse(CostVoucher.objects.exists())
        self.raise_voucher(project=order.pk, cost_type='fabric')
        self.assertEqual(CostVoucher.objects.get().project, order)

    def test_vouchers_in_pending_approvals(self):
        self.raise_voucher()
        response = self.client.get(reverse('inventory:pending_approvals'))
        self.assertContains(response, CostVoucher.objects.get().voucher_number)


@override_settings(MERCHANDISING_ENABLED=False)
class CashBookTests(AccountingTestCase):
    def test_manual_entries_and_transfer(self):
        url = reverse('accounts:add_cashbook_entry')
        self.client.post(url, {'entry_type': 'in', 'entry_date': date.today().isoformat(), 'amount': '1000',
                               'mode': 'cash', 'description': 'Opening balance'})
        self.client.post(url, {'entry_type': 'to_bank', 'entry_date': date.today().isoformat(), 'amount': '400',
                               'mode': 'cash', 'bank_name': 'Prime Bank'})
        self.assertEqual(CashBookEntry.balance(mode='cash'), Decimal('600'))
        self.assertEqual(CashBookEntry.balance(mode='bank'), Decimal('400'))
        self.assertEqual(CashBookEntry.balance(), Decimal('1000'))
        response = self.client.get(reverse('accounts:cashbook'))
        self.assertEqual(response.context['total_balance'], Decimal('1000'))
        self.assertEqual(response.context['entries'][0].balance_after, Decimal('1000'))

    def test_money_in_needs_a_description(self):
        self.client.post(reverse('accounts:add_cashbook_entry'), {
            'entry_type': 'in', 'entry_date': date.today().isoformat(), 'amount': '10', 'mode': 'cash',
        })
        self.assertFalse(CashBookEntry.objects.exists())

    def test_payments_are_money_in_from_buyers_only(self):
        form = self.client.get(reverse('accounts:add_payment')).context['form']
        self.assertNotIn('supplier', form.fields)
        self.client.post(reverse('accounts:add_payment'), {
            'payment_type': 'receivable', 'payment_method': 'cash',
            'buyer': self.buyer.pk, 'amount': '1200', 'payment_date': date.today().isoformat(),
        })
        self.assertEqual(CashBookEntry.balance(mode='cash'), Decimal('1200'))

        # A supplier payment posted anyway is turned into nothing: no buyer -> refused.
        self.client.post(reverse('accounts:add_payment'), {
            'payment_type': 'payable', 'payment_method': 'bank',
            'supplier': self.supplier.pk, 'amount': '200', 'payment_date': date.today().isoformat(),
        })
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(CashBookEntry.balance(mode='bank'), Decimal('0'))

    def test_bank_book_pages_redirect_to_cash_book(self):
        for name in ['banks_list', 'bank_transactions_list', 'add_bank']:
            with self.subTest(page=name):
                self.assertRedirects(self.client.get(reverse(f'accounts:{name}')), reverse('accounts:cashbook'))
        response = self.client.get(reverse('accounts:accounts_dashboard'))
        self.assertNotContains(response, reverse('accounts:banks_list'))
        self.assertContains(response, reverse('accounts:cashbook'))


@override_settings(MERCHANDISING_ENABLED=False)
class PaymentsPageTests(AccountingTestCase):
    def record_payment(self, amount='500', method='bank'):
        return self.client.post(reverse('accounts:add_payment'), {
            'payment_type': 'receivable', 'payment_method': method, 'buyer': self.buyer.pk,
            'amount': amount, 'payment_date': date.today().isoformat(),
        })

    def test_payment_number_is_generated(self):
        self.record_payment()
        self.record_payment()
        first, second = Payment.objects.order_by('pk')
        self.assertEqual(first.payment_number, f"{first.created_at:%y}PAY{first.pk:05d}")
        self.assertEqual(int(second.payment_number[-5:]), first.pk + 1)
        self.assertNotIn('payment_number', self.client.get(reverse('accounts:add_payment')).context['form'].fields)

    def test_lc_is_not_a_payment_method(self):
        self.assertNotIn('lc', dict(Payment.PAYMENT_METHODS))
        self.record_payment(method='lc')
        self.assertFalse(Payment.objects.exists())

    def test_direct_and_lc_payments_on_one_page(self):
        lc = self.make_lc()
        self.record_payment(amount='500')
        response = self.client.post(reverse('accounts:add_lc_receipt'), {
            'lc': lc.pk, 'payment_date': date.today().isoformat(), 'amount': '2000', 'exchange_rate': '120',
            'bank_name': 'Prime Bank',
        })
        self.assertRedirects(response, reverse('accounts:payments_list') + '?source=lc')
        receipt = lc.lc_payments.get()
        self.assertEqual((receipt.amount, receipt.amount_bdt), (Decimal('2000'), Decimal('240000')))
        self.assertEqual(CashBookEntry.objects.get(source='lc_receipt').amount, Decimal('240000'))

        response = self.client.get(reverse('accounts:payments_list'))
        self.assertEqual(len(response.context['rows']), 2)
        self.assertEqual(response.context['total_received'], Decimal('240500'))   # BDT
        self.assertEqual(response.context['total_lc'], Decimal('240000'))
        self.assertEqual(response.context['total_lc_usd'], Decimal('2000'))
        self.assertContains(response, 'LC LC-1')
        self.assertContains(response, '৳ 2,40,000.00')
        self.assertContains(response, '$ 2,000.00')
        self.assertContains(response, receipt.receipt_number)
        self.assertEqual(len(self.client.get(reverse('accounts:payments_list'), {'source': 'lc'}).context['rows']), 1)
        self.assertEqual(len(self.client.get(reverse('accounts:payments_list'), {'source': 'direct'}).context['rows']), 1)

    def test_lc_receipt_needs_a_rate_and_bdt_can_be_typed(self):
        lc = self.make_lc()
        url = reverse('accounts:add_lc_receipt')
        self.client.post(url, {'lc': lc.pk, 'payment_date': date.today().isoformat(), 'amount': '100'})
        self.assertFalse(lc.lc_payments.exists())
        self.client.post(url, {'lc': lc.pk, 'payment_date': date.today().isoformat(), 'amount': '100',
                               'exchange_rate': '121.5', 'amount_bdt': '12140'})
        self.assertEqual(lc.lc_payments.get().amount_bdt, Decimal('12140'))
        # The next form suggests the last rate used.
        self.assertEqual(self.client.get(url).context['form'].initial['exchange_rate'], Decimal('121.5'))

    def test_direct_payment_order_must_match_buyer(self):
        order = self.make_order()
        other = Buyer.objects.create(buyer_code='B2', buyer_name='Other', country='BD', email='o@example.com',
                                     phone='1', address='x')
        self.client.post(reverse('accounts:add_payment'), {
            'payment_type': 'receivable', 'payment_method': 'bank', 'buyer': other.pk, 'project': order.pk,
            'amount': '1000', 'amount_usd': '10', 'payment_date': date.today().isoformat(),
        })
        self.assertFalse(Payment.objects.exists())
        # USD equivalent needs an order to count against.
        self.client.post(reverse('accounts:add_payment'), {
            'payment_type': 'receivable', 'payment_method': 'bank', 'buyer': self.buyer.pk,
            'amount': '1000', 'amount_usd': '10', 'payment_date': date.today().isoformat(),
        })
        self.assertFalse(Payment.objects.exists())
    def test_lc_payment_only_on_active_lcs(self):
        lc = self.make_lc()
        services.complete_lc(lc, Decimal('10000'), Decimal('120'), user=self.admin)
        self.client.post(reverse('accounts:add_lc_receipt'), {
            'lc': lc.pk, 'payment_date': date.today().isoformat(), 'amount': '10',
        })
        self.assertEqual(lc.lc_payments.count(), 1)  # only the completion receipt

    def test_inactive_tabs_are_styled_for_the_page_background(self):
        response = self.client.get(reverse('accounts:payments_list'))
        self.assertContains(response, '.content-wrapper .nav-tabs .nav-link {')


@override_settings(MERCHANDISING_ENABLED=False)
class AccountingWithoutMerchandisingTests(AccountingTestCase):
    def test_menu_shows_orders_but_not_pos_or_invoices(self):
        response = self.client.get(reverse('accounts:accounts_dashboard'))
        self.assertContains(response, 'Orders')
        self.assertNotContains(response, reverse('accounts:purchase_orders_list'))
        self.assertNotContains(response, reverse('accounts:invoices_list'))

    def test_po_and_invoice_pages_are_blocked(self):
        for name in ['purchase_orders_list', 'add_purchase_order', 'invoices_list', 'add_invoice']:
            with self.subTest(page=name):
                response = self.client.get(reverse(f'accounts:{name}'))
                self.assertRedirects(response, reverse('accounts:accounts_dashboard'))

    def test_dashboard_and_reports(self):
        order = self.make_order()                               # USD 5000
        Payment.objects.create(
            payment_type='receivable', payment_method='bank', buyer=self.buyer, project=order,
            amount=Decimal('145800'), amount_usd=Decimal('1200'), payment_date=date.today(), status='completed',
        )
        services.record_cost(Cost(project=order, cost_type='fabric', cost_date=date.today(), amount=Decimal('800')))
        services.record_cost(Cost(cost_type='rent', cost_date=date.today(), amount=Decimal('200')))

        response = self.client.get(reverse('accounts:accounts_dashboard'))
        self.assertEqual(response.context['monthly_sales'], Decimal('145800'))   # BDT
        self.assertEqual(response.context['receivables'], Decimal('3800'))      # USD
        self.assertEqual(response.context['cash_balance'], Decimal('-1000'))

        response = self.client.get(reverse('accounts:financial_reports'))
        self.assertEqual(response.context['all_order_costs'], Decimal('800'))
        self.assertEqual(response.context['all_overall_costs'], Decimal('200'))
        self.assertEqual(response.context['all_received'], Decimal('145800'))
        self.assertEqual(response.context['all_net'], Decimal('144800'))
        self.assertEqual(response.context['total_receivable'], Decimal('3800'))

    def test_order_receivable_in_usd_from_lc_and_direct_payments(self):
        lc = self.make_lc('3000')                             # order value USD 5000
        order = lc.project
        services.record_lc_receipt(LCPayment(lc=lc, payment_date=date.today(), amount=Decimal('2000'),
                                             exchange_rate=Decimal('120')), user=self.admin)
        Payment.objects.create(payment_type='receivable', payment_method='bank', buyer=self.buyer, project=order,
                               amount=Decimal('60000'), amount_usd=Decimal('500'), payment_date=date.today(),
                               status='completed')
        self.assertEqual(order.receivable_usd, Decimal('2500'))
        self.assertEqual(order.received_bdt, Decimal('300000'))
        response = self.client.get(reverse('accounts:project_detail', args=[order.pk]))
        self.assertContains(response, '$ 2,500.00')
        self.assertContains(response, '৳ 3,00,000.00')
    def test_all_accounting_pages_render(self):
        lc = self.make_lc()
        order = lc.project
        loan = services.take_loan(LCLoan(lc=lc, loan_date=date.today(), loan_amount=Decimal('100')), user=self.admin)
        for name, args in [('accounts_dashboard', []), ('buyers_list', []), ('suppliers_list', []),
                           ('projects_list', []), ('add_project', []), ('edit_project', [order.pk]),
                           ('project_detail', [order.pk]), ('payments_list', []), ('add_payment', []),
                           ('lc_list', []), ('add_lc', []), ('lc_detail', [lc.pk]), ('add_lc_loan', [lc.pk]),
                           ('add_lc_payment', [lc.pk]), ('repay_lc_loan', [loan.pk]),
                           ('costs_list', []), ('add_cost', []), ('add_overall_cost', []),
                           ('voucher_list', []), ('add_voucher', []), ('cashbook', []), ('add_cashbook_entry', []),
                           ('cost_sheets', []), ('add_cost_sheet', []), ('financial_reports', [])]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f'accounts:{name}', args=args)).status_code, 200)


@override_settings(MERCHANDISING_ENABLED=True)
class AccountingWithMerchandisingTests(AccountingTestCase):
    """Turning the setting on brings the full Project form, POs and Invoices back."""

    def test_full_pages_return(self):
        response = self.client.get(reverse('accounts:accounts_dashboard'))
        self.assertContains(response, reverse('accounts:purchase_orders_list'))
        for name in ['purchase_orders_list', 'add_purchase_order', 'invoices_list', 'add_invoice']:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f'accounts:{name}')).status_code, 200)
        response = self.client.get(reverse('accounts:add_project'))
        self.assertTemplateUsed(response, 'accounts/project_form.html')
        self.assertIn('sales_invoice', self.client.get(reverse('accounts:add_payment')).context['form'].fields)
        self.assertIn('purchase_order', self.client.get(reverse('accounts:add_cost')).context['form'].fields)


class SeedDataTests(TestCase):
    def test_seed_data_runs_and_cash_book_adds_up(self):
        from io import StringIO
        from django.core.management import call_command
        User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        call_command('seed_data', stdout=StringIO())
        call_command('seed_data', stdout=StringIO())  # idempotent
        self.assertTrue(Project.objects.filter(project_number__contains='ORD').exists())
        self.assertTrue(Cost.objects.filter(project__isnull=True).exists())
        self.assertEqual(LetterOfCredit.objects.filter(status='completed').count(), 1)
        completed = LetterOfCredit.objects.get(status='completed')
        self.assertGreater(completed.loan_adjusted, 0)
        self.assertTrue(all(loan.is_settled for loan in completed.lc_loans.all()))
        # Every cost is in the cash book exactly once.
        self.assertEqual(CashBookEntry.objects.filter(source='cost').count(), Cost.objects.count())


class AmountHelperTests(TestCase):
    def test_taka_in_words(self):
        from .amounts import taka_in_words
        self.assertEqual(taka_in_words(Decimal('1500')), 'One Thousand Five Hundred Taka Only')
        self.assertEqual(taka_in_words(Decimal('152340.50')),
                         'One Lakh Fifty Two Thousand Three Hundred Forty Taka and Fifty Paisa Only')
        self.assertEqual(taka_in_words(Decimal('12345678')),
                         'One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Taka Only')

    def test_format_taka(self):
        from .amounts import format_taka
        self.assertEqual(format_taka(Decimal('999')), '999.00')
        self.assertEqual(format_taka(Decimal('152340.5')), '1,52,340.50')
        self.assertEqual(format_taka(Decimal('12345678.99')), '1,23,45,678.99')


@override_settings(MERCHANDISING_ENABLED=False)
class VoucherPrintTests(AccountingTestCase):
    def make_voucher(self, user, **extra):
        data = dict(cost_type='maintenance', description='Generator service', amount=Decimal('152340.50'),
                    paid_by='cash', requested_by=user)
        data.update(extra)
        return CostVoucher.objects.create(**data)

    def test_print_shows_voucher_details(self):
        voucher = self.make_voucher(self.admin, supplier=self.supplier, remarks='Spare parts included')
        response = self.client.get(reverse('accounts:print_voucher', args=[voucher.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'DEBIT VOUCHER')
        self.assertContains(response, voucher.voucher_number)
        self.assertContains(response, 'Repair &amp; Maintenance')
        self.assertContains(response, 'Test Supplier')
        self.assertContains(response, 'Generator service')
        self.assertContains(response, '1,52,340.50', count=2)  # line + total
        self.assertContains(response, 'One Lakh Fifty Two Thousand')
        self.assertContains(response, 'Spare parts included')
        self.assertNotContains(response, 'REJECTED')

    def test_pay_to_falls_back_to_requester(self):
        staff = self.warehouse_user()
        staff.first_name, staff.last_name = 'Rahim', 'Uddin'
        staff.save()
        voucher = self.make_voucher(staff)
        self.client.force_login(staff)
        self.assertContains(self.client.get(reverse('accounts:print_voucher', args=[voucher.pk])), 'Rahim Uddin')

    def test_order_voucher_shows_order(self):
        order = self.make_order()
        voucher = self.make_voucher(self.admin, project=order, cost_type='fabric')
        self.assertContains(self.client.get(reverse('accounts:print_voucher', args=[voucher.pk])), order.project_number)

    def test_rejected_voucher_is_stamped(self):
        voucher = self.make_voucher(self.admin, status='rejected')
        self.assertContains(self.client.get(reverse('accounts:print_voucher', args=[voucher.pk])), 'REJECTED')

    def test_users_can_only_print_their_own(self):
        voucher = self.make_voucher(self.admin)
        self.client.force_login(self.warehouse_user())
        self.assertEqual(self.client.get(reverse('accounts:print_voucher', args=[voucher.pk])).status_code, 404)

    def test_print_button_in_list(self):
        voucher = self.make_voucher(self.admin)
        response = self.client.get(reverse('accounts:voucher_list'))
        self.assertContains(response, reverse('accounts:print_voucher', args=[voucher.pk]))
