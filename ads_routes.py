"""
Advertisement Management — REST APIs + admin page.

One backend serves ads to BOTH the website and the React Native mobile app.
Everything is managed from the existing ePaper admin panel (no separate mobile
admin). Nothing is hardcoded — all ads live in the database.

Storage : Postgres (Supabase) primary, local JSON file fallback (dev / DB down).
Auth    : reuses the ePaper admin session (epaper_routes._require_epaper_admin).
Images  : uploaded via the existing /api/epaper/admin/upload-image endpoint
          (Cloudinary), so this module only stores the returned URL.
"""
import json
import os
import re
import tempfile
import threading
from datetime import datetime, date

from flask import Blueprint, jsonify, render_template, request, redirect, session
from werkzeug.utils import secure_filename

# Reuse ePaper's DB + auth helpers so ads share the same infra and admin login.
try:
    from epaper_routes import _pg_url, _pg_connect, _require_epaper_admin, _CLOUDINARY_URL
except Exception:  # pragma: no cover - only if epaper module is unavailable
    def _pg_url():
        return os.getenv("SUPABASE_POSTGRES_URL") or os.getenv("DATABASE_URL") or ""

    _pg_connect = None
    _CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")

    def _require_epaper_admin():
        return jsonify({"error": "Admin auth unavailable."}), 500


ads_bp = Blueprint("ads", __name__)

# ── Allowed values ───────────────────────────────────────────
PLATFORMS = ("website", "mobile", "both")
WEBSITE_POSITIONS = (
    "homepage_hero", "homepage_top", "homepage_middle", "homepage_bottom",
    "sidebar", "footer", "article_page",
)
MOBILE_POSITIONS = ("home_top", "home_middle", "home_bottom", "between_epaper_cards")
# Common positions used for platform = "both" ads. Each concrete website/mobile
# position maps into one of these buckets, so a single "both" ad renders in the
# equivalent slot on each platform (e.g. "top" → website homepage_top + mobile home_top).
COMMON_POSITIONS = ("top", "middle", "bottom")
POSITION_TO_COMMON = {
    "homepage_top": "top",       "home_top": "top",
    "homepage_middle": "middle", "home_middle": "middle",
    "homepage_bottom": "bottom", "home_bottom": "bottom",
    "footer": "bottom",
}
ALL_POSITIONS = WEBSITE_POSITIONS + MOBILE_POSITIONS
VALID_POSITIONS = set(ALL_POSITIONS) | set(COMMON_POSITIONS)

# Advertisement media types (image is the legacy default → backward compatible).
AD_TYPES = ("image", "video", "audio")
ALLOWED_MEDIA_EXT = {
    "image": {"jpg", "jpeg", "png", "webp"},
    "video": {"mp4"},
    "audio": {"mp3"},
}

# ── File fallback paths ──────────────────────────────────────
ADS_FILE = os.path.join(os.path.dirname(__file__), "data", "advertisements.json")
_ADS_TMP = os.path.join(tempfile.gettempdir(), "advertisements.json")
_file_lock = threading.Lock()

_tables_ready = False

# Column order used when reading rows as tuples.
_COLS = [
    "id", "title", "image_url", "redirect_url", "platform", "position",
    "priority", "start_date", "end_date", "active", "impressions", "clicks",
    "last_displayed_at", "created_at", "updated_at",
]


# ── Helpers ──────────────────────────────────────────────────

def _use_pg():
    return bool(_pg_url()) and _pg_connect is not None


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _today_str():
    return date.today().isoformat()


