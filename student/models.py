from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models.functions import Lower
from principal.models import Department
from .photos import reencode_profile_photo, validate_profile_photo
from .validators import validate_not_future, validate_phone

# Create your models here.

class Student(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15,blank=True,validators=[validate_phone])
    dob = models.DateField(null= True,blank=True,validators=[validate_not_future])
    dept = models.ForeignKey(Department,on_delete=models.SET_NULL,null=True,blank=True)
    profile_pic = models.ImageField(
        upload_to='profiles/',null=True,blank=True,
        validators=[validate_profile_photo],
    )
    age = models.IntegerField(
        null=True,blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
    )
    year_of_admission = models.IntegerField(null=True,blank=True)
    rollno = models.IntegerField(unique=True,null=True,blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower('email'),
                name='student_email_ci_unique',
                violation_error_message='Email already exists',
            ),
        ]

    def __str__(self):
        return self.username

    def clean(self):
        super().clean()
        self.email = self.email.lower()

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        # Only a new upload is uncommitted; a stored photo is left as it is.
        if self.profile_pic and not self.profile_pic._committed:
            name, content = reencode_profile_photo(self.profile_pic)
            self.profile_pic.save(name, content, save=False)
        super().save(*args, **kwargs)
    
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
\
    def __str__(self):
        return f"{self.student} - {self.course}"
