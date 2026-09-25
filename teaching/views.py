from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from .forms import SchoolSessionForm, SessionContentForm, active_class_subjects
from .models import SchoolSession
from school.models import ClassSubject

SESSIONS_PER_PAGE = 12

#: Shown when two saves race for the same automatic session number.
DUPLICATE_SESSION_MESSAGE = (
    'هم‌زمان جلسه‌ی دیگری برای همین درس ثبت شد و شماره‌ی جلسه تکراری شد. '
    'اطلاعات شما حفظ شده است؛ لطفاً دوباره «ثبت جلسه» را بزنید.'
)


def _own_class_subjects(user):
    """
    Class subjects ``user`` may record and see sessions for: a teacher's
    own (through their TeacherAssignment), every one for a superuser,
    none for anybody else.
    """

    if user.is_superuser:
        return ClassSubject.objects.all()

    staff = getattr(user, 'staff_profile', None)
    teacher = getattr(staff, 'teacher_profile', None)

    if teacher is None:
        return ClassSubject.objects.none()

    return ClassSubject.objects.for_teacher(teacher)


def _add_save_errors(session_form, error):
    """
    Puts a ``ValidationError`` raised by ``SchoolSession.save()`` (it runs
    ``full_clean()`` once the session number is known) back on the form,
    so it is shown next to the field instead of as a raw message.
    """

    if hasattr(error, 'error_dict'):
        error_dict = error.error_dict
    else:
        error_dict = {NON_FIELD_ERRORS: error.error_list}

    for field, field_errors in error_dict.items():
        for field_error in field_errors:
            if field_error.code in ('unique', 'unique_together'):
                # the only unique rule is (class_subject, session_number),
                # and the number is automatic -- this is a race, not a
                # mistake the teacher made
                session_form.add_error(None, DUPLICATE_SESSION_MESSAGE)
            elif field in session_form.fields:
                session_form.add_error(field, field_error)
            else:
                session_form.add_error(None, field_error)


def _save_session(session_form, content_form):
    """
    Saves both forms in one transaction. Returns the session, or ``None``
    after putting the reason on ``session_form`` (nothing is saved then).
    """

    try:
        with transaction.atomic():
            # ابتدا جلسه را ذخیره می‌کنیم
            session = session_form.save()

            # سپس محتوا را به جلسه متصل و ذخیره می‌کنیم
            content = content_form.save(commit=False)
            content.session = session
            content.save()
    except ValidationError as error:
        _add_save_errors(session_form, error)
        return None
    except IntegrityError:
        session_form.add_error(None, DUPLICATE_SESSION_MESSAGE)
        return None

    return session


def _render_session_form(request, session_form, content_form, **extra):
    context = {
        'session_form': session_form,
        'content_form': content_form,
        # for the "which fields are optional" notice above the form
        'optional_labels': [
            field.label
            for form in (session_form, content_form)
            for field in form
            if not field.field.required
        ],
        **extra,
    }
    return render(request, 'teaching/session_form.html', context)


@login_required(login_url='accounts:login')
def school_session_form(request, class_subject_id):
    """
    ویو برای ایجاد جلسه درسی جدید همراه با محتوای آن
    """
    class_subjects = active_class_subjects(_own_class_subjects(request.user))
    class_subject = get_object_or_404(class_subjects, id=class_subject_id)

    if request.method == 'POST':
        session_form = SchoolSessionForm(request.POST, class_subjects=class_subjects)
        content_form = SessionContentForm(request.POST)

        if session_form.is_valid() and content_form.is_valid():
            session = _save_session(session_form, content_form)

            if session is not None:
                messages.success(
                    request,
                    f'جلسه {session.session_number} - {session.class_subject.subject.name} با موفقیت ثبت شد.'
                )
                # انتقال به صفحه حضور و غیاب همین جلسه
                return redirect('attendance:attendance_form', session.id)
        # Invalid forms are re-rendered with their errors (and with every
        # value the teacher typed); the page shows an error summary.
    else:
        session_form = SchoolSessionForm(
            initial={'class_subject': class_subject},
            class_subjects=class_subjects,
        )
        content_form = SessionContentForm()

    next_session_numbers = session_form.next_session_numbers()

    try:
        # the class subject currently selected in the dropdown (the posted
        # one after an error), whose next number is shown read-only
        session_number = next_session_numbers.get(int(session_form['class_subject'].value()))
    except (TypeError, ValueError):
        session_number = None

    return _render_session_form(
        request,
        session_form,
        content_form,
        class_subject=class_subject,
        class_subject_id=class_subject_id,
        next_session_numbers=next_session_numbers,
        session_number=session_number,
    )


@login_required(login_url='accounts:login')
def update_session(request, session_id):
    own_class_subjects = _own_class_subjects(request.user)
    session = get_object_or_404(
        SchoolSession.objects.filter(class_subject__in=own_class_subjects),
        id=session_id,
    )
    # the session's own class subject stays selectable even if it has
    # been deactivated since
    class_subjects = own_class_subjects.filter(
        Q(pk__in=active_class_subjects().values('pk')) | Q(pk=session.class_subject_id)
    )
    # older sessions may have been saved without content
    content = getattr(session, 'session_contents', None)

    if request.method == 'POST':
        session_form = SchoolSessionForm(request.POST, instance=session, class_subjects=class_subjects)
        content_form = SessionContentForm(request.POST, instance=content)

        if session_form.is_valid() and content_form.is_valid():
            if _save_session(session_form, content_form) is not None:
                messages.success(request, f'تغییرات جلسه {session.session_number} ذخیره شد.')
                return redirect('attendance:attendance_form', session.id)
    else:
        session_form = SchoolSessionForm(instance=session, class_subjects=class_subjects)
        content_form = SessionContentForm(instance=content)

    return _render_session_form(
        request,
        session_form,
        content_form,
        session=session,
        session_number=session.session_number,
        class_subject=session.class_subject,
        class_subject_id=session.class_subject_id,
    )


@login_required(login_url='accounts:login')
def session_list(request, class_subject_id):
    """
    ویو برای نمایش لیست جلسات درسی
    """
    class_subject = get_object_or_404(
        _own_class_subjects(request.user).select_related(
            'school_class__grade',
            'school_class__branch',
            'subject',
            'teacher_assignment__teacher__staff__user',
        ),
        id=class_subject_id,
        is_active=True
    )

    sessions = SchoolSession.objects.filter(
        class_subject=class_subject,
    ).select_related(
        'class_subject__school_class__grade',
        'class_subject__school_class__branch',
        'class_subject__subject',
        'session_contents'  # جلوگیری از N+1 و خطای RelatedObjectDoesNotExist
    ).order_by('-date', '-session_number')

    page_obj = Paginator(sessions, SESSIONS_PER_PAGE).get_page(request.GET.get('page'))

    context = {
        'sessions': page_obj.object_list,
        'page_obj': page_obj,
        'class_subject_id': class_subject_id,
        'class_subject': class_subject
    }

    return render(request, 'teaching/session_list.html', context)
