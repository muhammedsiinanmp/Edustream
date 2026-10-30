from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Student, CoursePurchase


@admin.register(Student)
class StudentAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Student details",
            {
                "fields": (
                    "phone",
                    "dob",
                    "age",
                    "dept",
                    "rollno",
                    "year_of_admission",
                    "profile_pic",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


admin.site.register(CoursePurchase)
