def deep_update(base_dict: dict, update_with: dict) -> dict:
    """Recursively update a dictionary with another dictionary."""
    for key, value in update_with.items():
        if isinstance(value, dict):
            base_dict_value = base_dict.get(key)

            if isinstance(base_dict_value, dict):
                base_dict[key] = deep_update(base_dict_value, value)
            else:
                base_dict[key] = value
        else:
            base_dict[key] = value

    return base_dict
