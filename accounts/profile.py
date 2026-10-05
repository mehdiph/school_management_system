"""
Read-only data for the teacher profile page (accounts.views.profile).
"""

from django.contrib.auth import password_validation

from core.selectors import active_classes_count, current_academic_year, teacher_class_subjects
from scheduling.services import build_teacher_weekly_schedule
from teaching.models import SchoolSession

_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def teacher_overview(teacher_profile):
    """Header of the profile page: year, subjects and classes taught, a few numbers."""

    year = current_academic_year()
    if year is None:
        return {'academic_year': None, 'subjects': [], 'classes': [],
                'weekly_periods': 0, 'active_classes': 0, 'sessions_this_year': 0}

    class_subjects = list(
        teacher_class_subjects(teacher_profile, year)
        .select_related('subject', 'school_class__grade', 'school_class__branch')
        .order_by('school_class__grade__level', 'school_class__section', 'subject__name')
    )

    subjects = sorted({cs.subject.name for cs in class_subjects})
    classes = list(dict.fromkeys(
        f'{cs.school_class.grade.name} - {cs.school_class.section} · {cs.school_class.branch.name}'
        for cs in class_subjects
    ))

    schedule = build_teacher_weekly_schedule(teacher_profile, year)

    return {
        'academic_year': year,
        'subjects': subjects,
        'classes': classes,
        'weekly_periods': schedule.summary(schedule.current_week).periods,
        'active_classes': active_classes_count(teacher_profile, year),
        'sessions_this_year': SchoolSession.objects.counted().filter(
            class_subject__teacher_assignment__teacher=teacher_profile,
            class_subject__school_class__year=year,
        ).count(),
    }


def password_rules():
    """
    The checklist next to «رمز عبور جدید», built from the configured
    AUTH_PASSWORD_VALIDATORS so it cannot drift from them. ``check`` names
    the live client-side hint (static/accounts/js/profile.js); rules the
    browser cannot judge (the common-password list, the national code)
    have none and are only checked by the server, which always decides.
    """

    rules = []
    for validator in password_validation.get_default_password_validators():
        name = type(validator).__name__
        if name == 'MinimumLengthValidator':
            rules.append({
                'check': 'length',
                'value': validator.min_length,
                'text': f'دست‌کم {str(validator.min_length).translate(_DIGITS)} نویسه',
            })
        elif name == 'NumericPasswordValidator':
            rules.append({'check': 'not-numeric', 'text': 'فقط از عدد تشکیل نشده باشد'})
        elif name == 'UserAttributeSimilarityValidator':
            rules.append({'check': 'not-similar', 'text': 'شبیه نام یا نام کاربری شما نباشد'})
        elif name == 'CommonPasswordValidator':
            rules.append({'check': '', 'text': 'از رمزهای رایج و ساده نباشد'})
        elif name == 'NotNationalCodePasswordValidator':
            rules.append({'check': '', 'text': 'با کد ملی شما یکسان نباشد'})
        else:
            rules.append({'check': '', 'text': validator.get_help_text()})
    return rules
