"""
E-Paper routes — edition/page/article APIs + AI features
"""
import asyncio
import io
import json
import os
import re
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import tempfile
from flask import jsonify, render_template, request, redirect, url_for, send_file, session, Response
from werkzeug.utils import secure_filename
from app import limiter

# ── Import from new modules ─────────────────────────────
from epaper_config import (
    epaper_bp,
    set_site_admin_check,
    tts_cache, TTS_CACHE_MAX,
    trans_cache, TRANS_CACHE_MAX,
    REDIS_EDITIONS_KEY, REDIS_EDITIONS_TTL, REDIS_LATEST_KEY, REDIS_LATEST_TTL, REDIS_EDITION_TTL,
    ADMIN_EMAIL,
    EPAPER_ADMIN_SESSION_KEY,
    CLOUDINARY_URL,
    EDITIONS_FILE,
    EPAPER_UPLOAD_DIR,
    EPAPER_TMP_UPLOAD_DIR,
    EPAPER_VIEWS_FILE,
    LANG_SLUG as _LANG_SLUG,
    redis_edition_key,
)
from epaper_storage import (
    redis_get,
    redis_set,
    redis_delete,
    pg_url,
    pg_connect,
    pg_ensure_table,
    row_to_edition,
    load_one_edition_pg,
    load_editions_from_file,
    load_editions_from_mongo,
    load_editions,
    invalidate_editions_cache,
    save_editions,
    save_editions_to_file,
    save_edition_backup,
    increment_edition_view,
    load_views_file,
    views_key,
    fast_editions_list_from_pg,
    fast_load_single_edition,
    upsert_edition_row,
    delete_edition_row,
    upload_to_cloudinary,
    get_redis,
)
from epaper_helpers import (
    require_epaper_admin,
    admin_login_redirect,
    require_admin,
    is_epaper_admin,
    public_request_root,
    absolute_public_url,
    epaper_preview_image_meta,
    epaper_preview_image_type,
    epaper_preview_title,
    epaper_preview_description,
    edition_preview_url,
    no_store_redirect,
    article_from_block,
    iter_epaper_articles,
    find_epaper_article,
    count_filled_articles,
    content_regression,
    per_page_wipes,
    merge_pages_into,
    allowed_image,
    allowed_upload,
    compress_image_bytes,
    tts_cache_key,
    trans_cache_key,
    evict,
    get_fcm,
    send_new_edition_notification,
    push_once_for_date,
    _sanitize_edition_payload,
    cloudinary_transform,
    PRESET_PAGE_VIEWER,
    PRESET_PAGE_WEB,
    PRESET_CARD,
    PRESET_THUMB,
    PRESET_MASTHEAD,
)

# ── Backward-compat re-exports (ads_routes.py imports these) ──
_pg_url = pg_url
_pg_connect = pg_connect
_require_epaper_admin = require_epaper_admin
_CLOUDINARY_URL = CLOUDINARY_URL
_EDITIONS_FILE = EDITIONS_FILE
_EDITIONS_TMP = os.path.join(os.path.dirname(__file__), "data", "epaper_editions.json")
EPAPER_VIEWS_FILE = EPAPER_VIEWS_FILE
_EPAPER_VIEWS_TMP = os.path.join(tempfile.gettempdir(), "epaper_views.json")

# Ensure EPAPER_TMP_UPLOAD_DIR is importable as module-level name
EPAPER_TMP_UPLOAD_DIR = EPAPER_TMP_UPLOAD_DIR


