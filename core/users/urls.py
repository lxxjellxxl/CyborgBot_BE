from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ChangeUserPasswordView,
    CsrfExemptTokenCreateView,
    CsrfExemptTokenDestroyView,
    DbTablesViewSet,
    UserDetailView,
    UserDetailViewNoId,
    UserGroupsViewSet,
    UserInfoView,
    UserViewViewSet,
    get_online_users,
    heartbeat,
)

app_name = 'users'

router = DefaultRouter()
# Dashboard configurations
router.register(r'preferences', UserViewViewSet, basename='user-preferences')
# Permission & Group Management
router.register(r'groups', UserGroupsViewSet, basename='user-groups')
router.register(r'db-tables', DbTablesViewSet, basename='db-tables')

urlpatterns = [
    # --- Custom Auth Overrides ---
    # We map these to allow specific behavior (like CSRF exempt) if needed
    path('token/login/', CsrfExemptTokenCreateView.as_view(), name='login'),
    path('token/logout/', CsrfExemptTokenDestroyView.as_view(), name='logout'),

    # --- Profile (Logged in User) ---
    path('me/', UserInfoView.as_view(), name='user-info'),

    # --- User Management (Admin Dashboard) ---
    path('admin/users/', UserDetailViewNoId.as_view(), name='admin-user-list-create'),
    path('admin/users/<int:pk>/', UserDetailView.as_view(), name='admin-user-detail'),
    path('admin/users/<int:pk>/password/', ChangeUserPasswordView.as_view(), name='admin-user-password'),

    # --- Monitoring ---
    path('heartbeat/', heartbeat, name='heartbeat'),
    path('online-users/', get_online_users, name='online-users'),

    # --- Router Endpoints (Groups, Preferences, Tables) ---
    path('', include(router.urls)),
]
