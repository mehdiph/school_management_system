from django.contrib import admin
from .models import User
from django.contrib.auth.admin import UserAdmin

# Register your models here.

@admin.register(User)
class CustomUserAdmin(UserAdmin):

    model = User

    list_display = ['get_full_name', 'role', 'phone_number']

    fieldsets = UserAdmin.fieldsets + (
        (
            'اطلاعات اضافی',
            {
                'fields':(
                    'role',
                    'phone_number',
                    'avatar'
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
                    'phone_number',
                    'avatar'
                )
            },
        ),
    )

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    get_full_name.short_description = 'نام و نام خانوادگی'