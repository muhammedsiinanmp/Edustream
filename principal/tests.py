from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
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
            reverse("principal:admin_deactivate_student", args=[self.student.id]),
            reverse("principal:admin_reactivate_student", args=[self.student.id]),
            reverse("principal:admin_delete_course", args=[self.course.id]),
            reverse("principal:admin_delete_department", args=[department.id]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 405, url)

        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "pending")
        self.assertTrue(Student.objects.filter(id=self.student.id).exists())
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)
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
            reverse("principal:admin_deactivate_student", args=[self.student.id]),
            reverse("principal:admin_reactivate_student", args=[self.student.id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 403)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "pending")
        self.assertTrue(Student.objects.filter(id=self.student.id).exists())
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

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

    def test_student_deactivate_does_not_lock_out_staff_accounts(self):
        for account in (self.colleague, self.admin):
            with self.subTest(account=account.username):
                response = self.client.post(
                    reverse("principal:admin_deactivate_student", args=[account.id])
                )
                self.assertEqual(response.status_code, 404)
                account.refresh_from_db()
                self.assertTrue(account.is_active)

    def test_student_reactivate_does_not_touch_staff_accounts(self):
        self.colleague.is_active = False
        self.colleague.save()
        response = self.client.post(
            reverse("principal:admin_reactivate_student", args=[self.colleague.id])
        )
        self.assertEqual(response.status_code, 404)
        self.colleague.refresh_from_db()
        self.assertFalse(self.colleague.is_active)


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


class CourseDeletionTests(TestCase):
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
        self.url = reverse("principal:admin_delete_course", args=[self.course.id])
        self.client.force_login(self.admin)

    def test_course_with_enrollments_is_kept_and_steers_to_deactivation(self):
        purchase = CoursePurchase.objects.create(
            student=self.student, course=self.course, status="completed"
        )

        response = self.client.post(self.url, follow=True)

        self.assertRedirects(response, reverse("principal:admin_courses"))
        self.assertContains(response, "Deactivate")
        self.assertContains(response, "alert-danger")
        self.assertTrue(AddOnCourse.objects.filter(id=self.course.id).exists())
        self.assertTrue(CoursePurchase.objects.filter(id=purchase.id).exists())

    def test_course_without_enrollments_can_be_deleted(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("principal:admin_courses"))
        self.assertFalse(AddOnCourse.objects.filter(id=self.course.id).exists())


class EnrollmentHistoryTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.url = reverse("principal:admin_enrollments")
        self.client.force_login(self.admin)

    def test_every_status_is_listed(self):
        for status in ("pending", "approved", "completed", "rejected"):
            course = AddOnCourse.objects.create(
                name=f"Course {status}", description="Intro.", price=100
            )
            CoursePurchase.objects.create(
                student=self.student, course=course, status=status
            )

        response = self.client.get(self.url)

        for status in ("pending", "approved", "completed", "rejected"):
            self.assertContains(response, f"Course {status}")
        self.assertContains(response, "asha")

    def test_history_is_paginated_newest_first(self):
        for number in range(25):
            course = AddOnCourse.objects.create(
                name=f"Course {number}", description="Intro.", price=100
            )
            CoursePurchase.objects.create(student=self.student, course=course)

        first = self.client.get(self.url)
        last = self.client.get(self.url, {"page": 2})

        self.assertEqual(len(first.context["purchases"]), 20)
        self.assertEqual(first.context["purchases"][0].course.name, "Course 24")
        self.assertEqual(len(last.context["purchases"]), 5)
        self.assertContains(first, "?page=2")

    def test_out_of_range_page_shows_the_last_page(self):
        response = self.client.get(self.url, {"page": 99})
        self.assertEqual(response.status_code, 200)

    def test_dashboard_links_to_history(self):
        response = self.client.get(reverse("principal:admin_dashboard"))
        self.assertContains(response, f'href="{self.url}"')

    def test_student_gets_403(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_logged_out_visitor_is_redirected_to_landing(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.url), "/", fetch_redirect_response=False
        )


class ListPerformanceTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.department = Department.objects.create(name="Commerce", description="x")
        self.client.force_login(self.admin)
        self.next_row = 0

    def add_requests(self, count):
        for _ in range(count):
            self.next_row += 1
            student = Student.objects.create_user(
                f"student{self.next_row}",
                f"student{self.next_row}@example.com",
                dept=self.department,
            )
            course = AddOnCourse.objects.create(
                name=f"Course {self.next_row}", description="Intro.", price=100
            )
            CoursePurchase.objects.create(student=student, course=course)

    def query_count(self, url):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def test_query_counts_do_not_grow_with_data(self):
        urls = [
            reverse("principal:admin_dashboard"),
            reverse("principal:admin_enrollments"),
            reverse("principal:admin_students"),
        ]
        self.add_requests(2)
        before = {url: self.query_count(url) for url in urls}

        self.add_requests(10)

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.query_count(url), before[url])


class PaginationTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(self.admin)

    def assert_paginated(self, url, context_name):
        first = self.client.get(url)
        second = self.client.get(url, {"page": 2})
        self.assertEqual(len(first.context[context_name]), 20)
        self.assertEqual(len(second.context[context_name]), 5)
        self.assertContains(first, "?page=2")

    def test_students_are_paginated(self):
        for number in range(25):
            Student.objects.create_user(f"s{number}", f"s{number}@example.com")
        self.assert_paginated(reverse("principal:admin_students"), "students")

    def test_departments_are_paginated(self):
        for number in range(25):
            Department.objects.create(name=f"Dept {number}", description="x")
        self.assert_paginated(reverse("principal:admin_departments"), "departments")

    def test_courses_are_paginated(self):
        for number in range(25):
            AddOnCourse.objects.create(
                name=f"Course {number}", description="x", price=1
            )
        self.assert_paginated(reverse("principal:admin_courses"), "courses")

    def test_pending_requests_are_paginated_and_the_total_stays_accurate(self):
        student = Student.objects.create_user("asha", "asha@example.com")
        for number in range(25):
            course = AddOnCourse.objects.create(
                name=f"Course {number}", description="x", price=1
            )
            CoursePurchase.objects.create(student=student, course=course)

        response = self.client.get(reverse("principal:admin_dashboard"))

        self.assertEqual(len(response.context["pending_purchases"]), 20)
        self.assertEqual(response.context["pending_purchases"].paginator.count, 25)
        self.assertContains(response, "?page=2")


class DecisionEmailTests(TestCase):
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
        self.approve_url = reverse("principal:approve_course", args=[self.purchase.id])
        self.reject_url = reverse("principal:reject_course", args=[self.purchase.id])
        self.client.force_login(self.admin)

    def test_approval_emails_the_student(self):
        self.client.post(self.approve_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["asha@example.com"])
        self.assertIn("approved", mail.outbox[0].subject.lower())
        self.assertIn("Cloud Fundamentals", mail.outbox[0].body)

    def test_rejection_emails_the_student(self):
        self.client.post(self.reject_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["asha@example.com"])
        self.assertIn("rejected", mail.outbox[0].subject.lower())
        self.assertIn("Cloud Fundamentals", mail.outbox[0].body)

    def test_repeat_decision_sends_no_second_email(self):
        self.client.post(self.approve_url)
        self.client.post(self.approve_url)
        self.client.post(self.reject_url)
        self.assertEqual(len(mail.outbox), 1)

    def test_mail_failure_is_logged_and_the_decision_still_stands(self):
        for url, status in (
            (self.approve_url, "approved"),
            (self.reject_url, "rejected"),
        ):
            with self.subTest(status=status):
                CoursePurchase.objects.filter(id=self.purchase.id).update(
                    status="pending"
                )
                with (
                    mock.patch(
                        "django.core.mail.backends.locmem.EmailBackend.send_messages",
                        side_effect=OSError("mail server down"),
                    ),
                    self.assertLogs("student.notifications", "ERROR") as logs,
                ):
                    response = self.client.post(url)

                self.assertRedirects(response, reverse("principal:admin_dashboard"))
                self.purchase.refresh_from_db()
                self.assertEqual(self.purchase.status, status)
                self.assertIn("mail server down", logs.output[0])


class StudentCrudTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.department = Department.objects.create(
            name="Commerce", description="Finance."
        )
        self.student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        self.client.force_login(self.admin)

    def test_list_shows_students_and_not_staff(self):
        response = self.client.get(reverse("principal:admin_students"))
        self.assertContains(response, "asha@example.com")
        self.assertNotContains(response, "principal@example.com")

    def test_edit_updates_roll_number_and_department(self):
        response = self.client.post(
            reverse("principal:admin_edit_student", args=[self.student.id]),
            {"rollno": 42, "dept": self.department.id},
        )
        self.assertRedirects(response, reverse("principal:admin_students"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.rollno, 42)
        self.assertEqual(self.student.dept, self.department)

    def test_duplicate_roll_number_is_rejected(self):
        Student.objects.create_user(
            "ravi", "ravi@example.com", "Demo-pass-4821", rollno=42
        )
        response = self.client.post(
            reverse("principal:admin_edit_student", args=[self.student.id]),
            {"rollno": 42},
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.rollno)

    def test_delete_removes_student(self):
        response = self.client.post(
            reverse("principal:admin_delete_student", args=[self.student.id])
        )
        self.assertRedirects(response, reverse("principal:admin_students"))
        self.assertFalse(Student.objects.filter(id=self.student.id).exists())


class StudentDeactivationTests(TestCase):
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
            student=self.student, course=self.course, status="completed"
        )
        self.deactivate_url = reverse(
            "principal:admin_deactivate_student", args=[self.student.id]
        )
        self.reactivate_url = reverse(
            "principal:admin_reactivate_student", args=[self.student.id]
        )
        self.client.force_login(self.admin)

    def log_in_as_student(self, client):
        return client.post(
            reverse("student:login"),
            {"username": "asha", "password": "Demo-pass-4821"},
        )

    def test_deactivated_student_cannot_log_in(self):
        response = self.client.post(self.deactivate_url, follow=True)

        self.assertRedirects(response, reverse("principal:admin_students"))
        self.assertContains(response, "can no longer log in")
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

        visitor = Client()
        self.assertContains(self.log_in_as_student(visitor), "Invalid credentials")
        self.assertNotIn("_auth_user_id", visitor.session)

    def test_deactivation_ends_a_session_that_is_already_open(self):
        student_browser = Client()
        student_browser.force_login(self.student)
        dashboard = reverse("student:student_dashboard")
        self.assertEqual(student_browser.get(dashboard).status_code, 200)

        self.client.post(self.deactivate_url)

        self.assertRedirects(
            student_browser.get(dashboard), "/", fetch_redirect_response=False
        )

    def test_deactivated_student_stays_in_enrollment_history(self):
        self.client.post(self.deactivate_url)

        self.assertTrue(CoursePurchase.objects.filter(id=self.purchase.id).exists())
        response = self.client.get(reverse("principal:admin_enrollments"))
        self.assertContains(response, "asha")
        self.assertContains(response, "Cloud Fundamentals")

    def test_student_list_marks_inactive_students_and_offers_reactivation(self):
        active = self.client.get(reverse("principal:admin_students"))
        self.assertNotContains(active, "Inactive")
        self.assertContains(active, f'action="{self.deactivate_url}"')
        self.assertNotContains(active, f'action="{self.reactivate_url}"')

        self.client.post(self.deactivate_url)

        inactive = self.client.get(reverse("principal:admin_students"))
        self.assertContains(inactive, "Inactive")
        self.assertContains(inactive, f'action="{self.reactivate_url}"')
        self.assertNotContains(inactive, f'action="{self.deactivate_url}"')

    def test_reactivated_student_can_log_in_again(self):
        self.client.post(self.deactivate_url)

        response = self.client.post(self.reactivate_url, follow=True)

        self.assertRedirects(response, reverse("principal:admin_students"))
        self.assertContains(response, "can log in again")
        self.assertRedirects(
            self.log_in_as_student(Client()), reverse("student:student_dashboard")
        )

    def test_unknown_student_returns_404(self):
        for name in ("admin_deactivate_student", "admin_reactivate_student"):
            with self.subTest(name=name):
                response = self.client.post(reverse(f"principal:{name}", args=[999999]))
                self.assertEqual(response.status_code, 404)


class DepartmentCrudTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(self.admin)

    def test_add_creates_department(self):
        response = self.client.post(
            reverse("principal:admin_add_department"),
            {"name": "Science", "description": "Labs."},
        )
        self.assertRedirects(response, reverse("principal:admin_departments"))
        self.assertTrue(Department.objects.filter(name="Science").exists())

    def test_delete_keeps_the_students_who_belonged_to_it(self):
        department = Department.objects.create(name="Commerce", description="x")
        student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821", dept=department
        )

        response = self.client.post(
            reverse("principal:admin_delete_department", args=[department.id])
        )

        self.assertRedirects(response, reverse("principal:admin_departments"))
        self.assertFalse(Department.objects.filter(id=department.id).exists())
        student.refresh_from_db()
        self.assertIsNone(student.dept)


class CourseCrudTests(TestCase):
    def setUp(self):
        self.admin = Student.objects.create_superuser(
            "principal", "principal@example.com", "Demo-pass-4821"
        )
        self.client.force_login(self.admin)

    def test_add_creates_course(self):
        response = self.client.post(
            reverse("principal:admin_add_course"),
            {
                "name": "Data Basics",
                "description": "Intro.",
                "price": 500,
                "status": "active",
            },
        )
        self.assertRedirects(response, reverse("principal:admin_courses"))
        self.assertEqual(AddOnCourse.objects.get(name="Data Basics").price, 500)

    def test_edit_can_deactivate_a_course_with_enrollments(self):
        course = AddOnCourse.objects.create(
            name="Cloud Fundamentals", description="Core concepts.", price=2999
        )
        student = Student.objects.create_user(
            "asha", "asha@example.com", "Demo-pass-4821"
        )
        CoursePurchase.objects.create(student=student, course=course)

        response = self.client.post(
            reverse("principal:admin_edit_course", args=[course.id]),
            {
                "name": course.name,
                "description": course.description,
                "price": course.price,
                "status": "inactive",
            },
        )

        self.assertRedirects(response, reverse("principal:admin_courses"))
        course.refresh_from_db()
        self.assertEqual(course.status, "inactive")
