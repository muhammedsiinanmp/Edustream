from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import StudentRegisterForm, LoginForm
from .models import CoursePurchase
from principal.models import AddOnCourse
from .forms import StudentProfileUpdateForm
from django.core.mail import send_mail
from django.conf import settings


# ============================
# STUDENT REGISTRATION
# ============================
def register(request):
    if request.method == "POST":
        form = StudentRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            student = form.save()
            
            send_mail(
                subject="Welcome to Edustream 🎓",
                message=(
                    f"Hi {student.username},\n\n"
                    "Welcome to Edustream!\n\n"
                    "Your account has been created successfully.\n\n"
                    "— Edustream Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student.email],
                fail_silently=True, 
            )

            messages.success(request, "Registration successful. Please login.")
            return redirect("student:login")
    else:
        form = StudentRegisterForm()

    return render(request, "student/register.html", {"form": form})


# ============================
# STUDENT LOGIN
# ============================
def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )

            if user is not None:
                login(request, user)

                # Role-based redirect
                if user.is_staff:
                    return redirect("principal:admin_dashboard")
                return redirect("student:student_dashboard")

            messages.error(request, "Invalid credentials")
    else:
        form = LoginForm()

    return render(request, "student/login.html", {"form": form})


# ============================
# LOGOUT
# ============================
def logout_view(request):
    logout(request)
    messages.info(request, "Logged out successfully")
    return redirect("student:login")


# ============================
# STUDENT DASHBOARD
# ============================


@login_required(login_url="student:login")
def student_dashboard(request):
    # 🔒 BLOCK ADMIN / STAFF USERS
    if request.user.is_staff:
        return redirect("principal:admin_dashboard")

    courses = AddOnCourse.objects.filter(status="active")
    purchases = CoursePurchase.objects.filter(student=request.user)

    purchased_course_ids = purchases.values_list("course_id", flat=True)
    completed_count = purchases.filter(status="completed").count()

    context = {
        "courses": courses,
        "purchases": purchases,
        "purchased_course_ids": purchased_course_ids,
        "completed_count": completed_count,
    }

    return render(request, "student/dashboard.html", context)


# ============================
# PURCHASE COURSE (REQUEST)
# ============================
@login_required(login_url="student:login")
def purchase_course(request, course_id):
    course = get_object_or_404(AddOnCourse, id=course_id)

    # Prevent duplicate purchase
    if CoursePurchase.objects.filter(student=request.user, course=course).exists():
        messages.info(request, "You already requested this course")
        return redirect("student:student_dashboard")

    CoursePurchase.objects.create(student=request.user, course=course, status="pending")

    messages.success(request, "Course request submitted for approval")
    return redirect("student:student_dashboard")


# ============================
# COMPLETE COURSE
# ============================
@login_required(login_url="student:login")
def complete_course(request, purchase_id):
    purchase = get_object_or_404(CoursePurchase, id=purchase_id, student=request.user)

    if purchase.status == "approved":
        purchase.status = "completed"
        purchase.save()
        messages.success(request, "Course marked as completed")

    return redirect("student:student_dashboard")


# Student Profile


@login_required(login_url="student:login")
def student_profile(request):
    student = request.user

    return render(request, "student/profile.html", {"student": student})


@login_required(login_url="student:login")
def edit_profile(request):
    student = request.user

    if request.method == "POST":
        form = StudentProfileUpdateForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully")
            return redirect("student:student_profile")
    else:
        form = StudentProfileUpdateForm(instance=student)

    return render(request, "student/edit_profile.html", {"form": form})