def _ensure_table(conn):
    global _tables_ready
    if _tables_ready:
        return
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS advertisements (
                id                BIGSERIAL PRIMARY KEY,
                title             TEXT NOT NULL,
                image_url         TEXT NOT NULL DEFAULT '',
                redirect_url      TEXT NOT NULL DEFAULT '',
                platform          TEXT NOT NULL DEFAULT 'both',
                position          TEXT NOT NULL DEFAULT '',
                priority          INTEGER NOT NULL DEFAULT 0,
                start_date        DATE,
                end_date          DATE,
                active            BOOLEAN NOT NULL DEFAULT TRUE,
                impressions       BIGINT NOT NULL DEFAULT 0,
                clicks            BIGINT NOT NULL DEFAULT 0,
                last_displayed_at TIMESTAMPTZ,
                ad_type           TEXT NOT NULL DEFAULT 'image',
                media_url         TEXT NOT NULL DEFAULT '',
                thumbnail         TEXT NOT NULL DEFAULT '',
                duration          INTEGER,
                created_at        TIMESTAMPTZ DEFAULT NOW(),
                updated_at        TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Backward-compatible migration for tables created before video/audio support.
        # Existing image ads keep working: ad_type defaults to 'image'.
        for ddl in (
            "ALTER TABLE advertisements ADD COLUMN IF NOT EXISTS ad_type TEXT NOT NULL DEFAULT 'image'",
            "ALTER TABLE advertisements ADD COLUMN IF NOT EXISTS media_url TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE advertisements ADD COLUMN IF NOT EXISTS thumbnail TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE advertisements ADD COLUMN IF NOT EXISTS duration INTEGER",
        ):
            cur.execute(ddl)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ads_platform_pos ON advertisements (platform, position)")
    conn.commit()
    _tables_ready = True


def _rows_as_dicts(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _serialize(ad):
    """Normalize a raw ad dict (from PG or file) into a JSON-safe dict."""
    imp = int(ad.get("impressions") or 0)
    clk = int(ad.get("clicks") or 0)
    ctr = round((clk / imp) * 100, 2) if imp else 0.0
    duration = ad.get("duration")
    try:
        duration = int(duration) if duration not in (None, "") else None
    except (TypeError, ValueError):
        duration = None
    return {
        "id": ad.get("id"),
        "title": ad.get("title") or "",
        "image_url": ad.get("image_url") or "",
        "redirect_url": ad.get("redirect_url") or "",
        "platform": ad.get("platform") or "both",
        "position": ad.get("position") or "",
        "priority": int(ad.get("priority") or 0),
        "ad_type": ad.get("ad_type") or "image",
        "media_url": ad.get("media_url") or "",
        "thumbnail": ad.get("thumbnail") or "",
        "duration": duration,
        "start_date": _iso(ad.get("start_date")),
        "end_date": _iso(ad.get("end_date")),
        "active": bool(ad.get("active", True)),
        "impressions": imp,
        "clicks": clk,
        "ctr": ctr,
        "last_displayed_at": _iso(ad.get("last_displayed_at")),
        "created_at": _iso(ad.get("created_at")),
        "updated_at": _iso(ad.get("updated_at")),
        "status": _status(ad),
        "click_url": f"/api/v1/ads/{ad.get('id')}/click",
    }


def _status(ad):
    if not bool(ad.get("active", True)):
        return "inactive"
    today = _today_str()
    end = _iso(ad.get("end_date"))
    start = _iso(ad.get("start_date"))
    if end and end < today:
        return "expired"
    if start and start > today:
        return "scheduled"
    return "active"


def _is_live(ad):
    """True if the ad should currently be served (active + within date window)."""
    if not bool(ad.get("active", True)):
        return False
    today = _today_str()
    start = _iso(ad.get("start_date"))
    end = _iso(ad.get("end_date"))
    if start and start > today:
        return False
    if end and end < today:
        return False
    return True


def _platform_match(ad_platform, requested):
    """A website request also matches 'both'; a mobile request also matches 'both'."""
    if not requested or requested == "both":
        return True
    return ad_platform == requested or ad_platform == "both"


# ── File fallback storage ────────────────────────────────────

def _load_file_ads():
    for path in (ADS_FILE, _ADS_TMP):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f) or []
            except Exception:
                continue
    return []


def _save_file_ads(ads):
    for path in (ADS_FILE, _ADS_TMP):
        try:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(ads, f, ensure_ascii=False, indent=2)
            return True
        except (PermissionError, OSError):
            continue
    return False


def _file_next_id(ads):
    return (max([int(a.get("id", 0)) for a in ads], default=0) + 1)


# ── Data access (PG primary, file fallback) ──────────────────

def _fetch_all(filters=None):
    """Return all ads (admin view). filters is an optional dict applied in-Python."""
    filters = filters or {}
    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM advertisements ORDER BY priority DESC, created_at DESC")
                ads = _rows_as_dicts(cur)
            conn.close()
        except Exception as exc:
            print(f"[ads] PG fetch_all failed, using file: {exc}")
            ads = sorted(_load_file_ads(), key=lambda a: (-int(a.get("priority") or 0), a.get("created_at") or ""))
    else:
        ads = sorted(_load_file_ads(), key=lambda a: (-int(a.get("priority") or 0), a.get("created_at") or ""))

    out = [_serialize(a) for a in ads]
    return [a for a in out if _passes_admin_filters(a, filters)]


def _passes_admin_filters(ad, filters):
    q = (filters.get("q") or "").strip().lower()
    platform = filters.get("platform")
    position = filters.get("position")
    status = filters.get("status")
    if q and q not in (ad["title"] or "").lower():
        return False
    if platform and ad["platform"] != platform:
        return False
    if position and ad["position"] != position:
        return False
    if status and ad["status"] != status:
        return False
    return True


def _positions_to_match(position):
    """A concrete position also matches its common bucket, so "both" ads stored
    with a common slug (top/middle/bottom) surface in the equivalent slot."""
    if not position:
        return None
    matches = [position]
    bucket = POSITION_TO_COMMON.get(position)
    if bucket and bucket != position:
        matches.append(bucket)
    return matches


def _fetch_live(platform, position=None, limit=None):
    """Return only ads that should be served right now, sorted by priority."""
    positions = _positions_to_match(position)
    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            # Compare against the IST calendar date (not the DB's UTC CURRENT_DATE)
            # so serving matches the date the admin sees. Avoids a 1-day gap where
            # a "starts today" ad stays hidden because the DB clock is still on
            # the previous UTC day.
            today_sql = "(NOW() AT TIME ZONE 'Asia/Kolkata')::date"
            clauses = [
                "active = TRUE",
                f"(start_date IS NULL OR start_date <= {today_sql})",
                f"(end_date IS NULL OR end_date >= {today_sql})",
            ]
            params = []
            if platform and platform != "both":
                clauses.append("(platform = %s OR platform = 'both')")
                params.append(platform)
            if positions:
                clauses.append("position = ANY(%s)")
                params.append(positions)
            sql = ("SELECT * FROM advertisements WHERE " + " AND ".join(clauses) +
                   " ORDER BY priority DESC, created_at DESC")
            if limit:
                sql += " LIMIT %s"
                params.append(int(limit))
            with conn.cursor() as cur:
                cur.execute(sql, params)
                ads = _rows_as_dicts(cur)
            conn.close()
            return [_serialize(a) for a in ads]
        except Exception as exc:
            print(f"[ads] PG fetch_live failed, using file: {exc}")

    ads = [a for a in _load_file_ads()
           if _is_live(a) and _platform_match(a.get("platform", "both"), platform)
           and (not positions or a.get("position") in positions)]
    ads.sort(key=lambda a: (-int(a.get("priority") or 0), a.get("created_at") or ""))
    if limit:
        ads = ads[:int(limit)]
    return [_serialize(a) for a in ads]


def _get_one(ad_id):
    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM advertisements WHERE id = %s", (ad_id,))
                rows = _rows_as_dicts(cur)
            conn.close()
            return _serialize(rows[0]) if rows else None
        except Exception as exc:
            print(f"[ads] PG get_one failed, using file: {exc}")
    for a in _load_file_ads():
        if str(a.get("id")) == str(ad_id):
            return _serialize(a)
    return None


# ── Payload validation ───────────────────────────────────────

def _clean_payload(data):
    """Validate + normalize an incoming create/update payload.
    Returns (clean_dict, error_str)."""
    title = (data.get("title") or "").strip()
    if not title:
        return None, "Title is required."

    platform = (data.get("platform") or "both").strip().lower()
    if platform not in PLATFORMS:
        return None, f"Invalid platform. Allowed: {', '.join(PLATFORMS)}."

    position = (data.get("position") or "").strip()
    if position and position not in VALID_POSITIONS:
        return None, f"Invalid position '{position}'."

    ad_type = (data.get("advertisement_type") or data.get("ad_type") or "image").strip().lower()
    if ad_type not in AD_TYPES:
        return None, f"Invalid advertisement type. Allowed: {', '.join(AD_TYPES)}."

    media_url = (data.get("media_url") or "").strip()
    thumbnail = (data.get("thumbnail") or "").strip()
    image_url = (data.get("image_url") or "").strip()
    # Video/audio need a media file; image ads keep their existing (optional) banner.
    if ad_type in ("video", "audio") and not media_url:
        return None, f"A media file is required for {ad_type} advertisements."

    duration_raw = data.get("duration")
    try:
        duration = int(float(duration_raw)) if duration_raw not in (None, "") else None
    except (TypeError, ValueError):
        duration = None

    def _norm_date(v):
        v = (v or "").strip()
        if not v:
            return None
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(f"Invalid date '{v}'. Use YYYY-MM-DD.")
        return v

    try:
        start_date = _norm_date(data.get("start_date"))
        end_date = _norm_date(data.get("end_date"))
    except ValueError as e:
        return None, str(e)

    if start_date and end_date and end_date < start_date:
        return None, "End date cannot be before start date."

    try:
        priority = int(data.get("priority") or 0)
    except (TypeError, ValueError):
        return None, "Priority must be a number."

    clean = {
        "title": title,
        "image_url": image_url,
        "redirect_url": (data.get("redirect_url") or "").strip(),
        "platform": platform,
        "position": position,
        "priority": priority,
        "start_date": start_date,
        "end_date": end_date,
        "active": bool(data.get("active", True)),
        "ad_type": ad_type,
        "media_url": media_url,
        "thumbnail": thumbnail,
        "duration": duration,
    }
    return clean, None


# ══════════════════════════════════════════════════════════════
#  PUBLIC APIs  (no auth — consumed by website + mobile app)
# ══════════════════════════════════════════════════════════════

@ads_bp.route("/api/v1/ads")
def api_list_ads():
    """Return only ACTIVE ads whose current date is within [start,end], sorted by
    priority (highest first).
    Query params: platform=website|mobile|both, position=<slug>, limit=<n>."""
    platform = (request.args.get("platform") or "").strip().lower() or None
    position = (request.args.get("position") or "").strip() or None
    limit = request.args.get("limit")
    ads = _fetch_live(platform, position, limit)
    public = [{
        "id": a["id"],
        "title": a["title"],
        "ad_type": a["ad_type"],
        # image_url kept for backward compatibility with existing image clients.
        "image_url": a["image_url"],
        # media_url is the uniform source: image banner, video file, or audio file.
        "media_url": a["media_url"] or a["image_url"],
        # thumbnail: video poster; for images it falls back to the banner itself.
        "thumbnail": a["thumbnail"] or (a["image_url"] if a["ad_type"] == "image" else ""),
        "duration": a["duration"],
        "redirect_url": a["redirect_url"],
        "click_url": a["click_url"],
        "platform": a["platform"],
        "position": a["position"],
        "priority": a["priority"],
    } for a in ads]
    return jsonify({"success": True, "count": len(public), "ads": public})


@ads_bp.route("/api/v1/ads/<int:ad_id>/impression", methods=["POST"])
def api_track_impression(ad_id):
    """Fire when an ad is actually shown on screen. Increments impressions and
    updates last_displayed timestamp."""
    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE advertisements SET impressions = impressions + 1, "
                    "last_displayed_at = NOW() WHERE id = %s", (ad_id,))
            conn.commit()
            conn.close()
            return jsonify({"success": True})
        except Exception as exc:
            print(f"[ads] impression PG failed, using file: {exc}")
    with _file_lock:
        ads = _load_file_ads()
        for a in ads:
            if str(a.get("id")) == str(ad_id):
                a["impressions"] = int(a.get("impressions") or 0) + 1
                a["last_displayed_at"] = datetime.utcnow().isoformat()
                _save_file_ads(ads)
                break
    return jsonify({"success": True})


