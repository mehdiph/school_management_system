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


# ----------------------------------------------------------------------
# Teacher profile (accounts.views.profile)
# ----------------------------------------------------------------------

class AriaErrorsMixin:
    """Marks fields with errors aria-invalid and points them at their message (id "<field id>-error")."""

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                attrs['aria-invalid'] = 'true'
                attrs['aria-describedby'] = f'{self[name].auto_id}-error'


class ProfileForm(AriaErrorsMixin, forms.ModelForm):
    """
    What a teacher may change about themselves: picture, mobile, email.
    Name, username, national code, personnel code stay with the admin.
    """

    avatar = forms.FileField(
        label='تصویر پروفایل',
        required=False,
        widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}),
    )
    remove_avatar = forms.BooleanField(label='حذف تصویر', required=False)

    class Meta:
        model = User
        fields = ['phone_number', 'email']
        labels = {
            'phone_number': 'شماره موبایل',
            'email': 'ایمیل',
        }
        error_messages = {
            'phone_number': {'required': 'شماره موبایل را وارد کنید.'},
            'email': {'invalid': 'ایمیل معتبر نیست؛ مثل name@example.com.'},
        }
        widgets = {
            'phone_number': forms.TextInput(attrs={
                'inputmode': 'tel', 'autocomplete': 'tel', 'dir': 'ltr', 'placeholder': '09xxxxxxxxx',
            }),
            'email': forms.EmailInput(attrs={
                'autocomplete': 'email', 'dir': 'ltr', 'placeholder': 'name@example.com',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone_number'].required = True
        self.fields['email'].required = False
        for name in ('phone_number', 'email'):
            self.fields[name].widget.attrs['class'] = 'ui-input ui-input--ltr'

    def clean_phone_number(self):
        from .validators import normalize_mobile, validate_mobile

        value = normalize_mobile(self.cleaned_data.get('phone_number'))
        validate_mobile(value)
        return value

    def clean_email(self):
        return (self.cleaned_data.get('email') or '').strip().lower()

    def clean_avatar(self):
        from .avatars import validate_avatar

        uploaded = self.cleaned_data.get('avatar')
        if uploaded:
            validate_avatar(uploaded)
        return uploaded


#: Persian text for Django's password validators, by error code. Django's
#: own Persian catalogue leaves some of these in English and says
#: «گذرواژه» where this project says «رمز عبور».
PASSWORD_ERROR_MESSAGES = {
    'password_too_short': 'رمز عبور باید دست‌کم {min_length} نویسه باشد.',
    'password_too_common': 'این رمز عبور بیش از حد رایج است.',
    'password_entirely_numeric': 'رمز عبور نباید فقط از عدد تشکیل شده باشد.',
    'password_too_similar': 'رمز عبور به اطلاعات حساب شما (مثل نام یا نام کاربری) بیش از حد شبیه است.',
}


class ProfilePasswordChangeForm(AriaErrorsMixin, PasswordChangeForm):
    """PasswordChangeForm (clears must_change_password) with Persian labels and errors."""

    error_messages = {
        'password_mismatch': 'تکرار رمز عبور با رمز عبور جدید یکسان نیست.',
        'password_incorrect': 'رمز عبور فعلی درست نیست.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'رمز عبور فعلی'
        self.fields['new_password1'].label = 'رمز عبور جدید'
        self.fields['new_password2'].label = 'تکرار رمز عبور جدید'
        self.fields['old_password'].widget.attrs.pop('autofocus', None)
        for field in self.fields.values():
            field.error_messages['required'] = 'این فیلد را پر کنید.'
            field.widget.attrs['class'] = 'ui-input ui-input--ltr'
            field.widget.attrs['dir'] = 'ltr'

    def validate_password_for_user(self, user, password_field_name='password2'):
        from django.contrib.auth import password_validation

        password = self.cleaned_data.get(password_field_name)
        if not password:
            return
        try:
            password_validation.validate_password(password, user)
        except forms.ValidationError as error:
            for item in error.error_list:
                template = PASSWORD_ERROR_MESSAGES.get(item.code)
                if template:
                    params = {
                        key: _persian_digits(value)
                        for key, value in (item.params or {}).items()
                    }
                    item = forms.ValidationError(template.format(**params), code=item.code)
                self.add_error(password_field_name, item)


def _persian_digits(value):
    return str(value).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
