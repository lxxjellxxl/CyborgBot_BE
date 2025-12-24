# core/users/models.py
from datetime import timedelta
from dirtyfields import DirtyFieldsMixin
from django.contrib.auth.models import (
    AbstractBaseUser, 
    BaseUserManager, 
    PermissionsMixin
)
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .utils import compress_image

class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **kwargs):
        if not username:
            raise ValueError(_('Users must have a username'))

        user = self.model(username=username, **kwargs)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **kwargs):
        kwargs.setdefault('is_staff', True)
        kwargs.setdefault('is_superuser', True)

        if kwargs.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if kwargs.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(username, password, **kwargs)


class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(max_length=255, unique=True, blank=True, null=True)
    
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'username'

    def __str__(self):
        return self.username


class UserView(models.Model):
    """
    Controls specific permissions for pages/reports in the frontend (Quasar).
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='user_view', verbose_name=_('User')
    )
    pages = models.TextField(blank=True, default='', verbose_name=_('Pages'))
    reports = models.TextField(blank=True, default='', verbose_name=_('Reports'))
    tables = models.TextField(blank=True, default='', verbose_name=_('Tables'))
    
    report_days = models.PositiveSmallIntegerField(default=7, verbose_name=_('Report Days'))
    is_admin = models.BooleanField(default=False, verbose_name=_('Is Admin'))

    class Meta:
        verbose_name = _('User View')
        verbose_name_plural = _('User Views')

    def __str__(self):
        return self.user.username


class UserProfile(DirtyFieldsMixin, models.Model):
    class UserType(models.TextChoices):
        TEACHER = 'TEACHER', _('Teacher')
        SUPERVISOR = 'SUPERVISOR', _('Supervisor')
        ADMIN = 'ADMIN', _('Admin')
        TRADER = 'TRADER', _('Trader')  # Added TRADER type for your specific needs

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile', verbose_name=_('User')
    )
    user_type = models.CharField(
        max_length=20, choices=UserType.choices, default=UserType.TRADER, verbose_name=_('User Type')
    )
    phone_number = models.CharField(max_length=15, blank=True, null=True, verbose_name=_('Phone'))
    address = models.CharField(max_length=200, blank=True, null=True, verbose_name=_('Address'))
    about = models.TextField(max_length=500, blank=True, null=True, verbose_name=_('About'))
    photo = models.ImageField(upload_to='profile/', blank=True, null=True, verbose_name=_('Photo'))

    class Meta:
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')

    def __str__(self):
        return self.user.username

    def delete_old_image(self):
        if not self.pk:
            return
        try:
            old_instance = UserProfile.objects.get(pk=self.pk)
            if old_instance.photo and old_instance.photo != self.photo:
                old_instance.photo.delete(save=False)
        except UserProfile.DoesNotExist:
            pass

    def save(self, *args, **kwargs):
        self.delete_old_image()
        
        # Compress image if it's new or changed
        if 'photo' in self.get_dirty_fields() or not self.pk:
            if self.photo:
                try:
                    compressed = compress_image(self.photo, quality=20)
                    self.photo.save(
                        self.photo.name, 
                        ContentFile(compressed.getvalue()), 
                        save=False
                    )
                except Exception:
                    # Fallback if compression fails (e.g. invalid image format)
                    pass

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.photo:
            self.photo.delete(save=False)
        super().delete(*args, **kwargs)


class ActiveUser(models.Model):
    """
    Tracks when the user was last seen to show Online/Offline status.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='last_seen', verbose_name=_('User')
    )
    last_seen = models.DateTimeField(default=timezone.now, verbose_name=_('Last Seen'))

    class Meta:
        verbose_name = _('Active User')
        verbose_name_plural = _('Active Users')

    @property
    def online(self):
        if not self.last_seen:
            return False
        return timezone.now() - self.last_seen < timedelta(minutes=1)

    def __str__(self):
        return f'{self.user.username} ({ "Online" if self.online else "Offline" })'