# ── Viewer Page (language variants) ──────────────────
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
        editions = load_editions()
        published = [e for e in editions
                     if e.get("published", True)
                     and e.get("language", "Hindi") == language]
        if date:
            edition = next((e for e in published if e["date"] == date), None) or \
                      (sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None)
        else:
            edition = sorted(published, key=lambda e: e["date"], reverse=True)[0] if published else None
        if edition:
            # Edition data is loaded via the JSON API on the client; do NOT embed
            # the full (potentially ~1MB) edition inline in the HTML.
            initial_edition_json = None
    except Exception:
        pass
    og_url = absolute_public_url(request.path)
    og_image_meta = epaper_preview_image_meta(edition)
    og_title = epaper_preview_title(edition, date)
    og_description = epaper_preview_description(edition)
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
@epaper_bp.route("/epaper/latest/english")
@epaper_bp.route("/epaper/latest/hindi")
@epaper_bp.route("/epaper/latest/marathi")
def epaper_latest_language():
    slug = request.path.rstrip("/").rsplit("/", 1)[-1].lower()
    language = _LANG_SLUG.get(slug)
    if not language:
        return no_store_redirect(url_for("epaper.epaper_viewer"))

    try:
        editions = load_editions()
    except Exception:
        editions = []

    candidates = [
        e for e in editions
        if e.get("published", True)
        and e.get("active", True)
        and e.get("language", "Hindi") == language
    ]

    if not candidates:
        notice = f"No {language} ePaper edition is available yet."
        return no_store_redirect(url_for("epaper.epaper_viewer", notice=notice))

    latest = sorted(
        candidates,
        key=lambda e: (str(e.get("date", "")), str(e.get("created_at", ""))),
        reverse=True,
    )[0]

    reader_url = f"/epaper/{slug}/{urllib.parse.quote(str(latest['date']))}"

    image_meta = epaper_preview_image_meta(latest)
    html = render_template(
        "epaper_latest_redirect.html",
        language=language,
        reader_url=reader_url,
        canonical_url=absolute_public_url(reader_url),
        og_url=absolute_public_url(request.path),
        og_title=epaper_preview_title(latest, latest.get("date")),
        og_description=epaper_preview_description(latest),
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
        target_date = date
        target_lang = request.args.get("lang", None)
        
        fast_list = fast_editions_list_from_pg()
        if fast_list is None:
            file_editions = load_editions_from_file() or []
            fast_list = [
                {
                    "date": e["date"],
                    "language": e.get("language", "Hindi"),
                    "published": e.get("published", True)
                }
                for e in file_editions
            ]
            
        published_metadata = [e for e in fast_list if e.get("published", True)]
        
        if published_metadata:
            if target_date:
                meta = next((e for e in published_metadata if e["date"] == target_date and (not target_lang or e["language"] == target_lang)), None)
                if not meta:
                    meta = next((e for e in published_metadata if e["date"] == target_date), None)
                if not meta:
                    meta = sorted(published_metadata, key=lambda e: e["date"], reverse=True)[0]
            else:
                meta = sorted(published_metadata, key=lambda e: e["date"], reverse=True)[0]
                
            if meta:
                target_date = meta["date"]
                target_lang = meta["language"]
                
        if target_date:
            if pg_url():
                try:
                    conn = pg_connect()
                    pg_ensure_table(conn)
                    edition = load_one_edition_pg(conn, target_date, target_lang or "Hindi")
                    conn.close()
                except Exception as exc:
                    print(f"[epaper] viewer load pg failed: {exc}")
                    edition = None
            if not edition:
                file_editions = load_editions_from_file() or []
                edition = next((e for e in file_editions if e["date"] == target_date and e.get("language", "Hindi") == (target_lang or "Hindi")), None)
                if not edition:
                    edition = next((e for e in file_editions if e["date"] == target_date), None)
                    
        if edition:
            # Edition data is loaded via the JSON API on the client; do NOT embed
            # the full edition inline in the HTML.
            initial_edition_json = None
    except Exception as e:
        print(f"[epaper] Viewer logic exception: {e}")
    og_url = absolute_public_url(request.path)
    og_image_meta = epaper_preview_image_meta(edition)
    og_image = og_image_meta["url"]
    og_title = epaper_preview_title(edition, date)
    og_description = epaper_preview_description(edition)
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
    return admin_login_redirect()


@epaper_bp.route("/epaper-admin/logout")
def epaper_admin_logout():
    session.pop(EPAPER_ADMIN_SESSION_KEY, None)
    host = (request.host or "").lower()
    if host.startswith("epaper."):
        return redirect("https://www.vidyarthimitra.org/admin/login")
    return redirect("/admin/login")


# ── Admin Page ────────────────────────────────────
@epaper_bp.route("/epaper-admin")
def epaper_admin_v2():
    guard = require_epaper_admin()
    if guard is not None:
        return guard
    admin_user = session.get("auth_user", {})
    return render_template("epaper_admin_v2.html", admin_user=admin_user)


@epaper_bp.route("/api/epaper/admin/cloudinary-sign", methods=["POST"])
def api_cloudinary_sign():
    guard = require_epaper_admin()
    if guard is not None: return guard
    if not CLOUDINARY_URL:
        return jsonify({"error": "Cloudinary not configured"}), 503
    try:
        import cloudinary.utils
        timestamp = int(__import__('time').time())
        req_data = request.get_json(silent=True) or {}
        resource_type = req_data.get("resource_type", "auto")
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
    guard = require_epaper_admin()
    if guard is not None: return guard
    image = request.files.get("image") or request.files.get("file")
    if not image or not image.filename:
        return jsonify({"error": "file required"}), 400
    if not allowed_upload(image.filename):
        return jsonify({"error": "Unsupported file type. Allowed: images and PDF"}), 400

    original = secure_filename(image.filename)
    stem, ext = os.path.splitext(original)
    ts = datetime.now().strftime('%Y%m%d%H%M%S%f')

    if ext.lower() == ".pdf":
        try:
            import fitz
            pdf_bytes = image.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pg = doc[0]
            mat = fitz.Matrix(2.0, 2.0)
            pix = pg.get_pixmap(matrix=mat)
            doc.close()
            filename = f"{stem[:48]}-{ts}.png"
            file_bytes = pix.tobytes("png")
        except Exception as e:
            return jsonify({"error": f"PDF conversion failed: {str(e)}"}), 500
    else:
        filename = f"{stem[:48]}-{ts}{ext.lower()}"
        file_bytes = image.read()

    file_bytes, filename = compress_image_bytes(file_bytes, filename)

    if CLOUDINARY_URL:
        try:
            url = upload_to_cloudinary(file_bytes, filename)
            return jsonify({"success": True, "url": url}), 201
        except Exception as e:
            return jsonify({"error": f"Cloudinary upload failed: {e}"}), 500

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
    guard = require_epaper_admin()
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

    if not CLOUDINARY_URL:
        return jsonify({"error": "Cloudinary not configured"}), 503

    results = [None] * len(pages_data)

    def _upload_page(item):
        idx, img_bytes, filename = item
        url = upload_to_cloudinary(img_bytes, filename)
        return idx, url

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_upload_page, item): item[0] for item in pages_data}
        for fut in as_completed(futures):
            idx, url = fut.result()
            results[idx] = url

    return jsonify({"success": True, "pages": results})


