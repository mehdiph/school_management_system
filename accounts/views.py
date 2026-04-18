from django.shortcuts import render, redirect
# from django.contrib.auth.forms import AuthenticationForm
from .forms import LoginForm
from django.contrib.auth import logout, login, authenticate

# Create your views here.

def login_form(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            user = authenticate(request,
                         username=cd['username'],
                         password=cd['password'])
            if user is not None:
                login(request, user)
                return redirect('core:dashboard')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})

def auth_logout(request):
    logout(request)
    return redirect('accounts:login')