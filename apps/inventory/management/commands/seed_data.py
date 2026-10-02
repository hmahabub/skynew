"""
Seeds demo data across Accounts, HR and Inventory so every list page in the
app has realistic, varied records to look at instead of being empty or
holding one or two hand-entered test rows.

Idempotent: everything is created with get_or_create keyed on a unique
field, so running this command again won't create duplicates - it just
tops up anything still missing.

Usage: python manage.py seed_data
"""
import random
from datetime import timedelta, date, time as dtime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import (
    Buyer, Supplier, Project, PurchaseOrder, PurchaseOrderItem,
    SalesInvoice, SalesInvoiceItem, Payment,
    CostSheet, BankAccount, BankTransaction,
    LetterOfCredit, LCPayment, LCLoan, Cost, CashBookEntry,
)
from apps.hr.models import (
    Department, Designation, Employee, Attendance, Leave, ProductionOutput,
    PieceRateSetting, Payroll, Loan,
)
from apps.inventory.models import (
    Fabric, FabricRoll, Trim, GoodsReceipt, GoodsReceiptDetail,
    TrimReceipt, TrimReceiptDetail, ProductionIssue, ProductionIssueDetail,
    FinishedGoods, FinishedGoodsProduction, Dispatch, DispatchDetail,
    StockMovement, StockTransfer,
    Machine, MachineEvent, SparePart, SparePartConsumption,
    StationeryItem, StationeryConsumption, SupplyAdjustment,
)

from apps.accounts import services as accounts_services
from apps.inventory.views import _add_fabric_lot

TODAY = date.today()
DEMO_RATE = Decimal('121.50')  # BDT per USD for demo LC receipts / payments
random.seed(42)


def rand_date(days_ago_min, days_ago_max):
    return TODAY - timedelta(days=random.randint(days_ago_min, days_ago_max))


