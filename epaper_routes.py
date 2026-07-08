"""
E-Paper routes — edition/page/article APIs + AI features
"""
import asyncio
import hashlib
import hmac
import io
import json
import os
import queue as _queue
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import contextlib
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, send_file, session, Response, stream_with_context
from werkzeug.utils import secure_filename

# ── In-memory caches ──────────────────────────────────────
_tts_cache: OrderedDict[str, bytes] = OrderedDict()     # cache_key → bytes
_TTS_CACHE_MAX = 30

_trans_cache: OrderedDict[str, str] = OrderedDict()   # cache_key → translated_text
_TRANS_CACHE_MAX = 80

# ── Editions in-memory cache (avoids DB hit on every request) ──
_editions_cache: list = None
_editions_cache_ts: float = 0
_EDITIONS_CACHE_TTL: int = 60          # seconds; invalidated on every save
_editions_cache_lock = threading.Lock()

# ── Global MongoDB client (created once, reused across requests) ──
_mongo_client = None
_mongo_client_lock = threading.Lock()

def _tts_cache_key(text, voice, rate, pitch):
    return hashlib.md5(f"{text}|{voice}|{rate}|{pitch}".encode("utf-8")).hexdigest()

def _trans_cache_key(text, target):
    return hashlib.md5(f"{text[:4000]}|{target}".encode("utf-8")).hexdigest()

def _evict(cache, max_size):
    while len(cache) >= max_size:
        if isinstance(cache, OrderedDict):
            cache.popitem(last=False)
        else:
            del cache[next(iter(cache))]

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

# ── Epaper admin credentials ──────────────────────
_EPAPER_ADMIN_USER = os.getenv("EPAPER_ADMIN_USER", "")
_EPAPER_ADMIN_PASS = os.getenv("EPAPER_ADMIN_PASS", "")
_EPAPER_ADMIN_SESSION_KEY = "epaper_admin_auth"

def _is_epaper_admin():
    return session.get(_EPAPER_ADMIN_SESSION_KEY) is True

def _require_epaper_admin():
    if _is_epaper_admin():
        return None
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Unauthorized. Please log in to epaper admin."}), 401
    return redirect(url_for("epaper.epaper_admin_login", next=request.full_path))

# ── Cloudinary auto-config ─────────────────────────
_CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")
if _CLOUDINARY_URL:
    try:
        import cloudinary
        cloudinary.config(cloudinary_url=_CLOUDINARY_URL)
    except Exception:
        pass


def _upload_to_cloudinary(file_bytes, filename):
    """Upload bytes to Cloudinary. Returns secure_url string or raises."""
    import io
    import cloudinary.uploader
    result = cloudinary.uploader.upload(
        io.BytesIO(file_bytes),
        folder="epaper",
        public_id=os.path.splitext(filename)[0],
        overwrite=True,
        resource_type="image",
        quality=100,           # no lossy compression
        flags="preserve_transparency",  # keep PNG alpha
    )
    # Strip any auto-transformation segment Cloudinary may insert in the URL
    url = result["secure_url"]
    url = re.sub(r'/upload/[^/]+/upload/', '/upload/', url)
    return url


def _require_admin():
    """Return redirect to login if user is not an admin, else None."""
    user = session.get("auth_user")
    if not user or user.get("email", "").lower() != ADMIN_EMAIL.lower():
        return redirect(url_for("login"))
    return None

epaper_bp = Blueprint("epaper", __name__)

import tempfile

EDITIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "epaper_editions.json")
_EDITIONS_TMP = os.path.join(tempfile.gettempdir(), "epaper_editions.json")
EPAPER_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "epaper")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | {"pdf"}


# ── MongoDB helpers ──────────────────────────────────

def _mongo_url():
    return os.getenv("MONGODB_URI", "")


def _get_mongo_client():
    """Return a cached global MongoClient (created once, reused across requests)."""
    global _mongo_client
    url = _mongo_url()
    if not url:
        return None
    if _mongo_client is None:
        with _mongo_client_lock:
            if _mongo_client is None:
                try:
                    from pymongo import MongoClient
                    _mongo_client = MongoClient(
                        url,
                        serverSelectionTimeoutMS=3000,
                        connectTimeoutMS=3000,
                        socketTimeoutMS=5000,
                        maxPoolSize=5,
                    )
                except Exception as e:
                    print(f"[epaper] MongoDB client init failed: {e}")
                    return None
    return _mongo_client


def _load_editions_from_mongo():
    """Read editions from MongoDB (Railway admin's database). Read-only — never writes."""
    client = _get_mongo_client()
    if not client:
        return []
    try:
        db_name = os.getenv("MONGODB_DB", "vm")
        col_name = os.getenv("MONGODB_COLLECTION", "editions")
        docs = list(client[db_name][col_name].find({}, {"_id": 0}))
        return docs
    except Exception as e:
        print(f"[epaper] MongoDB load failed: {e}")
        return []


# ── Postgres (Supabase) helpers ─────────────────────

def _pg_url():
    return os.getenv("SUPABASE_POSTGRES_URL") or os.getenv("DATABASE_URL")


def _pg_connect():
    import psycopg2
    # Prefer pooler URL (pgBouncer port 6543) — much faster on serverless
    url = os.getenv("SUPABASE_POOLER_URL") or _pg_url()
    conn = psycopg2.connect(
        url,
        connect_timeout=8,
        options="-c statement_timeout=25000",  # 25s max per query — prevents hanging
    )
    conn.autocommit = False
    return conn


# Skip repeated DDL on warm instances — reset to False on cold start
_tables_ensured = False

def _pg_ensure_table(conn):
    global _tables_ensured
    if _tables_ensured:
        return
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS epaper_editions_store (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL DEFAULT '[]'::jsonb,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            INSERT INTO epaper_editions_store (id, data)
            VALUES ('editions', '[]'::jsonb)
            ON CONFLICT (id) DO NOTHING
        """)
        # Per-edition store (v2): one row per (date, language) so a save touches
        # only that edition instead of rewriting the whole ~32 MB blob.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS epaper_editions_v2 (
                edition_date TEXT NOT NULL,
                edition_language TEXT NOT NULL DEFAULT 'Hindi',
                data JSONB NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (edition_date, edition_language)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS epaper_edition_backups (
                id SERIAL PRIMARY KEY,
                edition_date TEXT NOT NULL,
                edition_language TEXT NOT NULL,
                edition_name TEXT,
                pages_count INTEGER DEFAULT 0,
                saved_at TIMESTAMPTZ DEFAULT NOW(),
                snapshot JSONB NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS epaper_edition_views (
                edition_date TEXT NOT NULL,
                edition_language TEXT NOT NULL DEFAULT '',
                view_count BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (edition_date, edition_language)
            )
        """)
    conn.commit()
    _tables_ensured = True


