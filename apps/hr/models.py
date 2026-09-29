from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date, datetime, time

class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    hod = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class Designation(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='designations')
    grade = models.CharField(max_length=10)
    basic_salary_min = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    basic_salary_max = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def __str__(self):
        return f"{self.name} - {self.department.name}"

class Employee(models.Model):
    SKILL_CATEGORIES = [
        ('cutting', 'Cutting'),
        ('stitching', 'Stitching'),
        ('finishing', 'Finishing'),
        ('washing', 'Washing'),
        ('qc', 'Quality Control'),
        ('maintenance', 'Maintenance'),
        ('supervisor', 'Supervisor'),
        ('management', 'Management'),
    ]
    
    EMPLOYMENT_TYPES = [
        ('monthly', 'Monthly Salary'),
        ('contractual', 'Contractual'),
    ]
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]
    
    MARITAL_STATUS = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    ]
    
    SHIFT_CHOICES = [
        ('morning', 'Morning (8 AM - 4 PM)'),
        ('day', 'Day (10 AM - 6 PM)'),
        ('night', 'Night (10 PM - 6 AM)'),
    ]
    
    # Personal Information
    employee_id = models.CharField(max_length=20, unique=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hr_employee')
    full_name = models.CharField(max_length=200)
    father_name = models.CharField(max_length=200)
    mother_name = models.CharField(max_length=200)
    spouse_name = models.CharField(max_length=200, blank=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    marital_status = models.CharField(max_length=10, choices=MARITAL_STATUS, default='single')
    national_id = models.CharField(max_length=50, unique=True)
    passport_number = models.CharField(max_length=50, blank=True)
    
    # Employment Information
    joining_date = models.DateField()
    confirmation_date = models.DateField(null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='employees')
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True, related_name='employees')
    skill_category = models.CharField(max_length=50, choices=SKILL_CATEGORIES)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES)
    line_assignment = models.CharField(max_length=50, blank=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='day')
    reporting_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')
    
    # Compensation
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    house_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    daily_wage_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Contact Information
    phone_number = models.CharField(max_length=15)
    emergency_contact = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    present_address = models.TextField()
    permanent_address = models.TextField()
    
    # Bank Information
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_no = models.CharField(max_length=50, blank=True)
    pf_account_no = models.CharField(max_length=50, blank=True)
    
    # Documents  
    profile_picture = models.ImageField(upload_to='employee_profiles/', null=True, blank=True)
    resume = models.FileField(upload_to='employee_resumes/', null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_on_leave = models.BooleanField(default=False)
    termination_date = models.DateField(null=True, blank=True)
    termination_reason = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_employees')
    
    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"
    
    @property
    def age(self):
        today = date.today()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
    
    @property
    def total_salary(self):
        return self.basic_salary + self.house_rent + self.medical_allowance + self.transport_allowance

    @property
    def ordinary_hourly_rate(self):
        """Standard hourly rate derived from gross monthly salary, based on
        a 26-day / 8-hour standard month (208 hours) commonly used for
        garment-sector payroll in Bangladesh."""
        if self.total_salary:
            return self.total_salary / Decimal('208')
        return Decimal('0')

    @property
    def overtime_hourly_rate(self):
        """Overtime is paid at double the ordinary hourly rate."""
        return self.ordinary_hourly_rate * Decimal('2')

    def leave_balance(self, year=None):
        """Returns {leave_type: {entitled, used, remaining}} for every
        leave type that carries an annual quota (see Leave.LEAVE_ANNUAL_QUOTA).
        Used for showing balances on the leave application form and for
        validating new leave requests."""
        year = year or date.today().year
        balance = {}
        for leave_type, quota in Leave.LEAVE_ANNUAL_QUOTA.items():
            used = Leave.days_used(self, leave_type, year)
            balance[leave_type] = {
                'entitled': quota,
                'used': used,
                'remaining': max(quota - used, 0),
            }
        return balance

    def save(self, *args, **kwargs):
        if not self.employee_id:
            last_employee = Employee.objects.filter(
                employee_id__startswith='EMP'
            ).order_by('-employee_id').first()

            if last_employee:
                last_count = int(last_employee.employee_id[3:])
                new_count = last_count + 1
            else:
                new_count = 1

            self.employee_id = f"EMP{new_count:04d}"

        super().save(*args, **kwargs)

    class Meta:
        ordering = ['employee_id']

class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('half_day', 'Half Day'),
        ('leave', 'Leave'),
        ('holiday', 'Holiday'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    is_late = models.BooleanField(default=False)
    late_minutes = models.IntegerField(default=0)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    working_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    remarks = models.TextField(blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        unique_together = ['employee', 'date']
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.employee.full_name} - {self.date} - {self.status}"
    
    def save(self, *args, **kwargs):
        if self.check_in_time and self.check_out_time:
            # Calculate working hours
            check_in = datetime.combine(date.today(), self.check_in_time)
            check_out = datetime.combine(date.today(), self.check_out_time)
            diff = check_out - check_in
            self.working_hours = diff.total_seconds() / 3600
            
            # Check if late (after 9 AM)
            if self.check_in_time > time(9, 0):
                self.is_late = True
                late = datetime.combine(date.today(), self.check_in_time) - datetime.combine(date.today(), time(9, 0))
                self.late_minutes = late.total_seconds() / 60
        
        super().save(*args, **kwargs)

class Leave(models.Model): 
    LEAVE_TYPES = [
        ('sick', 'Sick Leave'),
        ('casual', 'Casual Leave'),
        ('unpaid', 'Unpaid Leave'),
    ]

    # Annual entitlement, in days, per leave type. 'unpaid' intentionally
    # has no entry here - it is not quota-tracked, but every day taken as
    # unpaid leave is treated like an absence for payroll purposes.
    LEAVE_ANNUAL_QUOTA = {
        'casual': 14,
        'sick': 10,
    }

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leaves')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.IntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_leaves')
    approved_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.employee.full_name} - {self.leave_type} - {self.start_date} to {self.end_date}"

    @property
    def is_paid(self):
        """Unpaid leave does not draw against a paid-leave balance and is
        treated like an unexcused absence for payroll deduction purposes."""
        return self.leave_type != 'unpaid'

    @classmethod
    def days_used(cls, employee, leave_type, year, exclude_pk=None):
        """Total approved days of this leave type already used by the
        employee within the given calendar year."""
        qs = cls.objects.filter(
            employee=employee,
            leave_type=leave_type,
            status='approved',
            start_date__year=year,
        )
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        return qs.aggregate(total=models.Sum('total_days'))['total'] or 0

    @classmethod
    def remaining_balance(cls, employee, leave_type, year, exclude_pk=None):
        """Days remaining for a quota-tracked leave type, or None if the
        leave type (e.g. unpaid) isn't quota-tracked."""
        quota = cls.LEAVE_ANNUAL_QUOTA.get(leave_type)
        if quota is None:
            return None
        used = cls.days_used(employee, leave_type, year, exclude_pk=exclude_pk)
        return quota - used
    
    def save(self, *args, **kwargs):
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            self.total_days = delta.days + 1
        super().save(*args, **kwargs)

