from django.utils.functional import SimpleLazyObject

from .models import FooterLink, NavMenuItem, SiteSettings


def site_settings(request):
    """
    Navbar/footer data for base.html, which every page (dashboards
    included) extends. Lazy, so a page only pays for the queries whose
    values its template actually renders.
    """

    return {
        "site_settings": SimpleLazyObject(SiteSettings.load),
        "nav_items": SimpleLazyObject(lambda: list(NavMenuItem.objects.filter(is_active=True))),
        "footer_links": SimpleLazyObject(lambda: list(FooterLink.objects.filter(is_active=True))),
    }
