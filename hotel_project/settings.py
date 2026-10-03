"""
Django settings for hotel_project.

Environment variables:
    SECRET_KEY
    DEBUG
    ALLOWED_HOSTS
    DATABASE_URL
    CSRF_TRUSTED_ORIGINS
    ELECTRICITY_RATE_PER_UNIT
    DJANGO_LOG_LEVEL
    DEBUG_SQL
    AWS_S3_BUCKET_NAME
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_REGION
"""

from pathlib import Path
import os

from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv
import dj_database_url


# -----------------------------------------------------------------------------
# Base
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local .env if present.
load_dotenv(BASE_DIR / ".env")


# -----------------------------------------------------------------------------
# Security
# -----------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    # Useful for local development only.
    # Production should always provide SECRET_KEY through environment variables.
    SECRET_KEY = f"django-insecure-{get_random_secret_key()}"


DEBUG = os.getenv("DEBUG", "True").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable as a clean list."""
    return [
        item.strip()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    ]


ALLOWED_HOSTS = list(
    dict.fromkeys(
        [
            "127.0.0.1",
            "localhost",
            "testserver",
            *env_list("ALLOWED_HOSTS"),
        ]
    )
)


CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174",
)


# -----------------------------------------------------------------------------
# CORS (production only)
# -----------------------------------------------------------------------------
# The React frontend is served from a different origin than this API and
# authenticates with session cookies sent via `credentials: 'include'`, so
# CORS must explicitly allow those origins — a wildcard is not permitted
# alongside credentials.
#
# Set CORS_ALLOWED_ORIGINS to the deployed Vercel domain(s), comma separated.
# Nothing is enabled during local development, where both run on localhost.
if not DEBUG:
    CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

    # Optional regex for preview/staging Vercel domains, e.g.
    # r"https://panesar-.*\.vercel\.app"
    CORS_ALLOWED_ORIGIN_REGEXES = env_list("CORS_ALLOWED_ORIGIN_REGEXES")

    # Required for the session cookie to be accepted cross-origin.
    CORS_ALLOW_CREDENTIALS = True



# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rental",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    # Must sit above CommonMiddleware so the CORS headers are applied to
    # responses. Required because the React app is served from a different
    # origin (Vercel) than the API (Render).
    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "hotel_project.middleware.LoginRequiredMiddleware",
    "hotel_project.middleware.SecurityHeadersMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "hotel_project.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


WSGI_APPLICATION = "hotel_project.wsgi.application"


# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }

    # PostgreSQL production connections normally require SSL.
    if "postgresql" in DATABASES["default"].get("ENGINE", ""):
        DATABASES["default"].setdefault("OPTIONS", {})
        DATABASES["default"]["OPTIONS"].setdefault("sslmode", "require")

else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# -----------------------------------------------------------------------------
# Password validation
# -----------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# -----------------------------------------------------------------------------
# Internationalization
# -----------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")

USE_I18N = True
USE_TZ = True


# -----------------------------------------------------------------------------
# Rental application configuration
# -----------------------------------------------------------------------------

ELECTRICITY_RATE_PER_UNIT = os.getenv(
    "ELECTRICITY_RATE_PER_UNIT",
    "13.00",
)


# -----------------------------------------------------------------------------
# Static files
# -----------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = []


STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "rental.storage.MyStorage"
        ),
    },
}


# WhiteNoise
WHITENOISE_MANIFEST_STRICT = False
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG


# -----------------------------------------------------------------------------
# Media files
# -----------------------------------------------------------------------------

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# Optional S3 media storage.
AWS_BUCKET = os.getenv("AWS_S3_BUCKET_NAME")

if AWS_BUCKET:
    try:
        import storages  # noqa: F401

        AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
        AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
        AWS_STORAGE_BUCKET_NAME = AWS_BUCKET
        AWS_S3_REGION_NAME = os.getenv("AWS_REGION")

        AWS_S3_CUSTOM_DOMAIN = (
            f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
        )

        DEFAULT_FILE_STORAGE = (
            "storages.backends.s3boto3.S3Boto3Storage"
        )

        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"

    except ImportError:
        # Fall back to local media storage if django-storages isn't installed.
        pass


# -----------------------------------------------------------------------------
# Production security
# -----------------------------------------------------------------------------

if DEBUG:
    CSRF_COOKIE_HTTPONLY = False
    SESSION_COOKIE_HTTPONLY = False

else:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # JavaScript needs access to the CSRF cookie for API requests.
    CSRF_COOKIE_HTTPONLY = False

    SESSION_COOKIE_HTTPONLY = True

    # The frontend (Vercel) and the API (Render) are different *sites*, so a
    # `Lax` cookie is never sent on the app's XHR calls: login would appear to
    # succeed and then every later request would 401. `None` is required for
    # cross-site session auth and is only safe alongside `Secure` (set above)
    # over HTTPS. Overridable via env for single-origin deployments.
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "None")

    # Browsers only store a SameSite=None cookie on a secure origin, and the
    # React client reads the CSRF cookie from JavaScript.
    CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "None")

    CSRF_USE_SESSIONS = False

    SECURE_SSL_REDIRECT = True

    SECURE_HSTS_SECONDS = int(
        os.getenv("SECURE_HSTS_SECONDS", "31536000")
    )
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )

    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

LOG_LEVEL = os.getenv(
    "DJANGO_LOG_LEVEL",
    "INFO" if DEBUG else "WARNING",
)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "standard": {
            "format": (
                "[{asctime}] {levelname} "
                "{name}: {message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },

    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG" if os.getenv("DEBUG_SQL") else LOG_LEVEL,
            "propagate": False,
        },
    },

    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}


# -----------------------------------------------------------------------------
# Django defaults
# -----------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"