@ads_bp.route("/api/v1/ads/<int:ad_id>/click")
def api_track_click(ad_id):
    """Increment click count, then 302-redirect to the ad's target URL.
    Works for both a website <a href> and a mobile app openURL()."""
    target = "/"
    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE advertisements SET clicks = clicks + 1 WHERE id = %s "
                    "RETURNING redirect_url", (ad_id,))
                row = cur.fetchone()
            conn.commit()
            conn.close()
            if row and row[0]:
                target = row[0]
        except Exception as exc:
            print(f"[ads] click PG failed, using file: {exc}")
    else:
        with _file_lock:
            ads = _load_file_ads()
            for a in ads:
                if str(a.get("id")) == str(ad_id):
                    a["clicks"] = int(a.get("clicks") or 0) + 1
                    target = a.get("redirect_url") or "/"
                    _save_file_ads(ads)
                    break
    return redirect(target or "/", code=302)


# ══════════════════════════════════════════════════════════════
#  ADMIN APIs  (session-protected — same login as ePaper admin)
# ══════════════════════════════════════════════════════════════

@ads_bp.route("/api/v1/admin/ads", methods=["GET"])
def api_admin_list_ads():
    """List ALL ads (including inactive/expired) with analytics, for management.
    Supports ?q=&platform=&position=&status= filters."""
    guard = _require_epaper_admin()
    if guard is not None:
        return guard
    filters = {
        "q": request.args.get("q"),
        "platform": request.args.get("platform"),
        "position": request.args.get("position"),
        "status": request.args.get("status"),
    }
    ads = _fetch_all(filters)
    totals = {
        "count": len(ads),
        "impressions": sum(a["impressions"] for a in ads),
        "clicks": sum(a["clicks"] for a in ads),
    }
    totals["ctr"] = round((totals["clicks"] / totals["impressions"]) * 100, 2) if totals["impressions"] else 0.0
    return jsonify({"success": True, "ads": ads, "totals": totals})


