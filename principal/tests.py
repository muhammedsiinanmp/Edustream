from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from principal.models import AddOnCourse, Department
from principal.views import admin_dashboard
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

    def test_student_gets_403_on_principal_pages(self):
        self.client.force_login(self.student)
        for url in self.urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_student_gets_403_on_principal_actions(self):
        self.client.force_login(self.student)
        purchase = CoursePurchase.objects.create(
            student=self.student, course=self.course
        )
        urls = [
            reverse("principal:approve_course", args=[purchase.id]),
            reverse("principal:reject_course", args=[purchase.id]),
            reverse("principal:admin_delete_course", args=[self.course.id]),
            reverse("principal:admin_delete_department", args=[self.department.id]),
            reverse("principal:admin_delete_student", args=[self.student.id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 403)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "pending")
        self.assertTrue(Student.objects.filter(id=self.student.id).exists())

    def test_login_redirect_uses_the_real_login_page(self):
        # PublicAccessMiddleware sends anonymous browsers to the landing page
        # first, so this checks the view's own redirect target directly.
        request = RequestFactory().get(reverse("principal:admin_dashboard"))
        request.user = AnonymousUser()
        response = admin_dashboard(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("student:login")))

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


class StaffAccountProtectionTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.colleague = Student.objects.create_user(
            "vice", "vice@example.com", "Demo-pass-4821", is_staff=True
        )
        self.client.force_login(self.admin)

    def test_student_edit_page_does_not_open_staff_accounts(self):
        url = reverse("principal:admin_edit_student", args=[self.colleague.id])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"rollno": 7}).status_code, 404)
        self.colleague.refresh_from_db()
        self.assertIsNone(self.colleague.rollno)

    def test_student_delete_does_not_remove_staff_accounts(self):
        for account in (self.colleague, self.admin):
            with self.subTest(account=account.username):
                response = self.client.post(
                    reverse("principal:admin_delete_student", args=[account.id])
                )
                self.assertEqual(response.status_code, 404)
                self.assertTrue(Student.objects.filter(id=account.id).exists())


class AddStudentTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(self.admin)

    def test_valid_student_is_created_with_hashed_password(self):
        response = self.client.post(
            reverse("principal:admin_add_student"),
            {
                "username": "ravi",
                "email": "ravi@example.com",
                "password": "Sturdy-pass-7395",
            },
        )
        self.assertRedirects(response, reverse("principal:admin_students"))
        student = Student.objects.get(username="ravi")
        self.assertFalse(student.is_staff)
        self.assertTrue(student.check_password("Sturdy-pass-7395"))

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("principal:admin_add_student"),
            {"username": "ravi", "email": "ravi@example.com", "password": "12345"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["password"])
        self.assertFalse(Student.objects.filter(username="ravi").exists())


class CoursePriceTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.course = AddOnCourse.objects.create(
            name="Cloud Fundamentals", description="Core concepts.", price=2999
        )
        self.client.force_login(self.admin)

    def payload(self, price):
        return {
            "name": "Data Basics",
            "description": "Intro.",
            "price": price,
            "status": "active",
        }

    def test_negative_price_is_rejected_when_adding(self):
        response = self.client.post(
            reverse("principal:admin_add_course"), self.payload(-1)
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["price"])
        self.assertFalse(AddOnCourse.objects.filter(name="Data Basics").exists())

    def test_negative_price_is_rejected_when_editing(self):
        response = self.client.post(
            reverse("principal:admin_edit_course", args=[self.course.id]),
            self.payload(-1),
        )
        self.assertEqual(response.status_code, 200)
        self.course.refresh_from_db()
        self.assertEqual(self.course.price, 2999)

    def test_free_course_is_allowed(self):
        response = self.client.post(
            reverse("principal:admin_add_course"), self.payload(0)
        )
        self.assertRedirects(response, reverse("principal:admin_courses"))
        self.assertEqual(AddOnCourse.objects.get(name="Data Basics").price, 0)
