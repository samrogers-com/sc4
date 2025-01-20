# src/samscollectibles/settings/production.py

from .base import *

# For AWS production, environment variables are managed by ECS/Fargate, so rely on `config` to access those
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=[], cast=lambda v: [s.strip() for s in v.split(',')])

# Security settings
SECURE_SSL_REDIRECT = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# Ensure the secret key is retrieved from environment variables
SECRET_KEY = config('SECRET_KEY')


# Logging settings in settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',  # Change to INFO or ERROR in production
            'propagate': True,
        },
    },
}
