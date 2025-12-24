import yaml


def yaml_coarce(value: str) -> dict:
    """
        Coarce a string to a dictionary. If the value is not a string, it is returned as is.
        helpfull when working with docker files and environment variables.
    """
    if isinstance(value, str):
        return yaml.load(f'dummy: {value}', Loader=yaml.SafeLoader)['dummy']
    else:
        return value
