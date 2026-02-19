"""
Django settings for config project.
Configured for production on Railway & Go High Level OAuth.
"""

import os
from pathlib import Path
import dj_database_url # Necesario para la Base de Datos de Railway


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# --- CONFIGURACIÓN DE SEGURIDAD Y ENTORNO ---

# 1. SECRET KEY:
# Obligatorio en producción. En local genera una temporal automáticamente.
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if 'RAILWAY_ENVIRONMENT' in os.environ:
        raise RuntimeError("SECRET_KEY no configurada en producción. Añádela en Railway Variables.")
    else:
        import secrets
        SECRET_KEY = secrets.token_urlsafe(50)

# 2. DEBUG:
# False en producción (Railway), True en local.
DEBUG = 'RAILWAY_ENVIRONMENT' not in os.environ

# 3. ALLOWED HOSTS:
# En producción solo acepta dominios configurados. En local permite localhost.
_allowed = os.environ.get('ALLOWED_HOSTS', '')
if _allowed:
    ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']
else:
    ALLOWED_HOSTS = ['.railway.app', '.up.railway.app']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    # Apps:
    'ghl_middleware',
    'GHL_Front',
    'GHL_RRSS',
    'rest_framework',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# --- BASE DE DATOS (Auto-configurable) ---
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', 'sqlite:///db.sqlite3'),
        conn_max_age=600
    )
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# --- ARCHIVOS ESTÁTICOS (CSS/JS/IMG) ---
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --- CONFIGURACIÓN DRF ---
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}


# --- SEGURIDAD EXTRA PARA RAILWAY Y GHL ---
CSRF_TRUSTED_ORIGINS = [
    'https://api.leadconnectorhq.com',
    'https://widgets.leadconnectorhq.com',
    'https://app.gohighlevel.com',
    'https://*.railway.app',
    'https://*.up.railway.app'
]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Permitir iframe solo desde dominios de GHL y Railway
X_FRAME_OPTIONS = 'SAMEORIGIN'
# CSP frame-ancestors es más flexible que X_FRAME_OPTIONS para múltiples dominios
CSP_FRAME_ANCESTORS = "'self' https://app.gohighlevel.com https://*.leadconnectorhq.com"


# --- LOGGING (CRÍTICO PARA VER ERRORES EN RAILWAY) ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}


# --- CONFIGURACIÓN "EL CRUZADO" (OAUTH2 GHL MARKETPLACE) ---
GHL_CLIENT_ID = os.environ.get('GHL_CLIENT_ID', '')
GHL_CLIENT_SECRET = os.environ.get('GHL_CLIENT_SECRET', '')
GHL_REDIRECT_URI = os.environ.get('GHL_REDIRECT_URI', 'http://localhost:8000/api/oauth/callback/')

# Secreto para verificar webhooks de GHL (configurable por variable de entorno)
GHL_WEBHOOK_SECRET = os.environ.get('GHL_WEBHOOK_SECRET', '')

# Scopes
GHL_SCOPES = [
    'contacts.readonly',
    'contacts.write',
    'locations.readonly',
    'associations.readonly',
    'associations.write',
    'custom_objects/records.readonly',
    'custom_objects/records.write',
]

# --- CORS PARA GHL ---
# En producción usa orígenes explícitos, en local permite todo para desarrollo
CORS_ALLOW_ALL_ORIGINS = DEBUG

if not DEBUG:
    CORS_ALLOWED_ORIGINS = [
        'https://app.gohighlevel.com',
        'https://widgets.leadconnectorhq.com',
        'https://api.leadconnectorhq.com',
        'https://webprueba-olive.vercel.app',
    ]
    # Añadir dominios de Railway si están configurados
    _railway_url = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    if _railway_url:
        CORS_ALLOWED_ORIGINS.append(f'https://{_railway_url}')

CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_SAMESITE = 'None'
CSRF_COOKIE_SECURE = True




