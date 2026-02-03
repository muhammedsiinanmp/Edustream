from django import forms
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import UserChangeForm
from .models import Student

class StudentRegisterForm(forms.ModelForm):
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
            'dob':forms.DateInput(attrs={'class': 'form-control'}),
            'dept':forms.Select(attrs={'class': 'form-control'}),
            'profile_pic':forms.FileInput(attrs={'class': 'form-control'}),
            'age':forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Student.objects.filter(email = email).exists():
            raise ValidationError('Email already exists')
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('password') != cleaned_data.get('confirm_password'):
            raise ValidationError('Passwords does not match')
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
        widget = forms.TextInput(attrs={'class':'form-control'})
    )


class StudentProfileUpdateForm(UserChangeForm):
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
            'profile_pic': forms.FileInput(attrs={'class': 'form-control'}),
        }