@epaper_bp.route("/api/epaper/admin/pdf-to-pages", methods=["POST"])
def api_pdf_to_pages():
    guard = require_epaper_admin()
    if guard is not None: return guard
    pdf_file = request.files.get("pdf")
    if not pdf_file or not pdf_file.filename:
        return jsonify({"error": "PDF file required"}), 400
    if not pdf_file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400

    try:
        import fitz
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

    pages_data = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("jpeg", jpg_quality=88)
        pages_data.append((i, img_bytes, f"pdf_page_{ts}_{i+1}.jpg"))
    doc.close()

    if CLOUDINARY_URL:
        results = [None] * len(pages_data)

        def _upload_page(item):
            idx, img_bytes, filename = item
            url = upload_to_cloudinary(img_bytes, filename)
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
    safe = secure_filename(filename)
    filepath = os.path.join(EPAPER_TMP_UPLOAD_DIR, safe)
    if not os.path.exists(filepath):
        return jsonify({"error": "Not found"}), 404
    return send_file(filepath)


@epaper_bp.route("/article/<article_id>")
def epaper_article(article_id):
    article, related, edition, page = find_epaper_article(article_id)
    if not article:
        return redirect(url_for("epaper.epaper_viewer"))
    canonical_url = absolute_public_url(request.path)
    edition_image = ""
    if edition:
        img_meta = epaper_preview_image_meta(edition)
        edition_image = img_meta.get("url", "")
    return render_template(
        "epaper_article.html",
        article=article,
        related_articles=related,
        edition=edition,
        page=page,
        canonical_url=canonical_url,
        edition_image=edition_image,
    )


# ── API: List editions ─────────────────────────────
@epaper_bp.route("/api/epaper/editions")
@limiter.limit("60 per minute")
def api_editions():
    cached = redis_get(REDIS_EDITIONS_KEY)
    if cached is not None:
        return jsonify({"editions": cached})

    fast = fast_editions_list_from_pg()
    if fast is not None:
        redis_set(REDIS_EDITIONS_KEY, fast, ttl=REDIS_EDITIONS_TTL)
        return jsonify({"editions": fast})

    editions = load_editions()
    return jsonify({"editions": [
        {
            "date": e["date"],
            "name": e.get("name", ""),
            "language": e.get("language", "Hindi"),
            "total_pages": len(e.get("pages", [])),
            "published": e.get("published", True),
            "masthead_image_url": e.get("masthead_image_url", ""),
            "preview_image_url": edition_preview_url(e),
        }
        for e in editions
    ]})


