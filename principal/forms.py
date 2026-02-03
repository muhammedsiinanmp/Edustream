from django import forms 
from student.models import Student
from .models import Department,AddOnCourse
from django.contrib.auth.hashers import make_password

class AdminStudentForm(forms.ModelForm):
    password= forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Student
        fields = [
            'username','email','phone','dob',
            'dept','age','rollno','password'
        ]

    def save(self,commit=True):
        student = super().save(commit=False)
        student.password = make_password(self.cleaned_data['password'])
        if commit:
            student.save()
        return student
    
class AdminEditStudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['rollno','dept']

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = '__all__'

class AddOnCourseForm(forms.ModelForm):
    class Meta:
        model = AddOnCourse
        fields = ['name', 'description', 'price', 'status']