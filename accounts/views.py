from django.shortcuts import render, redirect
# from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import LoginForm, PasswordChangeForm
from .utils import role_dashboard
from django.contrib.auth import logout, login, authenticate, update_session_auth_hash

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
                    if user.must_change_password:
                        messages.warning(request, 'برای ادامه، ابتدا رمز عبور خود را تغییر دهید.')
                        return redirect('accounts:password_change')
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


@login_required
def password_change(request):
    """
    Where ForcePasswordChangeMiddleware sends users with
    ``must_change_password``; also usable by anyone to change theirs.
    """

    form = PasswordChangeForm(request.user, request.POST or None)

    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)  # stay logged in
        messages.success(request, 'رمز عبور شما با موفقیت تغییر کرد.')
        return redirect(role_dashboard(user))

    return render(request, 'accounts/password_change.html', {
        'form': form,
        'forced': request.user.must_change_password,
    })
