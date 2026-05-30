from django import forms
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