"""
What a student sees: everything is read here, once per page, whatever the
number of events, audiences and access rows. Time-based state comes from the
clock, never from a job (D9). A link or a credential enters a card only while
it may be shown, so it can't reach a template too early (D11, D12).
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from core.templatetags.jalali_tags import fa_digits, format_jalali
from school.colors import is_hex_color, safe_hex
from student.selectors import current_enrollment

from . import audience, crypto
from .models import Announcement, OnlineEvent, OnlineEventAccess
from .models.event import Tab
from .validators import safe_https_url

logger = logging.getLogger(__name__)


def countdown_text(seconds):
    """«۳ روز و ۲ ساعت دیگر»; ``static/online_classes/js/online.js`` writes the same while it ticks."""

    seconds = max(int(seconds), 0)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        parts = [f"{days} روز"] + ([f"{hours} ساعت"] if hours else [])
    elif hours:
        parts = [f"{hours} ساعت"] + ([f"{minutes} دقیقه"] if minutes else [])
    elif minutes:
        parts = [f"{minutes} دقیقه"] + ([f"{secs} ثانیه"] if secs else [])
    else:
        parts = [f"{secs} ثانیه"]
    return fa_digits(" و ".join(parts) + " دیگر")


def moment_text(moment):
    """«سه‌شنبه ۱۲ آذر ۱۴۰۵، ساعت ۱۰:۰۰» in Tehran time."""

    local = timezone.localtime(moment)
    return f"{format_jalali(local.date(), with_weekday=True)}، ساعت {fa_digits(local.strftime('%H:%M'))}"


def time_text(moment):
    return fa_digits(timezone.localtime(moment).strftime("%H:%M"))


@dataclass
class EventCard:
    event: OnlineEvent
    now: object
    join_url: str = ""
    test_url: str = ""
    username: str = ""
    password: str = ""
    access_code: str = ""
    note: str = ""
    has_row: bool = False
    has_personal_link: bool = False
    credentials_failed: bool = False

    @property
    def state(self):
        return self.event.state_at(self.now)

    @property
    def is_live(self):
        return self.event.is_scheduled and self.state == OnlineEvent.State.LIVE

    @property
    def is_past(self):
        return not self.event.is_postponed and self.state == OnlineEvent.State.ENDED

    @property
    def status_label(self):
        if self.event.is_cancelled:
            return "لغو شد"
        if self.event.is_postponed:
            return "به تعویق افتاد"
        if self.is_live:
            return "در حال برگزاری"
        if self.is_past:
            return "پایان یافت"
        return "به‌زودی"

    @property
    def status_kind(self):
        if self.event.is_cancelled:
            return "cancelled"
        if self.event.is_postponed:
            return "postponed"
        if self.is_live:
            return "live"
        return "ended" if self.is_past else "upcoming"

    @property
    def is_personal(self):
        return self.event.access_mode == OnlineEvent.AccessMode.PERSONAL

    @property
    def is_info_only(self):
        return self.event.access_mode == OnlineEvent.AccessMode.INFO

    @property
    def can_join(self):
        return self.event.can_join_at(self.now) and bool(self.join_url)

    @property
    def is_waiting_to_join(self):
        """Scheduled, has or will have a way in, and the join window hasn't opened yet."""

        has_link = self.has_personal_link or bool(self.event.join_url)
        return (
            self.event.is_scheduled
            and not self.is_info_only
            and has_link
            and self.now < self.event.join_opens_at
            and not self.missing_row
        )

    @property
    def missing_row(self):
        """«لینک شما هنوز ثبت نشده»: shown at all times, so a family can act before the exam."""

        return self.is_personal and not self.has_row and self.event.is_scheduled and self.now < self.event.end

    @property
    def credentials_open(self):
        return self.has_row and self.event.credentials_open_on(self.now) and not self.credentials_failed

    @property
    def has_credentials(self):
        return self.credentials_open and bool(self.username or self.password or self.access_code)

    @property
    def row_waiting(self):
        """A row exists; its details open later."""

        return self.has_row and self.event.is_scheduled and self.now < self.event.credentials_open_at

    @property
    def starts_text(self):
        return moment_text(self.event.start)

    @property
    def ends_text(self):
        return time_text(self.event.end)

    @property
    def joins_text(self):
        return moment_text(self.event.join_opens_at)

    @property
    def credentials_text(self):
        return moment_text(self.event.credentials_open_at)

    @property
    def seconds_to_start(self):
        return int((self.event.start - self.now).total_seconds())

    @property
    def shows_countdown(self):
        return self.event.is_scheduled and self.now < self.event.start

    @property
    def countdown(self):
        return countdown_text(self.seconds_to_start)

    @property
    def seconds_to_change(self):
        moment = self.event.next_change_after(self.now)
        return int((moment - self.now).total_seconds()) + 1 if moment else None

    @property
    def accent(self):
        """The subject's colour, else the platform's, else the panel's."""

        subject = self.event.subject
        if subject and is_hex_color(subject.color):
            return safe_hex(subject.color)
        platform = self.event.platform
        return safe_hex(platform.color) if platform and platform.color else safe_hex("")

    @property
    def icon(self):
        return self.event.subject.icon if self.event.subject else "fa-video"


