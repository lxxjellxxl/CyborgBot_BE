from core.project.settings.rest_framework import REST_FRAMEWORK

DEBUG = True
SECRET_KEY = 'django-insecure-rdjlaf8czs90@4lh9tosc0xh8_p!7e-!-(xjz#&mx=x8aces*s'

# WhatsApp Meta Cloud API Configuration
WHATSAPP_ACCESS_TOKEN = 'EAFgDO9jZBEzsBPiEX9F3x0zl7L0rCefoQZCvoCFQASMDlYPSK3fTnz03ZBJAF0LRpwgVGmE8rdQDAyko5UWl7HYWWEk3fw9x3YygGrmUZAtupcDaTOzL3pgZAriDJ60h7DUtXfJFoH6mqRMaDhlmynDGZCeE5ZA1zKSZB4zMgaD7R0NcTjgrP3OSOZA2Ta3CPetALa2uZC5esKhKTZBvIGZAG66LUHH6ofYgjSp7nONaBzAHOhMZD'  # ⚠️ Replace with your actual token
WHATSAPP_PHONE_NUMBER_ID = '751189598085602'
WHATSAPP_BUSINESS_ACCOUNT_ID = '651321444700847'
WHATSAPP_API_VERSION = 'v22.0'

# media root for local development
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')  # type: ignore # noqa: F821

# required for debug_toolbar
INTERNAL_IPS = [
    '127.0.0.1',
]

# Enable browsable API
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [  # type: ignore # noqa: F821
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',
]
REST_FRAMEWORK[
    'DEFAULT_AUTHENTICATION_CLASSES'].insert(  # type: ignore # noqa: F821
        1, 'rest_framework.authentication.SessionAuthentication'
    )  # type: ignore # noqa: F821

# SMTP
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_USE_TLS = True
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_HOST_USER = 'user'
EMAIL_HOST_PASSWORD = 'secret key'
DEFAULT_FROM_EMAIL = f'app_name <{EMAIL_HOST_USER}>'

# Djoser email templates
DOMAIN = 'localhost:9000'
SITE_NAME = 'Kodorat'


LOGGING['formatters']['colored'] = {  # type: ignore
    '()': 'colorlog.ColoredFormatter',
    'format': '%(log_color)s%(asctime)s %(levelname)s %(name)s %(bold_white)s%(message)s',
}
LOGGING['loggers']['core']['level'] = 'DEBUG'  # type: ignore
LOGGING['loggers']['django.server']['level'] = 'INFO'  # type: ignore
LOGGING['handlers']['console']['level'] = 'DEBUG'  # type: ignore
LOGGING['handlers']['console']['formatter'] = 'colored'  # type: ignore
