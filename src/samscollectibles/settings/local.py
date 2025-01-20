# src/samscollectibles/settings/local.py

from .base import *

# Explicitly specify the path to the local .env file
env_path = os.path.join(BASE_DIR, '.env.local')
config = Config(RepositoryEnv(env_path))

# Load necessary variables from the .env.local file
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=[], cast=lambda v: [s.strip() for s in v.split(',')])
SECRET_KEY = config('SECRET_KEY')

# # TEMPLATES configuration in src/samscollectibles/settings/base.py
# TEMPLATES = [
#     {
#         'BACKEND': 'django.template.backends.django.DjangoTemplates',
#         'DIRS': [os.path.join(BASE_DIR, 'templates')],  # You can add your custom template directory here
#         'APP_DIRS': True,  # This enables loading templates from within installed apps
#         'OPTIONS': {
#             'context_processors': [
#                 'django.template.context_processors.debug',
#                 'django.template.context_processors.request',
#                 'django.contrib.auth.context_processors.auth',
#                 'django.contrib.messages.context_processors.messages',
#             ],
#         },
#     },
# ]


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
            'level': 'DEBUG',  # Change to INFO or ERROR in production
            'propagate': True,
        },
    },
}
