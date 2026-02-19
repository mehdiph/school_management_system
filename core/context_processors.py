import jdatetime

def teacher_info(request):
    if request.user.is_authenticated:
        teacher = {
            'name': request.user.get_full_name() or request.user.username
        }
    else:
        teacher = {
            'name': ''
        }

    today_date = jdatetime.date.today().strftime("%Y/%m/%d")
    return {
        'teacher': teacher,
        'today_date': today_date,
    }
