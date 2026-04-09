# src/samscollectibles/settings/production.py

from .base import *

# Production environment variables are managed by the hosting provider (Cloudflare or Hostinger)
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=[], cast=lambda v: [s.strip() for s in v.split(',')])

# Security settings
# SSL redirect is handled by Cloudflare — Django should NOT redirect
# or it creates an infinite loop (Cloudflare → Nginx → Django → redirect → Cloudflare...)
SECURE_SSL_REDIRECT = False
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
