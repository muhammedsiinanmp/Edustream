from django.db import models
from django.contrib.auth.models import AbstractUser
from principal.models import Department

# Create your models here.

class Student(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15,blank=True)
    dob = models.DateField(null= True,blank=True)
    dept = models.ForeignKey(Department,on_delete=models.SET_NULL,null=True,blank=True)
    profile_pic = models.ImageField(upload_to='profiles/',null=True,blank=True)
    age = models.IntegerField(null=True,blank=True)
    year_of_admission = models.IntegerField(null=True,blank=True)
    rollno = models.IntegerField(unique=True,null=True,blank=True)

    def __str__(self):
        return self.username
    
class CoursePurchase(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey('principal.AddOnCourse', on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('completed', 'Completed'),
            ('rejected', 'Rejected')
        ],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student} - {self.course}"
