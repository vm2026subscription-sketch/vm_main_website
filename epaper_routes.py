"""
E-Paper routes — edition/page/article APIs + AI features
"""
import json
import os
import re
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename

epaper_bp = Blueprint("epaper", __name__)

# ── In-memory store (replace with DB later) ────────
EDITIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "epaper_editions.json")
EPAPER_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "epaper")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def _ensure_data_dir():
    d = os.path.dirname(EDITIONS_FILE)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _load_editions():
    _ensure_data_dir()
    if not os.path.exists(EDITIONS_FILE):
        return []
    try:
        with open(EDITIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_editions(data):
    _ensure_data_dir()
    with open(EDITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


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
@epaper_bp.route("/epaper-viewer")
@epaper_bp.route("/epaper-viewer/<date>")
@epaper_bp.route("/epaper-viewer/<date>/page-<int:page>")
def epaper_viewer(date=None, page=1):
    return render_template("epaper_viewer.html", initial_date=date, initial_page=page)


# ── Admin Page (Region Mapper) ─────────────────────
@epaper_bp.route("/epaper-admin")
def epaper_admin_v2():
    return render_template("epaper_admin_v2.html")


@epaper_bp.route("/api/epaper/admin/upload-image", methods=["POST"])
def api_upload_epaper_image():
    image = request.files.get("image")
    if not image or not image.filename:
        return jsonify({"error": "image file required"}), 400
    if not _allowed_image(image.filename):
        return jsonify({"error": "Unsupported image type"}), 400

    os.makedirs(EPAPER_UPLOAD_DIR, exist_ok=True)
    original = secure_filename(image.filename)
    stem, ext = os.path.splitext(original)
    filename = f"{stem[:48]}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}{ext.lower()}"
    image.save(os.path.join(EPAPER_UPLOAD_DIR, filename))
    return jsonify({
        "success": True,
        "url": url_for("static", filename=f"uploads/epaper/{filename}"),
    }), 201


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
        {"date": e["date"], "name": e.get("name", ""), "language": e.get("language", "Hindi"),
         "total_pages": len(e.get("pages", []))}
        for e in editions
    ]})


# ── API: Get edition by date ───────────────────────
@epaper_bp.route("/api/epaper/edition/<date>")
def api_edition(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    editions = _load_editions()
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
    })


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
    data = request.get_json(silent=True) or {}
    date_str = data.get("date", "")
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "date required (YYYY-MM-DD)."}), 400

    editions = _load_editions()
    existing = next((e for e in editions if e["date"] == date_str), None)

    if existing:
        existing["name"] = data.get("name", existing.get("name", ""))
        existing["language"] = data.get("language", existing.get("language", "Hindi"))
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
            "masthead_image_url": data.get("masthead_image_url", ""),
            "footer_links": data.get("footer_links", []),
            "header_items": data.get("header_items", []),
            "pages": data.get("pages", []),
            "created_at": datetime.now().isoformat(),
        })

    _save_editions(editions)
    return jsonify({"success": True}), 201


# ── API: Delete edition ───────────────────────────
@epaper_bp.route("/api/epaper/admin/edition/<date>", methods=["DELETE"])
def api_delete_edition(date):
    editions = _load_editions()
    editions = [e for e in editions if e["date"] != date]
    _save_editions(editions)
    return jsonify({"success": True})


# ── AI: Translate ──────────────────────────────────
@epaper_bp.route("/api/epaper/translate", methods=["POST"])
def api_translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    target = data.get("target_lang", "en")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    # Free fallback: simple placeholder (replace with real API)
    # For production, integrate Google Translate API or LibreTranslate
    try:
        # Attempt LibreTranslate (self-hosted or free instance)
        from urllib.request import Request, urlopen
        libre_url = os.getenv("LIBRETRANSLATE_URL", "https://libretranslate.de/translate")
        req_body = json.dumps({
            "q": text[:2000],
            "source": "auto",
            "target": target,
            "format": "text",
        }).encode("utf-8")
        req = Request(libre_url, data=req_body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return jsonify({"translated_text": result.get("translatedText", text)})
    except Exception:
        # Fallback — return original text with a note
        return jsonify({
            "translated_text": text,
            "note": "Translation API unavailable. Showing original text."
        })


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


# ── AI: TTS (server-side, optional) ────────────────
@epaper_bp.route("/api/epaper/tts", methods=["POST"])
def api_tts():
    """Optional server-side TTS. Frontend uses Web Speech API by default."""
    return jsonify({
        "note": "Using browser-native Web Speech API. No server TTS needed.",
        "supported": True,
    })
