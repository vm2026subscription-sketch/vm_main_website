"""
E-Paper storage layer: Redis, MongoDB, Postgres, file I/O, Cloudinary, cache management.
"""
import contextlib
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from epaper_config import (
    editions_cache, editions_cache_ts, EDITIONS_CACHE_TTL, editions_cache_lock,
    REDIS_EDITIONS_KEY, REDIS_EDITIONS_TTL, REDIS_LATEST_KEY, REDIS_LATEST_TTL,
    redis_client, redis_client_lock,
    mongo_client, mongo_client_lock, mongo_disabled,
    CLOUDINARY_URL, EDITIONS_FILE, EDITIONS_TMP, EPAPER_VIEWS_FILE, EPAPER_VIEWS_TMP,
)

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None


# ── Redis helpers ─────────────────────────────────────────────

def get_redis():
    """Return a cached Upstash Redis client, or None if not configured."""
    global redis_client
    if redis_client is not None:
        return redis_client
    url = os.getenv("UPSTASH_REDIS_REST_URL", "")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    if not url or not token:
        return None
    with redis_client_lock:
        if redis_client is None:
            try:
                from upstash_redis import Redis
                redis_client = Redis(url=url, token=token)
            except Exception as e:
                print(f"[redis] init failed: {e}")
                return None
    return redis_client


def redis_get(key):
    """Get a JSON value from Redis. Returns parsed object or None."""
    r = get_redis()
    if not r:
        return None
    try:
        val = r.get(key)
        return json.loads(val) if val else None
    except Exception as e:
        print(f"[redis] get {key} failed: {e}")
        return None


def redis_set(key, value, ttl=300):
    """Set a JSON value in Redis with TTL (seconds)."""
    r = get_redis()
    if not r:
        return
    try:
        r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as e:
        print(f"[redis] set {key} failed: {e}")


def redis_delete(*keys):
    """Delete one or more keys from Redis."""
    r = get_redis()
    if not r:
        return
    try:
        r.delete(*keys)
    except Exception as e:
        print(f"[redis] delete failed: {e}")


# ── MongoDB helpers ───────────────────────────────────────────

def _mongo_url():
    return os.getenv("MONGODB_URI", "")


def get_mongo_client():
    """Return a cached global MongoClient (created once, reused across requests)."""
    global mongo_client
    if mongo_disabled:
        return None
    url = _mongo_url()
    if not url:
        return None
    if mongo_client is None:
        with mongo_client_lock:
            if mongo_client is None:
                try:
                    from pymongo import MongoClient
                    mongo_client = MongoClient(
                        url,
                        serverSelectionTimeoutMS=3000,
                        connectTimeoutMS=3000,
                        socketTimeoutMS=5000,
                        maxPoolSize=5,
                    )
                except Exception as e:
                    print(f"[epaper] MongoDB client init failed: {e}")
                    return None
    return mongo_client


def load_editions_from_mongo():
    """Read editions from MongoDB (Railway admin's database). Read-only -- never writes."""
    global mongo_disabled
    if mongo_disabled:
        return []
    client = get_mongo_client()
    if not client:
        return []
    try:
        db_name = os.getenv("MONGODB_DB", "vm")
        col_name = os.getenv("MONGODB_COLLECTION", "editions")
        docs = list(client[db_name][col_name].find({}, {"_id": 0}))
        return docs
    except Exception as e:
        print(f"[epaper] MongoDB load failed: {e}")
        if "auth" in str(e).lower() or "timeout" in str(e).lower() or "connection" in str(e).lower():
            print("[epaper] MongoDB disabled globally to prevent further timeouts.")
            mongo_disabled = True
        return []


# ── Postgres (Supabase) helpers ──────────────────────────────

def pg_url():
    return os.getenv("SUPABASE_POSTGRES_URL") or os.getenv("DATABASE_URL")


def pg_connect():
    import psycopg2
    url = os.getenv("SUPABASE_POOLER_URL") or pg_url()
    conn = psycopg2.connect(
        url,
        connect_timeout=8,
        options="-c statement_timeout=25000",
    )
    conn.autocommit = False
    return conn


# Skip repeated DDL on warm instances -- reset to False on cold start
_tables_ensured = False


def pg_ensure_table(conn):
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


def save_edition_backup(edition, conn=None):
    """Save a snapshot of one edition to the backup table. Keeps last 30 per edition."""
    if not pg_url():
        return
    owns_conn = conn is None
    try:
        if owns_conn:
            conn = pg_connect()
            pg_ensure_table(conn)
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


# ── File fallback helpers ─────────────────────────────────────

def ensure_data_dir():
    d = os.path.dirname(EDITIONS_FILE)
    if d and not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass


def load_editions_from_file():
    ensure_data_dir()
    for path in [EDITIONS_TMP, EDITIONS_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return []


def save_editions_to_file(data):
    ensure_data_dir()
    last_exc = None
    for path in [EDITIONS_FILE, EDITIONS_TMP]:
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


def ensure_lock_dir(path):
    lock_dir = os.path.dirname(path) or os.getcwd()
    os.makedirs(lock_dir, exist_ok=True)
    return lock_dir


@contextlib.contextmanager
def exclusive_file_lock(path):
    ensure_lock_dir(path)
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


# ── Edition view counters ─────────────────────────────────────

def views_key(date, language):
    return f"{date}|{language or ''}"


def load_views_file():
    for path in [EPAPER_VIEWS_FILE, EPAPER_VIEWS_TMP]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {}


def save_views_file(data):
    ensure_data_dir()
    for path in [EPAPER_VIEWS_FILE, EPAPER_VIEWS_TMP]:
        try:
            dir_ = os.path.dirname(path)
            if dir_:
                os.makedirs(dir_, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return
        except (PermissionError, OSError):
            continue


def increment_edition_view(date, language):
    """Increment and return the view count for one edition."""
    if pg_url():
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
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
    with exclusive_file_lock(lock_path):
        data = load_views_file()
        key = views_key(date, language)
        data[key] = int(data.get(key, 0)) + 1
        save_views_file(data)
        return data[key]


# ── Edition data helpers ──────────────────────────────────────

def row_to_edition(row_data):
    """A v2 row's data column -> edition dict."""
    return json.loads(row_data) if isinstance(row_data, str) else row_data


def upsert_edition_row(cur, edition):
    """Upsert a single edition into the per-edition v2 table."""
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


def load_one_edition_pg(conn, date, lang):
    """Read a single edition row from v2. Returns dict or None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT data FROM epaper_editions_v2 WHERE edition_date=%s AND edition_language=%s",
            (date, lang),
        )
        row = cur.fetchone()
    return row_to_edition(row[0]) if row else None


def delete_edition_row(date, lang):
    """Explicitly delete ONE edition row from v2."""
    if not pg_url():
        return
    conn = pg_connect()
    try:
        pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM epaper_editions_v2 WHERE edition_date=%s AND edition_language=%s",
                (date, lang or "Hindi"),
            )
        conn.commit()
    finally:
        conn.close()


def load_editions_from_pg():
    """Load editions from epaper_editions_v2. Returns list or None on failure."""
    if not pg_url():
        return None
    try:
        conn = pg_connect()
        pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM epaper_editions_v2")
            rows = cur.fetchall()
        v2_editions = [row_to_edition(r[0]) for r in rows] if rows else []
        conn.close()
        if not v2_editions:
            return load_editions_from_file() or []
        return v2_editions
    except Exception as e:
        print(f"[epaper] Postgres load failed, falling back: {e}")
        return None


# ── Edition cache management ──────────────────────────────────

def _edition_key(edition):
    return (edition.get("date", ""), edition.get("language", "Hindi"))


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


def load_editions():
    """Load editions with in-memory cache (60s TTL) + parallel Postgres & MongoDB fetch."""
    global editions_cache, editions_cache_ts

    now = time.time()
    with editions_cache_lock:
        if editions_cache is not None and (now - editions_cache_ts) < EDITIONS_CACHE_TTL:
            return editions_cache

    with ThreadPoolExecutor(max_workers=2) as ex:
        pg_future = ex.submit(load_editions_from_pg)
        mongo_future = ex.submit(load_editions_from_mongo)
        pg_data = pg_future.result()
        mongo_data = mongo_future.result()

    base = pg_data if pg_data is not None else load_editions_from_file()
    result = _merge_edition_lists(base or [], mongo_data or [])

    with editions_cache_lock:
        editions_cache = result
        editions_cache_ts = time.time()

    return result


def invalidate_editions_cache(date=None, lang=None):
    """Clear in-memory cache and Redis cache for editions list."""
    global editions_cache, editions_cache_ts
    with editions_cache_lock:
        editions_cache = None
        editions_cache_ts = 0
    from epaper_config import redis_edition_key
    keys_to_delete = [REDIS_EDITIONS_KEY, REDIS_LATEST_KEY]
    if date:
        for l in [lang, "any", "hindi", "english", "marathi", None]:
            keys_to_delete.append(redis_edition_key(date, l))
    redis_delete(*keys_to_delete)


def save_editions(data):
    """Persist a full list of editions by upserting each into v2."""
    invalidate_editions_cache()
    if pg_url():
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
            with conn.cursor() as cur:
                for ed in data:
                    upsert_edition_row(cur, ed)
            conn.commit()
            conn.close()
            try:
                save_editions_to_file(data)
            except Exception as fe:
                print(f"[epaper] Local file sync after v2 save failed (non-fatal): {fe}")
            return
        except Exception as e:
            print(f"[epaper] v2 save failed, falling back to file: {e}")
    save_editions_to_file(data)


def fast_editions_list_from_pg():
    """Server-side JSON extraction -- returns only metadata fields."""
    if not pg_url():
        return None
    try:
        conn = pg_connect()
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


def fast_load_single_edition(date, lang=None):
    """Fetch one edition from Postgres by date without loading all editions."""
    if not pg_url():
        return None
    try:
        conn = pg_connect()
        pg_ensure_table(conn)
        edition = None
        if lang:
            edition = load_one_edition_pg(conn, date, lang)
        if not edition:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM epaper_editions_v2 WHERE edition_date = %s ORDER BY edition_language",
                    (date,)
                )
                rows = cur.fetchall()
            for r in rows:
                e = row_to_edition(r[0])
                if e.get("published", True):
                    edition = e
                    break
        conn.close()
        return edition
    except Exception as e:
        print(f"[epaper] Fast single edition load failed: {e}")
        return None


# ── Cloudinary upload ─────────────────────────────────────────

def upload_to_cloudinary(file_bytes, filename):
    """Upload bytes to Cloudinary. Returns secure_url string or raises."""
    import io
    import cloudinary.uploader
    import re as _re
    result = cloudinary.uploader.upload(
        io.BytesIO(file_bytes),
        folder="epaper",
        public_id=os.path.splitext(filename)[0],
        overwrite=True,
        resource_type="image",
        quality=100,
        flags="preserve_transparency",
    )
    url = result["secure_url"]
    url = _re.sub(r'/upload/[^/]+/upload/', '/upload/', url)
    return url
