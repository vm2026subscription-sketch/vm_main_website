"""
E-Paper configuration: constants, caches, globals, Blueprint.
"""
import os
import tempfile
import threading
from collections import OrderedDict
from flask import Blueprint

# ── In-memory caches ──────────────────────────────────────
tts_cache: OrderedDict[str, bytes] = OrderedDict()     # cache_key -> bytes
TTS_CACHE_MAX = 30

trans_cache: OrderedDict[str, str] = OrderedDict()   # cache_key -> translated_text
TRANS_CACHE_MAX = 80

# ── Editions in-memory cache (avoids DB hit on every request) ──
editions_cache: list = None
editions_cache_ts: float = 0
EDITIONS_CACHE_TTL: int = 60          # seconds; invalidated on every save
editions_cache_lock = threading.Lock()

# ── Redis cache key constants ──────────────────────────────────
REDIS_EDITIONS_KEY = "ep:editions:list"
REDIS_EDITIONS_TTL = 300   # 5 minutes
REDIS_EDITION_TTL  = 600   # 10 minutes per single edition
REDIS_LATEST_KEY   = "ep:latest"
REDIS_LATEST_TTL   = 300   # 5 minutes

# ── Upstash Redis (L2 cache - survives cold starts) ───────────
redis_client = None
redis_client_lock = threading.Lock()

# ── Global MongoDB client (created once, reused across requests) ──
mongo_client = None
mongo_client_lock = threading.Lock()
mongo_disabled = (
    os.getenv("MONGO_DISABLED", "").lower() in ("1", "true", "yes") or
    not os.getenv("MONGODB_URI", "")
)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

# ── Epaper admin credentials ──────────────────────
EPAPER_ADMIN_USER = os.getenv("EPAPER_ADMIN_USER", "")
EPAPER_ADMIN_PASS = os.getenv("EPAPER_ADMIN_PASS", "")
EPAPER_ADMIN_SESSION_KEY = "epaper_admin_auth"
legacy_checked = False

# Set by app.py to app._is_admin so a user who signed in on the normal login
# page with an admin account gets the epaper builder straight from their
# dashboard -- no second login at /epaper-admin/login.
site_admin_check = None

# ── Cloudinary auto-config ─────────────────────────
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")
if CLOUDINARY_URL:
    try:
        import cloudinary
        cloudinary.config(cloudinary_url=CLOUDINARY_URL)
    except Exception:
        pass

# ── Blueprint ──────────────────────────────────────
epaper_bp = Blueprint("epaper", __name__)

# ── File paths ─────────────────────────────────────
EDITIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "epaper_editions.json")
EDITIONS_TMP = os.path.join(tempfile.gettempdir(), "epaper_editions.json")
EPAPER_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "epaper")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | {"pdf"}

EPAPER_VIEWS_FILE = os.path.join(os.path.dirname(__file__), "data", "epaper_views.json")
EPAPER_VIEWS_TMP = os.path.join(tempfile.gettempdir(), "epaper_views.json")

EPAPER_TMP_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "epaper_uploads")

# ── FCM (push notifications) ──────────────────────
fcm_ready = None

# ── Language slug lookup ───────────────────────────
LANG_SLUG = {"english": "English", "hindi": "Hindi", "marathi": "Marathi"}


def set_site_admin_check(fn):
    global site_admin_check
    site_admin_check = fn


def redis_edition_key(date, lang):
    return f"ep:ed:{date}:{(lang or 'any').lower()}"
