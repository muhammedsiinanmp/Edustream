from django.test import Client, TestCase
from django.urls import reverse

from principal.models import AddOnCourse, Department
from student.models import CoursePurchase, Student


class AdminActionTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.course = AddOnCourse.objects.create(
            name="Cloud Fundamentals", description="Core concepts.", price=2999
        )
        self.purchase = CoursePurchase.objects.create(
            student=self.student, course=self.course
        )
        self.client.force_login(self.admin)

    def test_get_cannot_change_data(self):
        department = Department.objects.create(name="Commerce", description="Finance.")
        urls = [
            reverse("principal:approve_course", args=[self.purchase.id]),
            reverse("principal:reject_course", args=[self.purchase.id]),
            reverse("principal:admin_delete_student", args=[self.student.id]),
            reverse("principal:admin_delete_course", args=[self.course.id]),
            reverse("principal:admin_delete_department", args=[department.id]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 405, url)

        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "pending")
        self.assertTrue(Student.objects.filter(id=self.student.id).exists())
        self.assertTrue(AddOnCourse.objects.filter(id=self.course.id).exists())
        self.assertTrue(Department.objects.filter(id=department.id).exists())

    def test_post_approves_request(self):
        self.client.post(reverse("principal:approve_course", args=[self.purchase.id]))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "approved")

    def test_post_rejects_request(self):
        self.client.post(reverse("principal:reject_course", args=[self.purchase.id]))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "rejected")

    def test_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(
            reverse("principal:approve_course", args=[self.purchase.id])
        )
        self.assertEqual(response.status_code, 403)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "pending")

    def test_student_cannot_approve(self):
        self.client.force_login(self.student)
        self.client.post(reverse("principal:approve_course", args=[self.purchase.id]))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "pending")


class PageSmokeTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.department = Department.objects.create(
            name="Commerce", description="Finance."
        )
        self.course = AddOnCourse.objects.create(
            name="Cloud Fundamentals", description="Core concepts.", price=2999
        )
        self.urls = [
            reverse("principal:admin_dashboard"),
            reverse("principal:admin_students"),
            reverse("principal:admin_add_student"),
            reverse("principal:admin_edit_student", args=[self.student.id]),
            reverse("principal:admin_departments"),
            reverse("principal:admin_add_department"),
            reverse("principal:admin_edit_department", args=[self.department.id]),
            reverse("principal:admin_courses"),
            reverse("principal:admin_add_course"),
            reverse("principal:admin_edit_course", args=[self.course.id]),
        ]

    def test_principal_can_open_every_page(self):
        self.client.force_login(self.admin)
        for url in self.urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_student_is_redirected_to_default_login_url(self):
        self.client.force_login(self.student)
        for url in self.urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith("/accounts/login/"))

    def test_logged_out_visitor_is_redirected_to_landing(self):
        for url in self.urls:
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), "/", fetch_redirect_response=False
                )


class DepartmentEditTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.department = Department.objects.create(
            name="Commerce", description="Finance."
        )
        self.url = reverse(
            "principal:admin_edit_department", args=[self.department.id]
        )
        self.client.force_login(self.admin)

    def test_edit_page_shows_current_department(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Commerce"')

    def test_invalid_post_shows_form_again(self):
        response = self.client.post(self.url, {"name": "", "description": "Finance."})
        self.assertEqual(response.status_code, 200)
        self.department.refresh_from_db()
        self.assertEqual(self.department.name, "Commerce")

    def test_valid_post_updates_department(self):
        response = self.client.post(
            self.url, {"name": "Business", "description": "Finance."}
        )
        self.assertRedirects(response, reverse("principal:admin_departments"))
        self.department.refresh_from_db()
        self.assertEqual(self.department.name, "Business")
