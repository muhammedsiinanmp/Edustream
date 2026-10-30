from django import forms
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.password_validation import validate_password
from .models import Student

PHOTO_INPUT_ATTRS = {
    'class': 'form-control',
    'accept': 'image/jpeg,image/png,image/webp',
}


class PasswordRulesMixin:
    """Applies AUTH_PASSWORD_VALIDATORS to a form's `password` field."""

    def check_password_rules(self, cleaned_data):
        password = cleaned_data.get('password')
        if not password:
            return
        candidate = Student(
            username=cleaned_data.get('username', ''),
            email=cleaned_data.get('email', ''),
        )
        try:
            validate_password(password, candidate)
        except ValidationError as error:
            self.add_error('password', error)


class UniqueEmailMixin:
    """Lowercases `email` and rejects addresses taken in any letter case."""

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        others = Student.objects.exclude(pk=self.instance.pk)
        if others.filter(email__iexact=email).exists():
            raise ValidationError('Email already exists')
        return email


class StudentRegisterForm(UniqueEmailMixin, PasswordRulesMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class':'form_control'})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class':'form_control'})
    )

    class Meta:
        model = Student
        fields = [
            'username','email','phone','dob','dept',
            'profile_pic','age','password'
        ]

        widgets ={
            'username':forms.TextInput(attrs={'class': 'form-control'}),
            'email':forms.EmailInput(attrs={'class': 'form-control'}),
            'phone':forms.TextInput(attrs={'class': 'form-control'}),
            'dob':forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'dept':forms.Select(attrs={'class': 'form-control'}),
            'profile_pic':forms.FileInput(attrs=PHOTO_INPUT_ATTRS),
            'age':forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('password') != cleaned_data.get('confirm_password'):
            raise ValidationError('Passwords does not match')
        self.check_password_rules(cleaned_data)
        return cleaned_data
    
    def save(self,commit=True):
        student = super().save(commit=False)
        student.password = make_password(self.cleaned_data['password'])
        if commit:
            student.save()
        return student
    
class LoginForm(forms.Form):
    username = forms.CharField(
        widget = forms.TextInput(attrs={'class':'form-control'})
    )
    password = forms.CharField(
        widget = forms.PasswordInput(attrs={'class':'form-control'})
    )


class StudentProfileUpdateForm(UniqueEmailMixin, UserChangeForm):
    password = None  # hide password field

    class Meta:
        model = Student
        fields = [
            'email',
            'phone',
            'dob',
            'age',
            'dept',
            'profile_pic',
        ]
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control'}),
            'dept': forms.Select(attrs={'class': 'form-select'}),
            'profile_pic': forms.FileInput(attrs=PHOTO_INPUT_ATTRS),
        }
