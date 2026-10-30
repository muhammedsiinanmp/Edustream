import re

from django.core import mail
from django.test import TestCase
from django.urls import reverse

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
