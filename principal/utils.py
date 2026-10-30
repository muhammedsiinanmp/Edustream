from django.core.exceptions import PermissionDenied


def is_admin(user):
    # Raising here turns user_passes_test's login redirect into a 403 for
    # logged-in students. Anonymous users are caught by login_required first.
    if user.is_authenticated and not user.is_staff:
        raise PermissionDenied
    return user.is_authenticated
