import json

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

# Ensure this import path matches your folder name (managment vs management)
from core.users.models import ActiveUser, User, UserProfile, UserView

# ==============================================================================
# 1. HELPER SERIALIZERS
# ==============================================================================


class ContentTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for Database Tables (ContentTypes)
    """
    name = serializers.SerializerMethodField()

    class Meta:
        model = ContentType
        fields = ['id', 'app_label', 'model', 'name']

    def get_name(self, obj):
        # Returns "app.model" (e.g., "management.student")
        return f'{obj.app_label}.{obj.model}'


class PermissionSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename']


# ==============================================================================
# 2. GROUP SERIALIZER
# ==============================================================================


class UserGroupsSerializer(serializers.ModelSerializer):
    # WRITE: Accepts list of Permission IDs (e.g., [1, 5, 9])
    permissions = serializers.PrimaryKeyRelatedField(many=True, queryset=Permission.objects.all(), required=False)

    # READ: Shows detailed permission objects
    permissions_details = PermissionSimpleSerializer(source='permissions', many=True, read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permissions_details']


# ==============================================================================
# 3. USER CONFIGURATION (UserView) - THE CRITICAL FIX
# ==============================================================================


class UserViewSerializer(serializers.ModelSerializer):
    """
    Serializer for User Dashboard Preferences.
    CRITICAL FIX: Handles conversion between API (JSON) and DB (TextField).
    """
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    # 1. API expects JSON (Array/Object), not String
    pages = serializers.JSONField(required=False, initial=list)
    reports = serializers.JSONField(required=False, initial=list)
    tables = serializers.JSONField(required=False, initial=dict)

    class Meta:
        model = UserView
        fields = '__all__'

    def to_representation(self, instance):
        """
        READ: Convert DB String -> API JSON
        When sending data to Frontend
        """
        ret = super().to_representation(instance)

        json_fields = ['pages', 'reports', 'tables']

        for field in json_fields:
            val = ret.get(field)
            default = {} if field == 'tables' else []

            if isinstance(val, str):
                try:
                    # Convert string from DB to JSON object
                    ret[field] = json.loads(val) if val else default
                except (json.JSONDecodeError, TypeError):
                    ret[field] = default
            elif val is None:
                ret[field] = default

        return ret

    def validate(self, attrs):
        """
        WRITE: Convert API JSON -> DB String
        Before saving to Database
        """
        json_fields = ['pages', 'reports', 'tables']

        for field in json_fields:
            if field in attrs:
                value = attrs[field]
                # If it's a list or dict, dump it to string for the TextField
                if isinstance(value, (list, dict)):
                    attrs[field] = json.dumps(value)
                # If it's already a string, ensure it's valid JSON
                elif isinstance(value, str):
                    try:
                        json.loads(value)  # Validation check
                    except json.JSONDecodeError:
                        # Fallback: Treat as raw string or empty list
                        attrs[field] = '[]' if field != 'tables' else '{}'

        return attrs


# ==============================================================================
# 4. USER PROFILE & DETAILS
# ==============================================================================

class UserProfileSerializer(serializers.ModelSerializer):
    photo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = UserProfile
        fields = ['user', 'user_type', 'phone_number', 'address', 'about', 'photo']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.photo:
            request = self.context.get('request')
            if request:
                ret['photo'] = request.build_absolute_uri(instance.photo.url)
        return ret


class UserSimpleSerializer(serializers.ModelSerializer):
    """ Used for creation/updates of base User model """
    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_superuser', 'is_staff', 'last_login'
        )
        read_only_fields = ['last_login']


class UserProfileCreateSerializer(serializers.Serializer):
    """
    Combined serializer for creating User + Profile in one go
    """
    username = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    re_password = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)

    # Profile fields
    user_type = serializers.ChoiceField(choices=UserProfile.UserType.choices, default=UserProfile.UserType.TEACHER)
    phone_number = serializers.CharField(required=False)
    address = serializers.CharField(required=False)
    about = serializers.CharField(required=False)
    photo = serializers.ImageField(required=False)

    # Permissions / Config
    group = serializers.IntegerField(required=False, allow_null=True)
    tables = serializers.JSONField(required=False)


class UserProfileDetailedSerializer(serializers.ModelSerializer):
    """
    Full Data: User + Profile + Group + Permissions + View Config
    """
    profile = UserProfileSerializer(read_only=True)

    # Computed Fields
    user_type = serializers.SerializerMethodField()

    user_view = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser',
            'last_login', 'user_type', 'profile',
            'user_view', 'group', 'roles', 'permissions'
        ]

    def get_user_type(self, obj):
        """
        Determines the effective user type based on hierarchy:
        1. Superuser -> 'ADMIN'
        2. Has Teacher Profile -> 'TEACHER'
        3. Profile String -> 'STUDENT'/'PARENT'/etc.
        4. Default -> 'USER'
        """
        # 1. Highest Priority: Admin
        if obj.is_superuser:
            return 'ADMIN'
        # 4. Fallback
        return 'USER'
    
    def get_user_view(self, obj):
        # Use the smart serializer to get parsed JSON
        if hasattr(obj, 'user_view'):
            return UserViewSerializer(obj.user_view).data
        return None

    def get_group(self, obj):
        first = obj.groups.first()
        return first.id if first else None

    def get_roles(self, obj):
        roles = []
        if obj.is_superuser:
            roles.append('admin')
        if obj.is_staff:
            roles.append('staff')

        # Check Profile
        profile = getattr(obj, 'profile', None)
        if profile and profile.user_type:
            roles.append(profile.user_type.lower())

        return list(set(roles))  # Remove duplicates

    def get_permissions(self, obj):
        if obj.is_superuser:
            return ['all']
        return obj.get_all_permissions()


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer specific for Admin updating a User.
    Includes explicit fields for Schools and Classes so they appear in Swagger
    and are validated correctly.
    """
    # Standard User Fields
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False)
    is_superuser = serializers.BooleanField(required=False)
    is_staff = serializers.BooleanField(required=False)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'is_active', 'is_superuser', 'is_staff',
        ]

    def update(self, instance, validated_data):
        # 2. Update Standard User Fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance


# --- IMPORTANT: ALIAS FOR DJOSER ---
UserInfoSerializer = UserProfileDetailedSerializer


class UserListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the Admin User List Table
    """
    profile = UserProfileSerializer(read_only=True)
    group_name = serializers.SerializerMethodField()
    user_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'profile', 'group_name', 'last_login',
            'user_type'
        ]

    def get_group_name(self, obj):
        if obj.groups.exists():
            return obj.groups.first().name
        return None

    def get_user_type(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.user_type
        if obj.is_superuser:
            return 'ADMIN'
        return 'USER'


class UserPasswordChangeSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)
    re_password = serializers.CharField(required=True)


class ActiveUserSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ActiveUser
        fields = ['user', 'username', 'last_seen']
