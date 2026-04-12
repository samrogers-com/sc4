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

# Trust Cloudflare proxy for CSRF — without this, POST forms get 403
CSRF_TRUSTED_ORIGINS = [
    'https://samscollectibles.net',
    'https://www.samscollectibles.net',
]

# Tell Django to trust X-Forwarded-Proto from Cloudflare/Nginx
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

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
