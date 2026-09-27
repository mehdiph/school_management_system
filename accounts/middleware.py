from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

PASSWORD_CHANGE_REQUIRED = "must_change_password"


def _url_prefix(url):
    """'static/' -> '/static/'; absolute URLs (CDN) are not served by us."""
    if not url or "://" in url:
        return None
    return "/" + url.lstrip("/")


def _wants_json(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
        or request.content_type == "application/json"
    )


class ForcePasswordChangeMiddleware:
    """
    A user with ``must_change_password`` (e.g. created by the Excel import
    with their national code as password) can do nothing but change it:
    pages redirect to the password change form, JSON/AJAX requests get a
    403 with ``{"error": "must_change_password"}``. Applies to every
    login path -- the site's own login and the admin's -- because it
    looks at the session's user, not at how they logged in.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if (
            user is not None
            and user.is_authenticated
            and user.must_change_password
            and not self._is_exempt(request.path_info)
        ):
            change_url = reverse("accounts:password_change")
            if _wants_json(request):
                return JsonResponse(
                    {
                        "error": PASSWORD_CHANGE_REQUIRED,
                        "detail": "ابتدا رمز عبور خود را تغییر دهید.",
                        "password_change_url": change_url,
                    },
                    status=403,
                )
            return redirect(change_url)

        return self.get_response(request)

    def _is_exempt(self, path):
        exact = {
            reverse("accounts:password_change"),
            reverse("accounts:logout"),
            reverse("admin:logout"),
        }
        if path in exact:
            return True

        prefixes = filter(None, (_url_prefix(settings.STATIC_URL), _url_prefix(settings.MEDIA_URL)))
        return any(path.startswith(prefix) for prefix in prefixes)
