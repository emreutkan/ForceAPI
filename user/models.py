from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
import uuid
from core.models import TimestampedModel
from django.db.models.signals import post_save
from django.dispatch import receiver

## Basic info about the models

## Model.model = default django model class
## TimestampedModel = Model.model + created_at and updated_at fields

class CustomUserManager(BaseUserManager):
    """
    Custom user manager that overrides the create_user and create_superuser methods to use the email field for authentication.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email) ## This is the normalize_email() method from Django's BaseUserManager. It normalizes the email address by converting it to lowercase and removing whitespace.
        user = self.model(email=email, **extra_fields)
        user.set_password(password) ## That set_password() method is from Django's AbstractUser. It automatically hashes the password using Django's default password hasher (PBKDF2 with SHA256 by default).
        user.save(using=self._db) ## This is the save() method from Django's Model. It saves the user to the database.
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True) ## This is the is_staff field from Django's AbstractUser. It is a boolean field that indicates whether the user is a staff member.
        extra_fields.setdefault('is_superuser', True) ## This is the is_superuser field from Django's AbstractUser. It is a boolean field that indicates whether the user is a superuser.
        return self.create_user(email, password, **extra_fields) 

## AbstractUser = User model template that includes username, password, first_name, last_name, email, is_active, is_staff, is_superuser, last_login, date_joined fields
class CustomUser(AbstractUser, TimestampedModel):
    """
    Custom user with email login and basic verification state.
    Inherits Django auth fields plus timestamp fields.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True) ## abstract user already has an email field, but we need to make it unique so we override it
    is_verified = models.BooleanField(default=False)
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')], default='male', help_text="Gender for body fat calculations and recommendations")
    
    # PRO subscription fields
    is_pro = models.BooleanField(default=False, help_text="Whether user has active PRO subscription")
    pro_until = models.DateTimeField(null=True, blank=True, help_text="PRO subscription expiration date")
    subscription_id = models.CharField(max_length=255, blank=True, help_text="Payment provider subscription ID (Stripe, RevenueCat, etc.)")
    
    # Free trial fields
    trial_until = models.DateTimeField(null=True, blank=True, help_text="Free trial expiration date")

    # Developer accounts (e.g. bypass rate limiting)
    is_developer = models.BooleanField(default=False, help_text="Developer accounts bypass rate limiting")

    # Supabase auth
    supabase_uid = models.UUIDField(unique=True, null=True, blank=True, help_text="Supabase user UUID (sub claim in JWT)")

    USERNAME_FIELD = 'email'  ## this tells Django that the email field is used for authentication instead of the username field
    REQUIRED_FIELDS = []
    
    objects = CustomUserManager() ## This is the custom user manager that we created above. It is used to create and manage users.

class UserProfile(TimestampedModel):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    body_weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Body weight in kg for calorie calculations")
    height = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Height in cm")

class WeightHistory(TimestampedModel):
    """Track user weight over time"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='weight_history')
    weight = models.DecimalField(max_digits=5, decimal_places=2, help_text="Weight in kg")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Weight Histories'
    
    def __str__(self):
        return f"{self.user.email} - {self.created_at.date()} - {self.weight}kg"

class SecurityStatus(TimestampedModel):
    """
    Security status for user including login attempt tracking and lockout functionality.
    """
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

class Preferences(TimestampedModel):
    """
    User preferences including auto warmup settings and rest time. Rest time is the time in seconds between sets.
    """
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    auto_warmup_set = models.BooleanField(default=False)
    rest_time = models.PositiveIntegerField(default=90)
    units = models.CharField(max_length=10, choices=[('metric', 'Metric'), ('imperial', 'Imperial')], default='metric')

@receiver(post_save, sender=CustomUser)
# This function creates the user related records when a new user is created.
# Current Behavior:  manual registration (RegisterSerializer) does not create these related objects.
# Social Login Behavior: Social login also won't create them automatically.
# Solution: Create a receiver function that creates the user related records when a new user is created.
def create_user_related_records(sender, instance, created, **kwargs):
    if created:
        Preferences.objects.create(user=instance)
        UserProfile.objects.create(user=instance)
        SecurityStatus.objects.create(user=instance)