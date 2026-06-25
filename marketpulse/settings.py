"""
Django settings for the MarketPulse trading simulator.

A single-file, self-contained configuration tuned for a local demo:
SQLite (WAL mode), an in-process market-simulation engine, DRF, and
local-memory caching. No external services required.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security / debug ------------------------------------------------------
# Demo defaults. Do NOT use this key or DEBUG=True in production.
SECRET_KEY = "django-insecure-marketpulse-demo-key-change-me-0xC0FFEE"
DEBUG = True
ALLOWED_HOSTS = ["*"]

# --- Applications ----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third-party
    "rest_framework",
    # Local apps
    "market.apps.MarketConfig",
    "trading.apps.TradingConfig",
    "dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "marketpulse.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "marketpulse.wsgi.application"
ASGI_APPLICATION = "marketpulse.asgi.application"

# --- Database --------------------------------------------------------------
# SQLite with a longer timeout so the background market engine and web
# requests don't trip over each other under WAL journaling (set in apps.py).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

# --- Password validation ---------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# --- I18N ------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static ----------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Caching (local-memory; used for leaderboard + market snapshots) -------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "marketpulse-locmem",
    }
}

# --- Auth flow -------------------------------------------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# --- Django REST Framework -------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}

# --- MarketPulse engine configuration --------------------------------------
# The simulation runs in a daemon thread inside the runserver process.
MARKET_ENGINE = {
    "AUTOSTART": True,          # auto-launch under `runserver`
    "TICK_INTERVAL": 1.5,       # seconds between price ticks
    "STARTING_CASH": 100_000.0,  # demo portfolios start with this much cash
    "MAX_HISTORY_TICKS": 600,   # ticks retained per instrument before pruning
}