@ads_bp.route("/api/v1/admin/ads", methods=["POST"])
def api_admin_create_ad():
    guard = _require_epaper_admin()
    if guard is not None:
        return guard
    data = request.get_json(force=True, silent=True) or {}
    clean, err = _clean_payload(data)
    if err:
        return jsonify({"success": False, "error": err}), 400

    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO advertisements
                        (title, image_url, redirect_url, platform, position,
                         priority, start_date, end_date, active,
                         ad_type, media_url, thumbnail, duration)
                    VALUES (%(title)s, %(image_url)s, %(redirect_url)s, %(platform)s,
                            %(position)s, %(priority)s, %(start_date)s, %(end_date)s, %(active)s,
                            %(ad_type)s, %(media_url)s, %(thumbnail)s, %(duration)s)
                    RETURNING id
                """, clean)
                new_id = cur.fetchone()[0]
            conn.commit()
            conn.close()
            return jsonify({"success": True, "ad": _get_one(new_id)}), 201
        except Exception as exc:
            print(f"[ads] create PG failed, using file: {exc}")

    with _file_lock:
        ads = _load_file_ads()
        clean["id"] = _file_next_id(ads)
        clean["impressions"] = 0
        clean["clicks"] = 0
        clean["last_displayed_at"] = None
        clean["created_at"] = datetime.utcnow().isoformat()
        clean["updated_at"] = clean["created_at"]
        ads.append(clean)
        _save_file_ads(ads)
    return jsonify({"success": True, "ad": _serialize(clean)}), 201


@ads_bp.route("/api/v1/admin/ads/<int:ad_id>", methods=["PUT"])
def api_admin_update_ad(ad_id):
    guard = _require_epaper_admin()
    if guard is not None:
        return guard
    data = request.get_json(force=True, silent=True) or {}
    clean, err = _clean_payload(data)
    if err:
        return jsonify({"success": False, "error": err}), 400

    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE advertisements SET
                        title=%(title)s, image_url=%(image_url)s, redirect_url=%(redirect_url)s,
                        platform=%(platform)s, position=%(position)s, priority=%(priority)s,
                        start_date=%(start_date)s, end_date=%(end_date)s, active=%(active)s,
                        ad_type=%(ad_type)s, media_url=%(media_url)s, thumbnail=%(thumbnail)s,
                        duration=%(duration)s, updated_at=NOW()
                    WHERE id=%(id)s
                """, {**clean, "id": ad_id})
                found = cur.rowcount > 0
            conn.commit()
            conn.close()
            if not found:
                return jsonify({"success": False, "error": "Ad not found."}), 404
            return jsonify({"success": True, "ad": _get_one(ad_id)})
        except Exception as exc:
            print(f"[ads] update PG failed, using file: {exc}")

    with _file_lock:
        ads = _load_file_ads()
        found = None
        for a in ads:
            if str(a.get("id")) == str(ad_id):
                a.update(clean)
                a["updated_at"] = datetime.utcnow().isoformat()
                found = a
                break
        if not found:
            return jsonify({"success": False, "error": "Ad not found."}), 404
        _save_file_ads(ads)
    return jsonify({"success": True, "ad": _serialize(found)})


