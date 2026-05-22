from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from school.models import AcademicYear, ClassSubject
from teaching.models import SchoolSession
from school.utils import get_current_week_type, get_today_schedule_day
from datetime import date


@login_required
def dashboard(request):
    """
    Dashboard view for the teacher.
    """
    
    
    
    # 2. Academic Year
    current_year = AcademicYear.objects.filter(is_current=True).first()
    academic_year_title = current_year.title if current_year else "تعریف نشده"

    # 3. Class Subjects (Active only)
    # Filter by user and current year (if exists)
    class_subjects_query = ClassSubject.objects.filter(
            teacher=request.user,
            is_active=True,
            school_class__is_active=True,
        )\
        .select_related('school_class', 'school_class__grade', 'subject', 'teacher')\
        .prefetch_related('schedules')\
        .order_by('school_class__grade__level', 'subject__name', 'school_class__section')

    today_day = get_today_schedule_day(date.today())
    week_type = get_current_week_type(date.today())
    if current_year:
        class_subjects_query = class_subjects_query.filter(school_class__year=current_year,
                                                           schedules__day_of_week=today_day,
                                                           schedules__week_type=week_type)

    # Process data for "Today's Teaching" cards AND "My Classes" list
    # Since we don't have a daily schedule model, we show all active classes as potential teaching targets.
    today_class_subjects = []
    class_subjects_summary = []
    
    for cs in class_subjects_query:

        # Common data
        class_name = f"{cs.school_class.grade.name} - {cs.school_class.section}"
        subject_name = cs.subject.name
        grade_name = cs.school_class.grade.name

        # For Summary List
        class_subjects_summary.append({
            'class_name': class_name,
            'subject_name': subject_name,
            'grade_name': grade_name,
            'id': cs.id
        })

        # For Cards (Fetch last session)
        last_session = SchoolSession.objects.filter(class_subject=cs).order_by('-session_number').first()
        last_session_num = 0
        last_summary = ""

        if last_session:
            last_session_num = last_session.session_number
            # efficient way? Maybe prefetch related would be better but loop is fine for N < 20
            try:
                 if hasattr(last_session, 'sessioncontent'):
                     last_summary = last_session.sessioncontent.content
            except:
                 pass
        
        today_class_subjects.append({
            'id': cs.id,
            'class_name': class_name,
            'subject_name': subject_name,
            'last_session_number': last_session_num,
            'last_session_summary': last_summary
        })

    # 4. Recent Sessions
    recent_sessions = SchoolSession.objects.filter(
        class_subject__teacher=request.user
    ).select_related('class_subject', 'class_subject__subject', 'class_subject__school_class').order_by('-date', '-created_at')[:5]

    # 5. Stats
    total_sessions = SchoolSession.objects.filter(class_subject__teacher=request.user).count()

    context = {
        'academic_year': academic_year_title,
        'today_class_subjects': today_class_subjects[:6],
        'class_subjects_summary': class_subjects_summary,
        'recent_sessions': recent_sessions,
        'total_sessions': total_sessions,
    }

    print(class_subjects_summary)

    return render(request, 'core/dashboard.html', context)
