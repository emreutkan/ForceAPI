import os
import warnings
import environ
from pathlib import Path

# Initialize environ
env = environ.Env(
  
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Take environment variables from .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
LOCALHOST = env('LOCALHOST')  # Read early for Sentry initialization

# Sentry error tracking (optional) - initialize early
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN and LOCALHOST == 'False':
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style='url',
                middleware_spans=True,
                signals_spans=True,
            ),
            LoggingIntegration(
                level=None,  # Capture all logs
                event_level=None,  # Send all events
            ),
        ],
        traces_sample_rate=0.1,  # 10% of transactions
        send_default_pii=False,  # Don't send personally identifiable information
        environment='production',
    )

# Validate SECRET_KEY in production
if LOCALHOST == 'False':
    if not SECRET_KEY or SECRET_KEY == 'your-secret-key-here' or len(SECRET_KEY) < 50:
        raise ValueError(
            "SECRET_KEY must be set to a secure random value in production. "
            "Generate one using: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
        )


DEPLOY_HOST = env('DEPLOY_HOST', default='')
POSTGRES_USER = env('POSTGRES_USER', default="")
POSTGRES_PASSWORD = env('POSTGRES_PASSWORD', default="")
POSTGRES_DB = env('POSTGRES_DB', default="")
# DB_HOST and DB_PORT are set conditionally based on LOCALHOST and DATABASE_URL
DB_HOST = env('DB_HOST', default='localhost')
DB_PORT = env('DB_PORT', default='5432')
try:
    DATABASE_URL = env('DATABASE_URL')
except Exception:
    DATABASE_URL = None
if not DATABASE_URL and POSTGRES_USER and POSTGRES_PASSWORD and POSTGRES_DB:
    DATABASE_URL = f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"

# Localhost: Postgres (Docker or local). DB_HOST in .env: use 'localhost' when Django runs on host, 'db' when in Docker.
if LOCALHOST == 'True':
    DEBUG = True
    ALLOWED_HOSTS = ['*']
    if not POSTGRES_USER or not POSTGRES_PASSWORD or not POSTGRES_DB:
        raise ValueError(
            "Local dev uses Postgres. Set POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB in .env "
            "and run Postgres (e.g. docker compose --profile postgres up -d db). Use DB_HOST=localhost when Django runs on host."
        )
    DB_HOST = env('DB_HOST', default='localhost')
    DB_PORT = env('DB_PORT', default='5432')
    DATABASE_URL = f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"
    os.environ['DATABASE_URL'] = DATABASE_URL
    DATABASES = {'default': env.db('DATABASE_URL')}

elif LOCALHOST == 'False' and DATABASE_URL:  # Production: Docker or bare metal (OCI)
    DEBUG = False
    ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])
    
    # Validate production environment variables
    if not ALLOWED_HOSTS:
        raise ValueError("ALLOWED_HOSTS must be set in production. Set it in your .env file as a comma-separated list.")
    
    if 'db:5432' in DATABASE_URL:
        DB_HOST = 'db'
        DB_PORT = 5432
    else:
        DB_HOST = env('DB_HOST', default='localhost')
        DB_PORT = env('DB_PORT', default='5432')
    DATABASES = {
        'default': env.db('DATABASE_URL')
    }
    CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=['https://api.utrack.irfanemreutkan.com'])
    
    # Production Security Settings
    # SECURE_SSL_REDIRECT: Set to False if SSL is terminated at load balancer/proxy
    # Set to True if Django handles SSL directly
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
    
    # If SSL is terminated externally, trust the X-Forwarded-Proto header
    if not SECURE_SSL_REDIRECT:
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    SECURE_HSTS_SECONDS = 31536000  # 1 year - HTTP Strict Transport Security
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME sniffing
    SECURE_BROWSER_XSS_FILTER = True  # XSS protection
    X_FRAME_OPTIONS = 'DENY'  # Prevent clickjacking
    SESSION_COOKIE_SECURE = True  # Secure session cookies
    CSRF_COOKIE_SECURE = True  # Secure CSRF cookies
    CSRF_COOKIE_HTTPONLY = True  # Prevent JS access to CSRF cookie
    SESSION_COOKIE_HTTPONLY = True  # Prevent XSS on cookies
elif LOCALHOST == 'False' and not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")
else:
    raise ValueError("LOCALHOST is not set", LOCALHOST, DATABASE_URL)

AUTH_USER_MODEL = 'user.CustomUser'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'core',
    'rest_framework',
    'user',
    'exercise',
    'workout',
    'body_measurements',
    'drf_spectacular',
]


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'force.middleware.RequestResponseLogMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'force.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'force.wsgi.application'


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization          
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (Images, uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Email Configuration
# Use console backend for development, SMTP for production
if LOCALHOST == 'True':
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)
    
    # Validate email settings in production
    if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
        warnings.warn(
            "EMAIL_HOST_USER and EMAIL_HOST_PASSWORD should be set in production for email functionality.",
            UserWarning
        )

# Frontend URL for email links
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Settings
# For mobile apps, CORS is less critical but should still be configured
if LOCALHOST == 'True':
    CORS_ALLOW_ALL_ORIGINS = True  # Development: allow all origins
    CORS_ALLOW_CREDENTIALS = True
else:
    # Production: configure from environment or allow all (mobile apps don't use browsers)
    CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=True)
    CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
    CORS_ALLOW_CREDENTIALS = env.bool('CORS_ALLOW_CREDENTIALS', default=True)

# CSRF Settings

# REST Framework Config
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_THROTTLE_CLASSES': [
        'force.throttles.AnonBurstRateThrottle',
        'force.throttles.AnonSustainedRateThrottle',
        'force.throttles.BurstRateThrottle',
        'force.throttles.SustainedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon_burst': '10/minute',
        'anon_sustained': '100/hour',
        'burst': '60/minute',
        'sustained': '1000/hour',
        'pro_user': '200/minute',
        'check_date': '30/minute',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'force.exceptions.custom_exception_handler',
}

# Logging Configuration
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)  # Create logs directory if it doesn't exist

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
        'request': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'file_errors': {
            'level': 'ERROR',
            'class': 'force.logging_handlers.WindowsSafeRotatingFileHandler',
            'filename': LOGS_DIR / 'errors.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,  # Keep 10 backup files
            'formatter': 'verbose',
        },
        'file_info': {
            'level': 'INFO',
            'class': 'force.logging_handlers.WindowsSafeRotatingFileHandler',
            'filename': LOGS_DIR / 'info.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,  # Keep 5 backup files
            'formatter': 'simple',
        },
        'file_requests': {
            'level': 'INFO',
            'class': 'force.logging_handlers.WindowsSafeRotatingFileHandler',
            'filename': LOGS_DIR / 'requests.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,  # Keep 5 backup files
            'formatter': 'request',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'console_debug': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file_info', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_errors', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['file_info', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'force': {
            'handlers': ['file_info', 'file_errors', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'force.requests': {
            'handlers': ['file_requests', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'workout': {
            'handlers': ['file_info', 'file_errors', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'user': {
            'handlers': ['file_info', 'file_errors', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'exercise': {
            'handlers': ['file_info', 'file_errors', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['file_info', 'file_errors', 'console'],
        'level': 'INFO',
    },
}
