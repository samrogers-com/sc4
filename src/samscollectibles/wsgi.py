"""
WSGI config for samscollectibles project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application

# Set the default settings module. Use 'production' if DJANGO_ENV is set to 'production', else default to 'local'.
os.environ.setdefault(
   'DJANGO_SETTINGS_MODULE',
   'samscollectibles.settings.production' if os.getenv('DJANGO_ENV') == 'production' else 'samscollectibles.settings.local'
)

application = get_wsgi_application()
