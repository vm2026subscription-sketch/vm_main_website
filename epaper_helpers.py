"""
E-Paper helpers: auth, edition metadata, article helpers, content safety, FCM, image utils.
"""
import hashlib
import io
import json
import os
import re
import urllib.parse

from flask import jsonify, redirect, request, session, url_for

from epaper_config import (
    ADMIN_EMAIL, EPAPER_ADMIN_SESSION_KEY, site_admin_check, CLOUDINARY_URL,
    ALLOWED_IMAGE_EXTENSIONS, ALLOWED_UPLOAD_EXTENSIONS, fcm_ready,
)
from epaper_storage import (
    pg_url, pg_connect, pg_ensure_table, row_to_edition, load_one_edition_pg,
    load_editions_from_file, load_editions, save_editions_to_file,
    fast_editions_list_from_pg, fast_load_single_edition,
)


# ── Auth helpers ──────────────────────────────────────────────

def is_epaper_admin():
    if session.get(EPAPER_ADMIN_SESSION_KEY) is True:
        return True
    if site_admin_check is not None:
        try:
            return bool(site_admin_check())
        except Exception:
            return False
    return False


def require_epaper_admin():
    if is_epaper_admin():
        return None
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Unauthorized. Please log in to epaper admin."}), 401
    return admin_login_redirect()


def admin_login_redirect():
    next_url = request.args.get("next") or "/epaper-admin"
    if "?" in next_url:
        next_url = next_url.split("?")[0]
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/epaper-admin"
    quoted = urllib.parse.quote(next_url, safe="")
    host = (request.host or "").lower()
    if host.startswith("epaper."):
        return redirect(f"https://www.vidyarthimitra.org/admin/login?next={quoted}")
    return redirect(f"/admin/login?next={quoted}")


def require_admin():
    """Return redirect to login if user is not an admin, else None."""
    user = session.get("auth_user")
    if not user or user.get("email", "").lower() != ADMIN_EMAIL.lower():
        return redirect(url_for("login"))
    return None


# ── Cache key helpers ─────────────────────────────────────────

def tts_cache_key(text, voice, rate, pitch):
    return hashlib.md5(f"{text}|{voice}|{rate}|{pitch}".encode("utf-8")).hexdigest()


def trans_cache_key(text, target):
    return hashlib.md5(f"{text[:4000]}|{target}".encode("utf-8")).hexdigest()


def evict(cache, max_size):
    while len(cache) >= max_size:
        from collections import OrderedDict
        if isinstance(cache, OrderedDict):
            cache.popitem(last=False)
        else:
            del cache[next(iter(cache))]


# ── Edition helpers ───────────────────────────────────────────

def public_request_root():
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("X-Forwarded-Host") or request.host or "").split(",")[0].strip()
    if host:
        return f"{proto}://{host}/"
    return request.url_root


