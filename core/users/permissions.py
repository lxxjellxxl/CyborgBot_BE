from django.contrib.auth.models import AnonymousUser
from rest_framework.permissions import BasePermission
from users.models import UserView


class HasModelPermissionOrAdmin(BasePermission):
    """
    Custom permission to check model-level permissions or if the user is an admin.
    """
    def has_permission(self, request, view):
        # Allow access if the user is an admin
        if request.user.is_superuser or request.user.is_staff:
            return True
        if request.user.user_view.is_admin:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        user_view = UserView.objects.filter(user=request.user).first()
        if user_view and user_view.is_admin:
            return True

        # Check model-level permission based on the action
        model_name = view.queryset.model._meta.model_name
        app_name = view.queryset.model._meta.app_label

        if view.action == 'export':
            required_permission = f'{app_name}.export_{model_name}'
        elif view.action in ['list', 'retrieve', 'get_all', 'get_between', 'get_similar_products']:
            required_permission = f'{app_name}.view_{model_name}'
        elif view.action == 'create' or view.action == 'create_all':
            required_permission = f'{app_name}.add_{model_name}'
        elif view.action in ['update', 'partial_update'] or view.action == 'create_all':
            required_permission = f'{app_name}.change_{model_name}'
        elif view.action == 'destroy':
            required_permission = f'{app_name}.delete_{model_name}'
        else:
            # Fallback if action is not recognized
            print('unknown action', view.action)
            return False
        return request.user.has_perm(required_permission)


class HasAdminPermissions(BasePermission):
    """
    If user is admin based on the extended table of userview, allow access
    """
    def has_permission(self, request, view):
        # Allow access if the user is an admin
        print('checking permissions', view)
        return request.user.is_superuser or request.user.is_staff or request.user.user_view.is_admin