# ── API: Latest published edition ─────────────────
@epaper_bp.route("/api/epaper/latest")
@limiter.limit("60 per minute")
def api_latest_edition():
    cached = redis_get(REDIS_LATEST_KEY)
    if cached is not None:
        return jsonify(cached)

    meta_list = fast_editions_list_from_pg()
    if meta_list is not None:
        published_meta = [e for e in meta_list if e.get("published", True)]
        if not published_meta:
            return jsonify({"error": "No published editions."}), 404
        best = sorted(published_meta, key=lambda e: e["date"], reverse=True)[0]
        edition = fast_load_single_edition(best["date"], best["language"])
        if edition:
            result = {
                "date": edition["date"],
                "name": edition.get("name", ""),
                "language": edition.get("language", "Hindi"),
                "masthead_image_url": edition.get("masthead_image_url", ""),
                "footer_links": edition.get("footer_links", []),
                "header_items": edition.get("header_items", []),
                "pages": edition.get("pages", []),
                "published": edition.get("published", True),
            }
            redis_set(REDIS_LATEST_KEY, result, ttl=REDIS_LATEST_TTL)
            return jsonify(result)

    editions = load_editions()
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


@epaper_bp.route("/api/epaper/admin/edition/<date>/publish", methods=["POST"])
def api_publish_edition(date):
    guard = require_epaper_admin()
    if guard is not None: return guard
    data = request.get_json(silent=True) or {}
    published = bool(data.get("published", True))
    lang = request.args.get("lang", None)
    effective_lang = lang or "Hindi"

    edition = None
    if pg_url():
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
            edition = load_one_edition_pg(conn, date, effective_lang)
            if not edition and lang:
                conn.close()
                return jsonify({"error": "Edition not found."}), 404
            elif not edition:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT data FROM epaper_editions_v2 WHERE edition_date=%s LIMIT 1",
                        (date,),
                    )
                    row = cur.fetchone()
                edition = row_to_edition(row[0]) if row else None
            
            if edition:
                edition["published"] = published
                with conn.cursor() as cur:
                    upsert_edition_row(cur, edition)
                conn.commit()
                invalidate_editions_cache(date=date, lang=effective_lang)
                save_edition_backup(edition, conn=conn)
                conn.close()
                
                try:
                    all_eds = load_editions_from_file() or []
                    for e in all_eds:
                        if e["date"] == edition["date"] and e.get("language", "Hindi") == edition.get("language", "Hindi"):
                            e["published"] = published
                            break
                    save_editions_to_file(all_eds)
                except Exception as fe:
                    print(f"[epaper] Local file sync after publish failed (non-fatal): {fe}")

                return jsonify({"success": True, "published": published})
            conn.close()
        except Exception as exc:
            return jsonify({"error": f"Publish failed: {exc}"}), 500

    editions = load_editions_from_file()
    for e in editions:
        if e["date"] == date and (not lang or e.get("language", "Hindi") == lang):
            e["published"] = published
            try:
                save_editions_to_file(editions)
            except Exception as exc:
                return jsonify({"error": f"Save failed: {exc}"}), 500
            save_edition_backup(e)
            invalidate_editions_cache(date=date, lang=effective_lang)
            return jsonify({"success": True, "published": published})
            
    return jsonify({"error": "Edition not found."}), 404


