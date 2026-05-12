"""
E-Paper routes — edition/page/article APIs + AI features
"""
import json
import os
import re
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, send_file
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
    text = data.get("text", "").strip()
    target = data.get("target_lang", "en")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    try:
        from deep_translator import GoogleTranslator
        # Split into chunks ≤4500 chars (Google Translate limit)
        chunks, start = [], 0
        while start < len(text):
            end = min(start + 4500, len(text))
            # Break at sentence boundary if possible
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
        return jsonify({"translated_text": text, "note": f"Translation failed: {str(e)}"})


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


# ── AI: TTS (Google gTTS — reliable for Indian languages) ──
@epaper_bp.route("/api/epaper/tts", methods=["POST"])
def api_tts():
    """Server-side TTS using Google gTTS. Returns MP3 audio. Supports Hindi, Marathi, English."""
    import io

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    voice = data.get("voice", "")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    text = text[:5000]

    # Auto-detect language from text or voice hint
    VOICE_TO_LANG = {
        "hi-IN-MadhurNeural": "hi", "hi-IN-SwaraNeural": "hi",
        "mr-IN-ManoharNeural": "mr", "mr-IN-AarohiNeural": "mr",
        "en-IN-PrabhatNeural": "en", "en-IN-NeerjaNeural": "en",
    }
    lang = VOICE_TO_LANG.get(voice, "")

    if not lang:
        devanagari_chars = len(re.findall(r'[ऀ-ॿ]', text))
        devanagari_ratio = devanagari_chars / max(len(text), 1)
        MARATHI_WORDS = ['आहे','नाही','आणि','मला','आपण','होते','केले','झाले','त्यांनी','म्हणाले','महाराष्ट्र','पुणे','मुंबई']
        HINDI_WORDS   = ['है','नहीं','और','था','हैं','यह','हो','उन्होंने','कहा','इससे','बताया']
        marathi_hits = sum(1 for w in MARATHI_WORDS if w in text)
        hindi_hits   = sum(1 for w in HINDI_WORDS if w in text)

        if devanagari_ratio > 0.3:
            lang = "mr" if marathi_hits > hindi_hits else "hi"
        else:
            lang = "en"

    # Normalize newlines so gTTS never pauses mid-sentence at a \n
    text = re.sub(r'\r\n', ' ', text)
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r' +', ' ', text).strip()

    try:
        from gtts import gTTS

        # Split text at sentence boundaries into chunks ≤ 90 chars so gTTS
        # never has to cut a sentence at an arbitrary space mid-word.
        def _sentence_chunks(t, max_chars=90):
            parts = re.split(r'(?<=[.!?।])\s+', t.strip())
            chunks, buf = [], ''
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if not buf:
                    buf = part
                elif len(buf) + 1 + len(part) <= max_chars:
                    buf += ' ' + part
                else:
                    chunks.append(buf)
                    buf = part
            if buf:
                chunks.append(buf)
            return chunks or [t]

        audio_buf = io.BytesIO()
        for chunk in _sentence_chunks(text):
            gTTS(text=chunk, lang=lang, slow=False).write_to_fp(audio_buf)
        audio_buf.seek(0)
        return send_file(
            audio_buf,
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
        {"id": "hi-IN-MadhurNeural",  "name": "माधुर ♂ (Hindi)",   "lang": "hi", "gender": "male"},
        {"id": "hi-IN-SwaraNeural",   "name": "स्वरा ♀ (Hindi)",   "lang": "hi", "gender": "female"},
        {"id": "mr-IN-ManoharNeural", "name": "मनोहर ♂ (Marathi)", "lang": "mr", "gender": "male"},
        {"id": "mr-IN-AarohiNeural",  "name": "आरोही ♀ (Marathi)", "lang": "mr", "gender": "female"},
        {"id": "en-IN-PrabhatNeural", "name": "Prabhat ♂ (English)","lang": "en", "gender": "male"},
        {"id": "en-IN-NeerjaNeural",  "name": "Neerja ♀ (English)", "lang": "en", "gender": "female"},
    ]})
