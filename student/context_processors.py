
def student_info(request):
    if request.user.is_authenticated:
        if request.user.role == 'student':
            student = request.user
            # The current year's active enrollment (a student keeps old
            # years' rows); None rather than an IndexError when there is none.
            enrollment = (
                request.user.student_profile.enrollments
                .filter(status='active')
                .select_related('school_class__grade', 'school_class__branch')
                .order_by('-academic_year__is_current', '-academic_year__start_date')
                .first()
            )
            school_class = enrollment.school_class if enrollment else None
            return {'student': student, 'school_class': school_class}
        else:
            return {}
    else:
        return {}
