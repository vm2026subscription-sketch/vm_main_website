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
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, send_file, session, Response, stream_with_context
from werkzeug.utils import secure_filename

# ── In-memory caches ──────────────────────────────────────
_tts_cache: dict = {}     # cache_key → bytes
_TTS_CACHE_MAX = 30

_trans_cache: dict = {}   # cache_key → translated_text
_TRANS_CACHE_MAX = 80

def _tts_cache_key(text, voice, rate, pitch):
    return hashlib.md5(f"{text}|{voice}|{rate}|{pitch}".encode("utf-8")).hexdigest()

def _trans_cache_key(text, target):
    return hashlib.md5(f"{text[:4000]}|{target}".encode("utf-8")).hexdigest()

def _evict(cache, max_size):
    while len(cache) >= max_size:
        del cache[next(iter(cache))]

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "saurabhedict@gmail.com")

# ── Epaper admin credentials ──────────────────────
_EPAPER_ADMIN_USER = "admin"
_EPAPER_ADMIN_PASS = "vm2026"
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


def _load_editions_from_mongo():
    """Read editions from MongoDB (Railway admin's database). Read-only — never writes."""
    url = _mongo_url()
    if not url:
        return []
    try:
        from pymongo import MongoClient
        client = MongoClient(url, serverSelectionTimeoutMS=4000, connectTimeoutMS=4000)
        db_name = os.getenv("MONGODB_DB", "vm")
        col_name = os.getenv("MONGODB_COLLECTION", "editions")
        db = client[db_name]
        docs = list(db[col_name].find({}, {"_id": 0}))
        client.close()
        return docs
    except Exception as e:
        print(f"[epaper] MongoDB load failed: {e}")
        return []


# ── Postgres (Supabase) helpers ─────────────────────

def _pg_url():
    return os.getenv("SUPABASE_POSTGRES_URL") or os.getenv("DATABASE_URL")


def _pg_connect():
    import psycopg2
    url = _pg_url()
    conn = psycopg2.connect(url, connect_timeout=5)
    conn.autocommit = False
    return conn


def _pg_ensure_table(conn):
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


def _save_edition_backup(edition):
    """Save a snapshot of one edition to the backup table. Keeps last 30 per edition."""
    if not _pg_url():
        return
    try:
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

    data = _load_views_file()
    key = _views_key(date, language)
    data[key] = int(data.get(key, 0)) + 1
    _save_views_file(data)
    return data[key]


# ── Public load / save ──────────────────────────────

def _load_editions():
    pg_data = None
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM epaper_editions_store WHERE id = 'editions'")
                row = cur.fetchone()
            conn.close()
            pg_data = row[0] if row else []
            if isinstance(pg_data, str):
                pg_data = json.loads(pg_data)
            if not pg_data:
                file_data = _load_editions_from_file()
                if file_data:
                    _save_editions(file_data)
                pg_data = file_data
        except Exception as e:
            print(f"[epaper] Postgres load failed, falling back: {e}")
            pg_data = None

    mongo_data = _load_editions_from_mongo()

    # Merge Supabase + MongoDB; Supabase takes precedence on same (date, language)
    base = pg_data if pg_data is not None else _load_editions_from_file()
    if not mongo_data:
        return base
    if not base:
        return mongo_data
    existing_keys = {(e.get("date", ""), e.get("language", "Hindi")) for e in base}
    merged = list(base)
    for e in mongo_data:
        if (e.get("date", ""), e.get("language", "Hindi")) not in existing_keys:
            merged.append(e)
    return merged


