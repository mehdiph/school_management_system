"""
Read-side data of the public pages that is more than "the page row and
its active items": who of the teachers may be shown, and how the
«معلمان» page groups and filters them.
"""

from dataclasses import dataclass, field

from django.db.models import Q

from .models import LandingTeacher


def public_teachers():
    """
    Teacher cards a public page may show: active, and not linked to
    someone who has left (an inactive ``Staff``). Each page then narrows
    it with its own tick (``on_home`` / ``on_teachers_page``).
    """

    return (
        LandingTeacher.objects.filter(is_active=True)
        .filter(Q(teacher__isnull=True) | Q(teacher__staff__is_active=True))
        .select_related("teacher__staff__user", "group")
    )


@dataclass
class TeacherSection:
    title: str
    teachers: list
    group: object = None  # None: the teachers without a group

    @property
    def anchor(self):
        return f"tc-group-{self.group.pk}" if self.group else "tc-group-other"


@dataclass
class TeacherListing:
    sections: list = field(default_factory=list)
    groups: list = field(default_factory=list)  # groups in use, in order: the filter chips
    selected: object = None  # the group filtered on, or None for everyone
    grouped: bool = False  # False: one flat list with a visually hidden heading
    count: int = 0

    @property
    def show_chips(self):
        return len(self.groups) >= 2


def _group_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def teachers_page_listing(page, group_param=None):
    """
    The «معلمان» page's teachers, one section per group in use (in group
    order) and the teachers without a group last; or the one section of
    ``group_param`` when it names a group in use. Anything else (unknown,
    inactive, empty or not a number) shows everyone.

    One query: groups come with the teachers (``select_related``) and are
    collected here, in Python.
    """

    teachers = list(
        public_teachers()
        .filter(on_teachers_page=True)
        .filter(Q(group__isnull=True) | Q(group__is_active=True))
    )

    by_group, groups = {}, {}
    for teacher in teachers:
        by_group.setdefault(teacher.group_id, []).append(teacher)
        if teacher.group_id:
            groups[teacher.group_id] = teacher.group
    ordered = sorted(groups.values(), key=lambda group: (group.order, group.pk))

    listing = TeacherListing(groups=ordered, grouped=bool(ordered))
    if not ordered:
        if teachers:
            listing.sections = [TeacherSection(title=page.list_title, teachers=teachers)]
        listing.count = len(teachers)
        return listing

    listing.selected = groups.get(_group_id(group_param))
    if listing.selected:
        listing.sections = [
            TeacherSection(title=listing.selected.title, teachers=by_group[listing.selected.pk], group=listing.selected)
        ]
    else:
        listing.sections = [TeacherSection(title=g.title, teachers=by_group[g.pk], group=g) for g in ordered]
        if None in by_group:
            listing.sections.append(TeacherSection(title=page.other_group_title, teachers=by_group[None]))
    listing.count = sum(len(section.teachers) for section in listing.sections)
    return listing
