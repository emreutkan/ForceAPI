import os
import warnings
import environ
from pathlib import Path

# Initialize environ
env = environ.Env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Take environment variables from .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
# Single switch: True = local/dev (Docker or host; access at localhost or your LAN IP), False = production (VPS / ALLOWED_HOSTS)
IS_LOCAL = env.bool('LOCALHOST', default=True)

DATABASE_URL = env('DATABASE_URL')


if IS_LOCAL:
    DEBUG = True
    ALLOWED_HOSTS = ['*']
    DATABASES = {
        'default': env.db('DATABASE_URL'),
        'vectordb': env.db('VECTOR_DATABASE_URL', default='sqlite:///' + str(BASE_DIR / 'vector.sqlite3'))
    }

elif not IS_LOCAL and DATABASE_URL:  # Production: Docker or bare metal (OCI)
    DEBUG = False
    # VPS IP hardcoded; override via ALLOWED_HOSTS in .env (comma-separated; spaces are stripped)
    # When client sends Host: 192.168.1.2:8000, Django requires that exact value in ALLOWED_HOSTS
    _allowed = [h.strip() for h in env.list('ALLOWED_HOSTS', default=['89.167.52.206']) if h.strip()]
    _with_ports = set(_allowed)
    for h in _allowed:
        if ':' not in h:
            _with_ports.add(f"{h}:8000")   # runserver / dev
            _with_ports.add(f"{h}:80")
            _with_ports.add(f"{h}:443")
    ALLOWED_HOSTS = list(_with_ports)

    DATABASES = {
        'default': env.db('DATABASE_URL'),
        'vectordb': env.db('VECTOR_DATABASE_URL', default='sqlite:///' + str(BASE_DIR / 'vector.sqlite3'))
    }
    _origins = env.list('CSRF_TRUSTED_ORIGINS', default=['http://89.167.52.206'])
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _origins if o.strip()]

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
elif not IS_LOCAL and not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")
else:
    raise ValueError("LOCALHOST must be True or False (or set IS_LOCAL via env)", DATABASE_URL)

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
    'ai_chat',
]


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'force.middleware.RequestResponseLogMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
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

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Media files (Images, uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Email Configuration
# Use console backend for development, SMTP for production
if IS_LOCAL:
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
if IS_LOCAL:
    CORS_ALLOW_ALL_ORIGINS = True  # Development: allow all origins
    CORS_ALLOW_CREDENTIALS = True
else:
    # Production: configure from environment or allow all (mobile apps don't use browsers)
    CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=True)
    CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
    CORS_ALLOW_CREDENTIALS = env.bool('CORS_ALLOW_CREDENTIALS', default=True)

# CSRF Settings

# REST Framework Config
SUPABASE_JWT_SECRET = env('SUPABASE_JWT_SECRET', default='')
SUPABASE_URL = env('SUPABASE_URL', default='')
SUPABASE_ANON_KEY = env('SUPABASE_ANON_KEY', default='')

# RevenueCat webhook: set in dashboard and in .env; if set, incoming webhook must send same value in Authorization header
REVENUECAT_WEBHOOK_AUTHORIZATION = env('REVENUECAT_WEBHOOK_AUTHORIZATION', default='')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'user.authentication.SupabaseJWTAuthentication',
    ],
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

# LLM Configuration
# Priority: GEMINI=True > LOCAL_LLM=False (DeepSeek) > LOCAL_LLM=True (Ollama)
LOCAL_LLM = env.bool('LOCAL_LLM', default=True)
GEMINI = env.bool('GEMINI', default=False)

if GEMINI:
    # Google Gemini via its OpenAI-compatible endpoint — no extra package needed
    LLM_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
    LLM_MODEL = env('GEMINI_MODEL', default='gemini-2.0-flash')
    LLM_API_KEY = env('GEMINI_API_KEY')
elif LOCAL_LLM:
    LLM_BASE_URL = env('LOCAL_LLM_HOST', default='http://192.168.1.2:11434') + '/v1'
    LLM_MODEL = env('LOCAL_LLM_MODEL', default='deepseek-r1:8b')
    LLM_API_KEY = 'ollama'  # Ollama doesn't need a real key but openai client requires one
else:
    LLM_BASE_URL = 'https://api.deepseek.com'
    LLM_MODEL = env('LLM_MODEL', default='deepseek-chat')
    LLM_API_KEY = env('LLM_API_KEY')

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