def _save_editions(data):
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO epaper_editions_store (id, data, updated_at)
                    VALUES ('editions', %s::jsonb, NOW())
                    ON CONFLICT (id) DO UPDATE
                        SET data = EXCLUDED.data, updated_at = NOW()
                """, (json.dumps(data, ensure_ascii=False),))
            conn.commit()
            conn.close()
            return
        except Exception as e:
            print(f"[epaper] Postgres save failed, falling back to file: {e}")
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
    for article, edition, page in _iter_epaper_articles():
        if str(article.get("id")) == str(article_id):
            related = [
                candidate for candidate, _, _ in _iter_epaper_articles()
                if str(candidate.get("id")) != str(article_id)
                and candidate.get("category") == article.get("category")
            ][:3]
            if len(related) < 3:
                related_ids = {str(item.get("id")) for item in related}
                related.extend([
                    candidate for candidate, _, _ in _iter_epaper_articles()
                    if str(candidate.get("id")) != str(article_id)
                    and str(candidate.get("id")) not in related_ids
                ][:3 - len(related)])
            return article, related, edition, page
    return None, [], None, None


# ── Viewer Page ────────────────────────────────────
@epaper_bp.route("/epaper")
@epaper_bp.route("/epaper/<date>")
@epaper_bp.route("/epaper/<date>/page-<int:page>")
def epaper_viewer(date=None, page=1):
    import json as _json
    initial_edition_json = None
    try:
        editions = _load_editions()
        published = [e for e in editions if e.get("published", True)]
        if date:
            edition = next((e for e in published if e["date"] == date), None) or \
                      (sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None)
        else:
            edition = sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None
        if edition:
            initial_edition_json = _json.dumps(edition, ensure_ascii=False).replace('</script>', r'<\/script>')
    except Exception:
        pass
    return render_template("epaper_viewer.html", initial_date=date, initial_page=page,
                           initial_edition_json=initial_edition_json)


# ── Epaper Admin Login / Logout ───────────────────
@epaper_bp.route("/epaper-admin/login", methods=["GET", "POST"])
def epaper_admin_login():
    if _is_epaper_admin():
        return redirect(url_for("epaper.epaper_admin_v2"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_ok = hmac.compare_digest(username, _EPAPER_ADMIN_USER)
        pass_ok = hmac.compare_digest(password, _EPAPER_ADMIN_PASS)
        if user_ok and pass_ok:
            session[_EPAPER_ADMIN_SESSION_KEY] = True
            session.permanent = True
            next_url = request.args.get("next") or url_for("epaper.epaper_admin_v2")
            # strip query string artifacts
            if "?" in next_url:
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
@epaper_bp.route("/api/epaper/editions")
def api_editions():
    editions = _load_editions()
    return jsonify({"editions": [
        {
            "date": e["date"],
            "name": e.get("name", ""),
            "language": e.get("language", "Hindi"),
            "total_pages": len(e.get("pages", [])),
            "published": e.get("published", True),
            "masthead_image_url": e.get("masthead_image_url", ""),
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
    data = request.get_json(silent=True) or {}
    date_str = data.get("date", "")
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "date required (YYYY-MM-DD)."}), 400

    lang_str = data.get("language", "Hindi")
    original_date = data.get("original_date", "")
    original_lang = data.get("original_lang", "")

    # ── Single DB connection for load + save (avoids two round-trips) ──
    conn = None
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM epaper_editions_store WHERE id = 'editions'")
                row = cur.fetchone()
            editions = row[0] if row else []
            if isinstance(editions, str):
                editions = json.loads(editions)
            if not editions:
                editions = _load_editions_from_file()
        except Exception as e:
            print(f"[epaper] DB load in save failed: {e}")
            try: conn.close()
            except: pass
            conn = None
            editions = _load_editions_from_file()
    else:
        editions = _load_editions_from_file()

    # If date/lang changed, remove old entry first
    if original_date and (original_date != date_str or original_lang != lang_str):
        editions = [e for e in editions
                    if not (e["date"] == original_date and e.get("language", "Hindi") == original_lang)]

    existing = next(
        (e for e in editions if e["date"] == date_str and e.get("language", "Hindi") == lang_str),
        None,
    )

    if existing:
        existing["name"] = data.get("name", existing.get("name", ""))
        existing["language"] = data.get("language", existing.get("language", "Hindi"))
        existing["published"] = data.get("published", existing.get("published", True))
        existing["masthead_image_url"] = data.get("masthead_image_url", existing.get("masthead_image_url", ""))
        if "footer_links" in data:
            existing["footer_links"] = data.get("footer_links", existing.get("footer_links", []))
        if "header_items" in data:
            existing["header_items"] = data.get("header_items", existing.get("header_items", []))
        if "pages" in data:
            existing["pages"] = data["pages"]
    else:
        editions.append({
            "date": date_str,
            "name": data.get("name", f"Edition {date_str}"),
            "language": data.get("language", "Hindi"),
            "published": data.get("published", True),
            "masthead_image_url": data.get("masthead_image_url", ""),
            "footer_links": data.get("footer_links", []),
            "header_items": data.get("header_items", []),
            "pages": data.get("pages", []),
            "created_at": datetime.now().isoformat(),
        })

    saved_edition = existing if existing else editions[-1]

    try:
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO epaper_editions_store (id, data, updated_at)
                    VALUES ('editions', %s::jsonb, NOW())
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                """, (json.dumps(editions, ensure_ascii=False),))
            conn.commit()
            conn.close()
        else:
            _save_editions_to_file(editions)
    except Exception as exc:
        if conn:
            try: conn.close()
            except: pass
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
    original_count = len(editions)
    editions = [e for e in editions if not (e["date"] == date and e.get("language", "Hindi") == lang)]
    if len(editions) == original_count:
        return jsonify({"error": f"No edition found for date={date} lang={lang}"}), 404
    try:
        _save_editions(editions)
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
    except Exception:
        pass

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
        except Exception:
            pass

    return jsonify({"error": "Translation failed."}), 500


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


# ── AI: LLM-optimized TTS script ───────────────────
@epaper_bp.route("/api/epaper/tts-script", methods=["POST"])
def api_tts_script():
    """Use Groq LLM to process raw text into an optimized broadcast script for TTS."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "No text provided."}), 400

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return jsonify({"error": "Groq API key not configured"}), 500

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        system_prompt = """You are a senior broadcast script writer for India's top news channels (Aaj Tak, NDTV India, Zee 24 Taas, ABP Maza, Times Now). Transform raw news text into a broadcast-ready narration script that sounds exactly like a real live news anchor — not a robot.

