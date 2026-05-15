"""
E-Paper routes — edition/page/article APIs + AI features
"""
import json
import os
import re
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, send_file, session
from werkzeug.utils import secure_filename

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "saurabhedict@gmail.com")


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
    conn.commit()


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


# ── Public load / save ──────────────────────────────

def _load_editions():
    if _pg_url():
        try:
            conn = _pg_connect()
            _pg_ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM epaper_editions_store WHERE id = 'editions'")
                row = cur.fetchone()
            conn.close()
            db_data = row[0] if row else []
            if isinstance(db_data, str):
                db_data = json.loads(db_data)
            # Auto-migrate: if DB empty but JSON file has data, seed DB once
            if not db_data:
                file_data = _load_editions_from_file()
                if file_data:
                    _save_editions(file_data)
                return file_data
            return db_data
        except Exception as e:
            print(f"[epaper] Postgres load failed, falling back to file: {e}")
    return _load_editions_from_file()


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
@epaper_bp.route("/epaper-viewer")
@epaper_bp.route("/epaper-viewer/<date>")
@epaper_bp.route("/epaper-viewer/<date>/page-<int:page>")
def epaper_viewer(date=None, page=1):
    return render_template("epaper_viewer.html", initial_date=date, initial_page=page)


# ── Admin Page (Region Mapper) ─────────────────────
@epaper_bp.route("/epaper-admin")
def epaper_admin_v2():
    admin_user = session.get("auth_user", {})
    return render_template("epaper_admin_v2.html", admin_user=admin_user)


EPAPER_TMP_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "epaper_uploads")


@epaper_bp.route("/api/epaper/admin/upload-image", methods=["POST"])
def api_upload_epaper_image():
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

    # Try primary static uploads dir; fall back to /tmp on read-only filesystems (Vercel)
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
    lang_str = data.get("language", "Hindi")
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

    try:
        _save_editions(editions)
    except Exception as exc:
        return jsonify({"error": f"Save failed: {exc}"}), 500
    return jsonify({"success": True}), 201


# ── API: Get edition (admin — no published filter) ────
@epaper_bp.route("/api/epaper/admin/edition/<date>", methods=["GET"])
def api_get_edition_admin(date):
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
    lang = request.args.get("lang", None)
    editions = _load_editions()
    if lang:
        editions = [e for e in editions if not (e["date"] == date and e.get("language", "Hindi") == lang)]
    else:
        editions = [e for e in editions if e["date"] != date]
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

    lang_names = {
        'hi': 'Hindi', 'mr': 'Marathi', 'en': 'English',
        'bn': 'Bengali', 'ta': 'Tamil', 'te': 'Telugu',
    }
    target_name = lang_names.get(target, target)

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
            return jsonify({"translated_text": translated})
        except Exception as e:
            import traceback
            traceback.print_exc()

    # Fallback: deep_translator
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
        return jsonify({"translated_text": "\n\n".join(translated_chunks)})
    except Exception as e:
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500


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
@epaper_bp.route("/api/epaper/tts", methods=["POST"])
def api_tts():
    """Server-side TTS using Microsoft Edge Neural voices.
    Returns MP3 audio with natural Indian news anchor voice.
    """
    import asyncio
    import io

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    voice = data.get("voice", "")  # optional override
    rate = data.get("rate", "+0%")  # e.g. "+10%", "-5%"
    pitch = data.get("pitch", "+0Hz")  # e.g. "+5Hz", "-5Hz"

    if not text:
        return jsonify({"error": "No text provided."}), 400

    text = text[:5000]

    # ── Language detection ──────────────────────────────────────────────────
    devanagari_chars = len(re.findall(r'[ऀ-ॿ]', text))
    devanagari_ratio = devanagari_chars / max(len(text), 1)

    MARATHI_WORDS = [
        'आहे', 'नाही', 'आणि', 'मला', 'आपण', 'होते', 'केले', 'झाले',
        'त्यांनी', 'म्हणाले', 'यावर', 'यामुळे', 'सांगितले', 'महाराष्ट्र',
        'पुणे', 'मुंबई', 'नागपूर', 'ठाणे', 'सरकार', 'विद्यार्थी'
    ]
    HINDI_WORDS = [
        'है', 'नहीं', 'और', 'था', 'हैं', 'यह', 'हो', 'उन्होंने',
        'कहा', 'इससे', 'इसलिए', 'बताया', 'राज्य', 'सरकार'
    ]
    marathi_hits = sum(1 for w in MARATHI_WORDS if w in text)
    hindi_hits = sum(1 for w in HINDI_WORDS if w in text)

    if not voice:
        if devanagari_ratio > 0.3:
            if marathi_hits > hindi_hits:
                voice = "mr-IN-ManoharNeural"
                if rate == "+0%": rate = "-2%"
                if pitch == "+0Hz": pitch = "+2Hz"
            else:
                voice = "hi-IN-MadhurNeural"
                if rate == "+0%": rate = "-2%"
                if pitch == "+0Hz": pitch = "+2Hz"
        else:
            voice = "en-IN-PrabhatNeural"
            if rate == "+0%": rate = "-2%"
            if pitch == "+0Hz": pitch = "+1Hz"
    else:
        _voice_defaults = {
            "hi-IN-MadhurNeural":  ("-2%", "+2Hz"),
            "hi-IN-SwaraNeural":   ("-1%", "+1Hz"),
            "mr-IN-ManoharNeural": ("-2%", "+2Hz"),
            "mr-IN-AarohiNeural":  ("-1%", "+1Hz"),
            "en-IN-PrabhatNeural": ("-2%", "+1Hz"),
            "en-IN-NeerjaNeural":  ("-1%", "+1Hz"),
        }
        if voice in _voice_defaults and rate == "+0%" and pitch == "+0Hz":
            rate, pitch = _voice_defaults[voice]

    # ── Server-side text preprocessing for natural delivery ─────────────────
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

    if isinstance(rate, (int, float)):
        pct = int((rate - 1) * 100)
        rate = f"+{pct}%" if pct >= 0 else f"{pct}%"

    async def _generate_audio():
        import edge_tts
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    try:
        import sys
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_bytes = loop.run_until_complete(_generate_audio())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        if not audio_bytes:
            return jsonify({"error": "TTS generation failed."}), 500

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="tts_audio.mp3",
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
