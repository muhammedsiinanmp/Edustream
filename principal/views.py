from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import ProtectedError
from django.views.decorators.http import require_POST
from student.models import Student, CoursePurchase
from student.notifications import notify
from .models import Department, AddOnCourse
from .forms import (
    AdminStudentForm,
    AdminEditStudentForm,
    DepartmentForm,
    AddOnCourseForm,
)
from .utils import is_admin, paginate


# ADMIN DASHBOARD
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_dashboard(request):
    pending_purchases = (
        CoursePurchase.objects.filter(status="pending")
        .select_related("student", "course")
        .order_by("created_at", "id")
    )

    context = {
        "student_count": Student.objects.count(),
        "department_count": Department.objects.count(),
        "course_count": AddOnCourse.objects.count(),
        "pending_purchases": paginate(request, pending_purchases),
    }
    return render(request, "principal/dashboard.html", context)


# STUDENT CRUD
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_students(request):
    students = Student.objects.filter(is_staff=False).select_related("dept").order_by("id")
    return render(
        request, "principal/students.html", {"students": paginate(request, students)}
    )


@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_add_student(request):
    if request.method == "POST":
        form = AdminStudentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Student added successfully")
            return redirect("principal:admin_students")
    else:
        form = AdminStudentForm()

    return render(request, "principal/add_student.html", {"form": form})


@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_edit_student(request, id):
    student = get_object_or_404(Student, id=id, is_staff=False)

    if request.method == "POST":
        form = AdminEditStudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "Student updated successfully")
            return redirect("principal:admin_students")
    else:
        form = AdminEditStudentForm(instance=student)

    return render(request, "principal/edit_student.html", {"form": form})


@require_POST
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_delete_student(request, id):
    student = get_object_or_404(Student, id=id, is_staff=False)
    try:
        student.delete()
    except ProtectedError:
        messages.error(
            request,
            "This student has enrollment history and can't be deleted. "
            "Deactivate the account instead, which stops them logging in "
            "and keeps their records.",
        )
    else:
        messages.success(request, "Student deleted successfully")
    return redirect("principal:admin_students")


@require_POST
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_deactivate_student(request, id):
    student = get_object_or_404(Student, id=id, is_staff=False)
    student.is_active = False
    student.save(update_fields=["is_active"])
    messages.success(
        request, f"{student.username} was deactivated and can no longer log in"
    )
    return redirect("principal:admin_students")


@require_POST
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_reactivate_student(request, id):
    student = get_object_or_404(Student, id=id, is_staff=False)
    student.is_active = True
    student.save(update_fields=["is_active"])
    messages.success(request, f"{student.username} was reactivated and can log in again")
    return redirect("principal:admin_students")


# DEPARTMENT CRUD
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_departments(request):
    departments = Department.objects.order_by("id")
    return render(
        request,
        "principal/departments.html",
        {"departments": paginate(request, departments)},
    )


@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_add_department(request):
    form = DepartmentForm(request.POST or None)

    if form.is_valid():
        form.save()
        messages.success(request, "Department added successfully")
        return redirect("principal:admin_departments")

    return render(request, "principal/add_department.html", {"form": form})


@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_edit_department(request, id):
    dept = get_object_or_404(Department, id=id)
    form = DepartmentForm(request.POST or None, instance=dept)

    if form.is_valid():
        form.save()
        messages.success(request, "Department updated successfully")
        return redirect("principal:admin_departments")

    return render(request, "principal/edit_departments.html", {"form": form})


@require_POST
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_delete_department(request, id):
    dept = get_object_or_404(Department, id=id)
    dept.delete()
    messages.success(request, "Department deleted successfully")
    return redirect("principal:admin_departments")


# COURSE CRUD
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_courses(request):
    courses = AddOnCourse.objects.order_by("id")
    return render(
        request, "principal/courses.html", {"courses": paginate(request, courses)}
    )


@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_add_course(request):
    form = AddOnCourseForm(request.POST or None)

    if form.is_valid():
        form.save()
        messages.success(request, "Course added successfully")
        return redirect("principal:admin_courses")

    return render(request, "principal/add_course.html", {"form": form})


@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_edit_course(request, id):
    course = get_object_or_404(AddOnCourse, id=id)
    form = AddOnCourseForm(request.POST or None, instance=course)

    if form.is_valid():
        form.save()
        messages.success(request, "Course updated successfully")
        return redirect("principal:admin_courses")

    return render(request, "principal/edit_course.html", {"form": form})


@require_POST
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_delete_course(request, id):
    course = get_object_or_404(AddOnCourse, id=id)
    try:
        course.delete()
    except ProtectedError:
        messages.error(
            request,
            "This course has enrollment history and can't be deleted. "
            "Deactivate it instead by setting its status to Inactive.",
        )
    else:
        messages.success(request, "Course deleted successfully")
    return redirect("principal:admin_courses")


# ENROLLMENT HISTORY
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def admin_enrollments(request):
    purchases = CoursePurchase.objects.select_related("student", "course").order_by(
        "-created_at", "-id"
    )
    return render(
        request, "principal/enrollments.html", {"purchases": paginate(request, purchases)}
    )


# COURSE APPROVAL FLOW
@require_POST
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def approve_course(request, purchase_id):
    purchase = get_object_or_404(CoursePurchase, id=purchase_id)

    if purchase.status == "pending":
        purchase.status = "approved"
        purchase.save()
        messages.success(request, f"Approved course for {purchase.student.username}")
        notify(
            purchase.student,
            "Your Edustream course request was approved",
            f"Hi {purchase.student.username},\n\n"
            f"Your request for {purchase.course.name} has been approved.\n\n"
            "— Edustream Team",
        )

    return redirect("principal:admin_dashboard")


@require_POST
@login_required(login_url="student:login")
@user_passes_test(is_admin)
def reject_course(request, purchase_id):
    purchase = get_object_or_404(CoursePurchase, id=purchase_id)

    if purchase.status == "pending":
        purchase.status = "rejected"
        purchase.save()
        messages.warning(request, f"Rejected course for {purchase.student.username}")
        notify(
            purchase.student,
            "Your Edustream course request was rejected",
            f"Hi {purchase.student.username},\n\n"
            f"Your request for {purchase.course.name} was not approved.\n\n"
            "— Edustream Team",
        )

    return redirect("principal:admin_dashboard")