class Command(BaseCommand):
    help = "Seed demo data for Accounts, HR and Inventory."

    def handle(self, *args, **options):
        self.user = User.objects.filter(is_superuser=True).order_by('id').first()

        with transaction.atomic():
            self.seed_cashbook_opening()
            self.seed_buyers()
            self.seed_suppliers()
            self.seed_projects()
            self.seed_purchase_orders()
            self.seed_sales_invoices()
            self.seed_bank_accounts()
            self.seed_cost_sheets()
            self.seed_letters_of_credit()
            self.seed_costs()

            self.seed_departments()
            self.seed_designations()
            self.seed_employees()
            self.seed_attendance()
            self.seed_leaves()
            self.seed_production_output()
            self.seed_piece_rates()
            self.seed_payroll()
            self.seed_loans()

            self.seed_fabrics()
            self.seed_fabric_rolls()
            self.seed_trims()
            self.seed_goods_receipts()
            self.seed_trim_receipts()
            self.seed_finished_goods()
            self.seed_finished_goods_production()
            self.seed_production_issues()
            self.seed_dispatches()
            self.seed_stock_transfers()

            self.seed_machines()
            self.seed_machine_events()
            self.seed_spare_parts()
            self.seed_spare_part_consumptions()
            self.seed_stationery_items()
            self.seed_stationery_consumptions()
            self.seed_supply_adjustments()

            self.clamp_negative_stock()

        self.stdout.write(self.style.SUCCESS("Seed data complete."))
        self.print_summary()

    # ---------------------------------------------------------------- accounts

    def seed_buyers(self):
        data = [
            ('BYR-001', 'Northstar Garments Co.', 'USA'),
            ('BYR-002', 'EuroStyle Fashions', 'Germany'),
            ('BYR-003', 'Urban Threads International', 'UK'),
            ('BYR-004', 'Pacific Rim Clothing', 'Australia'),
            ('BYR-005', 'Trendline Apparel Ltd', 'Canada'),
            ('BYR-006', 'Iberia Fashion Group', 'Spain'),
        ]
        self.buyers = []
        for code, name, country in data:
            obj, _ = Buyer.objects.get_or_create(
                buyer_code=code,
                defaults=dict(
                    buyer_name=name, country=country,
                    email=f"orders@{name.lower().split()[0]}.example.com",
                    phone=f"+1{random.randint(2000000000, 9999999999)}",
                    address=f"{random.randint(10,999)} Trade Ave, {country}",
                    credit_limit=Decimal(random.randint(50000, 300000)),
                    credit_days=random.choice([30, 45, 60]),
                ),
            )
            self.buyers.append(obj)

    def seed_suppliers(self):
        data = [
            ('SUP-001', 'Padma Textile Mills', 'fabric'),
            ('SUP-002', 'Karnaphuli Fabrics Ltd', 'fabric'),
            ('SUP-003', 'Green Delta Yarns', 'fabric'),
            ('SUP-004', 'Silk Route Trims', 'trim'),
            ('SUP-005', 'Bay Fabrics International', 'both'),
            ('SUP-006', 'Meghna Dyeing & Finishing', 'service'),
        ]
        self.suppliers = []
        for code, name, s_type in data:
            obj, _ = Supplier.objects.get_or_create(
                supplier_code=code,
                defaults=dict(
                    supplier_name=name, supplier_type=s_type,
                    email=f"sales@{name.lower().split()[0]}.example.com",
                    phone=f"+8801{random.randint(700000000, 999999999)}",
                    address=f"{random.randint(1,200)} Industrial Rd, Dhaka",
                    bank_name="Prime Bank Ltd",
                    bank_account=str(random.randint(10**9, 10**10 - 1)),
                    credit_days=random.choice([15, 30, 45]),
                ),
            )
            self.suppliers.append(obj)

    def seed_projects(self):
        names = [
            "Classic Crew Tee", "Slim Fit Polo", "Zip-Up Hoodie", "Denim Jeans",
            "Summer Maxi Dress", "Bomber Jacket", "Cargo Shorts", "Flannel Shirt",
        ]
        statuses = ['order', 'production', 'shipped', 'delivered']
        self.projects = []
        for i, name in enumerate(names, start=1):
            buyer_ref = f"STY-2026-{i:03d}"
            qty = random.randint(2000, 15000)
            unit_price = Decimal(random.randint(4, 25))
            obj, _ = Project.objects.get_or_create(
                buyer_ref=buyer_ref,
                defaults=dict(
                    buyer=random.choice(self.buyers),
                    description=name,
                    order_quantity=qty,
                    unit_price=unit_price,
                    total_value=unit_price * qty,
                    currency='USD',
                    cm_charge=Decimal(random.randint(1, 4)),
                    agent_commission=Decimal(random.randint(0, 2)),
                    fabric_cost=Decimal(random.randint(10000, 40000)),
                    trim_cost=Decimal(random.randint(2000, 8000)),
                    labor_cost=Decimal(random.randint(5000, 20000)),
                    overhead_cost=Decimal(random.randint(2000, 10000)),
                    order_date=rand_date(60, 200),
                    delivery_date=rand_date(-60, 30),
                    status=random.choice(statuses),
                ),
            )
            if not obj.total_cost:
                obj.calculate_profit()
            self.projects.append(obj)

    def seed_purchase_orders(self):
        for i in range(1, 6):
            po_number = f"PO-2026-{i:03d}"
            if PurchaseOrder.objects.filter(po_number=po_number).exists():
                continue
            total = Decimal(random.randint(50000, 200000))
            po = PurchaseOrder.objects.create(
                po_number=po_number,
                supplier=random.choice(self.suppliers),
                style=random.choice(self.projects),
                order_date=rand_date(30, 120),
                delivery_date=rand_date(-30, 20),
                total_amount=total,
                advance_paid=total * Decimal('0.3'),
                net_amount=total,
                status=random.choice(['approved', 'received', 'completed']),
                created_by=self.user,
            )
            for _ in range(random.randint(1, 3)):
                qty = Decimal(random.randint(500, 5000))
                price = Decimal(random.randint(100, 500))
                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    item_description=random.choice(["Cotton Fabric", "Buttons", "Zippers", "Thread Cones"]),
                    quantity=qty, unit_price=price, total_price=qty * price,
                )

    def seed_sales_invoices(self):
        for i in range(1, 7):
            inv_number = f"INV-2026-{i:03d}"
            if SalesInvoice.objects.filter(invoice_number=inv_number).exists():
                continue
            style = random.choice(self.projects)
            amount = Decimal(random.randint(30000, 150000))
            inv = SalesInvoice.objects.create(
                invoice_number=inv_number,
                style=style, buyer=style.buyer,
                invoice_date=rand_date(10, 90),
                due_date=rand_date(-30, 10),
                amount=amount, net_amount=amount,
                currency='USD',
                status=random.choice(['sent', 'pending', 'partial', 'paid']),
                created_by=self.user,
            )
            SalesInvoiceItem.objects.create(
                invoice=inv, item_description=style.description,
                quantity=random.randint(500, 3000),
                unit_price=style.unit_price,
                total_price=amount,
            )
            if inv.status == 'paid':
                pay_number = f"PAY-2026-{i:03d}"
                if not Payment.objects.filter(payment_number=pay_number).exists():
                    payment = Payment.objects.create(
                        payment_number=pay_number,
                        payment_type='receivable',
                        payment_method=random.choice(['bank', 'cheque', 'online']),
                        buyer=inv.buyer, sales_invoice=inv, project=style,
                        # Received in taka; the invoice is USD.
                        amount=(amount * DEMO_RATE).quantize(Decimal('0.01')), amount_usd=amount,
                        payment_date=rand_date(0, 8),
                        created_by=self.user,
                    )
                    payment.process_payment()
                    accounts_services.record_payment(payment, user=self.user)

    def seed_bank_accounts(self):
        data = [
            ('OPR-0001', 'Operating Account', 'Prime Bank Ltd', 'Gulshan Branch', 'current'),
            ('PAY-0001', 'Payroll Account', 'Prime Bank Ltd', 'Gulshan Branch', 'savings'),
        ]
        self.bank_accounts = []
        for acc_no, name, bank, branch, acc_type in data:
            obj, _ = BankAccount.objects.get_or_create(
                account_number=acc_no,
                defaults=dict(
                    account_name=name, bank_name=bank, branch_name=branch,
                    account_type=acc_type,
                    opening_balance=Decimal(random.randint(200000, 800000)),
                    current_balance=Decimal(random.randint(200000, 800000)),
                ),
            )
            self.bank_accounts.append(obj)

        if not BankTransaction.objects.exists():
            for acc in self.bank_accounts:
                for _ in range(3):
                    txn_type = random.choice(['deposit', 'withdrawal', 'payment'])
                    txn = BankTransaction.objects.create(
                        bank_account=acc, transaction_type=txn_type,
                        amount=Decimal(random.randint(5000, 50000)),
                        transaction_date=rand_date(1, 30),
                        description=f"{txn_type.title()} - demo transaction",
                        created_by=self.user,
                    )
                    txn.process_transaction()

    def seed_cashbook_opening(self):
        if CashBookEntry.objects.exists():
            return
        accounts_services.post_cashbook('in', Decimal('50000'), "Opening balance - cash in hand",
                                        entry_date=TODAY - timedelta(days=90), mode='cash', user=self.user)
        accounts_services.post_cashbook('in', Decimal('750000'), "Opening balance - bank",
                                        entry_date=TODAY - timedelta(days=90), mode='bank',
                                        bank_name='Prime Bank Ltd', user=self.user)

    def seed_cost_sheets(self):
        if CostSheet.objects.exists():
            return
        for style in self.projects[:5]:
            cs = CostSheet.objects.create(
                style=style, cost_date=style.order_date,
                fabric_cost=style.fabric_cost, trim_cost=style.trim_cost,
                packaging_cost=Decimal(random.randint(500, 2000)),
                cutting_labor=Decimal(random.randint(1000, 3000)),
                stitching_labor=Decimal(random.randint(3000, 8000)),
                finishing_labor=Decimal(random.randint(1000, 3000)),
                qc_labor=Decimal(random.randint(500, 1500)),
                factory_overhead=Decimal(random.randint(2000, 6000)),
                administrative_cost=Decimal(random.randint(1000, 3000)),
                selling_cost=Decimal(random.randint(500, 1500)),
                selling_price=style.total_value,
                created_by=self.user,
            )
            cs.calculate_totals()

    def seed_letters_of_credit(self):
        if LetterOfCredit.objects.exists():
            return
        for i, project in enumerate(self.projects[:3], start=1):
            lc = LetterOfCredit.objects.create(
                lc_number=f"LC-2026-{i:03d}",
                project=project,
                lc_date=project.order_date,
                bank_name="Prime Bank Ltd",
                lc_amount=project.total_value,
                currency=project.currency,
                expiry_date=project.delivery_date,
                status='active',
                created_by=self.user,
            )
            accounts_services.record_lc_receipt(LCPayment(
                lc=lc, payment_date=rand_date(30, 40),
                amount=(lc.lc_amount * Decimal('0.2')).quantize(Decimal('0.01')),
                exchange_rate=DEMO_RATE,
                bank_name=lc.bank_name, reference=f"REF-{lc.lc_number}-1",
            ), user=self.user)
            if i in (1, 2):
                loan = accounts_services.take_loan(LCLoan(
                    lc=lc, loan_date=rand_date(20, 30), bank_name=lc.bank_name,
                    loan_amount=(lc.lc_amount * DEMO_RATE * Decimal('0.4')).quantize(Decimal('0.01')),
                    interest=(lc.lc_amount * DEMO_RATE * Decimal('0.01')).quantize(Decimal('0.01')),
                    other_charges=Decimal(random.randint(5000, 20000)),
                ), user=self.user)
                accounts_services.repay_loan(
                    loan, (loan.loan_amount * Decimal('0.25')).quantize(Decimal('0.01')),
                    repayment_date=rand_date(5, 15), bank_name=lc.bank_name, user=self.user,
                )
            if i == 2:
                # Completed LC: the rest of its loan is adjusted from the realised amount.
                accounts_services.complete_lc(lc, lc.lc_outstanding, Decimal('122.00'), completion_date=rand_date(1, 4),
                                              reference=f"REAL-{lc.lc_number}", user=self.user)

    def seed_costs(self):
        if Cost.objects.exists():
            return
        order_cost_types = ['fabric', 'accessories', 'production', 'transport', 'commission', 'documentation']
        for project in self.projects:
            for cost_type in random.sample(order_cost_types, k=3):
                accounts_services.record_cost(Cost(
                    project=project,
                    cost_type=cost_type,
                    cost_date=rand_date(5, 60),
                    description=f"{cost_type.title()} for {project.buyer_ref or project.project_number}",
                    amount=Decimal(random.randint(1000, 15000)),
                    currency=project.currency,
                    paid_by=random.choice(['cash', 'bank']),
                    bank_name='Prime Bank Ltd',
                    supplier=random.choice(self.suppliers) if cost_type in ('fabric', 'accessories') else None,
                ), user=self.user)
        for cost_type, amount in [('rent', 60000), ('utilities', 18000), ('salaries', 250000),
                                  ('office', 7500), ('maintenance', 12000)]:
            accounts_services.record_cost(Cost(
                cost_type=cost_type, cost_date=rand_date(1, 25),
                description=f"{dict(Cost.COST_TYPES)[cost_type]} - this month",
                amount=Decimal(amount), paid_by='bank' if amount > 10000 else 'cash', bank_name='Prime Bank Ltd',
            ), user=self.user)

    # --------------------------------------------------------------------- hr

    def seed_departments(self):
        data = [
            ('Cutting', 'CUT'), ('Sewing', 'SEW'), ('Finishing', 'FIN'),
            ('Quality Control', 'QC'), ('Merchandising', 'MER'),
            ('HR & Admin', 'HR'), ('Store & Warehouse', 'STR'), ('Maintenance', 'MNT'),
        ]
        self.departments = {}
        for name, code in data:
            obj, _ = Department.objects.get_or_create(code=code, defaults=dict(name=name, hod=f"{name} Head"))
            self.departments[code] = obj

    def seed_designations(self):
        data = [
            ('CUT', 'Cutting Master', 'G3'), ('CUT', 'Cutting Operator', 'G5'),
            ('SEW', 'Line Supervisor', 'G3'), ('SEW', 'Sewing Operator', 'G5'),
            ('FIN', 'Finishing In-charge', 'G3'), ('FIN', 'Finishing Helper', 'G6'),
            ('QC', 'QC Manager', 'G2'), ('QC', 'QC Inspector', 'G4'),
            ('MER', 'Merchandiser', 'G3'), ('MER', 'Senior Merchandiser', 'G2'),
            ('HR', 'HR Executive', 'G3'), ('HR', 'Admin Officer', 'G4'),
            ('STR', 'Store Keeper', 'G4'), ('STR', 'Store Assistant', 'G5'),
            ('MNT', 'Maintenance Technician', 'G4'), ('MNT', 'Electrician', 'G5'),
        ]
        self.designations = {}
        for dept_code, name, grade in data:
            obj, _ = Designation.objects.get_or_create(
                name=name, department=self.departments[dept_code],
                defaults=dict(grade=grade, basic_salary_min=Decimal(8000), basic_salary_max=Decimal(25000)),
            )
            self.designations.setdefault(dept_code, []).append(obj)

    def seed_employees(self):
        first_male = ['Rasel', 'Arif', 'Kamal', 'Jahangir', 'Habibur', 'Shakil', 'Mahmud',
                       'Tanvir', 'Rezaul', 'Ashraf', 'Nazrul', 'Imran', 'Sohel', 'Faruk', 'Mizanur']
        first_female = ['Rima', 'Shirin', 'Nasrin', 'Ayesha', 'Farida', 'Salma', 'Rehana',
                         'Taslima', 'Jesmin', 'Shabnam', 'Ruma', 'Monira', 'Parvin', 'Lucky', 'Halima']
        last_names = ['Islam', 'Ahmed', 'Hossain', 'Rahman', 'Khan', 'Akter', 'Begum',
                      'Chowdhury', 'Miah', 'Sarker', 'Talukder', 'Molla', 'Sheikh', 'Uddin', 'Kabir']
        skill_by_dept = {
            'CUT': 'cutting', 'SEW': 'stitching', 'FIN': 'finishing', 'QC': 'qc',
            'MER': 'management', 'HR': 'management', 'STR': 'supervisor', 'MNT': 'maintenance',
        }

        self.employees = list(Employee.objects.all())
        existing = Employee.objects.count()
        target = 30
        dept_codes = list(self.departments.keys())

        for i in range(existing, target):
            gender = random.choice(['male', 'female'])
            first = random.choice(first_male if gender == 'male' else first_female)
            last = random.choice(last_names)
            full_name = f"{first} {last}"
            national_id = f"19{random.randint(70, 99)}{random.randint(10**8, 10**9 - 1)}"
            if Employee.objects.filter(national_id=national_id).exists():
                continue
            dept_code = dept_codes[i % len(dept_codes)]
            designation = random.choice(self.designations[dept_code])
            basic = Decimal(random.randint(9000, 22000))
            emp = Employee.objects.create(
                full_name=full_name,
                father_name=f"{random.choice(first_male)} {last}",
                mother_name=f"{random.choice(first_female)} {last}",
                date_of_birth=rand_date(365 * 20, 365 * 45),
                gender=gender,
                marital_status=random.choice(['single', 'married']),
                national_id=national_id,
                joining_date=rand_date(30, 365 * 5),
                department=self.departments[dept_code],
                designation=designation,
                skill_category=skill_by_dept[dept_code],
                employment_type=random.choice(['monthly', 'monthly', 'contractual']),
                shift=random.choice(['morning', 'day', 'night']),
                basic_salary=basic,
                house_rent=basic * Decimal('0.4'),
                medical_allowance=Decimal(500),
                transport_allowance=Decimal(300),
                phone_number=f"+8801{random.randint(700000000, 999999999)}",
                emergency_contact=f"+8801{random.randint(700000000, 999999999)}",
                present_address=f"House {random.randint(1,200)}, Dhaka",
                permanent_address=f"Village Rd, {random.choice(['Comilla','Bogura','Rangpur','Jessore'])}",
                created_by=self.user,
            )
            self.employees.append(emp)

    def seed_attendance(self):
        for emp in self.employees:
            for d in range(5):
                day = TODAY - timedelta(days=d)
                if Attendance.objects.filter(employee=emp, date=day).exists():
                    continue
                status = random.choices(
                    ['present', 'present', 'present', 'late', 'absent'],
                    weights=[5, 5, 5, 2, 1],
                )[0]
                if status in ('present', 'late'):
                    check_in = dtime(9, random.randint(0, 40)) if status == 'present' else dtime(9, random.randint(41, 59))
                    Attendance.objects.create(
                        employee=emp, date=day, status=status,
                        check_in_time=check_in, check_out_time=dtime(18, random.randint(0, 30)),
                        marked_by=self.user,
                    )
                else:
                    Attendance.objects.create(employee=emp, date=day, status=status, marked_by=self.user)

    def seed_leaves(self):
        if Leave.objects.filter(reason="Personal reasons").count() >= 10:
            return
        for emp in random.sample(self.employees, min(10, len(self.employees))):
            start = rand_date(5, 60)
            Leave.objects.create(
                employee=emp,
                leave_type=random.choice(['sick', 'casual', 'unpaid']),
                start_date=start, end_date=start + timedelta(days=random.randint(0, 3)),
                reason="Personal reasons",
                status=random.choice(['pending', 'approved', 'approved', 'rejected']),
                approved_by=self.user,
            )

    def seed_production_output(self):
        if ProductionOutput.objects.exists():
            return
        floor_employees = [e for e in self.employees if e.skill_category in ('cutting', 'stitching', 'finishing')]
        for emp in floor_employees:
            for d in range(3):
                produced = random.randint(80, 300)
                defective = random.randint(0, 10)
                ProductionOutput.objects.create(
                    employee=emp, date=TODAY - timedelta(days=d),
                    style_number=random.choice(self.projects).project_number,
                    operation_name=random.choice(['Collar Attach', 'Side Seam', 'Hemming', 'Button Hole']),
                    quantity_produced=produced, defective_quantity=defective,
                    line_supervisor="Line Supervisor", shift=emp.shift,
                    machine_hours=Decimal(str(round(random.uniform(6, 9), 2))),
                )

    def seed_piece_rates(self):
        if PieceRateSetting.objects.exists():
            return
        ops = ['Collar Attach', 'Side Seam', 'Hemming', 'Button Hole', 'Zipper Attach']
        for i, project in enumerate(self.projects[:5]):
            PieceRateSetting.objects.create(
                style_number=project.project_number, operation_name=ops[i % len(ops)],
                skill_level=random.choice(['beginner', 'intermediate', 'expert']),
                rate_per_piece=Decimal(str(round(random.uniform(1.5, 6.0), 2))),
                target_per_day=random.randint(80, 200),
                effective_from=rand_date(30, 120),
            )

    def seed_payroll(self):
        month, year = TODAY.month, TODAY.year
        for emp in self.employees:
            if Payroll.objects.filter(employee=emp, month=month, year=year).exists():
                continue
            pr = Payroll(
                employee=emp, month=month, year=year,
                basic_pay=emp.basic_salary, house_rent=emp.house_rent,
                medical_allowance=emp.medical_allowance, transport_allowance=emp.transport_allowance,
                overtime_amount=Decimal(random.randint(0, 2000)),
                pf_deduction=emp.basic_salary * Decimal('0.05'),
                days_present=random.randint(22, 26), days_absent=random.randint(0, 3),
                status='processed', generated_by=self.user,
            )
            pr.calculate_totals()
            pr.save()

    def seed_loans(self):
        if Loan.objects.exists():
            return
        for emp in random.sample(self.employees, min(5, len(self.employees))):
            start = rand_date(30, 180)
            Loan.objects.create(
                employee=emp, loan_type=random.choice(['personal', 'education']),
                amount=Decimal(random.randint(10000, 50000)),
                interest_rate=Decimal('0'),
                tenure_months=random.choice([6, 12, 18]),
                reason="Family emergency",
                status=random.choice(['approved', 'pending']),
                start_date=start, end_date=start + timedelta(days=365),
            )

    # -------------------------------------------------------------- inventory

    def seed_fabrics(self):
        names = ['Cotton Poplin', 'Pique Knit', 'French Terry', 'Denim Twill',
                 'Jersey Single', 'Rib Knit', 'Corduroy', 'Chambray',
                 'Fleece', 'Oxford Weave', 'Satin', 'Voile', 'Canvas',
                 'Interlock Knit', 'Herringbone Twill']
        colors = ['Black', 'White', 'Navy', 'Grey', 'Red', 'Royal Blue', 'Olive', 'Beige']
        types = [t[0] for t in Fabric.FABRIC_TYPES]

        self.fabrics = []
        for i, name in enumerate(names, start=1):
            fname = f"{name} - {colors[i % len(colors)]}"
            project = random.choice(self.projects)
            obj, created = Fabric.objects.get_or_create(
                fabric_name=fname,
                defaults=dict(
                    fabric_type=types[i % len(types)],
                    color=colors[i % len(colors)],
                    gsm=random.randint(120, 400),
                    width=Decimal(random.randint(44, 64)),
                    supplier=random.choice(self.suppliers).supplier_name,
                    project=project.project_number,
                    purchase_order=f"PO-{random.randint(1000, 9999)}",
                    buyer=project.buyer.buyer_name,
                    unit='meter',
                    unit_price=Decimal(random.randint(150, 650)),
                    description=f"{fname} sourced for demo styles.",
                ),
            )
            self.fabrics.append(obj)

    def seed_fabric_rolls(self):
        if FabricRoll.objects.exists():
            return
        n = 1
        for fabric in self.fabrics:
            for _ in range(random.randint(1, 2)):
                length = Decimal(random.randint(100, 500))
                used = Decimal(random.randint(0, int(length) // 2))
                lot_number = f"LOT-{n:05d}"
                roll = FabricRoll.objects.create(
                    roll_number=lot_number, fabric=fabric,
                    lot_number=lot_number,
                    length=length, used_length=used, remaining_length=length - used,
                    location="Main Warehouse", rack_number=f"R{random.randint(1,20)}",
                    bin_number=f"B{random.randint(1,50)}",
                    received_date=rand_date(5, 120),
                    quality_status='passed',
                )
                # Fabric stock is the sum of what's left in its lots.
                Fabric.objects.filter(pk=fabric.pk).update(current_stock=F('current_stock') + roll.remaining_length)
                StockMovement.objects.create(
                    movement_type='receipt', reference_number=f"LOT-{lot_number}",
                    reference_id=roll.pk, fabric=fabric, fabric_roll=roll, quantity=length,
                    notes="Demo lot", created_by=self.user,
                )
                if used:
                    StockMovement.objects.create(
                        movement_type='issue', reference_number=f"LOT-{lot_number}",
                        reference_id=roll.pk, fabric=fabric, fabric_roll=roll, quantity=-used,
                        notes="Issued to Production", created_by=self.user,
                    )
                n += 1
        for fabric in self.fabrics:
            fabric.refresh_from_db()

    def seed_trims(self):
        names = ['Plastic Button 4-hole', 'YKK Zipper 7"', 'Woven Label', 'Elastic Band 1"',
                 'Satin Ribbon', 'Cotton Lace', 'Size Tag', 'Hook & Loop Strip',
                 'Polyester Thread 40s', 'Metal Snap Button', 'Drawcord', 'Care Label',
                 'Main Label', 'Poly Bag', 'Hang Tag']
        types = [t[0] for t in Trim.TRIM_TYPES]
        stock_buckets = [100, 400, 800, 1500, 3000]
        self.trims = []
        for i, name in enumerate(names, start=1):
            obj, _ = Trim.objects.get_or_create(
                trim_name=name,
                defaults=dict(
                    trim_type=types[i % len(types)],
                    supplier=random.choice(self.suppliers),
                    unit=random.choice(['pcs', 'meter', 'roll']),
                    unit_price=Decimal(str(round(random.uniform(0.5, 15), 2))),
                    current_stock=stock_buckets[i % len(stock_buckets)],
                    color=random.choice(['Black', 'White', 'Natural', '']),
                    description=f"{name} for demo styles.",
                ),
            )
            self.trims.append(obj)

    def seed_goods_receipts(self):
        for i in range(1, 5):
            invoice_number = f"SUPINV-{1000+i}"
            if GoodsReceipt.objects.filter(invoice_number=invoice_number).exists():
                continue
            supplier = random.choice(self.suppliers)
            receipt = GoodsReceipt.objects.create(
                supplier=supplier, invoice_number=invoice_number,
                invoice_date=rand_date(5, 60),
                received_by=self.user,
                notes="Demo goods receipt",
            )
            total_qty = Decimal('0')
            for fabric in random.sample(self.fabrics, k=3):
                qty = Decimal(random.randint(100, 400))
                price = fabric.unit_price
                GoodsReceiptDetail.objects.create(
                    goods_receipt=receipt, fabric=fabric, quantity=qty, unit_price=price,
                )
                _add_fabric_lot(
                    fabric, qty, self.user,
                    notes=f"Goods receipt from {supplier.supplier_name}",
                    reference_number=receipt.receipt_number, reference_id=receipt.pk,
                )
                total_qty += qty
            receipt.total_quantity = total_qty
            receipt.save()

    def seed_trim_receipts(self):
        for i in range(1, 5):
            invoice_number = f"TRIMINV-{1000+i}"
            if TrimReceipt.objects.filter(invoice_number=invoice_number).exists():
                continue
            supplier = random.choice(self.suppliers)
            receipt = TrimReceipt.objects.create(
                supplier=supplier, invoice_number=invoice_number,
                invoice_date=rand_date(5, 60),
                received_by=self.user,
                notes="Demo trim receipt",
            )
            total_qty = 0
            for trim in random.sample(self.trims, k=3):
                qty = random.randint(200, 1000)
                TrimReceiptDetail.objects.create(
                    trim_receipt=receipt, trim=trim, quantity=qty, unit_price=trim.unit_price,
                )
                Trim.objects.filter(pk=trim.pk).update(current_stock=F('current_stock') + qty)
                total_qty += qty
                StockMovement.objects.create(
                    movement_type='receipt', reference_number=receipt.receipt_number,
                    reference_id=receipt.pk, trim=trim, quantity=qty,
                    notes=f"Trim receipt from {supplier.supplier_name}", created_by=self.user,
                )
            receipt.total_quantity = total_qty
            receipt.save()

    def seed_finished_goods(self):
        style_codes = ['TSHIRT', 'POLO', 'HOODIE', 'JEANS', 'DRESS', 'JACKET']
        sizes = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
        colors = ['Black', 'White', 'Navy', 'Grey', 'Red', 'Blue']
        warehouses = ['WH-A Main', 'WH-B Finishing', 'WH-C Export']

        self.finished_goods = list(FinishedGoods.objects.all())
        existing = {(fg.style, fg.size, fg.color) for fg in self.finished_goods}

        combos = [(sc, sz, c) for sc in style_codes for sz in sizes for c in colors]
        random.shuffle(combos)

        created_count = 0
        target_new = 45
        for style_code, size, color in combos:
            if created_count >= target_new:
                break
            style = f"ST-{style_code}"
            if (style, size, color) in existing:
                continue

            in_stock = random.choice([0, random.randint(10, 100), random.randint(100, 800), random.randint(100, 800)])

            dispatched = random.randint(0, 500)
            produced = in_stock + dispatched

            fg = FinishedGoods.objects.create(
                style=style, size=size, color=color,
                quantity_produced=produced, quantity_in_stock=in_stock,
                quantity_dispatched=dispatched,
                quantity_defective=random.randint(0, 20),
                unit_price=Decimal(random.randint(300, 1500)),
                warehouse_location=random.choice(warehouses),
                rack_location=f"R{random.randint(1,30)}",
                bin_location=f"B{random.randint(1,80)}",
                description=f"{style_code.title()} - {size} - {color}",
            )
            self.finished_goods.append(fg)
            existing.add((style, size, color))
            created_count += 1

    def seed_finished_goods_production(self):
        if FinishedGoodsProduction.objects.exists():
            return
        for i, fg in enumerate(random.sample(self.finished_goods, min(15, len(self.finished_goods))), start=1):
            produced = random.randint(200, 1000)
            defective = random.randint(0, 30)
            FinishedGoodsProduction.objects.create(
                batch_number=f"BATCH-2026-{i:04d}",
                project=random.choice(self.projects),
                finished_goods=fg,
                production_date=rand_date(1, 90),
                quantity_produced=produced,
                quantity_defective=defective,
                quantity_good=produced - defective,
                production_line=f"Line-{random.randint(1,6)}",
                supervisor="Line Supervisor",
                quality_status=random.choice(['passed', 'partial', 'pending']),
                created_by=self.user,
            )

    def seed_production_issues(self):
        if ProductionIssue.objects.exists():
            return
        for i in range(1, 6):
            project = random.choice(self.projects)
            issue = ProductionIssue.objects.create(
                issue_number=f"ISS-2026-{i:03d}",
                project=project, issue_date=rand_date(1, 60),
                issued_by=self.user,
                department=self.departments['CUT'],
                production_line=f"Line-{random.randint(1,6)}",
                status='issued',
            )
            # Take the issue out of a real lot so fabric stock keeps matching its lots.
            lot = FabricRoll.objects.filter(status='in_stock', remaining_length__gt=20).order_by('?').first()
            if lot:
                fabric = lot.fabric
                qty = Decimal(random.randint(5, min(50, int(lot.remaining_length))))
                ProductionIssueDetail.objects.create(
                    production_issue=issue, fabric=fabric, fabric_roll=lot,
                    quantity_requested=qty, quantity_issued=qty,
                )
                lot.used_length += qty
                lot.save()
                Fabric.objects.filter(pk=fabric.pk).update(current_stock=F('current_stock') - qty)
                StockMovement.objects.create(
                    movement_type='issue', reference_number=issue.issue_number,
                    reference_id=issue.pk, fabric=fabric, fabric_roll=lot, quantity=-qty,
                    notes=f"Issued to production - {project.project_number}", created_by=self.user,
                )

    def seed_dispatches(self):
        """
        A mix of the three dispatch states: approved Dispatched (stock
        deducted), On-going / Pending (reserved - shows as Pending Dispatch),
        and one awaiting approval so Pending Approvals has a demo row.
        """
        if Dispatch.objects.exists():
            return
        available = [fg for fg in self.finished_goods if fg.quantity_in_stock > 10]
        plan = ['dispatched', 'dispatched', 'dispatched', 'dispatched', 'on_going', 'on_going', 'pending', 'awaiting']
        for i, state in enumerate(plan[:len(available)], start=1):
            fg = available[i - 1]
            fg.refresh_from_db()
            project = random.choice(self.projects)
            qty = random.randint(5, min(50, fg.quantity_in_stock))
            dispatch = Dispatch.objects.create(
                dispatch_number=f"DSP-2026-{i:03d}",
                project=project,
                dispatch_date=rand_date(1, 45),
                total_cartons=random.randint(1, 5),
                total_quantity=qty,
                shipping_line=random.choice(['Maersk', 'MSC', 'CMA CGM']),
                status='on_going' if state == 'awaiting' else state,
                dispatch_approval={'dispatched': 'approved', 'awaiting': 'pending'}.get(state, 'none'),
                approval_requested_by=self.user if state in ('dispatched', 'awaiting') else None,
                approved_by=self.user if state == 'dispatched' else None,
                approved_date=date.today() if state == 'dispatched' else None,
                created_by=self.user,
            )
            DispatchDetail.objects.create(
                dispatch=dispatch, finished_goods=fg,
                carton_number=f"CTN-{i:04d}", quantity=qty,
            )
            if state == 'dispatched':
                FinishedGoods.objects.filter(pk=fg.pk).update(
                    quantity_in_stock=F('quantity_in_stock') - qty,
                    quantity_dispatched=F('quantity_dispatched') + qty,
                )
                StockMovement.objects.create(
                    movement_type='dispatch', reference_number=dispatch.dispatch_number,
                    reference_id=dispatch.pk, finished_goods=fg, quantity=-qty,
                    notes=f"Dispatched to {project.buyer.buyer_name}", created_by=self.user,
                )

    def seed_stock_transfers(self):
        """A couple of transfer requests left pending, so Pending Approvals has demo rows."""
        if StockTransfer.objects.exists():
            return
        lot = FabricRoll.objects.filter(status='in_stock', remaining_length__gt=20).first()
        if lot:
            StockTransfer.objects.create(
                fabric=lot.fabric, fabric_roll=lot, quantity=Decimal('10'), reason='issue',
                issued_to='Cutting - Line 1', notes='Demo: awaiting approval', requested_by=self.user,
            )
        trim = next((t for t in self.trims if t.current_stock > 50), None)
        if trim:
            StockTransfer.objects.create(
                trim=trim, quantity=Decimal('25'), reason='issue',
                issued_to='Sewing - Line 2', notes='Demo: awaiting approval', requested_by=self.user,
            )

    # ---------------------------------------------------------------- machines

    def seed_machines(self):
        specs = [
            ('MC-00001', 'Single Needle Lockstitch #1', 'sewing_single_needle', 'Juki', 'active'),
            ('MC-00002', 'Single Needle Lockstitch #2', 'sewing_single_needle', 'Juki', 'active'),
            ('MC-00003', 'Overlock Machine #1', 'sewing_overlock', 'Brother', 'active'),
            ('MC-00004', 'Overlock Machine #2', 'sewing_overlock', 'Brother', 'idle'),
            ('MC-00005', 'Flatlock Machine #1', 'sewing_flatlock', 'Pegasus', 'active'),
            ('MC-00006', 'Bartack Machine #1', 'sewing_bartack', 'Juki', 'active'),
            ('MC-00007', 'Buttonhole Machine #1', 'sewing_buttonhole', 'Jack', 'under_maintenance'),
            ('MC-00008', 'Straight Knife Cutter', 'cutting_straight_knife', 'Eastman', 'active'),
            ('MC-00009', 'Band Knife Cutter', 'cutting_band_knife', 'Eastman', 'broken_down'),
            ('MC-00010', 'Fusing Press #1', 'fusing_press', 'Hashima', 'active'),
            ('MC-00011', 'Embroidery Machine #1', 'embroidery', 'Tajima', 'active'),
            ('MC-00012', 'Washing Machine #1', 'washing', 'Union', 'active'),
            ('MC-00013', 'Boiler Unit #1', 'boiler', 'Cleaver Brooks', 'active'),
            ('MC-00014', 'Generator Unit #1', 'generator', 'Cummins', 'idle'),
            ('MC-00015', 'Air Compressor #1', 'compressor', 'Atlas Copco', 'active'),
        ]
        dept_by_type = {
            'sewing': 'SEW', 'cutting': 'CUT', 'fusing_press': 'SEW',
            'embroidery': 'SEW', 'washing': 'FIN', 'boiler': 'MNT',
            'generator': 'MNT', 'compressor': 'MNT',
        }
        self.machines = []
        for code, name, m_type, brand, status in specs:
            dept_code = next((v for k, v in dept_by_type.items() if m_type.startswith(k)), 'MNT')
            machine, _ = Machine.objects.get_or_create(
                machine_code=code,
                defaults=dict(
                    machine_name=name, machine_type=m_type, brand=brand,
                    model_number=f"{brand[:2].upper()}-{random.randint(100,999)}",
                    serial_number=f"SN{random.randint(100000,999999)}",
                    supplier=random.choice(self.suppliers),
                    department=self.departments.get(dept_code),
                    line_number=f"Line-{random.randint(1,6)}",
                    location=f"Floor {random.randint(1,3)}, Line-{random.randint(1,6)}",
                    purchase_date=rand_date(180, 1500),
                    purchase_cost=Decimal(random.randint(50000, 800000)),
                    warranty_expiry=rand_date(-365, 365),
                    status=status,
                    created_by=self.user,
                ),
            )
            self.machines.append(machine)

    def seed_machine_events(self):
        if MachineEvent.objects.exists():
            return
        broken = next((m for m in self.machines if m.status == 'broken_down'), None)
        if broken:
            MachineEvent.objects.create(
                machine=broken, event_type='breakdown', event_date=rand_date(1, 10),
                description="Needle bar jammed, reported by line supervisor.",
                status='approved', approved_by=self.user, approved_date=date.today(),
                created_by=self.user,
            )
        maintenance = next((m for m in self.machines if m.status == 'under_maintenance'), None)
        if maintenance:
            MachineEvent.objects.create(
                machine=maintenance, event_type='maintenance', event_date=rand_date(1, 5),
                description="Routine servicing.", cost=Decimal(random.randint(500, 3000)),
                status='approved', approved_by=self.user, approved_date=date.today(),
                created_by=self.user,
            )
        # One pending 'scrapped' request so Pending Approvals has a demo row.
        idle = next((m for m in self.machines if m.status == 'idle'), None)
        if idle:
            MachineEvent.objects.create(
                machine=idle, event_type='scrapped', event_date=date.today(),
                description="Beyond economical repair - recommend scrapping.",
                counterparty="Local scrap dealer", cost=Decimal(random.randint(2000, 8000)),
                status='pending', created_by=self.user,
            )

    # ------------------------------------------------------------ spare parts

    def seed_spare_parts(self):
        names = [
            ('Sewing Machine Needle DBx1', 'needle', 'sewing_single_needle'),
            ('Overlock Needle', 'needle', 'sewing_overlock'),
            ('Servo Motor', 'motor', 'sewing_single_needle'),
            ('Drive Belt', 'belt', 'sewing_single_needle'),
            ('Bobbin Case', 'bobbin', 'sewing_single_needle'),
            ('Presser Foot Set', 'presser_foot', 'sewing_single_needle'),
            ('Ball Bearing 6203', 'bearing', 'other'),
            ('Feed Dog Gear', 'gear', 'sewing_single_needle'),
            ('Control Board PCB', 'electronic_board', 'sewing_single_needle'),
            ('Band Knife Blade', 'blade', 'cutting_band_knife'),
            ('Straight Knife Blade', 'blade', 'cutting_straight_knife'),
            ('Fusing Press Belt', 'belt', 'fusing_press'),
        ]
        stock_buckets = [20, 50, 100, 200, 400]
        self.spare_parts = []
        for i, (name, category, compat) in enumerate(names, start=1):
            part, _ = SparePart.objects.get_or_create(
                part_name=name,
                defaults=dict(
                    category=category, compatible_machine_type=compat,
                    supplier=random.choice(self.suppliers),
                    unit='pcs', unit_price=Decimal(str(round(random.uniform(1, 150), 2))),
                    current_stock=stock_buckets[i % len(stock_buckets)],
                    min_stock=30, max_stock=1000,
                    description=f"{name} for demo machinery.",
                ),
            )
            self.spare_parts.append(part)

    def seed_spare_part_consumptions(self):
        if SparePartConsumption.objects.exists():
            return
        departments = list(self.departments.values())
        for _ in range(10):
            part = random.choice(self.spare_parts)
            if part.current_stock < 2:
                continue
            qty = random.randint(1, min(5, part.current_stock))
            machine = random.choice(self.machines) if random.random() < 0.6 else None
            SparePartConsumption.objects.create(
                spare_part=part, department=random.choice(departments), machine=machine,
                quantity=qty, unit_price_at_consumption=part.unit_price,
                consumption_date=rand_date(0, 30), notes="Routine maintenance usage.",
                issued_by=self.user,
            )
            SparePart.objects.filter(pk=part.pk).update(current_stock=F('current_stock') - qty)
            StockMovement.objects.create(
                movement_type='issue', reference_number=f"SPC-{part.pk}-{qty}",
                reference_id=part.pk, spare_part=part, quantity=-qty,
                notes="Demo consumption", created_by=self.user,
            )

    # ------------------------------------------------------------ stationery

    def seed_stationery_items(self):
        names = [
            ('A4 Paper Ream', 'paper'), ('Ball Pen (Box of 50)', 'writing'),
            ('Printer Toner Cartridge', 'printing'), ('File Folder', 'filing'),
            ('Stapler', 'writing'), ('Whiteboard Marker', 'writing'),
            ('Cleaning Cloth Roll', 'cleaning'), ('Hand Sanitizer Bottle', 'cleaning'),
            ('Sticky Notes Pad', 'writing'), ('Envelope Pack', 'filing'),
        ]
        stock_buckets = [10, 30, 60, 120]
        self.stationery_items = []
        for i, (name, category) in enumerate(names, start=1):
            item, _ = StationeryItem.objects.get_or_create(
                item_name=name,
                defaults=dict(
                    category=category, unit='pcs',
                    unit_price=Decimal(str(round(random.uniform(0.5, 40), 2))),
                    current_stock=stock_buckets[i % len(stock_buckets)],
                    min_stock=15, max_stock=500,
                    description=f"{name} for office/floor use.",
                ),
            )
            self.stationery_items.append(item)

    def seed_stationery_consumptions(self):
        if StationeryConsumption.objects.exists():
            return
        departments = list(self.departments.values())
        for _ in range(8):
            item = random.choice(self.stationery_items)
            if item.current_stock < 2:
                continue
            qty = random.randint(1, min(5, item.current_stock))
            StationeryConsumption.objects.create(
                stationery_item=item, department=random.choice(departments),
                quantity=qty, unit_price_at_consumption=item.unit_price,
                consumption_date=rand_date(0, 30), notes="Routine office usage.",
                issued_by=self.user,
            )
            StationeryItem.objects.filter(pk=item.pk).update(current_stock=F('current_stock') - qty)
            StockMovement.objects.create(
                movement_type='issue', reference_number=f"STC-{item.pk}-{qty}",
                reference_id=item.pk, stationery_item=item, quantity=-qty,
                notes="Demo consumption", created_by=self.user,
            )

    # ------------------------------------------------------- supply adjustments

    def seed_supply_adjustments(self):
        if SupplyAdjustment.objects.exists():
            return
        # One approved correction, already applied.
        part = next((p for p in self.spare_parts if p.current_stock > 10), None)
        if part:
            qty = 3
            adjustment = SupplyAdjustment.objects.create(
                adjustment_type='damage', direction='decrease', spare_part=part,
                adjustment_date=rand_date(1, 10), quantity=qty,
                reason="Damaged in storage - demo approved adjustment.",
                status='approved', created_by=self.user,
                approved_by=self.user, approved_date=date.today(),
            )
            SparePart.objects.filter(pk=part.pk).update(current_stock=F('current_stock') - qty)
            StockMovement.objects.create(
                movement_type='adjustment', reference_number=adjustment.adjustment_number,
                reference_id=adjustment.pk, spare_part=part, quantity=-qty,
                notes=adjustment.reason, created_by=self.user,
            )

        # One pending correction so Pending Approvals has a demo row.
        item = next((s for s in self.stationery_items if s.current_stock > 5), None)
        if item:
            SupplyAdjustment.objects.create(
                adjustment_type='recount', direction='increase', stationery_item=item,
                adjustment_date=date.today(), quantity=5,
                reason="Physical recount found more stock than recorded - demo pending.",
                status='pending', created_by=self.user,
            )

    # ------------------------------------------------------------------- misc

    def clamp_negative_stock(self):
        """
        Safety net: several stock updates above compute quantities off
        in-memory objects that can go stale across a loop touching the same
        item twice (e.g. two production issues against the same fabric).
        The updates themselves use F() expressions so the DB never loses an
        update, but a too-generous quantity picked from a stale read could
        still push a balance below zero - clamp those back to 0 rather than
        let seeded demo data show impossible negative stock.
        """
        Fabric.objects.filter(current_stock__lt=0).update(current_stock=0)
        Trim.objects.filter(current_stock__lt=0).update(current_stock=0)
        FinishedGoods.objects.filter(quantity_in_stock__lt=0).update(quantity_in_stock=0)
        SparePart.objects.filter(current_stock__lt=0).update(current_stock=0)
        StationeryItem.objects.filter(current_stock__lt=0).update(current_stock=0)

    def print_summary(self):
        rows = [
            ("Buyers", Buyer.objects.count()), ("Suppliers", Supplier.objects.count()),
            ("Projects", Project.objects.count()), ("Purchase Orders", PurchaseOrder.objects.count()),
            ("Sales Invoices", SalesInvoice.objects.count()), ("Letters of Credit", LetterOfCredit.objects.count()),
            ("Costs", Cost.objects.count()), ("Departments", Department.objects.count()),
            ("Employees", Employee.objects.count()), ("Fabrics", Fabric.objects.count()),
            ("Trims", Trim.objects.count()), ("Finished Goods", FinishedGoods.objects.count()),
            ("Dispatches", Dispatch.objects.count()), ("Stock Transfers", StockTransfer.objects.count()),
            ("Stock Movements", StockMovement.objects.count()),
            ("Machines", Machine.objects.count()), ("Machine Events", MachineEvent.objects.count()),
            ("Spare Parts", SparePart.objects.count()), ("Spare Part Consumptions", SparePartConsumption.objects.count()),
            ("Stationery Items", StationeryItem.objects.count()), ("Stationery Consumptions", StationeryConsumption.objects.count()),
            ("Supply Adjustments", SupplyAdjustment.objects.count()),
        ]
        for label, count in rows:
            self.stdout.write(f"  {label}: {count}")
