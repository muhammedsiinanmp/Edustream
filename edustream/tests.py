import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from django.core.checks import run_checks
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

BASE_DIR = Path(__file__).resolve().parent.parent

# Blank values keep a developer's local .env out of these checks.
BLANK_ENV = dict.fromkeys(
    [
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "CSRF_COOKIE_SECURE",
        "DEBUG",
        "DEFAULT_FROM_EMAIL",
        "EMAIL_HOST_USER",
        "EMAIL_PORT",
        "LOG_LEVEL",
        "MEDIA_ROOT",
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        "SECURE_HSTS_PRELOAD",
        "SECURE_HSTS_SECONDS",
        "SECURE_SSL_REDIRECT",
        "SESSION_COOKIE_SECURE",
        "STATIC_ROOT",
        "TRUST_X_FORWARDED_PROTO",
    ],
    "",
)
READ_SETTINGS = """
import json
from django.conf import settings
names = {names!r}
print(json.dumps({{n: getattr(settings, n) for n in names}}, default=str))
"""


def load_settings(*names, **env):
    """Import settings in a fresh process, as a server would with this env."""
    result = subprocess.run(
        [sys.executable, "-c", READ_SETTINGS.format(names=names)],
        cwd=BASE_DIR,
        env={
            "PATH": os.environ["PATH"],
            "DJANGO_SETTINGS_MODULE": "edustream.settings",
            "SECRET_KEY": "settings-test-key",
            **BLANK_ENV,
            **env,
        },
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class ProductionSettingsTests(SimpleTestCase):
    SECURITY = (
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "SECURE_SSL_REDIRECT",
        "SECURE_HSTS_SECONDS",
    )

    def test_debug_on_keeps_plain_http_development(self):
        loaded = load_settings(*self.SECURITY, "ALLOWED_HOSTS", DEBUG="True")
        self.assertFalse(loaded["SESSION_COOKIE_SECURE"])
        self.assertFalse(loaded["CSRF_COOKIE_SECURE"])
        self.assertFalse(loaded["SECURE_SSL_REDIRECT"])
        self.assertEqual(loaded["SECURE_HSTS_SECONDS"], 0)
        self.assertEqual(loaded["ALLOWED_HOSTS"], [])

    def test_debug_off_turns_on_https_protections(self):
        loaded = load_settings(*self.SECURITY, DEBUG="False")
        self.assertTrue(loaded["SESSION_COOKIE_SECURE"])
        self.assertTrue(loaded["CSRF_COOKIE_SECURE"])
        self.assertTrue(loaded["SECURE_SSL_REDIRECT"])
        self.assertEqual(loaded["SECURE_HSTS_SECONDS"], 31536000)

    def test_protections_can_be_overridden_from_the_environment(self):
        loaded = load_settings(
            *self.SECURITY,
            "SECURE_HSTS_INCLUDE_SUBDOMAINS",
            "SECURE_HSTS_PRELOAD",
            DEBUG="False",
            SESSION_COOKIE_SECURE="False",
            CSRF_COOKIE_SECURE="False",
            SECURE_SSL_REDIRECT="False",
            SECURE_HSTS_SECONDS="3600",
            SECURE_HSTS_INCLUDE_SUBDOMAINS="True",
            SECURE_HSTS_PRELOAD="True",
        )
        self.assertFalse(loaded["SESSION_COOKIE_SECURE"])
        self.assertFalse(loaded["CSRF_COOKIE_SECURE"])
        self.assertFalse(loaded["SECURE_SSL_REDIRECT"])
        self.assertEqual(loaded["SECURE_HSTS_SECONDS"], 3600)
        self.assertTrue(loaded["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertTrue(loaded["SECURE_HSTS_PRELOAD"])

    def test_hosts_and_origins_come_from_the_environment(self):
        loaded = load_settings(
            "ALLOWED_HOSTS",
            "CSRF_TRUSTED_ORIGINS",
            ALLOWED_HOSTS="edustream.example.com, www.example.com",
            CSRF_TRUSTED_ORIGINS="https://edustream.example.com",
        )
        self.assertEqual(
            loaded["ALLOWED_HOSTS"], ["edustream.example.com", "www.example.com"]
        )
        self.assertEqual(
            loaded["CSRF_TRUSTED_ORIGINS"], ["https://edustream.example.com"]
        )

    def test_proxy_https_header_is_trusted_only_when_asked(self):
        name = "SECURE_PROXY_SSL_HEADER"
        self.assertIsNone(load_settings(name)[name])
        self.assertEqual(
            load_settings(name, TRUST_X_FORWARDED_PROTO="True")[name],
            ["HTTP_X_FORWARDED_PROTO", "https"],
        )

    def test_missing_email_port_does_not_crash_startup(self):
        self.assertEqual(load_settings("EMAIL_PORT")["EMAIL_PORT"], 587)

    def test_blank_sender_falls_back_to_an_address(self):
        name = "DEFAULT_FROM_EMAIL"
        self.assertTrue(load_settings(name)[name])
        self.assertEqual(
            load_settings(name, EMAIL_HOST_USER="mailer@example.com")[name],
            "mailer@example.com",
        )

    def test_collected_static_and_media_paths_are_configurable(self):
        defaults = load_settings("STATIC_ROOT", "MEDIA_ROOT")
        self.assertEqual(defaults["STATIC_ROOT"], str(BASE_DIR / "staticfiles"))
        self.assertEqual(defaults["MEDIA_ROOT"], str(BASE_DIR / "media"))
        custom = load_settings(
            "STATIC_ROOT",
            "MEDIA_ROOT",
            STATIC_ROOT="/srv/static",
            MEDIA_ROOT="/srv/media",
        )
        self.assertEqual(custom["STATIC_ROOT"], "/srv/static")
        self.assertEqual(custom["MEDIA_ROOT"], "/srv/media")

    def test_production_serves_static_files_through_whitenoise(self):
        loaded = load_settings("MIDDLEWARE", "STORAGES", DEBUG="False")
        self.assertEqual(
            loaded["MIDDLEWARE"][:2],
            [
                "django.middleware.security.SecurityMiddleware",
                "whitenoise.middleware.WhiteNoiseMiddleware",
            ],
        )
        self.assertEqual(
            loaded["STORAGES"]["staticfiles"]["BACKEND"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    def test_failures_are_logged_to_the_console(self):
        loaded = load_settings("LOGGING", LOG_LEVEL="WARNING", DEBUG="False")["LOGGING"]
        self.assertIn("console", loaded["root"]["handlers"])
        self.assertEqual(loaded["root"]["level"], "WARNING")
        self.assertIn("console", loaded["loggers"]["django"]["handlers"])


class ProjectCheckTests(SimpleTestCase):
    def test_no_warning_about_a_missing_static_directory(self):
        self.assertNotIn("staticfiles.W004", [issue.id for issue in run_checks()])

    def test_student_logger_reaches_a_handler(self):
        self.assertTrue(logging.getLogger("student.notifications").hasHandlers())


class MessageStylingTests(TestCase):
    def test_failed_login_shows_a_styled_error_alert(self):
        response = self.client.post(
            reverse("student:login"), {"username": "nobody", "password": "wrong"}
        )
        self.assertContains(response, "alert-danger")
        self.assertNotContains(response, "alert-error")
