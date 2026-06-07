
def role_dashboard(user):
    if user.role == 'teacher':
        return 'core:dashboard'
    elif user.role == 'student':
        return 'student:dashboard'