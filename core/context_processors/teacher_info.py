import jdatetime

#: The shell a page shared by several roles (class list, reports, session
#: form, ...) extends: ``{% extends panel_base|default:"base.html" %}``.
#: Teachers get the redesigned teacher panel; everybody else keeps base.html.
TEACHER_BASE = 'teacher/base.html'
DEFAULT_BASE = 'base.html'


def teacher_info_context(request):
    if request.user.is_authenticated:
        teacher = {
            'name': request.user.get_full_name() or request.user.username
        }
    else:
        teacher = {
            'name': ''
        }

    is_teacher = (
        request.user.is_authenticated
        and getattr(request.user, 'role', None) == 'teacher'
    )

    today_date = jdatetime.date.today().strftime("%Y/%m/%d")
    return {
        'teacher': teacher,
        'today_date': today_date,
        'panel_base': TEACHER_BASE if is_teacher else DEFAULT_BASE,
    }
