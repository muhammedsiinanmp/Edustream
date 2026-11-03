from django.core.management.base import CommandError
from django.db import migrations, models
from django.db.models.functions import Lower


def lowercase_emails(apps, schema_editor):
    """Lowercase stored emails, refusing to run if two would then collide."""
    Student = apps.get_model('student', 'Student')
    accounts = Student.objects.annotate(normalised=Lower('email'))

    by_email = {}
    for pk, email in accounts.order_by('id').values_list('id', 'normalised'):
        by_email.setdefault(email, []).append(pk)
    duplicates = {
        email: ids for email, ids in by_email.items() if len(ids) > 1
    }

    if duplicates:
        details = '\n'.join(
            f"  {email}: student ids {', '.join(map(str, ids))}"
            for email, ids in sorted(duplicates.items())
        )
        raise CommandError(
            'Cannot make student emails case-insensitively unique. These '
            'accounts share an address that differs only by letter case:\n'
            f'{details}\n'
            'No data was changed. Decide which account keeps each address, '
            'change the email on the others (or merge or delete them), then '
            'run migrate again.'
        )

    accounts.exclude(email=Lower('email')).update(email=Lower('email'))


class Migration(migrations.Migration):

    dependencies = [
        ('student', '0002_validate_profile_photo'),
    ]

    operations = [
        migrations.RunPython(lowercase_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='student',
            constraint=models.UniqueConstraint(
                Lower('email'),
                name='student_email_ci_unique',
                violation_error_message='Email already exists',
            ),
        ),
    ]
