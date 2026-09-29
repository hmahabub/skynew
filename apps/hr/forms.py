from django import forms
from django.contrib.auth.models import User
from .models import Employee, Department, Designation, Attendance, Leave, Payroll, ProductionOutput, PieceRateSetting, Loan
from datetime import date, datetime

class EmployeeForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=False)
    
    class Meta:
        model = Employee
        fields = '__all__'
        exclude = ['user', 'created_by', 'created_at', 'updated_at','employee_id']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
            'confirmation_date': forms.DateInput(attrs={'type': 'date'}),
            'termination_date': forms.DateInput(attrs={'type': 'date'}),
            'present_address': forms.Textarea(attrs={'rows': 3}),
            'permanent_address': forms.Textarea(attrs={'rows': 3}),
            'termination_reason': forms.Textarea(attrs={'rows': 2}),
        }
    
    def clean_employee_id(self):
        employee_id = self.cleaned_data.get('employee_id')
        if Employee.objects.filter(employee_id=employee_id).exists():
            if self.instance and self.instance.pk:
                if self.instance.employee_id != employee_id:
                    raise forms.ValidationError('Employee ID already exists')
            else:
                raise forms.ValidationError('Employee ID already exists')
        return employee_id
    
    def clean_national_id(self):
        national_id = self.cleaned_data.get('national_id')
        if Employee.objects.filter(national_id=national_id).exists():
            if self.instance and self.instance.pk:
                if self.instance.national_id != national_id:
                    raise forms.ValidationError('National ID already exists')
            else:
                raise forms.ValidationError('National ID already exists')
        return national_id

class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['employee', 'date', 'check_in_time', 'check_out_time', 'status', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'check_in_time': forms.TimeInput(attrs={'type': 'time'}),
            'check_out_time': forms.TimeInput(attrs={'type': 'time'}),
            'remarks': forms.Textarea(attrs={'rows': 2}),
        }

class BulkAttendanceForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple
    )
    status = forms.ChoiceField(choices=Attendance.STATUS_CHOICES)

class LeaveForm(forms.ModelForm):
    class Meta:
        model = Leave
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        employee = cleaned_data.get('employee')
        leave_type = cleaned_data.get('leave_type')

        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError('End date must be after start date')
            
            # Check for overlapping leaves
            if employee:
                overlapping = Leave.objects.filter(
                    employee=employee,
                    start_date__lte=end_date,
                    end_date__gte=start_date,
                    status__in=['pending', 'approved']
                )
                if self.instance and self.instance.pk:
                    overlapping = overlapping.exclude(pk=self.instance.pk)
                
                if overlapping.exists():
                    raise forms.ValidationError('Employee already has a leave request for this period')

            # Check the employee's remaining balance for quota-tracked
            # leave types (annual, sick, casual, maternity, paternity).
            # Unpaid leave has no quota and is always allowed.
            if employee and leave_type:
                requested_days = (end_date - start_date).days + 1
                remaining = Leave.remaining_balance(
                    employee, leave_type, start_date.year,
                    exclude_pk=self.instance.pk if self.instance and self.instance.pk else None
                )
                if remaining is not None and requested_days > remaining:
                    leave_type_label = dict(Leave.LEAVE_TYPES).get(leave_type, leave_type)
                    raise forms.ValidationError(
                        f'Insufficient {leave_type_label} balance for {start_date.year}: '
                        f'{remaining} day(s) remaining, but {requested_days} day(s) requested.'
                    )

        return cleaned_data

class PayrollForm(forms.ModelForm):
    class Meta:
        model = Payroll
        fields = '__all__'
        exclude = ['generated_by', 'generated_at', 'approved_by', 'approved_at']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }

class ProductionOutputForm(forms.ModelForm):
    class Meta:
        model = ProductionOutput
        fields = '__all__'
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

class PieceRateSettingForm(forms.ModelForm):
    class Meta:
        model = PieceRateSetting
        fields = '__all__'
        widgets = {
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_to': forms.DateInput(attrs={'type': 'date'}),
        }

class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['employee', 'loan_type', 'amount', 'interest_rate', 'tenure_months', 'reason', 'start_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }