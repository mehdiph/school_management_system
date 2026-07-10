from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from .forms import SchoolSessionForm, SessionContentForm
from .models import SchoolSession, SessionContent
from school.models import ClassSubject

# Create your views here.

def school_session_form(request, class_subject_id):
    """
    ویو برای ایجاد جلسه درسی جدید همراه با محتوای آن
    """
    if request.method == 'POST':
        session_form = SchoolSessionForm(request.POST)
        content_form = SessionContentForm(request.POST)
        
        if session_form.is_valid() and content_form.is_valid():
            try:
                with transaction.atomic():
                    # ابتدا جلسه را ذخیره می‌کنیم
                    session = session_form.save()
                    
                    # سپس محتوا را ذخیره می‌کنیم (بدون commit)
                    content = content_form.save(commit=False)
                    # جلسه را به محتوا متصل می‌کنیم
                    content.session = session
                    content.save()
                    
                    # پیام موفقیت
                    messages.success(
                        request,
                        f'جلسه {session.session_number} - {session.class_subject} با موفقیت ثبت شد!'
                    )
                    
                    # انتقال به لیست جلسات یا صفحه جدید
                    return redirect('attendance:attendance_form', session.id)
                    
            except Exception as e:
                # در صورت بروز خطا
                messages.error(
                    request,
                    f'خطا در ثبت جلسه: {str(e)}'
                )
        else:
            # نمایش خطاهای فرم
            messages.error(request, 'لطفاً خطاهای فرم را بررسی کنید.')
    else:
        class_subject = get_object_or_404(ClassSubject, id=class_subject_id)
        # Find the max session number for this class subject
        last_session = SchoolSession.objects.filter(class_subject=class_subject).order_by('-session_number').first()
        next_number = (last_session.session_number + 1) if last_session else 1
        
        session_form = SchoolSessionForm(initial={
            'session_number': next_number,
            'class_subject': class_subject
        })
        content_form = SessionContentForm()

    context = {
        'session_form': session_form,
        'content_form': content_form,
        'class_subject_id': class_subject_id,
    }
    
    return render(request, 'teaching/session_form.html', context)

def update_session(request, session_id):
    session = SchoolSession.objects.get(id=session_id)
    session_form = SchoolSessionForm(instance=session)
    content_form = SessionContentForm(instance=session.session_contents)
    
    if request.method == 'POST':
        session_form = SchoolSessionForm(request.POST, instance=session)
        content_form = SessionContentForm(request.POST, instance=session.session_contents)
        if session_form.is_valid() and content_form.is_valid():
            session_form.save()
            content_form.save()
            return redirect('attendance:attendance_form', session.id)
    
    context = {
        'session_form': session_form,
        'content_form': content_form,
        'session': session
    }
    
    return render(request, 'teaching/session_form.html', context)


def session_list(request, class_subject_id):
    """
    ویو برای نمایش لیست جلسات درسی
    """
    class_subject = get_object_or_404(
        ClassSubject.objects.select_related('school_class__grade', 'subject', 'teacher'),
        id=class_subject_id,
        is_active=True
    )

    sessions = SchoolSession.objects.filter(
        class_subject_id=class_subject_id,
        class_subject__is_active=True,
    ).select_related(
        'class_subject__school_class__grade',
        'class_subject__subject',
        'class_subject__teacher',
        'session_contents'  # جلوگیری از N+1 و خطای RelatedObjectDoesNotExist
    ).order_by('-date', '-session_number')
    
    context = {
        'sessions': sessions,
        'class_subject_id': class_subject_id,
        'class_subject': class_subject
    }
    
    return render(request, 'teaching/session_list.html', context)