class ProductionOutput(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='production_outputs')
    date = models.DateField()
    style_number = models.CharField(max_length=50)
    operation_name = models.CharField(max_length=100)
    quantity_produced = models.IntegerField()
    defective_quantity = models.IntegerField(default=0)
    rejected_quantity = models.IntegerField(default=0)
    line_supervisor = models.CharField(max_length=100)
    shift = models.CharField(max_length=20)
    machine_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    
    @property
    def good_quantity(self):
        return self.quantity_produced - self.defective_quantity - self.rejected_quantity
    
    @property
    def quality_rate(self):
        if self.quantity_produced > 0:
            return ((self.good_quantity) / self.quantity_produced) * 100
        return 100
    
    @property
    def efficiency(self):
        if self.machine_hours > 0:
            return (self.quantity_produced / self.machine_hours)
        return 0
    
    def __str__(self):
        return f"{self.employee.full_name} - {self.date} - {self.quantity_produced} pcs"
    
    class Meta:
        ordering = ['-date']

class PieceRateSetting(models.Model):
    style_number = models.CharField(max_length=50)
    operation_name = models.CharField(max_length=100)
    skill_level = models.CharField(max_length=20, choices=[
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ], default='intermediate')
    rate_per_piece = models.DecimalField(max_digits=10, decimal_places=2)
    target_per_day = models.IntegerField(default=100)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.style_number} - {self.operation_name} - {self.rate_per_piece}"

class Payroll(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payrolls')
    month = models.IntegerField()
    year = models.IntegerField()
    
    # Earnings
    basic_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    house_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    piece_rate_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    overtime_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    incentives = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Deductions
    pf_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    late_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    absence_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loan_installment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Attendance Summary
    total_working_days = models.IntegerField(default=26)
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    days_late = models.IntegerField(default=0)
    total_overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Totals
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_payable = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Payment
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, choices=[
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
    ], blank=True)
    bank_transaction_id = models.CharField(max_length=100, blank=True)
    
    # Additional
    remarks = models.TextField(blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_payrolls')
    generated_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_payrolls')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['employee', 'month', 'year']
        ordering = ['-year', '-month', 'employee__full_name']
    
    def __str__(self):
        return f"{self.employee.full_name} - {self.month}/{self.year} - {self.status}"
    
    def calculate_totals(self):
        self.total_earnings = (
            self.basic_pay + self.house_rent + self.medical_allowance + 
            self.transport_allowance + self.piece_rate_earnings + 
            self.overtime_amount + self.bonus + self.incentives + self.other_earnings
        )
        self.total_deductions = (
            self.pf_deduction + self.tax_deduction + self.advance_deduction +
            self.late_deduction + self.absence_deduction + self.loan_installment + 
            self.other_deductions
        )
        self.net_payable = self.total_earnings - self.total_deductions
        return self.net_payable

class Loan(models.Model):
    LOAN_TYPES = [
        ('personal', 'Personal Loan'),
        ('house', 'House Building Loan'),
        ('car', 'Car Loan'),
        ('education', 'Education Loan'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='loans')
    loan_type = models.CharField(max_length=20, choices=LOAN_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tenure_months = models.IntegerField()
    monthly_installment = models.DecimalField(max_digits=10, decimal_places=2)
    total_payable = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='approved_loans')
    approved_date = models.DateField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.employee.full_name} - {self.loan_type} - {self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.total_payable = self.amount + (self.amount * self.interest_rate / 100)
            self.monthly_installment = self.total_payable / self.tenure_months
            self.remaining_amount = self.total_payable
        super().save(*args, **kwargs)