import os
import secrets
import sys
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / '.env')
load_dotenv(BASE_DIR / '.env')
DEBUG = os.getenv('DJANGO_DEBUG', '1') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('DJANGO_SECRET_KEY est obligatoire en production.')
    secret_file = BASE_DIR / '.dev-secret'
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(64))
        secret_file.chmod(0o600)
    SECRET_KEY = secret_file.read_text().strip()
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'rest_framework', 'shop']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'shop.middleware.AdminLoginThrottleMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
DATABASES = {'default': dj_database_url.config(default=f'sqlite:///{BASE_DIR / "db.sqlite3"}', conn_max_age=60)}
if DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
    DATABASES['default']['OPTIONS'] = {'transaction_mode': 'IMMEDIATE', 'timeout': 20}
# PostgreSQL deployments share rate-limit counters between gunicorn workers (table created by migration 0005).
# SQLite development keeps the per-process memory cache.
if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache', 'LOCATION': 'stc_cache', 'OPTIONS': {'MAX_ENTRIES': 20000}}}
AUTH_USER_MODEL = 'shop.User'
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
# Tests run without collectstatic (CI, fresh checkout): hashed manifest names are only needed for collected files.
if sys.argv[1:2] == ['test']:
    STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG and os.getenv('SECURE_SSL_REDIRECT', '1') == '1'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if os.getenv('STC_TRUST_PROXY', '0') == '1' else None
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_FAILURE_VIEW = 'shop.views.csrf_failure'
REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'], 'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'], 'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'], 'EXCEPTION_HANDLER': 'shop.errors.exception_handler', 'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle', 'rest_framework.throttling.UserRateThrottle'], 'DEFAULT_THROTTLE_RATES': {'anon': os.getenv('ANON_THROTTLE_RATE', '3000/hour'), 'user': os.getenv('USER_THROTTLE_RATE', '3000/hour'), 'auth': os.getenv('AUTH_THROTTLE_RATE', '200/hour' if DEBUG else '20/hour'), 'orders': os.getenv('ORDER_THROTTLE_RATE', '300/hour' if DEBUG else '60/hour')}}
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'shop.email_backend.PrivateFileEmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_FILE_PATH = Path(os.getenv('STC_EMAIL_FILE_PATH', str(BASE_DIR / '.private-emails')))
EMAIL_FILE_PATH.mkdir(mode=0o700, exist_ok=True)
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', '1') == '1'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'STC <bonjour@stc.example>')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))
# Team addresses alerted of each confirmed order (comma separated); empty disables the alert.
ORDER_NOTIFICATION_EMAILS = [address.strip() for address in os.getenv('STC_ORDER_NOTIFICATION_EMAIL', '').split(',') if address.strip()]
# Stripe orders left unpaid longer than this are cancelled (cancel_stale_orders, payment resumption).
PENDING_PAYMENT_MINUTES = int(os.getenv('STC_PENDING_PAYMENT_MINUTES', '45'))
PASSWORD_RESET_TIMEOUT = 3600
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')
DEMO_MODE = os.getenv('STC_DEMO_MODE', '1') == '1'
if STRIPE_SECRET_KEY and not STRIPE_SECRET_KEY.startswith('sk_test_'):
    raise RuntimeError('Seules les clés Stripe de test sont autorisées dans cette livraison.')
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'handlers': {'console': {'class': 'logging.StreamHandler'}}, 'loggers': {'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False}, 'shop': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}}}

PAYMENT_MODE = os.getenv('STC_PAYMENT_MODE', 'simulation')
if PAYMENT_MODE not in {'simulation', 'stripe'}:
    raise RuntimeError('STC_PAYMENT_MODE doit être simulation ou stripe.')
if PAYMENT_MODE == 'stripe' and (not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET):
    raise RuntimeError('Les clés Stripe test et webhook sont obligatoires en mode stripe.')
if not DEBUG and not DEMO_MODE and PAYMENT_MODE == 'simulation':
    raise RuntimeError('Le mode simulation ne peut pas accepter de commandes réelles en production.')

LOGGING['handlers']['null'] = {'class': 'logging.NullHandler'}
LOGGING['loggers']['django.server'] = {'handlers': ['null'], 'propagate': False}

RUNTIME_DIR = Path(os.getenv('STC_RUNTIME_DIR', str(BASE_DIR.parent / '.runtime')))
TRUST_PROXY = os.getenv('STC_TRUST_PROXY', '0') == '1'
ADMIN_LOGIN_LIMIT = int(os.getenv('ADMIN_LOGIN_LIMIT', '100' if DEBUG else '10'))
ADMIN_LOGIN_WINDOW = int(os.getenv('ADMIN_LOGIN_WINDOW', '300'))
