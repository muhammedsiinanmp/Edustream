import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def notify(student, subject, message):
    """Email a student. A mail failure is logged and must not break the action."""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[student.email],
        )
    except Exception:
        logger.exception("Failed to send %r email to student %s", subject, student.pk)
        return False
    return True
