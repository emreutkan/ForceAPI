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


APPLE_KEY_ID = env('APPLE_KEY_ID')
APPLE_TEAM_ID = env('APPLE_TEAM_ID')
APPLE_CLIENT_ID = env('APPLE_CLIENT_ID')
APPLE_PRIVATE_KEY = env('APPLE_PRIVATE_KEY').replace('\\n', '\n') # Fixes newline issues in keys
DEPLOY_HOST = env('DEPLOY_HOST', default='')
POSTGRES_USER = env('POSTGRES_USER', default="")
POSTGRES_PASSWORD = env('POSTGRES_PASSWORD', default="")
POSTGRES_DB = env('POSTGRES_DB', default="")
# Suppress specific warnings from dj_rest_auth regarding allauth deprecations
warnings.filterwarnings('ignore', message='.*app_settings.USERNAME_REQUIRED is deprecated.*')
warnings.filterwarnings('ignore', message='.*app_settings.EMAIL_REQUIRED is deprecated.*')

# DB_HOST and DB_PORT are set conditionally based on LOCALHOST and DATABASE_URL
# Initialize with defaults to avoid errors if not set in .env
DB_HOST = env('DB_HOST', default='localhost')
DB_PORT = env('DB_PORT', default='5432')
# Build DATABASE_URL if not already set and we have the components
if POSTGRES_USER and POSTGRES_PASSWORD and POSTGRES_DB:
    # Check if DATABASE_URL is already set (from .env), if not, build it
    try:
        DATABASE_URL = env('DATABASE_URL')
    except:
        DATABASE_URL = f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"
else:
    DATABASE_URL = None

if LOCALHOST == 'True' and not DATABASE_URL:
    DEBUG = True
    ALLOWED_HOSTS = ['*']
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
elif LOCALHOST == 'True' and DATABASE_URL: # Localhost is True and DATABASE_URL is set WHICH MEANS WE ARE IN DOCKER COMPOSE
    DEBUG = True
    ALLOWED_HOSTS = ['*']
    DB_HOST = 'db' # because we are in docker compose
    DB_PORT = 5432 # because we are in docker compose
    DATABASE_URL = f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"

    DATABASES = {
        'default': env.db('DATABASE_URL')
    }

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
    'rest_framework.authtoken',
    'user',
    'exercise',
    'workout',
    'supplements',
    'body_measurements',
    'django.contrib.sites',       # Required by allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.apple',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'drf_spectacular',  # API documentation
    
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
    'allauth.account.middleware.AccountMiddleware', 
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

# Add Authentication Backends
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Allauth Configuration (matches your CustomUser email-only setup)
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'optional' # or 'mandatory'

# Social Account Providers
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    },
    'apple': {
        'APP': {
            # Your App ID (Bundle ID) from Apple Developer Console
            'client_id': os.environ.get('APPLE_CLIENT_ID'),
            
            # The Key ID (from the .p8 file details in Apple Developer Console)
            'secret': os.environ.get('APPLE_KEY_ID'),
            
            # Your Apple Team ID
            'key': os.environ.get('APPLE_TEAM_ID'),
            
            # The contents of the .p8 private key file you downloaded from Apple
            'certificate_key': os.environ.get('APPLE_PRIVATE_KEY')
        }
    }
}

# REST Framework Config (update existing)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'dj_rest_auth.jwt_auth.JWTCookieAuthentication', # Optional, for cookie auth
    ),
    # Rate limiting/throttling configuration
    'DEFAULT_THROTTLE_CLASSES': [
        'force.throttles.AnonBurstRateThrottle',
        'force.throttles.AnonSustainedRateThrottle',
        'force.throttles.BurstRateThrottle',
        'force.throttles.SustainedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        # Anonymous users
        'anon_burst': '10/minute',      # 10 requests per minute for anonymous users
        'anon_sustained': '100/hour',    # 100 requests per hour for anonymous users
        
        # Authenticated users (FREE)
        'burst': '60/minute',            # 60 requests per minute
        'sustained': '1000/hour',        # 1000 requests per hour
        
        # PRO users (higher limits)
        'pro_user': '200/minute',        # 200 requests per minute for PRO users
        
        # Specific endpoints
        'login': '5/minute',             # 5 login attempts per minute (prevent brute force)
        'registration': '3/hour',        # 3 registrations per hour per IP
        'password_reset': '3/hour',      # 3 password reset requests per hour
        'check_date': '30/minute',       # check-date / check previous workout per user
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'force.exceptions.custom_exception_handler',
}

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

# Use JWTs with dj-rest-auth
REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_HTTPONLY': False,
}

SITE_ID = 1

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