def _save_edition_backup(edition, conn=None):
    """Save a snapshot of one edition to the backup table. Keeps last 30 per edition.
    Accepts an existing conn to avoid opening a second DB connection."""
    if not _pg_url():
        return
    owns_conn = conn is None
    try:
        if owns_conn:
            conn = _pg_connect()
            _pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO epaper_edition_backups
                    (edition_date, edition_language, edition_name, pages_count, snapshot)
                VALUES (%s, %s, %s, %s, %s::jsonb)
            """, (
                edition.get("date", ""),
                edition.get("language", ""),
                edition.get("name", ""),
                len(edition.get("pages", [])),
                json.dumps(edition, ensure_ascii=False),
            ))
            # Keep only last 30 backups per (date, language)
            cur.execute("""
                DELETE FROM epaper_edition_backups
                WHERE id IN (
                    SELECT id FROM epaper_edition_backups
                    WHERE edition_date = %s AND edition_language = %s
                    ORDER BY saved_at DESC
                    OFFSET 30
                )
            """, (edition.get("date", ""), edition.get("language", "")))
        conn.commit()
        if owns_conn:
            conn.close()
    except Exception as e:
        print(f"[epaper] Backup save failed (non-fatal): {e}")


# ── File fallback helpers ───────────────────────────

def _ensure_data_dir():
    d = os.path.dirname(EDITIONS_FILE)
    if d and not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass


def _load_editions_from_file():
    _ensure_data_dir()
    for path in [_EDITIONS_TMP, EDITIONS_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return []


def _save_editions_to_file(data):
    _ensure_data_dir()
    last_exc = None
    for path in [EDITIONS_FILE, _EDITIONS_TMP]:
        try:
            dir_ = os.path.dirname(path)
            if dir_:
                os.makedirs(dir_, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return
        except (PermissionError, OSError) as exc:
            last_exc = exc
            continue
    raise RuntimeError(f"Cannot persist editions to file: {last_exc}")


def _ensure_lock_dir(path):
    lock_dir = os.path.dirname(path) or os.getcwd()
    os.makedirs(lock_dir, exist_ok=True)
    return lock_dir

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

@contextlib.contextmanager
def _exclusive_file_lock(path):
    _ensure_lock_dir(path)
    lock_path = f"{path}.lock"
    with open(lock_path, "a+b") as lock_file:
        if fcntl:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
        elif msvcrt:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            elif msvcrt:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass


# ── Edition view counters ───────────────────────────

EPAPER_VIEWS_FILE = os.path.join(os.path.dirname(__file__), "data", "epaper_views.json")
_EPAPER_VIEWS_TMP = os.path.join(tempfile.gettempdir(), "epaper_views.json")


def _views_key(date, language):
    return f"{date}|{language or ''}"


def _load_views_file():
    for path in [EPAPER_VIEWS_FILE, _EPAPER_VIEWS_TMP]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {}


def _save_views_file(data):
    _ensure_data_dir()
    for path in [EPAPER_VIEWS_FILE, _EPAPER_VIEWS_TMP]:
        try:
            dir_ = os.path.dirname(path)
            if dir_:
                os.makedirs(dir_, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return
        except (PermissionError, OSError):
            continue


def _increment_edition_view(date, language):
    """Increment and return the view count for one edition (keyed by date + language)."""
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO epaper_edition_views (edition_date, edition_language, view_count, updated_at)
                    VALUES (%s, %s, 1, NOW())
                    ON CONFLICT (edition_date, edition_language)
                    DO UPDATE SET view_count = epaper_edition_views.view_count + 1, updated_at = NOW()
                    RETURNING view_count
                """, (date, language or ""))
                count = cur.fetchone()[0]
            conn.commit()
            conn.close()
            return int(count)
        except Exception as e:
            print(f"[epaper] view increment (pg) failed, falling back to file: {e}")

    lock_path = f"{EPAPER_VIEWS_FILE}.lock"
    with _exclusive_file_lock(lock_path):
        data = _load_views_file()
        key = _views_key(date, language)
        data[key] = int(data.get(key, 0)) + 1
        _save_views_file(data)
        return data[key]


# ── Public load / save ──────────────────────────────

def _row_to_edition(row_data):
    """A v2 row's data column → edition dict (handles str or already-parsed jsonb)."""
    return json.loads(row_data) if isinstance(row_data, str) else row_data


def _upsert_edition_row(cur, edition):
    """Upsert a single edition into the per-edition v2 table using an open cursor."""
    cur.execute("""
        INSERT INTO epaper_editions_v2 (edition_date, edition_language, data, updated_at)
        VALUES (%s, %s, %s::jsonb, NOW())
        ON CONFLICT (edition_date, edition_language)
        DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
    """, (
        edition.get("date", ""),
        edition.get("language", "Hindi"),
        json.dumps(edition, ensure_ascii=False),
    ))


