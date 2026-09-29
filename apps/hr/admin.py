from django.contrib import admin

from .models import (
    Department, Designation, Employee, Attendance, Leave,
    ProductionOutput, PieceRateSetting, Payroll, Loan,
)

admin.site.register(Department)
admin.site.register(Designation)
admin.site.register(Employee)
admin.site.register(Attendance)
admin.site.register(Leave)
admin.site.register(ProductionOutput)
admin.site.register(PieceRateSetting)
admin.site.register(Payroll)
admin.site.register(Loan)
