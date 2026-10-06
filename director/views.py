from django.shortcuts import render

from .permissions import director_required


@director_required
def dashboard(request):
    return render(request, "director/dashboard.html")
