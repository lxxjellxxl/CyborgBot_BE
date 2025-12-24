from typing import List, Optional

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import models
from rest_framework.exceptions import ValidationError


def extract_error_messages(validation_error: ModelValidationError) -> List[str]:
    """
    Extracts and returns error messages from a ValidationError instance.
    """
    error_messages = []
    if isinstance(validation_error, ModelValidationError):
        error_dict = validation_error.message_dict

        for _, messages in error_dict.items():
            if isinstance(messages, list):
                error_messages.extend(messages)
            else:
                error_messages.append(messages)
    return error_messages


def clean_and_save_model_instance(instance: models.Model) -> Optional[models.Model]:
    try:
        instance.full_clean()
        instance.save()
        return instance
    except ModelValidationError as e:
        raise ValidationError(extract_error_messages(e))
    except Exception as e:
        raise ValidationError(str(e))
