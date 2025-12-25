# مثال برای استفاده از فرم SchoolClass در views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import SchoolClassForm


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
            return redirect('class_list')
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
    from django.shortcuts import get_object_or_404
    from .models import SchoolClass
    
    school_class = get_object_or_404(SchoolClass, pk=pk)
    
    if request.method == 'POST':
        form = SchoolClassForm(request.POST, instance=school_class)
        if form.is_valid():
            form.save()
            messages.success(request, 'کلاس با موفقیت ویرایش شد!')
            return redirect('class_list')
        else:
            messages.error(request, 'لطفاً خطاهای فرم را بررسی کنید.')
    else:
        form = SchoolClassForm(instance=school_class)
    
    context = {
        'form': form,
        'school_class': school_class,
    }
    
    return render(request, 'school/class_form.html', context)


# مثال برای URLs (باید در urls.py اضافه شود):
"""

"""
