from django.shortcuts import render, redirect
# from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.urls import reverse

from staff.decorators import teacher_required

from .avatars import process_avatar
from .forms import LoginForm, PasswordChangeForm, ProfileForm, ProfilePasswordChangeForm
from .profile import password_rules, teacher_overview
from .sessions import (
    can_end_sessions,
    end_other_sessions,
    recent_logins,
    update_session_auth_hash_tracked,
)
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
        update_session_auth_hash_tracked(request, user)  # stay logged in
        messages.success(request, 'رمز عبور شما با موفقیت تغییر کرد.')
        return redirect(role_dashboard(user))

    return render(request, 'accounts/password_change.html', {
        'form': form,
        'forced': request.user.must_change_password,
    })


# ----------------------------------------------------------------------
# Teacher profile & settings
# ----------------------------------------------------------------------

PROFILE_TABS = (
    ('personal', 'اطلاعات شخصی'),
    ('security', 'امنیت'),
)


def _profile_url(tab):
    return f"{reverse('accounts:profile')}?tab={tab}"


def _fa(number):
    return str(number).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


def _save_profile(form):
    """Saves the fields and swaps the picture; the old file goes once the new row is committed."""

    user = form.save(commit=False)
    old_name = user.avatar.name if user.avatar else None
    uploaded = form.cleaned_data.get('avatar')

    with transaction.atomic():
        if uploaded:
            picture = process_avatar(uploaded)
            user.avatar.save(picture.name, picture, save=False)
        elif form.cleaned_data.get('remove_avatar'):
            user.avatar = None
        user.save()

        new_name = user.avatar.name if user.avatar else None
        if old_name and old_name != new_name:
            storage = user._meta.get_field('avatar').storage
            transaction.on_commit(lambda: storage.delete(old_name))


@teacher_required
def profile(request):
    """
    «پروفایل و تنظیمات»: one page, two tabs (?tab=personal|security), so a
    form with errors comes back on its own tab. Every POST names its form
    in ``action``; a success redirects (PRG) with a toast.
    """

    user = request.user
    tab = request.GET.get('tab')
    if tab not in dict(PROFILE_TABS):
        tab = 'personal'

    profile_form = ProfileForm(instance=user)
    password_form = ProfilePasswordChangeForm(user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'personal':
            tab = 'personal'
            profile_form = ProfileForm(request.POST, request.FILES, instance=user)
            if profile_form.is_valid():
                _save_profile(profile_form)
                messages.success(request, 'اطلاعات شما ذخیره شد.')
                return redirect(_profile_url('personal'))
            # Validation wrote the rejected values onto request.user: put
            # the saved ones back for the header and the top bar.
            user.refresh_from_db()

        elif action == 'password':
            tab = 'security'
            password_form = ProfilePasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash_tracked(request, user)  # this device stays signed in
                if can_end_sessions():
                    end_other_sessions(request)  # already invalid by the new hash; tidy up
                messages.success(request, 'رمز عبور تغییر کرد. در دستگاه‌های دیگر باید دوباره وارد شوید.')
                return redirect(_profile_url('security'))

        elif action == 'end_sessions' and can_end_sessions():
            ended = end_other_sessions(request)
            if ended:
                messages.success(request, f'از {_fa(ended)} دستگاه دیگر خارج شدید.')
            else:
                messages.info(request, 'دستگاه دیگری وارد حساب شما نبود.')
            return redirect(_profile_url('security'))

        else:
            return redirect(_profile_url(tab))

    return render(request, 'accounts/profile.html', {
        'tabs': PROFILE_TABS,
        'tab': tab,
        'profile_form': profile_form,
        'password_form': password_form,
        'password_rules': password_rules(),
        'overview': teacher_overview(request.teacher_profile),
        'staff': request.teacher_profile.staff,
        'logins': recent_logins(user),
        'current_session_key': request.session.session_key,
        'can_end_sessions': can_end_sessions(),
    })