@ads_bp.route("/api/v1/admin/ads/<int:ad_id>", methods=["DELETE"])
def api_admin_delete_ad(ad_id):
    guard = _require_epaper_admin()
    if guard is not None:
        return guard

    if _use_pg():
        try:
            conn = _pg_connect()
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM advertisements WHERE id = %s", (ad_id,))
                found = cur.rowcount > 0
            conn.commit()
            conn.close()
            if not found:
                return jsonify({"success": False, "error": "Ad not found."}), 404
            return jsonify({"success": True})
        except Exception as exc:
            print(f"[ads] delete PG failed, using file: {exc}")

    with _file_lock:
        ads = _load_file_ads()
        new_ads = [a for a in ads if str(a.get("id")) != str(ad_id)]
        if len(new_ads) == len(ads):
            return jsonify({"success": False, "error": "Ad not found."}), 404
        _save_file_ads(new_ads)
    return jsonify({"success": True})


# ── Media upload (image / video / audio) ─────────────────────

def _cloudinary_resource_type(mtype):
    # Cloudinary stores audio under the 'video' resource type.
    return "image" if mtype == "image" else "video"


def _upload_media(file_bytes, filename, mtype):
    """Upload media to Cloudinary (compressed) and return
    {url, thumbnail, duration}. Falls back to local static storage in dev."""
    import io as _io
    import os as _os
    import re as _re

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    stem = _os.path.splitext(secure_filename(filename))[0][:48] or "ad_media"

    if _CLOUDINARY_URL:
        import cloudinary.uploader
        opts = {
            "folder": "ads",
            "public_id": stem,
            "overwrite": True,
            "resource_type": _cloudinary_resource_type(mtype),
            # Compress on upload (image: visually lossless; video/audio: auto).
            "quality": "auto:good" if mtype == "image" else "auto",
        }
        result = cloudinary.uploader.upload(_io.BytesIO(file_bytes), **opts)
        url = result["secure_url"]
        out = {"url": url, "thumbnail": "", "duration": None}
        if mtype == "video":
            # First-frame poster generated by Cloudinary (so_0 = start offset).
            poster = _re.sub(r"\.(mp4|mov|webm)$", ".jpg", url, flags=_re.I)
            out["thumbnail"] = poster.replace("/upload/", "/upload/so_0/", 1)
        if mtype in ("video", "audio") and result.get("duration") is not None:
            try:
                out["duration"] = int(round(float(result["duration"])))
            except (TypeError, ValueError):
                out["duration"] = None
        return out

    # Local fallback (dev only — Vercel filesystem is ephemeral).
    from datetime import datetime as _dt
    updir = _os.path.join(_os.path.dirname(__file__), "static", "uploads", "ads")
    _os.makedirs(updir, exist_ok=True)
    fname = f"{stem}-{_dt.now().strftime('%Y%m%d%H%M%S%f')}.{ext}"
    with open(_os.path.join(updir, fname), "wb") as fh:
        fh.write(file_bytes)
    return {"url": f"/static/uploads/ads/{fname}", "thumbnail": "", "duration": None}


