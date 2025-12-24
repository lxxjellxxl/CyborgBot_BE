import os

from .misc import yaml_coarce


def get_setting_from_environment(prefix: str) -> dict:
    """
        Get all environment variables that start with the prefix and return them as a dictionary.
    """
    return {key[len(prefix):]: yaml_coarce(value) for key, value in os.environ.items() if key.startswith(prefix)}