# ── API: Available languages for a date ───────────
@epaper_bp.route("/api/epaper/editions-by-date/<date>")
@limiter.limit("60 per minute")
def api_editions_by_date(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400

    cached_list = redis_get(REDIS_EDITIONS_KEY)
    if cached_list is not None:
        matches = [
            {"language": e.get("language", "Hindi"), "name": e.get("name", "")}
            for e in cached_list
            if e["date"] == date and e.get("published", True)
        ]
        return jsonify({"editions": matches})

    if pg_url():
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT edition_language,
                              COALESCE(data->>'name', '') AS name,
                              COALESCE((data->>'published')::boolean, true) AS published
                       FROM epaper_editions_v2
                       WHERE edition_date = %s
                       ORDER BY edition_language""",
                    (date,)
                )
                rows = cur.fetchall()
            conn.close()
            matches = [
                {"language": r[0] or "Hindi", "name": r[1] or ""}
                for r in rows if r[2] is not False
            ]
            return jsonify({"editions": matches})
        except Exception as e:
            print(f"[epaper] editions-by-date fast query failed: {e}")

    editions = load_editions()
    matches = [
        {"language": e.get("language", "Hindi"), "name": e.get("name", "")}
        for e in editions
        if e["date"] == date and e.get("published", True)
    ]
    return jsonify({"editions": matches})


# ── API: Get edition by date ───────────────────────
@epaper_bp.route("/api/epaper/edition/<date>")
@limiter.limit("60 per minute")
def api_edition(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    lang = request.args.get("lang", None)
    rkey = redis_edition_key(date, lang)

    edition = redis_get(rkey)

    if not edition:
        edition = fast_load_single_edition(date, lang)
        if edition:
            redis_set(rkey, edition, ttl=REDIS_EDITION_TTL)

    if not edition:
        editions = load_editions()
        if lang:
            edition = next(
                (e for e in editions if e["date"] == date and e.get("published", True) and e.get("language", "Hindi") == lang),
                None,
            )
        if not edition:
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
@limiter.limit("30 per minute")
def api_record_edition_view(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400
    language = request.args.get("lang", "")
    count = increment_edition_view(date, language)
    return jsonify({"date": date, "language": language, "views": count})


# ── API: Get edition view count (no increment) ────
@epaper_bp.route("/api/epaper/edition/<date>/views", methods=["GET"])
@limiter.limit("60 per minute")
def api_get_edition_views(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400
    language = request.args.get("lang", "")
    if pg_url():
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
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
    data = load_views_file()
    count = int(data.get(views_key(date, language), 0))
    return jsonify({"date": date, "language": language, "views": count})


# ── API: Get article ──────────────────────────────
@epaper_bp.route("/api/epaper/article/<article_id>")
@limiter.limit("60 per minute")
def api_article(article_id):
    article, related, edition, page = find_epaper_article(article_id)
    if article:
        return jsonify({**article, "related_articles": related})
    return jsonify({"error": "Article not found."}), 404


# ── API: Create / Update edition (Admin) ───────────
@epaper_bp.route("/api/epaper/admin/edition", methods=["POST"])
def api_create_edition():
    guard = require_epaper_admin()
    if guard is not None: return guard
    data = request.get_json(force=True, silent=True) or {}
    date_str = (data.get("date", "") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": f"Invalid date: '{date_str}'. Expected YYYY-MM-DD."}), 400

    lang_str = data.get("language", "Hindi")
    original_date = data.get("original_date", "")
    original_lang = data.get("original_lang", "")
    renamed = bool(original_date) and (original_date != date_str or original_lang != lang_str)

    def _apply_payload(existing):
        if existing is None:
            edition = {
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
        else:
            edition = existing
            edition["date"] = date_str
            edition["name"] = data.get("name", existing.get("name", ""))
            edition["language"] = data.get("language", existing.get("language", "Hindi"))
            edition["published"] = data.get("published", existing.get("published", True))
            edition["masthead_image_url"] = data.get("masthead_image_url", existing.get("masthead_image_url", ""))
            if "footer_links" in data:
                edition["footer_links"] = data["footer_links"]
            if "header_items" in data:
                edition["header_items"] = data["header_items"]
            if "pages" in data:
                edition["pages"] = data["pages"]
        return _sanitize_edition_payload(edition)

    if pg_url():
        conn = None
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
            existing = load_one_edition_pg(conn, date_str, lang_str)
            saved_edition = _apply_payload(existing)
            if data.get("merge_pages") and "pages" in data:
                saved_edition["pages"] = merge_pages_into(
                    saved_edition.get("pages"),
                    data.get("pages") or [],
                    data.get("page_set"),
                )
            if existing and not data.get("force"):
                guard = content_regression(existing, saved_edition.get("pages"))
                wiped = per_page_wipes(existing.get("pages"), saved_edition.get("pages"))
                if wiped:
                    if guard is None:
                        guard = {}
                    guard["wiped_pages"] = wiped[:8]
                    guard["total_wiped_pages"] = len(wiped)
                if guard:
                    detail = ""
                    if "existing_filled" in guard:
                        detail = (
                            f"filled articles {guard['existing_filled']} → "
                            f"{guard['incoming_filled']}"
                        )
                    elif guard.get("total_wiped_pages"):
                        detail = f"{guard['total_wiped_pages']} page(s) ka poora content khali ho jayega"
                    return jsonify({
                        "error": (
                            f"SAFETY GUARD: this save would drop {detail}. "
                            f"If this is intentional, confirm the overwrite in the editor."
                        ),
                        "guard": guard,
                    }), 409
            with conn.cursor() as cur:
                upsert_edition_row(cur, saved_edition)
                if renamed:
                    old_row = load_one_edition_pg(conn, original_date, original_lang or "Hindi")
                    if old_row:
                        save_edition_backup(old_row, conn=conn)
                    cur.execute(
                        "DELETE FROM epaper_editions_v2 WHERE edition_date=%s AND edition_language=%s",
                        (original_date, original_lang or "Hindi"),
                    )
            conn.commit()
            invalidate_editions_cache(date=date_str, lang=lang_str)
            if renamed:
                invalidate_editions_cache(date=original_date, lang=original_lang)
            if data.get("backup", True):
                save_edition_backup(saved_edition, conn=conn)
            try:
                if existing is None and saved_edition.get("published", True):
                    if push_once_for_date(conn, date_str):
                        send_new_edition_notification(saved_edition)
            except Exception as _pe:
                print(f"[epaper] new-edition push failed (non-fatal): {_pe}")
            conn.close()
            return jsonify({"success": True, "published": saved_edition.get("published", True)}), 201
        except Exception as exc:
            if conn:
                try: conn.close()
                except: pass
            print(f"[epaper] Postgres save failed, falling back to file: {exc}")

    editions = load_editions_from_file()
    if renamed:
        editions = [
            e for e in editions
            if not (e["date"] == original_date and e.get("language", "Hindi") == (original_lang or "Hindi"))
        ]
    existing = next(
        (e for e in editions if e["date"] == date_str and e.get("language", "Hindi") == lang_str),
        None,
    )
    if existing:
        saved_edition = _apply_payload(existing)
    else:
        saved_edition = _apply_payload(None)
        editions.append(saved_edition)
    if data.get("merge_pages") and "pages" in data:
        saved_edition["pages"] = merge_pages_into(
            saved_edition.get("pages"),
            data.get("pages") or [],
            data.get("page_set"),
        )
    if existing and not data.get("force"):
        guard = content_regression(existing, saved_edition.get("pages"))
        wiped = per_page_wipes(existing.get("pages"), saved_edition.get("pages"))
        if wiped:
            if guard is None:
                guard = {}
            guard["wiped_pages"] = wiped[:8]
            guard["total_wiped_pages"] = len(wiped)
        if guard:
            return jsonify({
                "error": (
                    f"SAFETY GUARD: this save would drop significant content. "
                    f"If this is intentional, confirm the overwrite in the editor."
                ),
                "guard": guard,
            }), 409
    try:
        save_editions_to_file(editions)
    except Exception as exc:
        return jsonify({"error": f"Save failed: {exc}"}), 500
    invalidate_editions_cache(date=date_str, lang=lang_str)
    if renamed:
        invalidate_editions_cache(date=original_date, lang=original_lang)
    if data.get("backup", True):
        save_edition_backup(saved_edition)
    try:
        if existing is None and saved_edition.get("published", True):
            send_new_edition_notification(saved_edition)
    except Exception as _pe:
        print(f"[epaper] new-edition push (file) failed (non-fatal): {_pe}")
    warning = None
    if not pg_url() and (os.getenv("VERCEL") == "1" or os.getenv("RENDER")):
        warning = "⚠️ Saved to local file (ephemeral on Vercel). Configure SUPABASE_POSTGRES_URL for persistence."
    return jsonify({"success": True, "published": saved_edition.get("published", True), "warning": warning}), 201


# ── API: Get edition (admin — no published filter) ────
@epaper_bp.route("/api/epaper/admin/edition/<date>", methods=["GET"])
def api_get_edition_admin(date):
    guard = require_epaper_admin()
    if guard is not None: return guard
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format"}), 400
    lang = request.args.get("lang", None)
    effective_lang = lang or "Hindi"

    edition = None
    if pg_url():
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
            edition = load_one_edition_pg(conn, date, effective_lang)
            if not edition and lang:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT data FROM epaper_editions_v2 WHERE edition_date=%s LIMIT 1",
                        (date,),
                    )
                    row = cur.fetchone()
                edition = row_to_edition(row[0]) if row else None
            conn.close()
        except Exception as exc:
            print(f"[epaper] admin get fast-path failed: {exc}")
            edition = None

    if edition is None:
        all_editions = load_editions_from_file() or []
        if lang:
            edition = next(
                (e for e in all_editions if e["date"] == date and e.get("language", "Hindi") == lang),
                None,
            )
            if not edition:
                edition = next((e for e in all_editions if e["date"] == date), None)
        else:
            edition = next((e for e in all_editions if e["date"] == date), None)

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
    guard = require_epaper_admin()
    if guard is not None: return guard
    lang = request.args.get("lang", None)
    if not lang:
        return jsonify({"error": "Language parameter required for deletion."}), 400
    try:
        if pg_url():
            conn = None
            try:
                conn = pg_connect()
                pg_ensure_table(conn)
                doomed = load_one_edition_pg(conn, date, lang)
                if doomed:
                    save_edition_backup(doomed, conn=conn)
                if conn:
                    conn.close()
                    conn = None
            except Exception as be:
                print(f"[epaper] pre-delete backup failed (non-fatal): {be}")
            finally:
                if conn:
                    try: conn.close()
                    except: pass
        delete_edition_row(date, lang)
        invalidate_editions_cache(date=date, lang=lang)
        try:
            all_editions = load_editions_from_file() or []
            remaining = [e for e in all_editions if not (e["date"] == date and e.get("language", "Hindi") == lang)]
            save_editions_to_file(remaining)
        except Exception as fe:
            print(f"[epaper] Local file sync after delete failed (non-fatal): {fe}")
    except Exception as exc:
        return jsonify({"error": f"Delete failed: {exc}"}), 500
    return jsonify({"success": True})


# ── AI: Translate ──────────────────────────────────
@epaper_bp.route("/api/epaper/translate", methods=["POST"])
@limiter.limit("10 per minute")
def api_translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    target = data.get("target_lang", "en")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    ck = trans_cache_key(text, target)
    if ck in trans_cache:
        trans_cache.move_to_end(ck)
        return jsonify({"translated_text": trans_cache[ck]})

    lang_names = {
        'hi': 'Hindi', 'mr': 'Marathi', 'en': 'English',
        'bn': 'Bengali', 'ta': 'Tamil', 'te': 'Telugu',
        'gu': 'Gujarati', 'kn': 'Kannada', 'ml': 'Malayalam', 'ur': 'Urdu',
    }
    target_name = lang_names.get(target, target)

    def _save_cache(translated):
        evict(trans_cache, TRANS_CACHE_MAX)
        trans_cache[ck] = translated

    fast_error = None
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
@limiter.limit("10 per minute")
def api_summarize():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    sentences = [s.strip() for s in re.split(r'[।.!?\n]+', text) if s.strip() and len(s.strip()) > 10]

    if not sentences:
        return jsonify({"summary": [text[:200]]})

    if len(sentences) <= 3:
        return jsonify({"summary": sentences})

    stopwords = {'का', 'की', 'के', 'में', 'है', 'हैं', 'को', 'से', 'और', 'पर', 'ने',
                 'एक', 'यह', 'वह', 'भी', 'इस', 'the', 'is', 'a', 'an', 'of', 'in',
                 'to', 'for', 'and', 'on', 'with', 'that', 'this', 'it', 'are', 'was'}
    words = re.findall(r'\w+', text.lower())
    freq = {}
    for w in words:
        if w not in stopwords and len(w) > 2:
            freq[w] = freq.get(w, 0) + 1

    max_freq = max(freq.values()) if freq else 1

    scored = []
    for i, sent in enumerate(sentences):
        score = 0
        sent_words = re.findall(r'\w+', sent.lower())
        for w in sent_words:
            score += freq.get(w, 0) / max_freq
        if i == 0:
            score += 3
        elif i == len(sentences) - 1:
            score += 1.5
        elif i < 3:
            score += 1
        if 20 < len(sent) < 150:
            score += 0.5
        if re.search(r'\d', sent):
            score += 1
        scored.append((score, i, sent))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = sorted(scored[:5], key=lambda x: x[1])
    summary = [s[2] for s in top]

    return jsonify({"summary": summary})


# ── AI: TTS (Edge Neural Voices — Real Indian Anchor) ───────────────────────────────────

def _preprocess_tts_text(text):
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
    t.join(timeout=6)

    if t.is_alive():
        raise TimeoutError("TTS generation timed out")
    if error_holder:
        raise error_holder[0]
    if not chunks:
        raise RuntimeError("TTS returned no audio data")
    return b"".join(chunks)


@epaper_bp.route("/api/epaper/tts", methods=["POST"])
@limiter.limit("5 per minute")
def api_tts():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    voice = data.get("voice", "")
    rate = data.get("rate", "+0%")
    pitch = data.get("pitch", "+0Hz")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    text = text[:800]
    text = _preprocess_tts_text(text)
    voice, rate, pitch = _resolve_voice(text, voice, rate, pitch)

    ck = tts_cache_key(text, voice, rate, pitch)

    if ck in tts_cache:
        tts_cache.move_to_end(ck)
        return send_file(io.BytesIO(tts_cache[ck]), mimetype="audio/mpeg",
                         as_attachment=False, download_name="tts_audio.mp3")

    try:
        audio_bytes = _collect_edge_tts_audio(text, voice, rate, pitch)
    except Exception as e:
        print(f"[TTS] edge_tts failed: {e}")
        return jsonify({"error": f"TTS unavailable: {str(e)}"}), 500

    evict(tts_cache, TTS_CACHE_MAX)
    tts_cache[ck] = audio_bytes
    return send_file(io.BytesIO(audio_bytes), mimetype="audio/mpeg",
                     as_attachment=False, download_name="tts_audio.mp3")


# ── API: Available TTS voices ───────────────────────
@epaper_bp.route("/api/epaper/tts/voices")
@limiter.limit("30 per minute")
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
@epaper_bp.route("/api/epaper/admin/resync-editions-store", methods=["POST"])
def api_resync_editions_store():
    guard = require_epaper_admin()
    if guard is not None: return guard
    if not pg_url():
        return jsonify({"error": "Database not configured"}), 500
    try:
        conn = pg_connect()
        pg_ensure_table(conn)
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

        with conn.cursor() as cur:
            cur.execute("SELECT edition_date, edition_language FROM epaper_editions_v2")
            existing = {(r[0], r[1]) for r in cur.fetchall()}

        new_count = 0
        with conn.cursor() as cur:
            for ed in blob:
                upsert_edition_row(cur, ed)
                key = (ed.get("date", ""), ed.get("language", "Hindi"))
                if key not in existing:
                    new_count += 1
        conn.commit()
        conn.close()
        invalidate_editions_cache()
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
    guard = require_epaper_admin()
    if guard is not None: return guard
    if not pg_url():
        return jsonify({"backups": []})
    date = request.args.get("date", "")
    lang = request.args.get("lang", "")
    try:
        conn = pg_connect()
        pg_ensure_table(conn)
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
    guard = require_epaper_admin()
    if guard is not None: return guard
    if not pg_url():
        return jsonify({"error": "Database not configured"}), 500
    try:
        conn = pg_connect()
        pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT snapshot FROM epaper_edition_backups WHERE id = %s", (backup_id,))
            row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Backup not found"}), 404
        edition = row[0]
        if isinstance(edition, str):
            edition = json.loads(edition)

        with conn.cursor() as cur:
            upsert_edition_row(cur, edition)
        conn.commit()
        conn.close()
        invalidate_editions_cache()
        return jsonify({"success": True,
                        "message": f"Edition {edition.get('date')} ({edition.get('language')}) restored successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Diagnostics: where do editions survive across every store? ──
@epaper_bp.route("/api/epaper/admin/diagnostics")
def api_epaper_diagnostics():
    guard = require_epaper_admin()
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

    if pg_url():
        try:
            conn = pg_connect()
            pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM epaper_editions_v2")
                v2 = [row_to_edition(r[0]) for r in cur.fetchall()]
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

    try:
        out["mongodb"] = _summary(load_editions_from_mongo())
    except Exception as e:
        out["mongo_error"] = str(e)

    r = get_redis()
    if not r:
        out["redis"] = "not configured (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN)"
    else:
        try:
            r.set("ep:diag", "ok", ex=30)
            out["redis"] = "reachable"
        except Exception as e:
            out["redis"] = f"configured but unreachable: {e}"

    try:
        out["local_file"] = _summary(load_editions_from_file())
    except Exception as e:
        out["file_error"] = str(e)

    try:
        out["what_site_shows"] = _summary(load_editions())
    except Exception as e:
        out["merge_error"] = str(e)

    return jsonify(out)


# ── Recovery: restore every missing edition from backups ──
@epaper_bp.route("/api/epaper/admin/restore-all-missing", methods=["POST"])
def api_restore_all_missing():
    guard = require_epaper_admin()
    if guard is not None:
        return guard
    if not pg_url():
        return jsonify({"error": "Database not configured."}), 500

    conn = None
    try:
        conn = pg_connect()
        pg_ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT edition_date, edition_language FROM epaper_editions_v2")
            live = {(r[0], r[1]) for r in cur.fetchall()}

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
                    continue
                edition = snap if not isinstance(snap, str) else json.loads(snap)
                upsert_edition_row(cur, edition)
                restored.append(f"{date} ({lang})")
        conn.commit()
        conn.close()
        invalidate_editions_cache()
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
    if not pg_url():
        return jsonify({"error": "Database not configured."}), 500
    try:
        conn = pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM epaper_editions_store")
            count = cur.fetchone()[0]
        conn.close()
        return jsonify({"success": True, "editions": count})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
