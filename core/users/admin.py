# core/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, UserView, ActiveUser

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'

class UserViewInline(admin.StackedInline):
    model = UserView
    can_delete = False
    verbose_name_plural = 'Frontend Settings'

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, UserViewInline)
    list_display = ('username', 'email', 'is_staff', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('username', 'email')
    ordering = ('username',)

admin.site.register(ActiveUser)