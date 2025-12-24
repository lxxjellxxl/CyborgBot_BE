from core.core.utils.collections import deep_update
from core.core.utils.settings import get_setting_from_environment

deep_update(globals(), get_setting_from_environment(ENVVAR_SETTINGS_PREFIX))  # type: ignore # noqa: F821
