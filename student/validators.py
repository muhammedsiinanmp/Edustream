from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone

validate_phone = RegexValidator(
    r'^\+?[0-9]{7,15}\Z',
    'Enter a phone number of 7 to 15 digits, optionally starting with +.',
)


def validate_not_future(value):
    if value > timezone.localdate():
        raise ValidationError('Date cannot be in the future.')
