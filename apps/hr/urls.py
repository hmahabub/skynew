from django.urls import path
from . import views

app_name = 'hr'

urlpatterns = [
    # Dashboard
    path('', views.hr_dashboard, name='hr_dashboard'),
    
    # Employee Management
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/add/', views.add_employee, name='add_employee'),
    path('employees/<int:pk>/edit/', views.edit_employee, name='edit_employee'),
    path('employees/<int:pk>/delete/', views.delete_employee, name='delete_employee'),
    
    # Attendance Management
    path('attendance/', views.attendance_view, name='attendance_view'),
    path('attendance/bulk/', views.bulk_attendance, name='bulk_attendance'),
    path('attendance/export/', views.export_attendance_csv, name='export_attendance'),
    
    # Leave Management
    path('leaves/', views.leave_requests, name='leave_requests'),
    path('leaves/apply/', views.apply_leave, name='apply_leave'),
    path('leaves/<int:pk>/approve/', views.approve_leave, name='approve_leave'),
    
    # Payroll Management
    path('payroll/', views.payroll_list, name='payroll_list'),
    path('payroll/generate/', views.generate_payroll, name='generate_payroll'),
    path('payroll/template/', views.download_payroll_template, name='download_payroll_template'),
    path('payroll/upload/', views.upload_payroll_excel, name='upload_payroll_excel'),
    
    # Production Tracking
    path('production/', views.production_tracking, name='production_tracking'),
    
    # Department Management
    path('departments/', views.department_list, name='department_list'),
    path('departments/add/', views.add_department, name='add_department'),

     # Designation URLs
    path('designations/', views.designation_list, name='designation_list'),
    path('designations/add/', views.add_designation, name='add_designation'),
    path('designations/<int:pk>/', views.designation_detail, name='designation_detail'),
    path('designations/<int:pk>/edit/', views.edit_designation, name='edit_designation'),
    path('designations/<int:pk>/delete/', views.delete_designation, name='delete_designation'),
]