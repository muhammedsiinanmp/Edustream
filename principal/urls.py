from django.urls import path
from . import views

app_name = 'principal'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # Student CRUD
    path('students/', views.admin_students, name='admin_students'),
    path('students/add/', views.admin_add_student, name='admin_add_student'),
    path('students/edit/<int:id>/', views.admin_edit_student, name='admin_edit_student'),
    path('students/delete/<int:id>/', views.admin_delete_student, name='admin_delete_student'),

    # Department CRUD
    path('departments/', views.admin_departments, name='admin_departments'),
    path('departments/add/', views.admin_add_department, name='admin_add_department'),
    path('departments/edit/<int:id>/', views.admin_edit_department, name='admin_edit_department'),
    path('departments/delete/<int:id>/', views.admin_delete_department, name='admin_delete_department'),

    # Course CRUD
    path('courses/', views.admin_courses, name='admin_courses'),
    path('courses/add/', views.admin_add_course, name='admin_add_course'),
    path('courses/edit/<int:id>/', views.admin_edit_course, name='admin_edit_course'),
    path('courses/delete/<int:id>/', views.admin_delete_course, name='admin_delete_course'),

    # Course approval
    path('approve/<int:purchase_id>/', views.approve_course, name='approve_course'),
    path('reject/<int:purchase_id>/', views.reject_course, name='reject_course'),
]
