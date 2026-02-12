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
# Lee de Railway o usa la default en local.
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-bqy+h6+*$li6+o^mrh)ys)$i&f(h)q0vhc7y7&n9c%3me1)yhl')

# 2. DEBUG:
# False en producción (Railway), True en local.
DEBUG = 'RAILWAY_ENVIRONMENT' not in os.environ

# 3. ALLOWED HOSTS:
# Permite el dominio dinámico de Railway.
ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',  # <--- NUEVO: Librería para permitir conexión desde GHL
    # Tus apps:
    'ghl_middleware', # Tu lógica
    'GHL_Front',      # Frontend/UI de GHL
    'GHL_RRSS',       # Redes Sociales de GHL
    'rest_framework', # Para la API
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', # <--- NUEVO: Debe ir EL PRIMERO
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware", # CRÍTICO: Para CSS en Railway
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
# CORRECCIÓN #38: Añadido fallback de SQLite para desarrollo local
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

# CORRECCIÓN #39: Migrado STATICFILES_STORAGE a STORAGES (Django 4.2+)
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
        'rest_framework.permissions.AllowAny',
    ]
}


# --- SEGURIDAD EXTRA PARA RAILWAY Y GHL ---
# Confía en el HTTPS de Railway
CSRF_TRUSTED_ORIGINS = [
    'https://api.leadconnectorhq.com', 
    'https://widgets.leadconnectorhq.com', 
    'https://app.gohighlevel.com', # <--- CORREGIDO: Añadida coma que faltaba
    'https://*.railway.app', 
    'https://*.up.railway.app'
] 
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Si vas a cargar esta app dentro de un IFRAME en GHL (Custom Menu Link):
X_FRAME_OPTIONS = 'ALLOWALL' 


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
# Estas variables DEBEN estar en "Variables" de tu proyecto en Railway.
# Si no las pones en Railway, fallará la autenticación.

# Credenciales de tu App en GHL Marketplace
GHL_CLIENT_ID = os.environ.get('GHL_CLIENT_ID', '')
GHL_CLIENT_SECRET = os.environ.get('GHL_CLIENT_SECRET', '')

# URL de redirección (debe coincidir con la del Marketplace)
GHL_REDIRECT_URI = os.environ.get('GHL_REDIRECT_URI', 'http://localhost:8000/api/oauth/callback/')

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

# --- NUEVO: PERMISOS CORS PARA GHL ---
# Esto permite que el navegador acepte peticiones desde los scripts de GHL
CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_SAMESITE = 'None'  # Permite que la cookie viaje entre dominios
CSRF_COOKIE_SECURE = True       # Obligatorio si usas 'None'
