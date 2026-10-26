"""
The blog's writes: drafts, the review workflow (D8), tags and images.

Every transition locks the post (``select_for_update``) inside a
transaction, checks the state it starts from and who asks, and raises
``TransitionError`` with a Persian message otherwise, so a double click
or two open tabs can't publish twice.

States::

    DRAFT ── submit (author, privacy ack) ──▶ SUBMITTED
    SUBMITTED ── withdraw (author) ──▶ DRAFT
    DRAFT / SUBMITTED / ARCHIVED ── publish (editor, checklist) ──▶ PUBLISHED (now or scheduled)
    SUBMITTED / PUBLISHED / ARCHIVED ── return_to_author (editor, note) ──▶ DRAFT
    PUBLISHED ── unpublish (editor) ──▶ ARCHIVED
    DRAFT ── archive (author, own) ──▶ ARCHIVED
    ARCHIVED ── reopen (author or editor) ──▶ DRAFT
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from . import permissions
from .models import Post, PostImage, Tag
from .text import normalize, search_key

S = Post.Status


class TransitionError(Exception):
    """A workflow step that isn't allowed from the post's current state; ``str()`` is Persian."""


def _locked(post):
    return Post.objects.select_for_update().get(pk=post.pk)


def _require(condition, message):
    if not condition:
        raise TransitionError(message)


def _require_editor(user):
    if not permissions.is_editor(user):
        raise PermissionDenied("فقط ویراستاران وبلاگ می‌توانند نوشته‌ها را منتشر یا بازگردانند.")


def _require_own(user, post):
    author = permissions.author_for(user)
    if author is None or post.author_id != author.pk or not permissions.can_write(user):
        raise PermissionDenied("این نوشته متعلق به شما نیست یا اجازه نوشتن ندارید.")


def _save(post, *fields):
    post.save(update_fields=[*fields, "updated_at"])
    return post


# ------------------------------------------------------------------- authors


def create_draft(user, section, **fields):
    """A new draft by ``user`` in ``section``. ``fields``: title, body, excerpt, category…"""

    if not permissions.can_write_in(user, section):
        raise PermissionDenied("شما اجازه نوشتن در این بخش را ندارید.")
    post = Post(section=section, author=permissions.author_for(user), status=S.DRAFT, **fields)
    post.full_clean()
    post.save()
    return post


def ensure_author_can_edit(user, post):
    """Raise unless ``user`` may change ``post`` now (own draft, section still granted)."""

    _require_own(user, post)
    _require(post.status == S.DRAFT, "فقط پیش‌نویس را می‌توانید ویرایش کنید. نوشته در انتظار بررسی را اول پس بگیرید.")
    if not permissions.can_write_in(user, post.section):
        raise PermissionDenied("شما دیگر اجازه نوشتن در این بخش را ندارید.")


@transaction.atomic
def submit(post, user, privacy_ack):
    """DRAFT → SUBMITTED, by its author, who must tick the privacy acknowledgement (D16)."""

    post = _locked(post)
    ensure_author_can_edit(user, post)
    _require(privacy_ack, "پیش از ارسال، جمله تأیید حریم خصوصی دانش‌آموزان را تیک بزنید.")
    _require(post.title.strip() and post.body_text.strip(), "نوشته‌ای که عنوان یا متن ندارد را نمی‌توان فرستاد.")
    try:
        post.full_clean(exclude=["slug"])
    except ValidationError as error:
        raise TransitionError(" ".join(error.messages)) from error
    now = timezone.now()
    post.status, post.submitted_at, post.privacy_ack_at, post.review_note = S.SUBMITTED, now, now, ""
    return _save(post, "status", "submitted_at", "privacy_ack_at", "review_note")


@transaction.atomic
def withdraw(post, user):
    """SUBMITTED → DRAFT, by its author, to edit it again."""

    post = _locked(post)
    _require_own(user, post)
    _require(post.status == S.SUBMITTED, "فقط نوشته در انتظار بررسی را می‌توان پس گرفت.")
    post.status = S.DRAFT
    return _save(post, "status")


@transaction.atomic
def archive(post, user):
    """DRAFT → ARCHIVED, by its author: the soft "delete" (ADR-011); nothing is removed."""

    post = _locked(post)
    _require_own(user, post)
    _require(post.status == S.DRAFT, "فقط پیش‌نویس را می‌توانید بایگانی کنید.")
    post.status = S.ARCHIVED
    return _save(post, "status")


@transaction.atomic
def reopen(post, user):
    """ARCHIVED → DRAFT, by its author or an editor. A post that was public goes offline until published again."""

    post = _locked(post)
    if not permissions.is_editor(user):
        _require_own(user, post)
    _require(post.status == S.ARCHIVED, "فقط نوشته بایگانی‌شده را می‌توان به پیش‌نویس برگرداند.")
    post.status = S.DRAFT
    return _save(post, "status")


# ------------------------------------------------------------------- editors


@transaction.atomic
def publish(post, user, *, checklist_confirmed, at=None):
    """
    DRAFT, SUBMITTED or ARCHIVED → PUBLISHED, by an editor who ticked the
    whole review checklist. ``at``: when it becomes public (default now; a
    future time schedules it). A draft is published only from the single
    post's review page: editors write there until the authoring area
    exists, and the page warns that the author never sent it.
    """

    _require_editor(user)
    post = _locked(post)
    _require(
        post.status in (S.DRAFT, S.SUBMITTED, S.ARCHIVED),
        "این نوشته همین حالا منتشرشده است." if post.status == S.PUBLISHED else "این نوشته را نمی‌توان منتشر کرد.",
    )
    _require(checklist_confirmed, "پیش از انتشار، همه موارد فهرست بررسی را تیک بزنید.")
    _require(post.title.strip() and post.body_text.strip(), "نوشته‌ای که عنوان یا متن ندارد را نمی‌توان منتشر کرد.")
    _require(post.section.is_active, "بخش این نوشته غیرفعال است.")
    now = timezone.now()
    post.status = S.PUBLISHED
    post.published_at = at or now
    post.reviewed_by, post.reviewed_at = user, now
    return _save(post, "status", "published_at", "reviewed_by", "reviewed_at")


@transaction.atomic
def unpublish(post, user):
    """PUBLISHED (or scheduled) → ARCHIVED, by an editor. ``published_at`` is kept as history."""

    _require_editor(user)
    post = _locked(post)
    _require(post.status == S.PUBLISHED, "فقط نوشته منتشرشده را می‌توان از انتشار خارج کرد.")
    post.status = S.ARCHIVED
    post.is_featured = False
    return _save(post, "status", "is_featured")


@transaction.atomic
def return_to_author(post, user, note):
    """SUBMITTED, PUBLISHED or ARCHIVED → DRAFT with a note for the author, by an editor."""

    _require_editor(user)
    note = (note or "").strip()
    _require(note, "برای بازگرداندن، یادداشتی برای نویسنده بنویسید.")
    post = _locked(post)
    _require(
        post.status in (S.SUBMITTED, S.PUBLISHED, S.ARCHIVED),
        "این نوشته همین حالا پیش‌نویس است.",
    )
    post.status, post.review_note = S.DRAFT, note
    post.reviewed_by, post.reviewed_at = user, timezone.now()
    post.is_featured = False
    return _save(post, "status", "review_note", "reviewed_by", "reviewed_at", "is_featured")


@transaction.atomic
def set_featured(post, user, featured):
    _require_editor(user)
    post = _locked(post)
    _require(not featured or post.status == S.PUBLISHED, "فقط نوشته منتشرشده می‌تواند ویژه باشد.")
    post.is_featured = bool(featured)
    return _save(post, "is_featured")


# ------------------------------------------------------------- tags, images


def parse_tag_names(raw):
    """«کتاب‌خوانی، اردو, والدگری» -> unique normalised names, in order."""

    names, keys = [], set()
    for part in (raw or "").replace("،", ",").split(","):
        name = normalize(part)[:40]
        key = search_key(name)
        if key and key not in keys:
            keys.add(key)
            names.append(name)
    return names


@transaction.atomic
def sync_tags(post, names):
    """
    Give ``post`` exactly these tags (names in any spelling): existing
    tags are reused, active or not, new ones are created (D14). At most
    ``BLOG_MAX_TAGS_PER_POST``.
    """

    unique = parse_tag_names(",".join(names))
    _require(
        len(unique) <= settings.BLOG_MAX_TAGS_PER_POST,
        f"حداکثر {settings.BLOG_MAX_TAGS_PER_POST} برچسب برای هر نوشته.",
    )
    tags = []
    for name in unique:
        tag = Tag.objects.named(name).first()
        if tag is None:
            tag = Tag.objects.create(name=name)
        tags.append(tag)
    post.tags.set(tags)
    return tags


def can_add_image(user, post):
    return permissions.can_edit_as_author(user, post) or permissions.can_edit_in_admin(user)


def add_image(post, file, user):
    """
    An image uploaded from the editor into ``post``: validated (type, 2 MB),
    re-encoded without metadata, stored as a ``PostImage``.
    """

    if not can_add_image(user, post):
        raise PermissionDenied("شما اجازه افزودن تصویر به این نوشته را ندارید.")
    image = PostImage(post=post, image=file, uploaded_by=user)
    image.full_clean(exclude=["post", "uploaded_by"])
    image.save()
    return image


@transaction.atomic
def merge_tags(sources, target):
    """
    Re-tag the posts of ``sources`` with ``target`` and deactivate the
    sources (D14). A post never ends up with more tags than it had.
    Returns how many posts were re-tagged.
    """

    sources = [tag for tag in sources if tag.pk != target.pk]
    posts = Post.objects.filter(tags__in=sources).distinct()
    count = 0
    for post in posts:
        post.tags.remove(*sources)
        post.tags.add(target)
        count += 1
    Tag.objects.filter(pk__in=[tag.pk for tag in sources]).update(is_active=False)
    return count