def _events():
    return OnlineEvent.objects.visible().select_related("platform", "subject")


def _attach_access(card, row):
    """Copies a row into its card, decrypting only what may be shown right now."""

    card.has_row = True
    card.has_personal_link = bool(row.url_encrypted)
    event = card.event
    now = card.now
    if not event.credentials_open_on(now):
        return
    try:
        secrets = row.read_secrets()
    except crypto.DecryptionFailed:
        # Details are logged, the family is told to contact the school; never a 500.
        logger.error("Online access row %s can't be decrypted with the configured keys", row.pk)
        card.credentials_failed = True
        return

    url = safe_https_url(secrets["url"]) or safe_https_url(event.join_url)
    card.username = row.username
    card.password = secrets["password"]
    card.access_code = secrets["access_code"]
    card.note = row.note
    if event.can_join_at(now):
        card.join_url = url
    else:
        card.test_url = url


def _cards(events, enrollment, now):
    cards = [EventCard(event=event, now=now) for event in events]

    personal = {card.event.pk: card for card in cards if card.is_personal}
    if personal:
        rows = OnlineEventAccess.objects.filter(student_id=enrollment.student_id, event__in=personal)
        for row in rows:
            _attach_access(personal[row.event_id], row)

    for card in cards:
        if card.event.access_mode == OnlineEvent.AccessMode.SHARED and card.event.can_join_at(now):
            card.join_url = safe_https_url(card.event.join_url)
    return cards


def event_cards(enrollment, tab):
    """The cards of one tab of ``/student/online/``: two queries at most."""

    now = timezone.now()
    events = audience.visible_to(_events().in_tab(tab).in_order(tab), enrollment)
    return _cards(events, enrollment, now)


def dashboard_cards(enrollment):
    """The dashboard's card: live first, then today's, then the next few."""

    now = timezone.now()
    events = audience.visible_to(_events().current_or_coming().in_order(), enrollment)
    return _cards(events[:settings.ONLINE_DASHBOARD_ITEMS], enrollment, now)


def refresh_seconds(cards):
    """When a page must fetch itself again because a card changes, or ``None``."""

    seconds = [card.seconds_to_change for card in cards if card.seconds_to_change is not None]
    return min(seconds) if seconds else None


# ----------------------------------------------------------------------
# Announcements
# ----------------------------------------------------------------------

@dataclass
class Banner:
    announcement: Announcement
    event_note: str = ""
    seconds_to_event: int = None
    countdown: str = ""


def _banner(announcement, now):
    banner = Banner(announcement=announcement)
    event = announcement.event
    if event is None or not event.is_active:
        return banner
    if event.is_cancelled:
        banner.event_note = "این برنامه لغو شده است."
    elif event.is_postponed:
        banner.event_note = "این برنامه به تعویق افتاده است؛ زمان جدید اعلام می‌شود."
    elif now < event.start:
        banner.seconds_to_event = int((event.start - now).total_seconds())
        banner.countdown = countdown_text(banner.seconds_to_event)
    return banner


def live_announcements(enrollment):
    """All the announcements a student may see right now, before any are dismissed; for the dismiss view."""

    return audience.visible_to(Announcement.objects.live(), enrollment)


def banners(enrollment):
    """At most ``ANNOUNCEMENT_MAX_VISIBLE``, by order of importance. One query."""

    if enrollment is None:
        return []
    now = timezone.now()
    announcements = (
        live_announcements(enrollment)
        .not_dismissed_by(enrollment.student_id)
        .in_order()
        .select_related("event")[:settings.ANNOUNCEMENT_MAX_VISIBLE]
    )
    return [_banner(announcement, now) for announcement in announcements]


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------

def online_page(student_profile, tab):
    enrollment = current_enrollment(student_profile)
    cards = event_cards(enrollment, tab) if enrollment else []
    return {
        "has_enrollment": enrollment is not None,
        "tab": tab,
        "tabs": Tab.choices,
        "cards": cards,
        "refresh_seconds": refresh_seconds(cards),
        "past_days": settings.ONLINE_PAST_DAYS,
    }


def dashboard_block(student_profile):
    enrollment = current_enrollment(student_profile)
    cards = dashboard_cards(enrollment) if enrollment else []
    return {
        "online_cards": cards,
        "online_refresh_seconds": refresh_seconds(cards),
        "banners": banners(enrollment),
    }