def _load_one_edition_pg(conn, date, lang):
    """Read a single edition row from v2. Returns dict or None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT data FROM epaper_editions_v2 WHERE edition_date=%s AND edition_language=%s",
            (date, lang),
        )
        row = cur.fetchone()
    return _row_to_edition(row[0]) if row else None


def _delete_edition_row(date, lang):
    """Explicitly delete ONE edition row from v2 (deletes are never implicit)."""
    if not _pg_url():
        return
    conn = _pg_connect()
    try:
        _pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM epaper_editions_v2 WHERE edition_date=%s AND edition_language=%s",
                (date, lang or "Hindi"),
            )
        conn.commit()
    finally:
        conn.close()


def _load_editions_from_pg():
    """Load editions from epaper_editions_v2. If the legacy epaper_editions_store
    blob has editions not yet in v2 (written by older code), auto-upsert them into
    v2 so the website always shows everything — no manual intervention needed.
    Returns list or None on failure."""
    if not _pg_url():
        return None
    try:
        conn = _pg_connect()
        _pg_ensure_table(conn)

        # Read per-row v2 editions
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM epaper_editions_v2")
            rows = cur.fetchall()
        v2_editions = [_row_to_edition(r[0]) for r in rows] if rows else []
        v2_keys = {_edition_key(e) for e in v2_editions}

        # Check legacy store blob for editions the older code wrote there
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM epaper_editions_store WHERE id = 'editions'")
            store_row = cur.fetchone()

        orphans = []
        if store_row:
            blob = store_row[0]
            if isinstance(blob, str):
                blob = json.loads(blob)
            if isinstance(blob, list):
                orphans = [e for e in blob if _edition_key(e) not in v2_keys]

        if orphans:
            # Auto-heal: upsert missing editions into v2 so they become permanent
            with conn.cursor() as cur:
                for ed in orphans:
                    _upsert_edition_row(cur, ed)
            conn.commit()
            print(f"[epaper] Auto-healed {len(orphans)} editions from store blob into v2")
            v2_editions = v2_editions + orphans

        conn.close()

        if not v2_editions:
            return _load_editions_from_file() or []

        return v2_editions
    except Exception as e:
        print(f"[epaper] Postgres load failed, falling back: {e}")
        return None


def _edition_key(edition):
    return (
        edition.get("date", ""),
        edition.get("language", "Hindi"),
    )


def _public_request_root():
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("X-Forwarded-Host") or request.host or "").split(",")[0].strip()
    if host:
        return f"{proto}://{host}/"
    return request.url_root


def _absolute_public_url(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return raw
    if raw.startswith("//"):
        scheme = (request.headers.get("X-Forwarded-Proto") or request.scheme or "https").split(",")[0].strip()
        return f"{scheme}:{raw}"
    return urllib.parse.urljoin(_public_request_root(), raw)


def _epaper_preview_image_meta(edition):
    pages = (edition or {}).get("pages", []) or []
    first_page = pages[0] if pages else {}
    image_url = ""
    for key in ("page_image_url", "image_path"):
        image_url = _absolute_public_url(first_page.get(key))
        if image_url:
            break
    if not image_url:
        fallback = _absolute_public_url(url_for("static", filename="logo.png"))
        return {
            "url": fallback,
            "type": _epaper_preview_image_type(fallback),
            "width": 512,
            "height": 512,
        }
    parsed = urllib.parse.urlparse(image_url)
    cloudinary_marker = "/image/upload/"
    if parsed.netloc.endswith("cloudinary.com") and cloudinary_marker in parsed.path:
        transformed_path = parsed.path.replace(
            cloudinary_marker,
            "/image/upload/f_jpg,q_auto,c_fill,g_north,w_1200,h_1500/",
            1,
        )
        transformed_url = urllib.parse.urlunparse(parsed._replace(path=transformed_path))
        return {
            "url": transformed_url,
            "type": "image/jpeg",
            "width": 1200,
            "height": 1500,
        }
    return {
        "url": image_url,
        "type": _epaper_preview_image_type(image_url),
        "width": None,
        "height": None,
    }


def _epaper_preview_image_type(image_url):
    path = urllib.parse.urlparse(str(image_url or "")).path.lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _epaper_preview_title(edition, requested_date=None):
    return "Vidyarthi Mitra ePaper - Read Marathi, Hindi & English Newspaper Online"


def _epaper_preview_description(edition):
    language = (edition.get("language") or "").strip() if edition else ""
    edition_date = (edition.get("date") or "").strip() if edition else ""
    base = (
        "Vidyarthi Mitra ePaper: Read today's latest education newspaper online with updates on "
        "entrance exams, results, careers, government jobs, scholarships and student news in "
        "Marathi, Hindi and English."
    )
    if language and edition_date:
        return f"{base} Current featured edition: {language} ePaper dated {edition_date}."
    if language:
        return f"{base} Current featured edition: {language} ePaper."
    return base


def _edition_score(edition):
    pages = edition.get("pages", []) or []
    preview_pages = sum(
        1 for page in pages
        if (page.get("page_image_url") or page.get("image_path") or page.get("blocks"))
    )
    created_at = edition.get("created_at", "") or ""
    return (
        1 if edition.get("published", True) else 0,
        len(pages),
        preview_pages,
        1 if edition.get("masthead_image_url") else 0,
        len(edition.get("footer_links", []) or []),
        created_at,
    )


def _merge_edition_lists(*sources):
    merged = {}
    for source in sources:
        for edition in source or []:
            key = _edition_key(edition)
            current = merged.get(key)
            if current is None or _edition_score(edition) > _edition_score(current):
                merged[key] = edition
    return list(merged.values())


def _load_editions():
    """Load editions with in-memory cache (60s TTL) + parallel Postgres & MongoDB fetch."""
    global _editions_cache, _editions_cache_ts

    # Serve from cache if fresh
    now = time.time()
    with _editions_cache_lock:
        if _editions_cache is not None and (now - _editions_cache_ts) < _EDITIONS_CACHE_TTL:
            return _editions_cache

    # Fetch Postgres and MongoDB in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        pg_future = ex.submit(_load_editions_from_pg)
        mongo_future = ex.submit(_load_editions_from_mongo)
        pg_data = pg_future.result()
        mongo_data = mongo_future.result()

    # Merge sources by edition identity and keep the richer version for duplicates.
    base = pg_data if pg_data is not None else _load_editions_from_file()
    result = _merge_edition_lists(base or [], mongo_data or [])

    # Store in cache
    with _editions_cache_lock:
        _editions_cache = result
        _editions_cache_ts = time.time()

    return result


def _invalidate_editions_cache():
    global _editions_cache, _editions_cache_ts
    with _editions_cache_lock:
        _editions_cache = None
        _editions_cache_ts = 0


def _save_editions(data):
    """Persist a full list of editions by upserting each into the per-edition v2
    table. Upsert-only: rows missing from `data` are NOT deleted here, so a
    momentarily-partial list can never wipe editions. Deletions go through
    _delete_edition_row(). Used by the (rare) publish path; the hot create/update
    path writes a single row directly in api_create_edition()."""
    # Invalidate cache immediately on any save
    _invalidate_editions_cache()
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                for ed in data:
                    _upsert_edition_row(cur, ed)
            conn.commit()
            conn.close()
            # Dual-write to local file so the file fallback stays in sync
            try:
                _save_editions_to_file(data)
            except Exception as fe:
                print(f"[epaper] Local file sync after v2 save failed (non-fatal): {fe}")
            return
        except Exception as e:
            print(f"[epaper] v2 save failed, falling back to file: {e}")
    _save_editions_to_file(data)


def _allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _allowed_upload(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def _article_from_block(block, edition=None, page=None):
    article_id = block.get("article_id") or block.get("id")
    return {
        "id": article_id,
        "article_id": article_id,
        "title": block.get("title") or block.get("headline") or "Untitled article",
        "headline": block.get("headline") or block.get("title") or "Untitled article",
        "slug": block.get("slug") or f"article-{article_id}",
        "content": block.get("content") or block.get("body_text") or "",
        "body_text": block.get("body_text") or block.get("content") or "",
        "body_html": block.get("body_html") or "",
        "author": block.get("author") or "Vidyarthi Mitra Desk",
        "category": block.get("category") or block.get("category_label") or "News",
        "category_label": block.get("category_label") or block.get("category") or "News",
        "image": block.get("image") or block.get("image_url") or block.get("article_image_url") or "",
        "image_url": block.get("image_url") or block.get("image") or block.get("article_image_url") or "",
        "gallery": block.get("gallery") or [],
        "publish_date": (edition or {}).get("date") or block.get("publish_date") or "",
        "edition_name": (edition or {}).get("name") or "",
        "page_number": (page or {}).get("page_number"),
    }


def _iter_epaper_articles():
    for edition in _load_editions():
        for page in edition.get("pages", []):
            sources = page.get("blocks") or page.get("articles", [])
            for block in sources:
                if block.get("type") == "shape":
                    continue
                yield _article_from_block(block, edition, page), edition, page


def _find_epaper_article(article_id):
    target_id = str(article_id)
    articles = []
    article_index = {}
    for article, edition, page in _iter_epaper_articles():
        aid = str(article.get("id"))
        articles.append((article, edition, page))
        article_index[aid] = (article, edition, page)

    if target_id not in article_index:
        return None, [], None, None

    article, edition, page = article_index[target_id]
    category = article.get("category")
    related = [candidate for candidate, _, _ in articles
               if str(candidate.get("id")) != target_id
               and candidate.get("category") == category][:3]
    if len(related) < 3:
        excluded_ids = {target_id} | {str(item.get("id")) for item in related}
        related.extend([
            candidate for candidate, _, _ in articles
            if str(candidate.get("id")) not in excluded_ids
        ][:3 - len(related)])
    return article, related, edition, page


# ── Language-specific viewer — /epaper/english, /epaper/hindi, /epaper/marathi ──
_LANG_SLUG = {"english": "English", "hindi": "Hindi", "marathi": "Marathi"}

@epaper_bp.route("/epaper/english")
@epaper_bp.route("/epaper/english/<date>")
@epaper_bp.route("/epaper/english/<date>/page-<int:page>")
@epaper_bp.route("/epaper/hindi")
@epaper_bp.route("/epaper/hindi/<date>")
@epaper_bp.route("/epaper/hindi/<date>/page-<int:page>")
@epaper_bp.route("/epaper/marathi")
@epaper_bp.route("/epaper/marathi/<date>")
@epaper_bp.route("/epaper/marathi/<date>/page-<int:page>")
def epaper_language_viewer(date=None, page=1):
    import json as _json
    path_parts = request.path.strip("/").split("/")
    language = _LANG_SLUG.get(path_parts[1].lower() if len(path_parts) > 1 else "", "Hindi")

    initial_edition_json = None
    edition = None
    try:
        editions = _load_editions()
        published = [e for e in editions
                     if e.get("published", True)
                     and e.get("language", "Hindi") == language]
        if date:
            edition = next((e for e in published if e["date"] == date), None) or \
                      (sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None)
        else:
            edition = sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None
        if edition:
            initial_edition_json = _json.dumps(edition, ensure_ascii=False).replace('</script>', r'<\/script>')
    except Exception:
        pass
    og_url = _absolute_public_url(request.path)
    og_image_meta = _epaper_preview_image_meta(edition)
    og_title = _epaper_preview_title(edition, date)
    og_description = _epaper_preview_description(edition)
    return render_template("epaper_viewer.html",
                           initial_date=date,
                           initial_page=page,
                           initial_language=language.lower(),
                           initial_edition_json=initial_edition_json if date else None,
                           og_url=og_url,
                           og_image=og_image_meta["url"],
                           og_title=og_title,
                           og_description=og_description,
                           og_image_type=og_image_meta["type"],
                           og_image_width=og_image_meta["width"],
                           og_image_height=og_image_meta["height"],
                           og_image_alt=og_title)


# ── Permanent "latest" redirects — /epaper/latest/<language> ──────────
# Always opens the newest published edition of the requested language.
# 302 (never cached) so a newly published edition is picked up automatically.
# No edition ID or date is ever hardcoded.

def _no_store_redirect(location):
    resp = redirect(location)  # 302 by default — MUST NOT be cached
    resp.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
    return resp


@epaper_bp.route("/epaper/latest/english")
@epaper_bp.route("/epaper/latest/hindi")
@epaper_bp.route("/epaper/latest/marathi")
def epaper_latest_language():
    slug = request.path.rstrip("/").rsplit("/", 1)[-1].lower()
    language = _LANG_SLUG.get(slug)
    if not language:
        return _no_store_redirect(url_for("epaper.epaper_viewer"))

    try:
        editions = _load_editions()
    except Exception:
        editions = []

    # Published + active editions of this language only.
    candidates = [
        e for e in editions
        if e.get("published", True)
        and e.get("active", True)
        and e.get("language", "Hindi") == language
    ]

    if not candidates:
        # No edition for this language yet — fall back to Today's Edition.
        notice = f"No {language} ePaper edition is available yet."
        return _no_store_redirect(url_for("epaper.epaper_viewer", notice=notice))

    # Newest by publication date; tie-break on the created/published timestamp.
    latest = sorted(
        candidates,
        key=lambda e: (str(e.get("date", "")), str(e.get("created_at", ""))),
        reverse=True,
    )[0]

    # Reuse the existing language reader route for that edition's date.
    reader_url = f"/epaper/{slug}/{urllib.parse.quote(str(latest['date']))}"

    # Serve a lightweight page that (a) carries the front-page image as its rich
    # link preview so WhatsApp/Facebook/etc. show the newspaper front page, and
    # (b) instantly forwards real visitors to the reader.
    image_meta = _epaper_preview_image_meta(latest)
    html = render_template(
        "epaper_latest_redirect.html",
        language=language,
        reader_url=reader_url,
        canonical_url=_absolute_public_url(reader_url),
        og_url=_absolute_public_url(request.path),
        og_title=_epaper_preview_title(latest, latest.get("date")),
        og_description=_epaper_preview_description(latest),
        og_image=image_meta["url"],
        og_image_type=image_meta["type"],
        og_image_width=image_meta["width"],
        og_image_height=image_meta["height"],
    )
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
    return resp


# ── Viewer Page ────────────────────────────────────
@epaper_bp.route("/epaper")
@epaper_bp.route("/epaper/<date>")
@epaper_bp.route("/epaper/<date>/page-<int:page>")
def epaper_viewer(date=None, page=1):
    import json as _json
    initial_edition_json = None
    edition = None
    try:
        editions = _load_editions()
        published = [e for e in editions if e.get("published", True)]
        if date:
            edition = next((e for e in published if e["date"] == date), None) or \
                      (sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None)
            if edition:
                initial_edition_json = _json.dumps(edition, ensure_ascii=False).replace('</script>', r'<\/script>')
        else:
            edition = sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None
        if edition and initial_edition_json is None and date:
            initial_edition_json = _json.dumps(edition, ensure_ascii=False).replace('</script>', r'<\/script>')
    except Exception:
        pass
    og_url = _absolute_public_url(request.path)
    og_image_meta = _epaper_preview_image_meta(edition)
    og_image = og_image_meta["url"]
    og_title = _epaper_preview_title(edition, date)
    og_description = _epaper_preview_description(edition)
    og_image_type = og_image_meta["type"]
    return render_template("epaper_viewer.html", initial_date=date, initial_page=page,
                           initial_language='',
                           initial_edition_json=initial_edition_json,
                           og_url=og_url,
                           og_image=og_image,
                           og_title=og_title,
                           og_description=og_description,
                           og_image_type=og_image_type,
                           og_image_width=og_image_meta["width"],
                           og_image_height=og_image_meta["height"],
                           og_image_alt=og_title)


# ── Epaper Admin Login / Logout ───────────────────
@epaper_bp.route("/epaper-admin/login", methods=["GET", "POST"])
def epaper_admin_login():
    if _is_epaper_admin():
        return redirect(url_for("epaper.epaper_admin_v2"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_ok = bool(_EPAPER_ADMIN_USER) and hmac.compare_digest(username, _EPAPER_ADMIN_USER)
        pass_ok = bool(_EPAPER_ADMIN_PASS) and hmac.compare_digest(password, _EPAPER_ADMIN_PASS)
        if user_ok and pass_ok:
            session[_EPAPER_ADMIN_SESSION_KEY] = True
            session.permanent = True
            next_url = request.args.get("next") or url_for("epaper.epaper_admin_v2")
            parsed = urllib.parse.urlparse(next_url)
            if parsed.scheme or parsed.netloc or next_url.startswith("//"):
                next_url = url_for("epaper.epaper_admin_v2")
            elif "?" in next_url:
                next_url = next_url.split("?")[0]
            return redirect(next_url)
        error = "Invalid username or password."
    return render_template("epaper_admin_login.html", error=error)


@epaper_bp.route("/epaper-admin/logout")
def epaper_admin_logout():
    session.pop(_EPAPER_ADMIN_SESSION_KEY, None)
    return redirect(url_for("epaper.epaper_admin_login"))


# ── Admin Page ────────────────────────────────────
@epaper_bp.route("/epaper-admin")
def epaper_admin_v2():
    guard = _require_epaper_admin()
    if guard is not None:
        return guard
    admin_user = session.get("auth_user", {})
    return render_template("epaper_admin_v2.html", admin_user=admin_user)


EPAPER_TMP_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "epaper_uploads")


@epaper_bp.route("/api/epaper/admin/cloudinary-sign", methods=["POST"])
def api_cloudinary_sign():
    """Return signed params for a direct browser→Cloudinary upload (bypasses Vercel size limit)."""
    guard = _require_epaper_admin()
    if guard is not None: return guard
    if not _CLOUDINARY_URL:
        return jsonify({"error": "Cloudinary not configured"}), 503
    try:
        import cloudinary.utils
        import time
        timestamp = int(time.time())
        req_data = request.get_json(silent=True) or {}
        resource_type = req_data.get("resource_type", "auto")
        # resource_type is NOT signed — it's a URL path param in Cloudinary API
        params = {"folder": "epaper", "timestamp": timestamp}
        signature = cloudinary.utils.api_sign_request(params, cloudinary.config().api_secret)
        return jsonify({
            "signature": signature,
            "timestamp": timestamp,
            "api_key": cloudinary.config().api_key,
            "cloud_name": cloudinary.config().cloud_name,
            "folder": "epaper",
            "resource_type": resource_type,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@epaper_bp.route("/api/epaper/admin/upload-image", methods=["POST"])
def api_upload_epaper_image():
    guard = _require_epaper_admin()
    if guard is not None: return guard
    image = request.files.get("image") or request.files.get("file")
    if not image or not image.filename:
        return jsonify({"error": "file required"}), 400
    if not _allowed_upload(image.filename):
        return jsonify({"error": "Unsupported file type. Allowed: images and PDF"}), 400

    original = secure_filename(image.filename)
    stem, ext = os.path.splitext(original)
    ts = datetime.now().strftime('%Y%m%d%H%M%S%f')

    if ext.lower() == ".pdf":
        try:
            import fitz  # PyMuPDF
            pdf_bytes = image.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pg = doc[0]
            mat = fitz.Matrix(4.0, 4.0)
            pix = pg.get_pixmap(matrix=mat)
            doc.close()
            filename = f"{stem[:48]}-{ts}.png"
            file_bytes = pix.tobytes("png")
        except Exception as e:
            return jsonify({"error": f"PDF conversion failed: {str(e)}"}), 500
    else:
        filename = f"{stem[:48]}-{ts}{ext.lower()}"
        file_bytes = image.read()

    # Cloudinary — persistent CDN storage (required on Vercel where filesystem is ephemeral)
    if _CLOUDINARY_URL:
        try:
            url = _upload_to_cloudinary(file_bytes, filename)
            return jsonify({"success": True, "url": url}), 201
        except Exception as e:
            return jsonify({"error": f"Cloudinary upload failed: {e}"}), 500

    # Local fallback: static uploads dir → /tmp (local dev only; /tmp is ephemeral on Vercel)
    for upload_dir, use_tmp in [(EPAPER_UPLOAD_DIR, False), (EPAPER_TMP_UPLOAD_DIR, True)]:
        try:
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as f:
                f.write(file_bytes)
            if use_tmp:
                serve_url = f"/api/epaper/uploads/{filename}"
            else:
                serve_url = url_for("static", filename=f"uploads/epaper/{filename}")
            return jsonify({"success": True, "url": serve_url}), 201
        except (PermissionError, OSError):
            continue

    return jsonify({"error": "Could not save image — filesystem unavailable"}), 500




@epaper_bp.route("/api/epaper/admin/pdf-url-to-pages", methods=["POST"])
def api_pdf_url_to_pages():
    """Convert a PDF already on Cloudinary (URL) to page images. Bypasses Vercel upload limit."""
    guard = _require_epaper_admin()
    if guard is not None: return guard
    data = request.get_json(silent=True) or {}
    pdf_url = data.get("pdf_url", "").strip()
    if not pdf_url:
        return jsonify({"error": "pdf_url required"}), 400
    try:
        import fitz
    except ImportError:
        return jsonify({"error": "PyMuPDF not installed"}), 500
    try:
        from urllib.request import urlopen
        pdf_bytes = urlopen(pdf_url).read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return jsonify({"error": f"Could not fetch/open PDF: {e}"}), 400

    dpi = 120
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    pages_data = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("jpeg", jpg_quality=88)
        pages_data.append((i, img_bytes, f"pdf_page_{ts}_{i+1}.jpg"))
    doc.close()

    if not _CLOUDINARY_URL:
        return jsonify({"error": "Cloudinary not configured"}), 503

    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = [None] * len(pages_data)

    def _upload_page(item):
        idx, img_bytes, filename = item
        url = _upload_to_cloudinary(img_bytes, filename)
        return idx, url

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_upload_page, item): item[0] for item in pages_data}
        for fut in as_completed(futures):
            idx, url = fut.result()
            results[idx] = url

    return jsonify({"success": True, "pages": results})


@epaper_bp.route("/api/epaper/admin/pdf-to-pages", methods=["POST"])
def api_pdf_to_pages():
    guard = _require_epaper_admin()
    if guard is not None: return guard
    pdf_file = request.files.get("pdf")
    if not pdf_file or not pdf_file.filename:
        return jsonify({"error": "PDF file required"}), 400
    if not pdf_file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return jsonify({"error": "PyMuPDF not installed. Run: pip install PyMuPDF"}), 500

    try:
        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return jsonify({"error": f"Could not open PDF: {e}"}), 400

    dpi = 120
    mat = fitz.Matrix(dpi / 72, dpi / 72)

    use_tmp = not os.path.exists(EPAPER_UPLOAD_DIR)
    if use_tmp:
        os.makedirs(EPAPER_TMP_UPLOAD_DIR, exist_ok=True)
    else:
        os.makedirs(EPAPER_UPLOAD_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d%H%M%S")

    # Render all pages to JPEG bytes first (JPEG ~5x smaller than PNG → faster upload)
    pages_data = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("jpeg", jpg_quality=88)
        pages_data.append((i, img_bytes, f"pdf_page_{ts}_{i+1}.jpg"))
    doc.close()

    if _CLOUDINARY_URL:
        # Upload all pages in parallel
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = [None] * len(pages_data)

        def _upload_page(item):
            idx, img_bytes, filename = item
            url = _upload_to_cloudinary(img_bytes, filename)
            return idx, url

        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(_upload_page, item): item[0] for item in pages_data}
            for fut in as_completed(futures):
                idx, url = fut.result()
                results[idx] = url

        page_urls = results
    else:
        page_urls = []
        save_dir = EPAPER_TMP_UPLOAD_DIR if use_tmp else EPAPER_UPLOAD_DIR
        for i, img_bytes, filename in pages_data:
            filepath = os.path.join(save_dir, filename)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
            if use_tmp:
                page_urls.append(f"/api/epaper/uploads/{filename}")
            else:
                page_urls.append(f"/static/uploads/epaper/{filename}")

    return jsonify({"success": True, "pages": page_urls}), 200


@epaper_bp.route("/api/epaper/uploads/<filename>")
def api_serve_tmp_upload(filename):
    """Serve images saved to /tmp (Vercel fallback)."""
    safe = secure_filename(filename)
    filepath = os.path.join(EPAPER_TMP_UPLOAD_DIR, safe)
    if not os.path.exists(filepath):
        return jsonify({"error": "Not found"}), 404
    return send_file(filepath)


@epaper_bp.route("/article/<article_id>")
def epaper_article(article_id):
    article, related, edition, page = _find_epaper_article(article_id)
    if not article:
        return redirect(url_for("epaper.epaper_viewer"))
    return render_template(
        "epaper_article.html",
        article=article,
        related_articles=related,
        edition=edition,
        page=page,
    )


# ── API: List editions ─────────────────────────────
def _edition_preview_url(edition):
    """Return the best preview image for an edition card — first page image or masthead."""
    pages = edition.get("pages", [])
    if pages:
        first = pages[0]
        url = first.get("page_image_url") or first.get("image_path") or ""
        if url:
            return url
    return edition.get("masthead_image_url", "")


def _fast_editions_list_from_pg():
    """Server-side JSON extraction — returns only the metadata fields needed by
    the editions list and calendar. Does NOT load full page/article content, so
    it stays well under Vercel's 10-second function timeout even with 200+ editions."""
    if not _pg_url():
        return None
    try:
        conn = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    edition_date,
                    edition_language,
                    COALESCE(data->>'name', '')                              AS name,
                    COALESCE((data->>'published')::boolean, true)            AS published,
                    COALESCE(data->>'masthead_image_url', '')                AS masthead_image_url,
                    jsonb_array_length(COALESCE(data->'pages','[]'::jsonb))  AS total_pages,
                    COALESCE(
                        data->'pages'->0->>'page_image_url',
                        data->'pages'->0->>'image_path',
                        ''
                    )                                                        AS preview_image_url
                FROM epaper_editions_v2
                ORDER BY edition_date DESC
            """)
            rows = cur.fetchall()
        conn.close()
        if rows is None:
            return []
        return [
            {
                "date":               r[0],
                "language":           r[1] or "Hindi",
                "name":               r[2] or "",
                "published":          r[3] if r[3] is not None else True,
                "masthead_image_url": r[4] or "",
                "total_pages":        r[5] or 0,
                "preview_image_url":  r[6] or "",
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[epaper] Fast editions list failed: {e}")
        return None


@epaper_bp.route("/api/epaper/editions")
def api_editions():
    # Fast path: metadata-only query, never loads full page/article JSON
    fast = _fast_editions_list_from_pg()
    if fast is not None:
        return jsonify({"editions": fast})
    # Fallback: full load (used when DB is unreachable or table missing)
    editions = _load_editions()
    return jsonify({"editions": [
        {
            "date": e["date"],
            "name": e.get("name", ""),
            "language": e.get("language", "Hindi"),
            "total_pages": len(e.get("pages", [])),
            "published": e.get("published", True),
            "masthead_image_url": e.get("masthead_image_url", ""),
            "preview_image_url": _edition_preview_url(e),
        }
        for e in editions
    ]})


# ── API: Latest published edition ─────────────────
@epaper_bp.route("/api/epaper/latest")
def api_latest_edition():
    editions = _load_editions()
    published = [e for e in editions if e.get("published", True)]
    if not published:
        return jsonify({"error": "No published editions."}), 404
    latest = sorted(published, key=lambda e: e["date"], reverse=True)[0]
    return jsonify({
        "date": latest["date"],
        "name": latest.get("name", ""),
        "language": latest.get("language", "Hindi"),
        "masthead_image_url": latest.get("masthead_image_url", ""),
        "footer_links": latest.get("footer_links", []),
        "header_items": latest.get("header_items", []),
        "pages": latest.get("pages", []),
        "published": latest.get("published", True),
    })


# ── API: Publish / Unpublish edition ─────────────
@epaper_bp.route("/api/epaper/admin/edition/<date>/publish", methods=["POST"])
def api_publish_edition(date):
    guard = _require_epaper_admin()
    if guard is not None: return guard
    data = request.get_json(silent=True) or {}
    published = bool(data.get("published", True))
    lang = request.args.get("lang", None)
    editions = _load_editions()
    for e in editions:
        if e["date"] == date and (not lang or e.get("language", "Hindi") == lang):
            e["published"] = published
            try:
                _save_editions(editions)
            except Exception as exc:
                return jsonify({"error": f"Save failed: {exc}"}), 500
            return jsonify({"success": True, "published": published})
    return jsonify({"error": "Edition not found."}), 404


# ── API: Available languages for a date ───────────
@epaper_bp.route("/api/epaper/editions-by-date/<date>")
def api_editions_by_date(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400
    editions = _load_editions()
    matches = [
        {"language": e.get("language", "Hindi"), "name": e.get("name", "")}
        for e in editions
        if e["date"] == date and e.get("published", True)
    ]
    return jsonify({"editions": matches})


# ── API: Get edition by date ───────────────────────
@epaper_bp.route("/api/epaper/edition/<date>")
def api_edition(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    lang = request.args.get("lang", None)
    editions = _load_editions()

    if lang:
        edition = next(
            (e for e in editions if e["date"] == date and e.get("published", True) and e.get("language", "Hindi") == lang),
            None,
        )
        # Fallback to first published edition for that date if exact language not found
        if not edition:
            edition = next((e for e in editions if e["date"] == date and e.get("published", True)), None)
    else:
        edition = next((e for e in editions if e["date"] == date and e.get("published", True)), None)

    if not edition:
        return jsonify({"error": "No edition for this date."}), 404

    return jsonify({
        "date": edition["date"],
        "name": edition.get("name", ""),
        "language": edition.get("language", "Hindi"),
        "masthead_image_url": edition.get("masthead_image_url", ""),
        "footer_links": edition.get("footer_links", []),
        "header_items": edition.get("header_items", []),
        "pages": edition.get("pages", []),
    })


# ── API: Record an edition view ───────────────────
@epaper_bp.route("/api/epaper/edition/<date>/view", methods=["POST"])
def api_record_edition_view(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400
    language = request.args.get("lang", "")
    count = _increment_edition_view(date, language)
    return jsonify({"date": date, "language": language, "views": count})


# ── API: Get edition view count (no increment) ────
@epaper_bp.route("/api/epaper/edition/<date>/views", methods=["GET"])
def api_get_edition_views(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400
    language = request.args.get("lang", "")
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT view_count FROM epaper_edition_views WHERE edition_date=%s AND edition_language=%s",
                    (date, language or "")
                )
                row = cur.fetchone()
            conn.close()
            count = int(row[0]) if row else 0
            return jsonify({"date": date, "language": language, "views": count})
        except Exception as e:
            print(f"[epaper] get views failed: {e}")
    data = _load_views_file()
    count = int(data.get(_views_key(date, language), 0))
    return jsonify({"date": date, "language": language, "views": count})


# ── API: Get article ──────────────────────────────
@epaper_bp.route("/api/epaper/article/<article_id>")
def api_article(article_id):
    article, related, edition, page = _find_epaper_article(article_id)
    if article:
        return jsonify({**article, "related_articles": related})
    return jsonify({"error": "Article not found."}), 404


# ── API: Create / Update edition (Admin) ───────────
@epaper_bp.route("/api/epaper/admin/edition", methods=["POST"])
def api_create_edition():
    guard = _require_epaper_admin()
    if guard is not None: return guard
    # force=True so Flask parses even if Content-Type isn't exactly application/json
    data = request.get_json(force=True, silent=True) or {}
    date_str = (data.get("date", "") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": f"Invalid date: '{date_str}'. Expected YYYY-MM-DD."}), 400

    lang_str = data.get("language", "Hindi")
    original_date = data.get("original_date", "")
    original_lang = data.get("original_lang", "")
    renamed = bool(original_date) and (original_date != date_str or original_lang != lang_str)

    def _apply_payload(existing):
        """Merge the request payload onto an existing edition (or build a new one),
        preserving fields the client did not send."""
        if existing is None:
            return {
                "date": date_str,
                "name": data.get("name", f"Edition {date_str}"),
                "language": data.get("language", "Hindi"),
                "published": data.get("published", True),
                "masthead_image_url": data.get("masthead_image_url", ""),
                "footer_links": data.get("footer_links", []),
                "header_items": data.get("header_items", []),
                "pages": data.get("pages", []),
                "created_at": datetime.now().isoformat(),
            }
        existing["date"] = date_str
        existing["name"] = data.get("name", existing.get("name", ""))
        existing["language"] = data.get("language", existing.get("language", "Hindi"))
        existing["published"] = data.get("published", existing.get("published", True))
        existing["masthead_image_url"] = data.get("masthead_image_url", existing.get("masthead_image_url", ""))
        if "footer_links" in data:
            existing["footer_links"] = data["footer_links"]
        if "header_items" in data:
            existing["header_items"] = data["header_items"]
        if "pages" in data:
            existing["pages"] = data["pages"]
        return existing

    _invalidate_editions_cache()

    # ── Fast path: write only THIS edition's row (no 32 MB rewrite) ──
    if _pg_url():
        conn = None
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            existing = _load_one_edition_pg(conn, date_str, lang_str)
            saved_edition = _apply_payload(existing)
            with conn.cursor() as cur:
                _upsert_edition_row(cur, saved_edition)
                # We deliberately DO NOT delete the "original" edition when the
                # date/language changes. Editing an edition and changing its date
                # used to move (delete) the old one, which silently wiped editions
                # (e.g. edit 131 -> change date -> 131 vanishes). Now a changed
                # date just creates a NEW edition; the old one stays. Deletion
                # happens ONLY via the explicit Delete button.
            conn.commit()
            # Reuse same connection for the per-edition snapshot backup
            _save_edition_backup(saved_edition, conn=conn)
            conn.close()
            return jsonify({"success": True}), 201
        except Exception as exc:
            if conn:
                try: conn.close()
                except: pass
            return jsonify({"error": f"Save failed: {exc}"}), 500

    # ── File-only fallback (no Postgres configured) ──
    editions = _load_editions_from_file()
    # No rename-delete: a changed date creates a new edition; the old one stays.
    existing = next(
        (e for e in editions if e["date"] == date_str and e.get("language", "Hindi") == lang_str),
        None,
    )
    if existing:
        saved_edition = _apply_payload(existing)
    else:
        saved_edition = _apply_payload(None)
        editions.append(saved_edition)
    try:
        _save_editions_to_file(editions)
    except Exception as exc:
        return jsonify({"error": f"Save failed: {exc}"}), 500
    _save_edition_backup(saved_edition)
    return jsonify({"success": True}), 201


# ── API: Get edition (admin — no published filter) ────
@epaper_bp.route("/api/epaper/admin/edition/<date>", methods=["GET"])
def api_get_edition_admin(date):
    guard = _require_epaper_admin()
    if guard is not None: return guard
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400
    lang = request.args.get("lang", None)
    editions = _load_editions()
    if lang:
        edition = next(
            (e for e in editions if e["date"] == date and e.get("language", "Hindi") == lang),
            None,
        )
        if not edition:
            edition = next((e for e in editions if e["date"] == date), None)
    else:
        edition = next((e for e in editions if e["date"] == date), None)
    if not edition:
        return jsonify({"error": "No edition for this date."}), 404
    return jsonify({
        "date": edition["date"],
        "name": edition.get("name", ""),
        "language": edition.get("language", "Hindi"),
        "masthead_image_url": edition.get("masthead_image_url", ""),
        "footer_links": edition.get("footer_links", []),
        "header_items": edition.get("header_items", []),
        "pages": edition.get("pages", []),
        "published": edition.get("published", True),
    })


# ── API: Delete edition ───────────────────────────
@epaper_bp.route("/api/epaper/admin/edition/<date>", methods=["DELETE"])
def api_delete_edition(date):
    guard = _require_epaper_admin()
    if guard is not None: return guard
    lang = request.args.get("lang", None)
    if not lang:
        return jsonify({"error": "Language parameter required for deletion."}), 400
    editions = _load_editions()
    remaining = [e for e in editions if not (e["date"] == date and e.get("language", "Hindi") == lang)]
    if len(remaining) == len(editions):
        return jsonify({"error": f"No edition found for date={date} lang={lang}"}), 404
    try:
        _delete_edition_row(date, lang)          # explicit single-row delete in v2
        _invalidate_editions_cache()
        # Keep the file fallback in sync (best-effort)
        try:
            _save_editions_to_file(remaining)
        except Exception as fe:
            print(f"[epaper] Local file sync after delete failed (non-fatal): {fe}")
    except Exception as exc:
        return jsonify({"error": f"Delete failed: {exc}"}), 500
    return jsonify({"success": True})


# ── AI: Translate ──────────────────────────────────
@epaper_bp.route("/api/epaper/translate", methods=["POST"])
def api_translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    target = data.get("target_lang", "en")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    # Check cache first
    ck = _trans_cache_key(text, target)
    if ck in _trans_cache:
        _trans_cache.move_to_end(ck)
        return jsonify({"translated_text": _trans_cache[ck]})

    lang_names = {
        'hi': 'Hindi', 'mr': 'Marathi', 'en': 'English',
        'bn': 'Bengali', 'ta': 'Tamil', 'te': 'Telugu',
        'gu': 'Gujarati', 'kn': 'Kannada', 'ml': 'Malayalam', 'ur': 'Urdu',
    }
    target_name = lang_names.get(target, target)

    def _save_cache(translated):
        _evict(_trans_cache, _TRANS_CACHE_MAX)
        _trans_cache[ck] = translated

    fast_error = None
    # ── Fast path: deep_translator (Google Translate, no API key, near-instant) ──
    try:
        from deep_translator import GoogleTranslator
        chunks, start = [], 0
        while start < len(text):
            end = min(start + 4500, len(text))
            if end < len(text):
                for sep in ('। ', '. ', '\n', ' '):
                    pos = text.rfind(sep, start, end)
                    if pos > start:
                        end = pos + len(sep)
                        break
            chunks.append(text[start:end].strip())
            start = end
        translated_chunks = [
            GoogleTranslator(source="auto", target=target).translate(c) or c
            for c in chunks if c
        ]
        result = "\n\n".join(translated_chunks)
        _save_cache(result)
        return jsonify({"translated_text": result})
    except Exception as exc:
        fast_error = f"Google Translate path failed: {str(exc)}"

    # ── Fallback: Groq LLM (higher quality but slower) ──
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are a professional translator. Translate the following text to {target_name}. "
                            "Return ONLY the translated text — no explanations, no notes, no extra lines."
                        ),
                    },
                    {"role": "user", "content": text[:3500]},
                ],
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                temperature=0.1,
                max_tokens=2000,
            )
            translated = response.choices[0].message.content.strip()
            _save_cache(translated)
            return jsonify({"translated_text": translated})
        except Exception as exc:
            return jsonify({"error": f"Groq translation fallback failed: {str(exc)}"}), 500

    return jsonify({"error": fast_error or "Translation failed after all translation providers."}), 500


# ── AI: Summarize ──────────────────────────────────
@epaper_bp.route("/api/epaper/summarize", methods=["POST"])
def api_summarize():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    # Smart extractive summary with sentence scoring
    sentences = [s.strip() for s in re.split(r'[।.!?\n]+', text) if s.strip() and len(s.strip()) > 10]

    if not sentences:
        return jsonify({"summary": [text[:200]]})

    if len(sentences) <= 3:
        return jsonify({"summary": sentences})

    # Build word frequency map (skip common Hindi/English stopwords)
    stopwords = {'का', 'की', 'के', 'में', 'है', 'हैं', 'को', 'से', 'और', 'पर', 'ने',
                 'एक', 'यह', 'वह', 'भी', 'इस', 'the', 'is', 'a', 'an', 'of', 'in',
                 'to', 'for', 'and', 'on', 'with', 'that', 'this', 'it', 'are', 'was'}
    words = re.findall(r'\w+', text.lower())
    freq = {}
    for w in words:
        if w not in stopwords and len(w) > 2:
            freq[w] = freq.get(w, 0) + 1

    max_freq = max(freq.values()) if freq else 1

    # Score each sentence
    scored = []
    for i, sent in enumerate(sentences):
        score = 0
        sent_words = re.findall(r'\w+', sent.lower())
        # Word importance score
        for w in sent_words:
            score += freq.get(w, 0) / max_freq
        # Position bonus (first and last sentences matter more)
        if i == 0:
            score += 3
        elif i == len(sentences) - 1:
            score += 1.5
        elif i < 3:
            score += 1
        # Length bonus (prefer medium-length sentences)
        if 20 < len(sent) < 150:
            score += 0.5
        # Number bonus (sentences with numbers are often key facts)
        if re.search(r'\d', sent):
            score += 1

        scored.append((score, i, sent))

    # Pick top 4-5 sentences, maintain original order
    scored.sort(key=lambda x: x[0], reverse=True)
    top = sorted(scored[:5], key=lambda x: x[1])
    summary = [s[2] for s in top]

    return jsonify({"summary": summary})


# ── AI: TTS (Edge Neural Voices — Real Indian Anchor) ───────────────────────────────────

def _preprocess_tts_text(text):
    """Shared text preprocessing for natural TTS delivery."""
    _abbr_map = {
        'JEE': 'जे ई ई', 'NEET': 'नीट', 'IIT': 'आई आई टी',
        'IIM': 'आई आई एम', 'NIT': 'एन आई टी',
        'CM': 'मुख्यमंत्री', 'PM': 'प्रधानमंत्री',
        'BJP': 'बी जे पी', 'RSS': 'आर एस एस',
        'CBSE': 'सी बी एस ई', 'SSC': 'एस एस सी', 'HSC': 'एच एस सी',
        'CET': 'सी ई टी', 'DTE': 'डी टी ई',
    }
    for abbr, expansion in _abbr_map.items():
        text = re.sub(rf'\b{abbr}\b', expansion, text)

    def _rupee_to_words(m):
        n = int(m.group(1).replace(',', ''))
        if n >= 10000000: return f"{n/10000000:.1f} करोड़ रुपये"
        if n >= 100000: return f"{n/100000:.1f} लाख रुपये"
        if n >= 1000: return f"{n/1000:.0f} हज़ार रुपये"
        return f"{n} रुपये"
    text = re.sub(r'₹\s?(\d[\d,]*)', _rupee_to_words, text)
    text = re.sub(r'(\d+)%', r'\1 प्रतिशत', text)
    text = re.sub(r'।\s*', '। ... ', text)
    text = re.sub(r'\.\s+', '. ... ', text)
    return text


def _resolve_voice(text, voice, rate, pitch):
    """Auto-detect voice from text language if not specified."""
    devanagari_ratio = len(re.findall(r'[ऀ-ॿ]', text)) / max(len(text), 1)
    MARATHI_WORDS = ['आहे', 'नाही', 'आणि', 'मला', 'आपण', 'होते', 'केले', 'झाले',
                     'त्यांनी', 'म्हणाले', 'महाराष्ट्र', 'पुणे', 'मुंबई', 'नागपूर']
    HINDI_WORDS = ['है', 'नहीं', 'और', 'था', 'हैं', 'यह', 'हो', 'उन्होंने', 'कहा', 'बताया']
    marathi_hits = sum(1 for w in MARATHI_WORDS if w in text)
    hindi_hits = sum(1 for w in HINDI_WORDS if w in text)

    if not voice:
        if devanagari_ratio > 0.3:
            voice = "mr-IN-ManoharNeural" if marathi_hits > hindi_hits else "hi-IN-MadhurNeural"
            if rate == "+0%": rate = "-2%"
            if pitch == "+0Hz": pitch = "+2Hz"
        else:
            voice = "en-IN-PrabhatNeural"
            if rate == "+0%": rate = "-2%"
            if pitch == "+0Hz": pitch = "+1Hz"
    else:
        _defaults = {
            "hi-IN-MadhurNeural": ("-2%", "+2Hz"), "hi-IN-SwaraNeural": ("-1%", "+1Hz"),
            "mr-IN-ManoharNeural": ("-2%", "+2Hz"), "mr-IN-AarohiNeural": ("-1%", "+1Hz"),
            "gu-IN-NiranjanNeural": ("-2%", "+2Hz"), "gu-IN-DhwaniNeural": ("-1%", "+1Hz"),
            "bn-IN-BashkarNeural": ("-2%", "+2Hz"), "bn-IN-TanishaaNeural": ("-1%", "+1Hz"),
            "ta-IN-ValluvarNeural": ("-2%", "+2Hz"), "ta-IN-PallaviNeural": ("-1%", "+1Hz"),
            "te-IN-MohanNeural": ("-2%", "+2Hz"), "te-IN-ShrutiNeural": ("-1%", "+1Hz"),
            "kn-IN-GaganNeural": ("-2%", "+2Hz"), "kn-IN-SapnaNeural": ("-1%", "+1Hz"),
            "ml-IN-MidhunNeural": ("-2%", "+2Hz"), "ml-IN-SobhanaNeural": ("-1%", "+1Hz"),
            "ur-IN-SalmanNeural": ("-2%", "+2Hz"), "ur-PK-AsadNeural": ("-2%", "+2Hz"),
            "ur-PK-UzmaNeural": ("-1%", "+1Hz"), "en-IN-PrabhatNeural": ("-2%", "+1Hz"),
            "en-IN-NeerjaNeural": ("-1%", "+1Hz"),
        }
        if voice in _defaults and rate == "+0%" and pitch == "+0Hz":
            rate, pitch = _defaults[voice]

    if isinstance(rate, (int, float)):
        pct = int((rate - 1) * 100)
        rate = f"+{pct}%" if pct >= 0 else f"{pct}%"
    return voice, rate, pitch


def _collect_edge_tts_audio(text, voice, rate, pitch):
    """Run edge_tts in a thread and return all audio as bytes. Raises on failure."""
    chunks = []
    error_holder = []

    async def _async():
        import edge_tts
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])

    def _run():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async())
        except Exception as exc:
            error_holder.append(exc)
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=25)

    if t.is_alive():
        raise TimeoutError("TTS generation timed out")
    if error_holder:
        raise error_holder[0]
    if not chunks:
        raise RuntimeError("TTS returned no audio data")
    return b"".join(chunks)


@epaper_bp.route("/api/epaper/tts", methods=["POST"])
def api_tts():
    """Server-side TTS using Microsoft Edge Neural voices."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    voice = data.get("voice", "")
    rate = data.get("rate", "+0%")
    pitch = data.get("pitch", "+0Hz")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    text = text[:5000]
    text = _preprocess_tts_text(text)
    voice, rate, pitch = _resolve_voice(text, voice, rate, pitch)

    ck = _tts_cache_key(text, voice, rate, pitch)

    # Serve from cache
    if ck in _tts_cache:
        _tts_cache.move_to_end(ck)
        return send_file(io.BytesIO(_tts_cache[ck]), mimetype="audio/mpeg",
                         as_attachment=False, download_name="tts_audio.mp3")

    # Collect all audio first — ensures exceptions surface as proper JSON errors
    try:
        audio_bytes = _collect_edge_tts_audio(text, voice, rate, pitch)
    except Exception as e:
        print(f"[TTS] edge_tts failed: {e}")
        return jsonify({"error": f"TTS unavailable: {str(e)}"}), 500

    _evict(_tts_cache, _TTS_CACHE_MAX)
    _tts_cache[ck] = audio_bytes
    return send_file(io.BytesIO(audio_bytes), mimetype="audio/mpeg",
                     as_attachment=False, download_name="tts_audio.mp3")


