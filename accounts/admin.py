from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import path

from .forms import UserImportForm
from .models import User
from .user_import import FileRejected, ROLE_COLUMNS, ROLE_LABELS, run_import
from .user_import_template import build_template
from django.contrib.auth.admin import UserAdmin

# Register your models here.

@admin.register(User)
class CustomUserAdmin(UserAdmin):

    model = User

    list_display = ['get_full_name', 'role', 'national_code', 'phone_number']

    search_fields = UserAdmin.search_fields + ('national_code',)

    fieldsets = UserAdmin.fieldsets + (
        (
            'اطلاعات اضافی',
            {
                'fields':(
                    'role',
                    'national_code',
                    'phone_number',
                    'avatar',
                    'must_change_password',
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'اطلاعات اضافی',
            {
                'fields':(
                    'role',
                    'national_code',
                    'phone_number',
                    'avatar'
                )
            },
        ),
    )

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    get_full_name.short_description = 'نام و نام خانوادگی'

    # ------------------------------------------------------------------
    # «ورود گروهی از اکسل» (accounts/user_import.py)
    # ------------------------------------------------------------------

    def get_urls(self):
        return [
            path(
                'import/',
                self.admin_site.admin_view(self.import_view),
                name='accounts_user_import',
            ),
            path(
                'import/template/<str:role>/',
                self.admin_site.admin_view(self.import_template_view),
                name='accounts_user_import_template',
            ),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), 'can_import': self.has_add_permission(request)}
        return super().changelist_view(request, extra_context=extra_context)

    def _check_import_permission(self, request):
        # Superusers, or anyone with accounts.add_user.
        if not self.has_add_permission(request):
            raise PermissionDenied

    def import_view(self, request):
        self._check_import_permission(request)

        form = UserImportForm(request.POST or None, request.FILES or None)
        context = {
            **self.admin_site.each_context(request),
            'opts': self.opts,
            'title': 'ورود گروهی کاربران از اکسل',
            'form': form,
            'roles': [
                {'value': role, 'label': label, 'columns': ROLE_COLUMNS[role]}
                for role, label in ROLE_LABELS.items()
            ],
        }

        if request.method == 'POST' and form.is_valid():
            role = form.cleaned_data['role']
            try:
                result = run_import(form.cleaned_data['file'], role, request.user)
            except FileRejected as exc:
                context['file_error'] = str(exc)
            else:
                context.update({
                    'title': 'نتیجه‌ی ورود گروهی',
                    'result': result,
                    'role_label': ROLE_LABELS[role],
                })
                return render(request, 'admin/accounts/user/import_result.html', context)

        return render(request, 'admin/accounts/user/import.html', context)

    def import_template_view(self, request, role):
        self._check_import_permission(request)
        if role not in ROLE_COLUMNS:
            raise Http404

        response = HttpResponse(
            build_template(role, request.user),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="user-import-{role}.xlsx"'
        return response
