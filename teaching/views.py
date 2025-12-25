from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from .forms import SchoolSessionForm, SessionContentForm
from .models import SchoolSession, SessionContent

# Create your views here.

def school_session_form(request):
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
                    return redirect('teaching:session_form')
                    
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
        session_form = SchoolSessionForm()
        content_form = SessionContentForm()

    context = {
        'session_form': session_form,
        'content_form': content_form
    }
    
    return render(request, 'teaching/session_form.html', context)


def session_list(request):
    """
    ویو برای نمایش لیست جلسات درسی
    """
    sessions = SchoolSession.objects.filter(
        class_subject__is_active=True
    ).select_related(
        'class_subject__school_class__grade',
        'class_subject__subject',
        'class_subject__teacher',
        'sessioncontent'  # جلوگیری از N+1 و خطای RelatedObjectDoesNotExist
    ).order_by('-date', '-session_number')
    
    context = {
        'sessions': sessions
    }
    
    return render(request, 'teaching/session_list.html', context)