# ── API: Available TTS voices ───────────────────────
@epaper_bp.route("/api/epaper/tts/voices")
def api_tts_voices():
    return jsonify({"voices": [
        {"id": "hi-IN-MadhurNeural",  "name": "माधुर (Hindi Male)",     "lang": "hi", "gender": "male",   "style": "News Anchor"},
        {"id": "hi-IN-SwaraNeural",   "name": "स्वरा (Hindi Female)",   "lang": "hi", "gender": "female", "style": "News Anchor"},
        {"id": "mr-IN-ManoharNeural", "name": "मनोहर (Marathi Male)",   "lang": "mr", "gender": "male",   "style": "News Anchor"},
        {"id": "mr-IN-AarohiNeural",  "name": "आरोही (Marathi Female)", "lang": "mr", "gender": "female", "style": "Professional"},
        {"id": "en-IN-PrabhatNeural", "name": "Prabhat (English Male)",  "lang": "en", "gender": "male",   "style": "News Anchor"},
        {"id": "en-IN-NeerjaNeural",  "name": "Neerja (English Female)", "lang": "en", "gender": "female", "style": "Professional"},
    ]})


# ── Re-sync: merge editions_store blob into v2 rows ──────────────────────────
# One-time fix for editions added while legacy (vansh-dev) code was in production.
# Safe to call multiple times — only upserts, never deletes.
@epaper_bp.route("/api/epaper/admin/resync-editions-store", methods=["POST"])
def api_resync_editions_store():
    guard = _require_epaper_admin()
    if guard is not None: return guard
    if not _pg_url():
        return jsonify({"error": "Database not configured"}), 500
    try:
        conn = _pg_connect()
        _pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM epaper_editions_store WHERE id = 'editions'")
            row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"synced": 0, "message": "epaper_editions_store has no editions blob — nothing to sync"})
        blob = row[0]
        if isinstance(blob, str):
            blob = json.loads(blob)
        if not isinstance(blob, list):
            conn.close()
            return jsonify({"error": "Unexpected data format in editions_store"}), 500

        # Get existing v2 keys so we can count what's new
        with conn.cursor() as cur:
            cur.execute("SELECT edition_date, edition_language FROM epaper_editions_v2")
            existing = {(r[0], r[1]) for r in cur.fetchall()}

        new_count = 0
        with conn.cursor() as cur:
            for ed in blob:
                _upsert_edition_row(cur, ed)
                key = (ed.get("date", ""), ed.get("language", "Hindi"))
                if key not in existing:
                    new_count += 1
        conn.commit()
        conn.close()
        _invalidate_editions_cache()
        return jsonify({
            "synced": len(blob),
            "new": new_count,
            "message": f"Merged {len(blob)} editions from store blob into v2 ({new_count} were new/updated)",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Backup: list backups for an edition ───────────────
@epaper_bp.route("/api/epaper/admin/backups")
def api_list_backups():
    guard = _require_epaper_admin()
    if guard is not None: return guard
    if not _pg_url():
        return jsonify({"backups": []})
    date = request.args.get("date", "")
    lang = request.args.get("lang", "")
    try:
        conn = _pg_connect()
        _pg_ensure_table(conn)
        with conn.cursor() as cur:
            if date and lang:
                cur.execute("""
                    SELECT id, edition_date, edition_language, edition_name,
                           pages_count, saved_at
                    FROM epaper_edition_backups
                    WHERE edition_date = %s AND edition_language = %s
                    ORDER BY saved_at DESC LIMIT 30
                """, (date, lang))
            else:
                cur.execute("""
                    SELECT DISTINCT ON (edition_date, edition_language)
                           id, edition_date, edition_language, edition_name,
                           pages_count, saved_at
                    FROM epaper_edition_backups
                    ORDER BY edition_date DESC, edition_language, saved_at DESC
                    LIMIT 50
                """)
            rows = cur.fetchall()
        conn.close()
        backups = [
            {"id": r[0], "date": r[1], "language": r[2], "name": r[3],
             "pages": r[4], "saved_at": r[5].isoformat() if r[5] else ""}
            for r in rows
        ]
        return jsonify({"backups": backups})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Backup: restore a specific backup ─────────────────
@epaper_bp.route("/api/epaper/admin/backups/<int:backup_id>/restore", methods=["POST"])
def api_restore_backup(backup_id):
    guard = _require_epaper_admin()
    if guard is not None: return guard
    if not _pg_url():
        return jsonify({"error": "Database not configured"}), 500
    try:
        conn = _pg_connect()
        _pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT snapshot FROM epaper_edition_backups WHERE id = %s", (backup_id,))
            row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Backup not found"}), 404
        edition = row[0]
        if isinstance(edition, str):
            edition = json.loads(edition)

        # Restore = upsert just this one edition's row in v2
        with conn.cursor() as cur:
            _upsert_edition_row(cur, edition)
        conn.commit()
        conn.close()
        _invalidate_editions_cache()
        return jsonify({"success": True,
                        "message": f"Edition {edition.get('date')} ({edition.get('language')}) restored successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Diagnostics: where do editions survive across every store? (read-only) ──
@epaper_bp.route("/api/epaper/admin/diagnostics")
def api_epaper_diagnostics():
    guard = _require_epaper_admin()
    if guard is not None:
        return guard

    def _summary(editions):
        eds = editions or []
        dates = sorted({str(e.get("date", "")) for e in eds if e.get("date")})
        return {
            "count": len(eds),
            "distinct_dates": len(dates),
            "min_date": dates[0] if dates else None,
            "max_date": dates[-1] if dates else None,
            "last_10_dates": dates[-10:],
        }

    out = {}

    # Postgres: v2 per-edition rows, backups table, legacy blob
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM epaper_editions_v2")
                v2 = [_row_to_edition(r[0]) for r in cur.fetchall()]
                out["postgres_v2"] = _summary(v2)

                cur.execute("""
                    SELECT COUNT(*), COUNT(DISTINCT (edition_date, edition_language)),
                           MIN(edition_date), MAX(edition_date)
                    FROM epaper_edition_backups
                """)
                bc, bd, bmn, bmx = cur.fetchone()
                cur.execute("""
                    SELECT DISTINCT edition_date FROM epaper_edition_backups
                    ORDER BY edition_date DESC LIMIT 10
                """)
                b_last = [r[0] for r in cur.fetchall()]
                out["backups_table"] = {
                    "snapshots": bc, "distinct_editions": bd,
                    "min_date": bmn, "max_date": bmx, "last_10_dates": b_last,
                }

                cur.execute("SELECT data FROM epaper_editions_store WHERE id = 'editions'")
                row = cur.fetchone()
                blob = row[0] if row else []
                if isinstance(blob, str):
                    blob = json.loads(blob)
                out["legacy_blob"] = _summary(blob)
            conn.close()
        except Exception as e:
            out["postgres_error"] = str(e)
    else:
        out["postgres"] = "not configured"

    # MongoDB read-only mirror
    try:
        out["mongodb"] = _summary(_load_editions_from_mongo())
    except Exception as e:
        out["mongo_error"] = str(e)

    # Local file fallback (bundled/ephemeral)
    try:
        out["local_file"] = _summary(_load_editions_from_file())
    except Exception as e:
        out["file_error"] = str(e)

    # What the site actually shows after merging everything
    try:
        out["what_site_shows"] = _summary(_load_editions())
    except Exception as e:
        out["merge_error"] = str(e)

    return jsonify(out)


# ── Recovery: restore every edition that exists in backups but is missing from
# the live v2 store (safe & idempotent — only ADDS missing editions, never
# deletes or overwrites what's already live). ──
@epaper_bp.route("/api/epaper/admin/restore-all-missing", methods=["GET", "POST"])
def api_restore_all_missing():
    guard = _require_epaper_admin()
    if guard is not None:
        return guard
    if not _pg_url():
        return jsonify({"error": "Database not configured."}), 500

    conn = None
    try:
        conn = _pg_connect()
        _pg_ensure_table(conn)
        with conn.cursor() as cur:
            # (date, language) pairs already live in v2
            cur.execute("SELECT edition_date, edition_language FROM epaper_editions_v2")
            live = {(r[0], r[1]) for r in cur.fetchall()}

            # Latest backup snapshot per (date, language)
            cur.execute("""
                SELECT DISTINCT ON (edition_date, edition_language)
                       edition_date, edition_language, snapshot
                FROM epaper_edition_backups
                ORDER BY edition_date, edition_language, saved_at DESC
            """)
            rows = cur.fetchall()

            restored = []
            for date, lang, snap in rows:
                if (date, lang) in live:
                    continue  # already present — never overwrite live data
                edition = snap if not isinstance(snap, str) else json.loads(snap)
                _upsert_edition_row(cur, edition)
                restored.append(f"{date} ({lang})")
        conn.commit()
        conn.close()
        _invalidate_editions_cache()
        return jsonify({
            "success": True,
            "restored_count": len(restored),
            "restored": sorted(restored, reverse=True),
        })
    except Exception as exc:
        if conn:
            try: conn.close()
            except: pass
        return jsonify({"error": str(exc)}), 500


@epaper_bp.route("/api/supabase/keepalive")
def api_supabase_keepalive():
    if not _pg_url():
        return jsonify({"error": "Database not configured."}), 500
    try:
        conn = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM epaper_editions_store")
            count = cur.fetchone()[0]
        conn.close()
        return jsonify({"success": True, "editions": count})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