@ads_bp.route("/api/v1/admin/ads/upload", methods=["POST"])
def api_admin_upload_media():
    """Upload an image / video / audio file for an advertisement.
    Validates the file format per type, compresses, and returns the media URL
    (+ auto thumbnail & duration for video/audio)."""
    guard = _require_epaper_admin()
    if guard is not None:
        return guard

    mtype = (request.form.get("type") or "image").strip().lower()
    if mtype not in ALLOWED_MEDIA_EXT:
        return jsonify({"success": False, "error": "Invalid media type."}), 400

    f = request.files.get("file") or request.files.get("image")
    if not f or not f.filename:
        return jsonify({"success": False, "error": "No file uploaded."}), 400

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_MEDIA_EXT[mtype]:
        allowed = ", ".join(sorted(ALLOWED_MEDIA_EXT[mtype])).upper()
        return jsonify({"success": False,
                        "error": f"Invalid file for {mtype}. Allowed: {allowed}."}), 400

    try:
        result = _upload_media(f.read(), f.filename, mtype)
        return jsonify({"success": True, **result}), 201
    except Exception as e:
        return jsonify({"success": False, "error": f"Upload failed: {e}"}), 500


# ── Admin page ───────────────────────────────────────────────

@ads_bp.route("/epaper-admin/ads")
def ads_admin_page():
    guard = _require_epaper_admin()
    if guard is not None:
        return guard
    return render_template(
        "ads_admin.html",
        website_positions=WEBSITE_POSITIONS,
        mobile_positions=MOBILE_POSITIONS,
        common_positions=COMMON_POSITIONS,
        ad_types=AD_TYPES,
    )