LANGUAGE DETECTION:
Detect the primary language: Hindi (हिंदी), Marathi (मराठी), or English.
Return "language" as: "hi" for Hindi, "mr" for Marathi, "en" for English.
Mixed scripts are normal — keep natural code-switching (e.g. English proper nouns in Hindi article).

MANDATORY TRANSFORMATIONS:

1. SENTENCE RHYTHM — Break long sentences at natural breath points. Each sentence max 15 words. Short punchy sentences for impact.

2. PAUSE INJECTION (critical for realistic delivery):
   - After headline: add "..." (anchor pause before story)
   - After key facts, numbers, names: add ", " (short beat)
   - Between topic shifts in Hindi/Marathi: add " | "
   - After dramatic statements: add " — "
   - End of important section: add full stop + new line

3. NUMBER & SYMBOL CONVERSION:
   Hindi/Marathi: ₹50,000 → पचास हजार रुपये | ₹2 crore → दो करोड़ रुपये | 50% → पचास प्रतिशत | 10 lakh → दस लाख
   English: $1M → one million dollars | 10% → ten percent | 2025 → twenty twenty-five

4. ABBREVIATION EXPANSION:
   Hindi: JEE→जे ई ई | NEET→नीट | IIT→आई आई टी | UP→उत्तर प्रदेश | CM→मुख्यमंत्री | PM→प्रधानमंत्री
   Marathi: JEE→जे ई ई | CM→मुख्यमंत्री | PM→पंतप्रधान | MH→महाराष्ट्र
   English: JEE→J-E-E | IIT→I-I-T | CM→Chief Minister | PM→Prime Minister

5. ANCHOR TONE BY LANGUAGE:
   Hindi (Aaj Tak style): आदरपूर्ण, स्पष्ट उच्चारण, थोड़ी urgency। वाक्य छोटे और प्रभावशाली।
   Marathi (Zee 24 Taas style): स्पष्ट मराठी उच्चारण। Standard Pune-style Marathi diction.
   English (NDTV style): Crisp neutral Indian English. Measured pace.

6. OPENING FORMAT (mandatory):
   Hindi: Start with "एक बड़ी खबर... " or "ताज़ा जानकारी के मुताबिक... "
   Marathi: Start with "महत्त्वाची बातमी... " or "ताज्या माहितीनुसार... "
   English: Start with "Breaking news — " or "In a major development, "

7. VOICE STYLE (choose based on story tone):
   Breaking/urgent: speed=1.0, pitch="+2Hz"
   Education/results: speed=0.95, pitch="+0Hz"
   Government/policy: speed=0.92, pitch="-2Hz"
   Positive/achievement: speed=1.0, pitch="+3Hz"

Return ONLY valid JSON — no markdown, no extra text:
{
  "language": "hi|mr|en",
  "title_script": "...",
  "body_script": "...",
  "voice_style": { "speed": 0.95, "pitch": "+0Hz", "emotion": "calm-authoritative", "pause_style": "short after facts" }
}"""

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": f"Raw News Article:\n\n{text[:4000]}"}],
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=2000,
        )

        import json as _json
        result = _json.loads(response.choices[0].message.content)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"LLM script optimization failed: {str(e)}"}), 500


# ── AI: TTS (Edge Neural Voices — Real Indian Anchor) ──
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


def _stream_edge_tts(text, voice, rate, pitch, cache_key):
    """Generator that streams edge_tts audio chunks and caches the full result."""
    q = _queue.Queue()
    collected = []

    async def _async():
        import edge_tts
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    q.put(chunk["data"])
        except Exception as exc:
            q.put(exc)
        finally:
            q.put(None)

    def _run_thread():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    t = threading.Thread(target=_run_thread, daemon=True)
    t.start()

    while True:
        try:
            item = q.get(timeout=30)
        except _queue.Empty:
            break
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        collected.append(item)
        yield item

    # Cache full audio after streaming completes
    if collected and cache_key:
        full = b"".join(collected)
        _evict(_tts_cache, _TTS_CACHE_MAX)
        _tts_cache[cache_key] = full


@epaper_bp.route("/api/epaper/tts", methods=["POST"])
def api_tts():
    """Server-side TTS using Microsoft Edge Neural voices — streams MP3 progressively."""
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

    # ── Serve from cache instantly ──────────────────────────────────────────
    if ck in _tts_cache:
        return send_file(
            io.BytesIO(_tts_cache[ck]),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="tts_audio.mp3",
        )

    # ── Stream from edge_tts (client starts playing on first chunk) ─────────
    try:
        return Response(
            stream_with_context(_stream_edge_tts(text, voice, rate, pitch, ck)),
            mimetype="audio/mpeg",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Transfer-Encoding": "chunked",
            },
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"TTS error: {str(e)}"}), 500


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

        editions = _load_editions()
        editions = [e for e in editions
                    if not (e.get("date") == edition.get("date")
                            and e.get("language") == edition.get("language"))]
        editions.append(edition)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO epaper_editions_store (id, data, updated_at)
                VALUES ('editions', %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
            """, (json.dumps(editions, ensure_ascii=False),))
        conn.commit()
        conn.close()
        return jsonify({"success": True,
                        "message": f"Edition {edition.get('date')} ({edition.get('language')}) restored successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
