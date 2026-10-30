from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator

PAGE_SIZE = 20


def is_admin(user):
    # Raising here turns user_passes_test's login redirect into a 403 for
    # logged-in students. Anonymous users are caught by login_required first.
    if user.is_authenticated and not user.is_staff:
        raise PermissionDenied
    return user.is_authenticated


def paginate(request, queryset):
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
