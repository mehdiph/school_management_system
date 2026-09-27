from django import forms
from django.core.validators import FileExtensionValidator
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.forms import AuthenticationForm
from .models import User

class LoginForm(AuthenticationForm):
    username = forms.CharField(label_suffix='', widget=forms.TextInput(attrs={
        'class': 'form-control'
    }))
    role = forms.ChoiceField(label_suffix='', label='نقش', choices=User.Roles.choices, widget=forms.Select(attrs={
        'class': 'form-control'
    }))
    password = forms.CharField(label_suffix='', label='رمز عبور', widget=forms.PasswordInput(attrs={
        'class': 'form-control'
    }))

class PasswordChangeForm(auth_forms.PasswordChangeForm):
    """
    Django's password change (old password + new twice, all
    AUTH_PASSWORD_VALIDATORS), and the one place that clears
    ``must_change_password``: only after the new password is saved.
    ``User.set_password`` deliberately does not touch the flag, because
    the Excel import calls it too.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
            field.label_suffix = ''

    def save(self, commit=True):
        user = super().save(commit=False)
        user.must_change_password = False
        if commit:
            user.save()
        return user


class UserImportForm(forms.Form):
    role = forms.ChoiceField(label='نقش', choices=())
    file = forms.FileField(
        label='فایل اکسل',
        validators=[FileExtensionValidator(['xlsx'], message='فقط فایل ‎.xlsx‎ پذیرفته می‌شود.')],
        widget=forms.ClearableFileInput(attrs={
            'accept': '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }),
        help_text='حداکثر ۵ مگابایت و ۲۰۰۰ ردیف.',
    )

    def __init__(self, *args, **kwargs):
        from .user_import import ROLE_LABELS

        super().__init__(*args, **kwargs)
        self.fields['role'].choices = list(ROLE_LABELS.items())

    def clean_file(self):
        from .user_import import MAX_FILE_SIZE

        uploaded = self.cleaned_data['file']
        if uploaded.size > MAX_FILE_SIZE:
            raise forms.ValidationError('حجم فایل نباید بیشتر از ۵ مگابایت باشد.')
        return uploaded
