import jdatetime

def teacher_info(request):
    # 1. Teacher & Date
    teacher = {
        'name': request.user.get_full_name() or request.user.username
    }

    today_date = jdatetime.date.today().strftime("%Y/%m/%d")
    return {
        'teacher': teacher,
        'today_date': today_date,
    }