

def student_info(request):
    if request.user.is_authenticated:
        if request.user.role == 'student':
            student = request.user
            school_class = request.user.student_profile.school_class
            return {'student': student, 'school_class': school_class}
        else:
            return {}
    else:
        return {}