def absolute_public_url(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return raw
    if raw.startswith("//"):
        scheme = (request.headers.get("X-Forwarded-Proto") or request.scheme or "https").split(",")[0].strip()
        return f"{scheme}:{raw}"
    return urllib.parse.urljoin(public_request_root(), raw)


def epaper_preview_image_type(image_url):
    path = urllib.parse.urlparse(str(image_url or "")).path.lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def epaper_preview_image_meta(edition):
    pages = (edition or {}).get("pages", []) or []
    first_page = pages[0] if pages else {}
    image_url = ""
    for key in ("page_image_url", "image_path"):
        image_url = absolute_public_url(first_page.get(key))
        if image_url:
            break
    if not image_url:
        fallback = absolute_public_url(url_for("static", filename="logo.png"))
        return {
            "url": fallback,
            "type": epaper_preview_image_type(fallback),
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
        "type": epaper_preview_image_type(image_url),
        "width": None,
        "height": None,
    }


def epaper_preview_title(edition, requested_date=None):
    return "Vidyarthi Mitra ePaper - Read Marathi, Hindi & English Newspaper Online"


def epaper_preview_description(edition):
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


def edition_preview_url(edition):
    """Return the best preview image for an edition card."""
    pages = edition.get("pages", [])
    if pages:
        first = pages[0]
        url = first.get("page_image_url") or first.get("image_path") or ""
        if url:
            return url
    return edition.get("masthead_image_url", "")


def no_store_redirect(location):
    resp = redirect(location)
    resp.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
    return resp


# ── Article helpers ───────────────────────────────────────────

def article_from_block(block, edition=None, page=None):
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


def iter_epaper_articles():
    for edition in load_editions():
        for page in edition.get("pages", []):
            sources = page.get("blocks") or page.get("articles", [])
            for block in sources:
                if block.get("type") == "shape":
                    continue
                yield article_from_block(block, edition, page), edition, page


def find_epaper_article(article_id):
    target_id = str(article_id)
    articles = []
    article_index = {}
    for article, edition, page in iter_epaper_articles():
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


# ── Content safety ────────────────────────────────────────────

def count_filled_articles(pages):
    """Count article blocks that actually have body content."""
    n = 0
    for p in pages or []:
        for b in p.get("blocks") or []:
            if b.get("type", "article") == "article" and (
                (b.get("body_text") or "").strip() or (b.get("body_html") or "").strip()
            ):
                n += 1
    return n


def content_regression(existing_edition, incoming_pages):
    """Detect a save that would drastically reduce stored article content."""
    old_n = count_filled_articles((existing_edition or {}).get("pages"))
    new_n = count_filled_articles(incoming_pages)
    if old_n >= 8 and new_n < (old_n * 7 + 9) // 10:
        return {"existing_filled": old_n, "incoming_filled": new_n}
    return None


def per_page_wipes(base_pages, new_pages):
    """Catch content loss on individual pages."""
    new_by = {}
    for p in new_pages or []:
        n = p.get("page_number")
        if n is not None:
            new_by[n] = p
    wiped = []
    for p in base_pages or []:
        n = p.get("page_number")
        if n is None:
            continue
        old_f = count_filled_articles([p])
        if old_f < 4:
            continue
        if n not in new_by:
            wiped.append({"page": n, "existing_filled": old_f, "incoming_filled": 0, "removed": True})
            continue
        new_f = count_filled_articles([new_by[n]])
        if new_f == 0:
            wiped.append({"page": n, "existing_filled": old_f, "incoming_filled": 0})
    return wiped


def merge_pages_into(base_pages, incoming_pages, page_set=None):
    """Merge incoming pages into base pages by page_number."""
    by_num = {}
    for p in incoming_pages or []:
        n = p.get("page_number")
        if n is not None:
            by_num[n] = p
    merged, replaced = [], set()
    for p in base_pages or []:
        n = p.get("page_number")
        if n in by_num:
            merged.append(by_num[n])
            replaced.add(n)
        else:
            merged.append(p)
    for p in incoming_pages or []:
        n = p.get("page_number")
        if n is not None and n not in replaced:
            merged.append(p)
    if isinstance(page_set, list):
        allowed = set(page_set)
        merged = [p for p in merged if p.get("page_number") in allowed]
    merged.sort(key=lambda p: p.get("page_number") or 0)
    return merged


# ── Image utils ───────────────────────────────────────────────

def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_upload(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def compress_image_bytes(file_bytes, filename, max_width=1600, quality=85):
    """Resize to max_width and convert to JPEG."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        if img.mode not in ('RGB',):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                bg.paste(img, mask=img.split()[-1])
            else:
                bg.paste(img)
            img = bg
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=quality, optimize=True)
        stem = os.path.splitext(filename)[0]
        return buf.getvalue(), stem + '.jpg'
    except Exception as e:
        print(f"[epaper] Image compression failed: {e}")
        return file_bytes, filename


# ── FCM (push notifications) ─────────────────────────────────

def get_fcm():
    """Initialise firebase-admin once. Returns True if push is usable."""
    global fcm_ready
    from epaper_config import fcm_ready as _fcm
    if _fcm is not None:
        return _fcm
    try:
        import firebase_admin
        from firebase_admin import credentials
        if not firebase_admin._apps:
            raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
            path = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
            if raw:
                cred = credentials.Certificate(json.loads(raw))
            elif path and os.path.exists(path):
                cred = credentials.Certificate(path)
            else:
                print("[epaper] FCM not configured (no service account) -- skipping push.")
                from epaper_config import fcm_ready as _fc
                _fc = False
                return False
            firebase_admin.initialize_app(cred)
        from epaper_config import fcm_ready as _fc
        _fc = True
        return True
    except Exception as e:
        print(f"[epaper] FCM init failed (non-fatal): {e}")
        from epaper_config import fcm_ready as _fc
        _fc = False
        return False


def send_new_edition_notification(edition):
    """Send a 'New ePaper Available' push to every subscribed phone."""
    if not get_fcm():
        return
    try:
        from firebase_admin import messaging
        msg = messaging.Message(
            topic="new_edition",
            notification=messaging.Notification(
                title="New ePaper Available",
                body="Aaj ka edition ab padhne ke liye taiyaar hai",
            ),
            data={"type": "new_edition", "date": str(edition.get("date", ""))},
        )
        resp = messaging.send(msg)
        print(f"[epaper] FCM new_edition push sent: {resp}")
    except Exception as e:
        print(f"[epaper] FCM send failed (non-fatal): {e}")


def push_once_for_date(conn, date):
    """Return True only the FIRST time a date is seen."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS epaper_push_sent (
                    edition_date TEXT PRIMARY KEY,
                    sent_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute(
                "INSERT INTO epaper_push_sent (edition_date) VALUES (%s) "
                "ON CONFLICT (edition_date) DO NOTHING",
                (date,),
            )
            first_time = cur.rowcount > 0
        conn.commit()
        return first_time
    except Exception as e:
        print(f"[epaper] push dedupe check failed (non-fatal): {e}")
        return False
