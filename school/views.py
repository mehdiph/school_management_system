from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import SchoolClassForm
from .models import SchoolClass, Grade


from django.contrib.auth.decorators import login_required
from school.models import ClassSubject, Grade, Subject

@login_required
def class_list(request):
    """
    Shows list of ClassSubjects assigned to the logged-in teacher.
    Supports filtering by Grade and Subject.
    """
    # Base query: Active assignments for this teacher
    queryset = ClassSubject.objects.filter(
        teacher=request.user,
        is_active=True,
        school_class__is_active=True
    ).select_related(
        'school_class',
        'school_class__grade',
        'school_class__year',
        'subject'
    ).order_by('school_class__grade__level', 'school_class__section', 'subject__name')

    # Filtering
    grade_id = request.GET.get('grade')
    subject_id = request.GET.get('subject')

    if grade_id:
        queryset = queryset.filter(school_class__grade_id=grade_id)
    
    if subject_id:
        queryset = queryset.filter(subject_id=subject_id)

    # Context data for filters (Dropdown options)
    # Get only grades and subjects relevant to this teacher to keep it clean, 
    # or all active ones. Querying all active ones is simpler and safer if assignments change.
    grades = Grade.objects.filter(is_active=True).order_by('level')
    subjects = Subject.objects.filter(is_active=True).order_by('name')

    context = {
        'class_subjects': queryset,
        'grades': grades,
        'subjects': subjects,
        'selected_grade': int(grade_id) if grade_id and grade_id.isdigit() else None,
        'selected_subject': int(subject_id) if subject_id and subject_id.isdigit() else None,
    }
    
    return render(request, 'school/class_list.html', context)


def class_create(request):
    """
    ویو برای ایجاد کلاس جدید
    """
    if request.method == 'POST':
        form = SchoolClassForm(request.POST)
        if form.is_valid():
            # ذخیره کلاس جدید
            school_class = form.save()
            
            # نمایش پیام موفقیت
            messages.success(request, f'کلاس {school_class.grade.name} - {school_class.section} با موفقیت ایجاد شد!')
            
            # انتقال به لیست کلاس‌ها
            return redirect('school:class_list')
        else:
            # نمایش پیام خطا
            messages.error(request, 'لطفاً خطاهای فرم را بررسی کنید.')
    else:
        # نمایش فرم خالی
        form = SchoolClassForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'school/class_form.html', context)


def class_update(request, pk):
    """
    ویو برای ویرایش کلاس موجود
    """
    school_class = get_object_or_404(SchoolClass, pk=pk)
    
    if request.method == 'POST':
        form = SchoolClassForm(request.POST, instance=school_class)
        if form.is_valid():
            form.save()
            messages.success(request, 'کلاس با موفقیت ویرایش شد!')
            return redirect('school:class_list')
        else:
            messages.error(request, 'لطفاً خطاهای فرم را بررسی کنید.')
    else:
        form = SchoolClassForm(instance=school_class)
    
    context = {
        'form': form,
        'school_class': school_class,
    }
    
    return render(request, 'school/class_form.html', context)

