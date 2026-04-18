from django import forms
from django.contrib.auth.forms import AuthenticationForm

class LoginForm(AuthenticationForm):
    username = forms.CharField(label_suffix='', widget=forms.TextInput(attrs={
        'class': 'form-control'
    }))
    password = forms.CharField(label_suffix='', label='رمز عبور', widget=forms.PasswordInput(attrs={
        'class': 'form-control'
    }))