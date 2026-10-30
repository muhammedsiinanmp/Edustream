import os
import re
import smtplib
import tempfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from principal.models import AddOnCourse
from student.models import CoursePurchase, Student

UUID_PHOTO_NAME = re.compile(r"^profiles/[0-9a-f]{32}\.(jpg|png|webp)$")


def photo_upload(name, image_format, size=(8, 6), mode="RGB", **save_options):
    buffer = BytesIO()
    Image.new(mode, size, "teal").save(buffer, format=image_format, **save_options)
    return SimpleUploadedFile(name, buffer.getvalue())


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


    def test_invalid_reset_link_explains_itself_and_offers_a_new_one(self):
        response = self.client.get(
            reverse(
                "student:password_reset_confirm",
                kwargs={"uidb64": "bad", "token": "bad-token"},
            ),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["validlink"])
        self.assertContains(response, "expired")
        self.assertContains(response, reverse("student:password_reset"))
        self.assertNotContains(response, "Update Password")

    def test_reset_link_cannot_be_used_twice(self):
        self.client.post(
            reverse("student:password_reset"), {"email": "asha@example.com"}
        )
        link = re.search(r"https?://[^/]+(/student/reset/\S+)", mail.outbox[0].body)
        form_page = self.client.get(link.group(1), follow=True)
        form_url = form_page.redirect_chain[-1][0]
        self.client.post(
            form_url,
            {"new_password1": "New-pass-7395", "new_password2": "New-pass-7395"},
        )

        reused = self.client.get(link.group(1), follow=True)
        self.assertFalse(reused.context["validlink"])
        self.assertContains(reused, "expired")


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

    def test_inactive_course_cannot_be_requested(self):
        self.course.status = "inactive"
        self.course.save()
        response = self.client.post(
            reverse("student:purchase_course", args=[self.course.id])
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CoursePurchase.objects.exists())

    def test_staff_cannot_request_course(self):
        admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(admin)
        response = self.client.post(
            reverse("student:purchase_course", args=[self.course.id])
        )
        self.assertRedirects(response, reverse("principal:admin_dashboard"))
        self.assertFalse(CoursePurchase.objects.exists())

    def test_racing_double_submit_does_not_return_500(self):
        # Simulates the second of two simultaneous requests: its duplicate
        # check ran before the first request's row was committed.
        url = reverse("student:purchase_course", args=[self.course.id])
        self.client.post(url)
        self.client.raise_request_exception = False

        with mock.patch("django.db.models.query.QuerySet.exists", return_value=False):
            response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
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


class CourseCompletionTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.course = AddOnCourse.objects.create(
            name="Cloud Fundamentals", description="Core concepts.", price=2999
        )
        self.purchase = CoursePurchase.objects.create(
            student=self.student, course=self.course, status="approved"
        )
        self.url = reverse("student:complete_course", args=[self.purchase.id])
        self.client.force_login(self.student)

    def dashboard(self):
        return self.client.get(reverse("student:student_dashboard"))

    def test_active_course_shows_one_completion_button(self):
        self.assertContains(self.dashboard(), f'action="{self.url}"', count=1)

    def test_deactivated_course_can_still_be_completed_from_the_dashboard(self):
        self.course.status = "inactive"
        self.course.save()

        self.assertContains(self.dashboard(), f'action="{self.url}"', count=1)

        self.client.post(self.url)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "completed")

    def test_no_completion_button_unless_approved(self):
        for status in ("pending", "rejected", "completed"):
            with self.subTest(status=status):
                self.purchase.status = status
                self.purchase.save()
                self.assertNotContains(self.dashboard(), f'action="{self.url}"')

    def test_other_students_purchase_cannot_be_completed(self):
        other = Student.objects.create_user(
            "ravi", "ravi@example.com", "Demo-pass-4821"
        )
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "approved")


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
            self.client.post(reverse("student:logout")), reverse("student:login")
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_get_does_not_log_out(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("student:logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)
        response = client.post(reverse("student:logout"))
        self.assertEqual(response.status_code, 403)
        self.assertIn("_auth_user_id", client.session)

    def test_navbar_logs_out_with_a_csrf_protected_post_form(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)
        page = client.get(reverse("student:student_dashboard")).content.decode()

        logout_form = re.search(
            rf'<form[^>]*action="{reverse("student:logout")}"[^>]*>.*?</form>',
            page,
            re.DOTALL,
        )
        self.assertIsNotNone(logout_form)
        self.assertIn('method="post"', logout_form.group(0))
        token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"', logout_form.group(0)
        )

        response = client.post(
            reverse("student:logout"), {"csrfmiddlewaretoken": token.group(1)}
        )
        self.assertRedirects(response, reverse("student:login"))
        self.assertNotIn("_auth_user_id", client.session)


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

    def upload(self, photo):
        return self.client.post(
            reverse("student:edit_profile"),
            {"email": "asha@example.com", "profile_pic": photo},
        )

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["profile_pic"])
        self.student.refresh_from_db()
        self.assertFalse(self.student.profile_pic)
        self.assertEqual(list(self.media_root.rglob("*.*")), [])

    def test_stored_filename_is_a_uuid_and_keeps_nothing_from_the_upload(self):
        self.upload(photo_upload("../my passport scan.PNG", "PNG"))
        self.student.refresh_from_db()
        self.assertRegex(self.student.profile_pic.name, UUID_PHOTO_NAME)
        self.assertTrue(self.student.profile_pic.name.endswith(".png"))

    def test_every_allowed_format_is_stored_in_that_format(self):
        for name, image_format, extension in (
            ("a.jpg", "JPEG", ".jpg"),
            ("a.jpeg", "JPEG", ".jpg"),
            ("a.png", "PNG", ".png"),
            ("a.webp", "WEBP", ".webp"),
        ):
            with self.subTest(name=name):
                self.upload(photo_upload(name, image_format))
                self.student.refresh_from_db()
                self.assertTrue(self.student.profile_pic.name.endswith(extension))
                path = self.media_root / self.student.profile_pic.name
                with Image.open(path) as stored:
                    self.assertEqual(stored.format, image_format)

    def test_exif_and_comments_are_removed_from_jpeg(self):
        exif = Image.Exif()
        exif[0x010F] = "SecretCameraMaker"
        exif[0x0132] = "2024:01:01 10:00:00"
        self.upload(
            photo_upload("a.jpg", "JPEG", exif=exif, comment=b"SecretComment")
        )

        self.student.refresh_from_db()
        path = self.media_root / self.student.profile_pic.name
        self.assertNotIn(b"SecretCameraMaker", path.read_bytes())
        self.assertNotIn(b"SecretComment", path.read_bytes())
        with Image.open(path) as stored:
            self.assertEqual(len(stored.getexif()), 0)
            self.assertNotIn("comment", stored.info)

    def test_exif_is_removed_from_png_and_webp(self):
        exif = Image.Exif()
        exif[0x010F] = "SecretCameraMaker"
        for name, image_format in (("a.png", "PNG"), ("a.webp", "WEBP")):
            with self.subTest(name=name):
                self.upload(photo_upload(name, image_format, exif=exif))
                self.student.refresh_from_db()
                path = self.media_root / self.student.profile_pic.name
                self.assertNotIn(b"SecretCameraMaker", path.read_bytes())

    def test_exif_rotation_is_applied_before_it_is_stripped(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 degrees to display upright
        self.upload(photo_upload("a.jpg", "JPEG", size=(40, 20), exif=exif))

        self.student.refresh_from_db()
        with Image.open(self.media_root / self.student.profile_pic.name) as stored:
            self.assertEqual(stored.size, (20, 40))

    def test_transparency_survives_reencoding(self):
        self.upload(photo_upload("a.png", "PNG", mode="RGBA"))
        self.student.refresh_from_db()
        with Image.open(self.media_root / self.student.profile_pic.name) as stored:
            self.assertEqual(stored.mode, "RGBA")

    def test_disallowed_format_is_rejected(self):
        self.assert_rejected(self.upload(photo_upload("a.gif", "GIF")))

    def test_disallowed_format_with_allowed_extension_is_rejected(self):
        self.assert_rejected(self.upload(photo_upload("a.png", "GIF")))

    def test_allowed_format_with_disallowed_extension_is_rejected(self):
        self.assert_rejected(self.upload(photo_upload("a.bmp", "PNG")))

    def test_non_image_with_allowed_extension_is_rejected(self):
        fake = SimpleUploadedFile("a.png", b"<script>alert(1)</script>")
        self.assert_rejected(self.upload(fake))

    def test_truncated_image_is_rejected_without_a_server_error(self):
        whole = photo_upload("a.jpg", "JPEG", size=(300, 300)).read()
        truncated = SimpleUploadedFile("a.jpg", whole[: len(whole) // 2])
        self.assert_rejected(self.upload(truncated))

    def test_photo_over_two_megabytes_is_rejected(self):
        noise = Image.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3))
        buffer = BytesIO()
        noise.save(buffer, format="PNG")
        self.assertGreater(len(buffer.getvalue()), 2 * 1024 * 1024)
        big = SimpleUploadedFile("a.png", buffer.getvalue())
        self.assert_rejected(self.upload(big))

    def test_image_with_excessive_pixel_count_is_rejected(self):
        small_file = photo_upload("a.png", "PNG", size=(6000, 6000), mode="1")
        self.assertLess(small_file.size, 2 * 1024 * 1024)
        self.assert_rejected(self.upload(small_file))

    def test_registration_applies_the_same_rules(self):
        self.client.logout()
        data = {
            "username": "ravi",
            "email": "ravi@example.com",
            "password": "Sturdy-pass-7395",
            "confirm_password": "Sturdy-pass-7395",
        }

        rejected = self.client.post(
            reverse("student:register"),
            {**data, "profile_pic": photo_upload("a.png", "GIF")},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(Student.objects.filter(username="ravi").exists())

        self.client.post(
            reverse("student:register"),
            {**data, "profile_pic": photo_upload("a.png", "PNG")},
        )
        student = Student.objects.get(username="ravi")
        self.assertRegex(student.profile_pic.name, UUID_PHOTO_NAME)

    def test_django_admin_applies_the_same_rules(self):
        admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(admin)
        url = reverse("admin:student_student_change", args=[self.student.id])
        data = {
            "username": "asha",
            "email": "asha@example.com",
            "date_joined_0": "2026-01-01",
            "date_joined_1": "10:00:00",
        }

        rejected = self.client.post(
            url, {**data, "profile_pic": photo_upload("a.png", "GIF")}
        )
        self.assertEqual(rejected.status_code, 200)
        self.student.refresh_from_db()
        self.assertFalse(self.student.profile_pic)

        accepted = self.client.post(
            url, {**data, "profile_pic": photo_upload("a.png", "PNG")}
        )
        self.assertEqual(accepted.status_code, 302)
        self.student.refresh_from_db()
        self.assertRegex(self.student.profile_pic.name, UUID_PHOTO_NAME)

    def test_unrelated_profile_save_leaves_the_stored_photo_untouched(self):
        self.upload(photo_upload("a.jpg", "JPEG", size=(64, 64)))
        self.student.refresh_from_db()
        name = self.student.profile_pic.name
        path = self.media_root / name
        original = path.read_bytes()

        response = self.client.post(
            reverse("student:edit_profile"),
            {"email": "asha@example.com", "phone": "9876543210"},
        )

        self.assertRedirects(response, reverse("student:student_profile"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone, "9876543210")
        self.assertEqual(self.student.profile_pic.name, name)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(list(self.media_root.rglob("*.*"))), 1)

    def test_unrelated_save_tolerates_a_legacy_photo_that_breaks_the_rules(self):
        legacy = self.media_root / "profiles" / "legacy.gif"
        legacy.parent.mkdir()
        legacy.write_bytes(photo_upload("a.gif", "GIF").read())
        Student.objects.filter(id=self.student.id).update(
            profile_pic="profiles/legacy.gif"
        )

        response = self.client.post(
            reverse("student:edit_profile"),
            {"email": "asha@example.com", "phone": "9876543210"},
        )

        self.assertRedirects(response, reverse("student:student_profile"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.profile_pic.name, "profiles/legacy.gif")


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


class ProfileFieldValidationTests(TestCase):
    def setUp(self):
        self.tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )

    def register(self, **fields):
        return self.client.post(
            reverse("student:register"),
            {
                "username": "ravi",
                "email": "ravi@example.com",
                "password": "Sturdy-pass-7395",
                "confirm_password": "Sturdy-pass-7395",
                **fields,
            },
        )

    def test_registration_rejects_invalid_fields(self):
        cases = [
            ("dob", self.tomorrow),
            ("dob", "not-a-date"),
            ("age", "-1"),
            ("age", "0"),
            ("age", "121"),
            ("phone", "call me"),
            ("phone", "12345"),
            ("phone", "98765-43210"),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                response = self.register(**{field: value})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors[field])
                self.assertFalse(Student.objects.filter(username="ravi").exists())

    def test_registration_accepts_valid_fields(self):
        response = self.register(
            dob=timezone.localdate().isoformat(), age="19", phone="+919876543210"
        )
        self.assertRedirects(response, reverse("student:login"))
        student = Student.objects.get(username="ravi")
        self.assertEqual(student.dob, timezone.localdate())
        self.assertEqual(student.age, 19)
        self.assertEqual(student.phone, "+919876543210")

    def test_registration_shows_a_date_picker_for_dob(self):
        response = self.client.get(reverse("student:register"))
        self.assertContains(response, 'type="date" name="dob"')

    def test_profile_edit_rejects_invalid_fields(self):
        self.client.force_login(self.student)
        for field, value in (
            ("dob", self.tomorrow),
            ("age", "-1"),
            ("phone", "call me"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    reverse("student:edit_profile"),
                    {"email": "asha@example.com", field: value},
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors[field])

    def test_principal_add_student_rejects_invalid_fields(self):
        admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(admin)
        for field, value in (
            ("dob", self.tomorrow),
            ("age", "-1"),
            ("phone", "call me"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    reverse("principal:admin_add_student"),
                    {
                        "username": "ravi",
                        "email": "ravi@example.com",
                        "password": "Sturdy-pass-7395",
                        field: value,
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors[field])


class EmailFailureTests(TestCase):
    def broken_mail_server(self):
        return mock.patch(
            "django.core.mail.backends.locmem.EmailBackend.send_messages",
            side_effect=smtplib.SMTPException("server unavailable"),
        )

    def test_smtp_connections_time_out(self):
        connection = mail.get_connection(
            "django.core.mail.backends.smtp.EmailBackend"
        )
        self.assertEqual(connection.timeout, settings.EMAIL_TIMEOUT)
        self.assertGreater(connection.timeout, 0)

    def test_failed_welcome_email_is_logged_and_registration_succeeds(self):
        data = {
            "username": "ravi",
            "email": "ravi@example.com",
            "password": "Sturdy-pass-7395",
            "confirm_password": "Sturdy-pass-7395",
        }
        with self.broken_mail_server(), self.assertLogs("student", "ERROR") as logs:
            response = self.client.post(reverse("student:register"), data)

        self.assertRedirects(response, reverse("student:login"))
        self.assertTrue(Student.objects.filter(username="ravi").exists())
        self.assertIn("server unavailable", logs.output[0])

    def test_failed_reset_email_is_logged_and_the_page_stays_neutral(self):
        Student.objects.create_user("asha", "asha@example.com", "Demo-pass-4821")
        with (
            self.broken_mail_server(),
            self.assertLogs("django.contrib.auth", "ERROR"),
        ):
            response = self.client.post(
                reverse("student:password_reset"),
                {"email": "asha@example.com"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)

    def test_reset_sent_page_does_not_claim_an_email_was_sent(self):
        response = self.client.get(reverse("student:password_reset_done"))
        self.assertNotContains(response, "Email Sent")
        self.assertContains(response, "If an account exists")


class EmailNormalisationTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )

    def registration(self, email):
        return {
            "username": "ravi",
            "email": email,
            "password": "Sturdy-pass-7395",
            "confirm_password": "Sturdy-pass-7395",
        }

    def test_model_save_stores_lowercase(self):
        student = Student.objects.create_user(
            "ravi", "Ravi.Kumar@Example.COM", "Demo-pass-4821"
        )
        student.refresh_from_db()
        self.assertEqual(student.email, "ravi.kumar@example.com")

    def test_registration_stores_lowercase(self):
        self.client.post(
            reverse("student:register"), self.registration("Ravi@Example.COM")
        )
        self.assertEqual(
            Student.objects.get(username="ravi").email, "ravi@example.com"
        )

    def test_registration_rejects_case_only_duplicate(self):
        response = self.client.post(
            reverse("student:register"), self.registration("ASHA@example.com")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["email"])
        self.assertFalse(Student.objects.filter(username="ravi").exists())

    def test_profile_edit_rejects_another_students_email_in_any_case(self):
        other = Student.objects.create_user(
            "ravi", "ravi@example.com", "Demo-pass-4821"
        )
        self.client.force_login(other)
        response = self.client.post(
            reverse("student:edit_profile"), {"email": "ASHA@EXAMPLE.COM"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["email"])
        other.refresh_from_db()
        self.assertEqual(other.email, "ravi@example.com")

    def test_profile_edit_accepts_own_email_in_another_case(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("student:edit_profile"), {"email": "Asha@Example.com"}
        )
        self.assertRedirects(response, reverse("student:student_profile"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "asha@example.com")

    def test_principal_add_student_rejects_case_only_duplicate(self):
        admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(admin)
        response = self.client.post(
            reverse("principal:admin_add_student"),
            {
                "username": "ravi",
                "email": "ASHA@example.com",
                "password": "Sturdy-pass-7395",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["email"])

    def test_django_admin_rejects_case_only_duplicate_without_a_server_error(self):
        admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(admin)
        response = self.client.post(
            reverse("admin:student_student_add"),
            {
                "username": "ravi",
                "email": "ASHA@example.com",
                "usable_password": "true",
                "password1": "Sturdy-pass-7395",
                "password2": "Sturdy-pass-7395",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Student.objects.filter(username="ravi").exists())

    def test_database_rejects_case_only_duplicate_written_around_the_model(self):
        other = Student.objects.create_user(
            "ravi", "ravi@example.com", "Demo-pass-4821"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.objects.filter(id=other.id).update(email="ASHA@EXAMPLE.COM")

    def test_password_reset_finds_student_typing_a_different_case(self):
        self.client.post(
            reverse("student:password_reset"), {"email": "ASHA@Example.com"}
        )
        self.assertEqual(len(mail.outbox), 1)


class EmailMigrationTests(TransactionTestCase):
    before = [("student", "0002_validate_profile_photo")]
    after = [("student", "0003_lowercase_unique_email")]

    def setUp(self):
        self.addCleanup(self.migrate_to_latest)
        self.old_student = self.migrate(self.before).apps.get_model(
            "student", "Student"
        )

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets)

    def migrate_to_latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_addresses_are_lowercased(self):
        self.old_student.objects.create(username="asha", email="Asha@Example.COM")

        self.migrate(self.after)

        self.assertEqual(Student.objects.get(username="asha").email, "asha@example.com")

    def test_case_only_duplicates_stop_the_migration_and_change_nothing(self):
        first = self.old_student.objects.create(
            username="asha", email="Asha@Example.com"
        )
        second = self.old_student.objects.create(
            username="asha2", email="asha@example.COM"
        )
        self.old_student.objects.create(username="ravi", email="Ravi@Example.com")

        with self.assertRaises(CommandError) as raised:
            self.migrate(self.after)

        message = str(raised.exception)
        self.assertIn("asha@example.com", message)
        self.assertIn(str(first.id), message)
        self.assertIn(str(second.id), message)
        self.assertIn("migrate", message)
        self.assertEqual(
            set(self.old_student.objects.values_list("email", flat=True)),
            {"Asha@Example.com", "asha@example.COM", "Ravi@Example.com"},
        )

        # Following the message's instructions lets the migration finish.
        second.delete()
        self.migrate(self.after)
        self.assertEqual(Student.objects.get(id=first.id).email, "asha@example.com")
