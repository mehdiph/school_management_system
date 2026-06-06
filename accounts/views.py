from django.shortcuts import render, redirect
# from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from .forms import LoginForm
from .utils import role_dashboard
from django.contrib.auth import logout, login, authenticate

# Create your views here.

def login_form(request):
    if not request.user.is_authenticated:
        if request.method == 'POST':
            form = LoginForm(request, data=request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                user = authenticate(request,
                            username=cd['username'],
                            password=cd['password'])
                if user is not None:
                    login(request, user)
                    messages.success(request, 'با موفقیت وارد شدید')
                    redirect_path = role_dashboard(user)
                    return redirect(redirect_path)
                else:
                    messages.error(request, 'نام کاربری یا رمز عبور اشتباه است')
            else:
                messages.error(request, 'خطای فرم را بررسی کنید')

        else:
            form = LoginForm()
        return render(request, 'accounts/login.html', {'form': form})
    else:
        redirect_path = role_dashboard(request.user)
        return redirect(redirect_path)
        

def auth_logout(request):
    logout(request)
    return redirect('accounts:login')