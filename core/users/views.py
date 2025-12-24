# --- Django Imports ---
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from djoser.views import TokenCreateView, TokenDestroyView
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from core.users.models import ActiveUser, User, UserProfile, UserView

# Permission Import Safety Check
try:
    from users.permissions import HasAdminPermissions
except ImportError:
    HasAdminPermissions = IsAdminUser

from .serializers import (
    ActiveUserSerializer,
    AdminUserUpdateSerializer,
    ContentTypeSerializer,
    UserGroupsSerializer,
    UserListSerializer,
    UserPasswordChangeSerializer,
    UserProfileCreateSerializer,
    UserProfileDetailedSerializer,
    UserProfileSerializer,
    UserSimpleSerializer,
    UserViewSerializer,
)
from .utils import change_permissions

# ==============================================================================
# 1. AUTHENTICATION OVERRIDES
# ==============================================================================


@method_decorator(csrf_exempt, name='dispatch')
class CsrfExemptTokenCreateView(TokenCreateView):
    pass


@method_decorator(csrf_exempt, name='dispatch')
class CsrfExemptTokenDestroyView(TokenDestroyView):
    pass


# ==============================================================================
# 2. USER PROFILE & MANAGEMENT
# ==============================================================================


class UserInfoView(APIView):
    """
    Get or Update the currently logged-in user's profile.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(operation_id='auth_user_info_retrieve')
    def get(self, request):
        user = request.user
        serializer = UserProfileDetailedSerializer(user, context={'request': request})

        #
        # Make a mutable copy of the data
        response_data = dict(serializer.data)

        # --- FIX: Inject Full Permissions (Groups + Direct Overrides) ---
        # user.get_all_permissions() returns a set of 'app_label.codename' strings.
        # This combines permissions from the user's Groups AND the user_permissions table.
        response_data['permissions'] = list(user.get_all_permissions())

        return Response(response_data)

    @swagger_auto_schema(
        operation_description='Update user profile',
        request_body=UserProfileSerializer,
        responses={
            200: UserProfileDetailedSerializer,
            400: 'Validation Error'
        }
    )
    def post(self, request, *args, **kwargs):
        request_data = request.data.copy()
        request_data['user'] = request.user.pk

        # 1. Handle Profile
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if user_profile:
            profile_serializer = UserProfileSerializer(user_profile, data=request_data, context={'request': request})
        else:
            profile_serializer = UserProfileSerializer(data=request_data, context={'request': request})

        if profile_serializer.is_valid():
            profile_serializer.save()
        else:
            return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 2. Handle User Base
        user_serializer = UserSimpleSerializer(request.user, data=request_data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()

            # Return fresh detailed data
            updated_user = User.objects.get(pk=request.user.pk)
            response_serializer = UserProfileDetailedSerializer(updated_user, context={'request': request})

            # --- FIX: Ensure updated response also has full permissions ---
            response_data = dict(response_serializer.data)
            response_data['permissions'] = list(updated_user.get_all_permissions())

            return Response(response_data, status=status.HTTP_200_OK)

        return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetailViewNoId(APIView):
    permission_classes = [IsAuthenticated, HasAdminPermissions]

    @swagger_auto_schema(operation_id='auth_user_list_all')
    def get(self, request):
        users = User.objects.all().select_related('profile').prefetch_related('groups')
        serializer = UserListSerializer(users, many=True, context={'request': request})
        return Response(serializer.data)

    def handle_teacher_data(self, user, data):
        """ Helper to assign schools/classes to teacher """
        # 1. Try getting from data first
        user_type = data.get('user_type')

        # 2. If not in data, try to fetch from profile
        if not user_type:
            try:
                # Force refresh or direct access to ensure we catch the just-created profile
                if hasattr(user, 'profile'):
                    user_type = user.profile.user_type
            except Exception:
                pass

    @swagger_auto_schema(operation_description='Create user with profile', request_body=UserProfileCreateSerializer)
    def post(self, request, *args, **kwargs):
        request_data = request.data.copy()
        with transaction.atomic():
            # 1. User
            user_serializer = UserSimpleSerializer(data=request_data)
            if user_serializer.is_valid():
                password = request_data.get('password')
                re_password = request_data.get('re_password')
                if password != re_password:
                    return Response({'re_password': 'Passwords do not match'}, status=400)

                created_user = user_serializer.save()
                created_user.set_password(password)
                created_user.save()
            else:
                return Response(user_serializer.errors, status=400)

            # 2. Profile
            request_data['user'] = created_user.id
            profile_serializer = UserProfileSerializer(data=request_data)

            if profile_serializer.is_valid():
                profile_instance = profile_serializer.save()

                # CRITICAL: Ensure request_data has the user_type (in case it was a default value)
                # This ensures handle_teacher_data sees the correct type
                if 'user_type' not in request_data:
                    request_data['user_type'] = profile_instance.user_type
            else:
                # Rollback if profile is invalid
                transaction.set_rollback(True)
                return Response(profile_serializer.errors, status=400)

            # 3. Teacher Data & Permissions
            try:
                change_permissions(created_user, request_data)
                self.handle_teacher_data(created_user, request_data)
            except Exception as e:
                print(f'Error setting extra data: {e}')

            # 4. CRITICAL: Refresh from DB to load reverse relations (Teacher/Profile)
            # This ensures get_user_type in the serializer works correctly
            created_user.refresh_from_db()

            response_serializer = UserProfileDetailedSerializer(created_user, context={'request': request})
            return Response(response_serializer.data, status=201)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated, HasAdminPermissions]

    @swagger_auto_schema(operation_id='auth_user_retrieve_detail')
    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(status=404)
        serializer = UserProfileDetailedSerializer(user, context={'request': request})

        # --- FIX: Inject Full Permissions for Admin View as well ---
        response_data = dict(serializer.data)
        response_data['permissions'] = list(user.get_all_permissions())

        return Response(response_data)

    @swagger_auto_schema(operation_description='Update user info (Admin)', request_body=AdminUserUpdateSerializer)
    def patch(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(status=404)

        serializer = AdminUserUpdateSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()

            # Handle Profile fields manually
            if hasattr(user, 'profile'):
                profile_data = {}
                if 'phone_number' in request.data:
                    profile_data['phone_number'] = request.data['phone_number']

                if profile_data:
                    profile_serializer = UserProfileSerializer(
                        user.profile, data=profile_data, partial=True, context={'request': request}
                    )
                    if profile_serializer.is_valid():
                        profile_serializer.save()

            # Handle Permissions (groups/tables)
            try:
                if any(k in request.data for k in ['tables', 'group', 'groups']):
                    change_permissions(user, request.data)
            except Exception as e:
                print(f'Permission update error: {e}')

            # Return fresh detailed data
            user.refresh_from_db()
            response_serializer = UserProfileDetailedSerializer(user, context={'request': request})

            # --- FIX: Return updated permissions ---
            response_data = dict(response_serializer.data)
            response_data['permissions'] = list(user.get_all_permissions())

            return Response(response_data, status=200)

        return Response(serializer.errors, status=400)


class ChangeUserPasswordView(APIView):
    permission_classes = [IsAuthenticated, HasAdminPermissions]

    @swagger_auto_schema(
        operation_description='User set password',
        request_body=UserPasswordChangeSerializer,
        responses={
            200: 'Accepted',
            400: 'Validation Error'
        }
    )
    def patch(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        request_data = request.data
        password = request_data.get('password')
        re_password = request_data.get('re_password')

        if password != re_password:
            return Response({'re_password': ["The password isn't retyped correctly."]},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password, user=user)
        except ValidationError as err:
            return Response({'password': err}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save()
        return Response({'result': 'Accepted'}, status=status.HTTP_202_ACCEPTED)


# ==============================================================================
# 3. SYSTEM CONFIG VIEWS
# ==============================================================================


class UserViewViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = UserView.objects.all()
    serializer_class = UserViewSerializer
    lookup_field = 'user__id'

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return UserView.objects.all()
        return UserView.objects.filter(user=user)

    def perform_create(self, serializer):
        user_id = self.request.data.get('user')
        if not self.request.user.is_staff and str(user_id) != str(self.request.user.id):
            raise ValidationError('You cannot create views for other users.')
        serializer.save()


class UserGroupsViewSet(ModelViewSet):
    permission_classes = [HasAdminPermissions]
    queryset = Group.objects.all()
    serializer_class = UserGroupsSerializer

    @action(detail=False, methods=['get'], url_path='available-permissions')
    def get_all_permissions(self, request):
        ignored_apps = ['admin', 'contenttypes', 'sessions', 'authtoken', 'sites']

        perms = Permission.objects.select_related('content_type')\
            .exclude(content_type__app_label__in=ignored_apps)\
            .order_by('content_type__model', 'name')

        grouped_perms = {}
        for p in perms:
            model_name = p.content_type.model.replace('_', ' ').title()
            if model_name not in grouped_perms:
                grouped_perms[model_name] = []
            grouped_perms[model_name].append({'id': p.id, 'name': p.name, 'codename': p.codename})

        return Response(grouped_perms)


class DbTablesViewSet(ReadOnlyModelViewSet):
    permission_classes = [HasAdminPermissions]
    serializer_class = ContentTypeSerializer

    def get_queryset(self):
        excluded_apps = [
            'contenttypes', 'sessions', 'messages', 'staticfiles', 'token_blacklist', 'authtoken', 'simple_history',
            'sites'
        ]

        qs = ContentType.objects.exclude(app_label__in=excluded_apps)
        return qs.exclude(model__istartswith='historical')


# ==============================================================================
# 4. MONITORING
# ==============================================================================


@api_view(['GET'])
@permission_classes([AllowAny])
@swagger_auto_schema(responses={200: openapi.Response('OK')})
def heartbeat(request):
    if request.user.is_authenticated:
        ActiveUser.objects.update_or_create(user=request.user, defaults={'last_seen': timezone.now()})
        return Response({'status': 'heartbeat OK'}, status=status.HTTP_200_OK)
    return Response({'status': 'guest'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasAdminPermissions])
@swagger_auto_schema(responses={200: ActiveUserSerializer(many=True)})
def get_online_users(request):
    online_users = ActiveUser.objects.select_related('user').all()
    serializer = ActiveUserSerializer(online_users, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
