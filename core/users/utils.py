import json
from io import BytesIO

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from PIL import Image


def compress_image(image, image_quality=70):
    """
    Compresses an image to JPEG format with specified quality.
    """
    if not image:
        return None

    im = Image.open(image)
    if im.mode != 'RGB':
        im = im.convert('RGB')

    im.thumbnail((800, 800), Image.LANCZOS)
    output = BytesIO()
    im.save(output, format='JPEG', quality=image_quality)
    output.seek(0)
    return output


def change_permissions(user, data):
    """
    Updates user permissions, groups, and assigned classes (via Teacher profile).
    """
    try:
        # --- 1. HANDLE DIRECT PERMISSIONS (TABLES) ---
        # Expecting JSON string for tables: '{"school": {"r": true, "c": false...}, ...}'
        tables_data = data.get('tables')
        if isinstance(tables_data, str):
            tables_data = json.loads(tables_data)
        elif not isinstance(tables_data, dict):
            tables_data = {}

        new_permissions = set()

        for model_name, perms in tables_data.items():
            if model_name.startswith('historical'):
                continue

            # Find the ContentType for the model (flexible search)
            content_type = ContentType.objects.filter(model=model_name).first()
            if not content_type:
                continue

            # Map generic keys to Django permission codenames
            mapping = {
                'r': f'view_{model_name}',
                'c': f'add_{model_name}',
                'u': f'change_{model_name}',
                'd': f'delete_{model_name}'
            }

            for action_key, codename in mapping.items():
                if perms.get(action_key, False):
                    try:
                        permission = Permission.objects.get(content_type=content_type, codename=codename)
                        new_permissions.add(permission)
                    except Permission.DoesNotExist:
                        continue

        # Apply Direct Permissions
        if new_permissions:
            user.user_permissions.set(new_permissions)

        # --- 2. HANDLE GROUP (SINGLE) ---
        if 'group' in data:
            group_id = data.get('group')
            if group_id:
                user.groups.set([group_id])
            else:
                user.groups.clear()

        # --- 3. HANDLE CLASSES (Via Teacher Model) ---
        # CRITICAL FIX: UserClasses was deleted. We now update the Teacher model.
        if 'classes' in data:
            classes_list = data.get('classes', [])

            # Check if user has a teacher profile
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                # Validate that the IDs passed are valid Class IDs (optional but safer)
                if classes_list:
                    teacher.classes.set(classes_list)
                else:
                    teacher.classes.clear()
            else:
                # Optional: You could create a teacher profile here if one doesn't exist,
                # but usually that's done via the creation flow.
                pass

        user.save()

    except Exception as e:
        print(f'Critical Error in change_permissions: {e}')
        # Re-raise to let the View handle the error response
        raise e
