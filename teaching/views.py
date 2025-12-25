from django.shortcuts import render
from .forms import *

# Create your views here.

def school_session_form(request):
    if request.method == 'POST':
        session_form = SchoolSessionForm(request.POST)
        content_form = SessionContentForm(request.POST)
        if session_form.is_valid() and content_form.is_valid():
            session_form.save()
            content_form.save()
    else:
        session_form = SchoolSessionForm()
        content_form = SessionContentForm()

    return render(
        request,
        'teaching/session_form.html',
        {
            'session_form': session_form,
            'content_form': content_form
        }
    )