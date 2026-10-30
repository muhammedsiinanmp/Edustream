import re
import tempfile
from io import BytesIO
from pathlib import Path

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from principal.models import AddOnCourse
from student.models import CoursePurchase, Student


class LoginFormTests(TestCase):
    def test_password_input_is_masked(self):
        response = self.client.get(reverse("student:login"))
        self.assertContains(response, 'type="password"')


class PasswordResetTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Old-pass-4821"
        )

    def test_page_is_public(self):
        response = self.client.get(reverse("student:password_reset"))
        self.assertEqual(response.status_code, 200)

    def test_full_reset_flow(self):
        self.client.post(
            reverse("student:password_reset"), {"email": "asha@example.com"}
        )
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://[^/]+(/student/reset/\S+)", mail.outbox[0].body)

        form_page = self.client.get(link.group(1), follow=True)
        self.assertEqual(form_page.status_code, 200)

        new_password = "New-pass-7395"
        response = self.client.post(
            form_page.redirect_chain[-1][0],
            {"new_password1": new_password, "new_password2": new_password},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(new_password))


class EnrollmentTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.course = AddOnCourse.objects.create(
            name="Cloud Fundamentals", description="Core concepts.", price=2999
        )
        self.client.force_login(self.student)

    def test_get_cannot_request_course(self):
        response = self.client.get(
            reverse("student:purchase_course", args=[self.course.id])
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(CoursePurchase.objects.exists())

    def test_post_requests_course_once(self):
        url = reverse("student:purchase_course", args=[self.course.id])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(CoursePurchase.objects.count(), 1)

    def test_only_approved_course_can_be_completed(self):
        purchase = CoursePurchase.objects.create(student=self.student, course=self.course)
        url = reverse("student:complete_course", args=[purchase.id])

        self.client.post(url)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "pending")

        purchase.status = "approved"
        purchase.save()
        self.client.post(url)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "completed")


class PageSmokeTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.urls = [
            reverse("student:student_dashboard"),
            reverse("student:student_profile"),
            reverse("student:edit_profile"),
        ]

    def test_student_can_open_every_page(self):
        self.client.force_login(self.student)
        for url in self.urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_logged_out_visitor_can_open_public_pages(self):
        urls = [
            reverse("landing"),
            reverse("student:login"),
            reverse("student:register"),
            reverse("student:password_reset"),
            reverse("student:password_reset_done"),
            reverse("student:password_reset_complete"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_logged_out_visitor_is_redirected_to_landing(self):
        for url in self.urls:
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), "/", fetch_redirect_response=False
                )

    def test_staff_dashboard_redirects_to_principal_dashboard(self):
        admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(admin)
        self.assertRedirects(
            self.client.get(reverse("student:student_dashboard")),
            reverse("principal:admin_dashboard"),
        )

    def test_logout_returns_to_login(self):
        self.client.force_login(self.student)
        self.assertRedirects(
            self.client.get(reverse("student:logout")), reverse("student:login")
        )
        self.assertNotIn("_auth_user_id", self.client.session)


class ProfilePhotoTests(TestCase):
    def setUp(self):
        media_root = tempfile.TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        self.media_root = Path(media_root.name)

        media_override = override_settings(MEDIA_ROOT=media_root.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.client.force_login(self.student)

    def test_uploaded_photo_is_stored(self):
        image = BytesIO()
        Image.new("RGB", (8, 6), "teal").save(image, format="PNG")
        photo = SimpleUploadedFile(
            "avatar.png", image.getvalue(), content_type="image/png"
        )

        response = self.client.post(
            reverse("student:edit_profile"),
            {"email": "asha@example.com", "profile_pic": photo},
        )

        self.assertRedirects(response, reverse("student:student_profile"))
        self.student.refresh_from_db()
        self.assertTrue(self.student.profile_pic.name.startswith("profiles/"))
        with Image.open(self.media_root / self.student.profile_pic.name) as stored:
            self.assertEqual(stored.format, "PNG")
            self.assertEqual(stored.size, (8, 6))


class StudentAdminTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(self.admin)

    def test_password_set_in_admin_is_hashed(self):
        response = self.client.post(
            reverse("admin:student_student_add"),
            {
                "username": "ravi",
                "email": "ravi@example.com",
                "usable_password": "true",
                "password1": "Admin-made-7395",
                "password2": "Admin-made-7395",
            },
        )

        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(username="ravi")
        self.assertNotEqual(student.password, "Admin-made-7395")
        self.assertTrue(student.check_password("Admin-made-7395"))

    def test_change_page_does_not_expose_password_as_editable_text(self):
        student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        response = self.client.get(
            reverse("admin:student_student_change", args=[student.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="password"')


class RegistrationTests(TestCase):
    def payload(self, **overrides):
        data = {
            "username": "ravi",
            "email": "ravi@example.com",
            "password": "Sturdy-pass-7395",
            "confirm_password": "Sturdy-pass-7395",
        }
        data.update(overrides)
        return data

    def test_valid_registration_creates_student_who_can_log_in(self):
        response = self.client.post(reverse("student:register"), self.payload())

        self.assertRedirects(response, reverse("student:login"))
        student = Student.objects.get(username="ravi")
        self.assertFalse(student.is_staff)
        self.assertTrue(student.check_password("Sturdy-pass-7395"))
        self.assertEqual(mail.outbox[0].to, ["ravi@example.com"])

        login = self.client.post(
            reverse("student:login"),
            {"username": "ravi", "password": "Sturdy-pass-7395"},
        )
        self.assertRedirects(login, reverse("student:student_dashboard"))

    def test_weak_passwords_are_rejected(self):
        weak_passwords = {
            "too short": "Ab1!",
            "common": "password123",
            "numeric": "8264917305",
            "similar to username": "ravikumar1",
        }
        for reason, password in weak_passwords.items():
            with self.subTest(reason=reason):
                response = self.client.post(
                    reverse("student:register"),
                    self.payload(
                        username="ravikumar",
                        password=password,
                        confirm_password=password,
                    ),
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors["password"])
                self.assertFalse(Student.objects.exists())

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(
            reverse("student:register"),
            self.payload(confirm_password="Different-pass-1"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Student.objects.exists())
