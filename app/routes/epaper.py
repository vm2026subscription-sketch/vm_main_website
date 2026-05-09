"""
E-Paper routes — edition/page/article APIs + AI features
All data stored in MongoDB. Article images on Cloudinary.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

epaper_bp = Blueprint("epaper", __name__)

# ── Simple in-memory API cache ────────────────────────
_cache = {}
_CACHE_TTL = 300  # 5 minutes

def _get_cached(key):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None

def _set_cached(key, data):
    _cache[key] = {"data": data, "ts": time.time()}

def _invalidate_cache(prefix=""):
    keys = [k for k in _cache if k.startswith(prefix)] if prefix else list(_cache.keys())
    for k in keys:
        _cache.pop(k, None)


# ── Helpers ─────────────────────────────────────────


def _get_editions_col():
    from app.utils.mongo import get_epaper_editions_collection
    return get_epaper_editions_collection()


def _get_logged_in_user():
    user = session.get("auth_user")
    if isinstance(user, dict) and user.get("email"):
        return user
    return None


def _is_admin_user():
    user = _get_logged_in_user()
    return bool(user and str(user.get("role", "")).strip().lower() == "admin")


def _is_api_request():
    return (
        request.path.startswith("/api/")
        or request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = _get_logged_in_user()
        if user is None:
            if _is_api_request():
                return jsonify({"error": "Login required."}), 401

            next_url = request.full_path.rstrip("?") if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))

        if not _is_admin_user():
            if _is_api_request():
                return jsonify({"error": "Admin access required."}), 403
            return "Admin access required.", 403

        return view(*args, **kwargs)

    return wrapped


# ── Viewer Page ────────────────────────────────────
@epaper_bp.route("/epaper-viewer")
@epaper_bp.route("/epaper-viewer/<date>")
@epaper_bp.route("/epaper-viewer/<date>/page-<int:page>")
def epaper_viewer(date=None, page=1):
    return render_template("pages/epaper_viewer.html", initial_date=date, initial_page=page)


# ── Admin Page (Region Mapper) ─────────────────────
@epaper_bp.route("/epaper-admin")
@admin_required
def epaper_admin_v2():
    return render_template("admin/epaper_admin_v2.html")


# ── API: List editions ─────────────────────────────
@epaper_bp.route("/api/epaper/editions")
def api_editions():
    cached = _get_cached("editions_list")
    if cached:
        resp = jsonify(cached)
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    col = _get_editions_col()
    editions = list(col.find({}, {"_id": 0}).sort("date", -1))
    result = {"editions": [
        {"date": e["date"], "name": e.get("name", ""), "language": e.get("language", "Hindi"),
         "total_pages": len(e.get("pages", []))}
        for e in editions
    ]}
    _set_cached("editions_list", result)
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


# ── API: Get edition by date ───────────────────────
@epaper_bp.route("/api/epaper/edition/<date>")
def api_edition(date):
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    cache_key = f"edition_{date}"
    cached = _get_cached(cache_key)
    if cached:
        resp = jsonify(cached)
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    col = _get_editions_col()
    edition = col.find_one({"date": date}, {"_id": 0})

    if not edition:
        return jsonify({"error": "No edition for this date."}), 404

    result = {
        "date": edition["date"],
        "name": edition.get("name", ""),
        "language": edition.get("language", "Hindi"),
        "pages": edition.get("pages", []),
    }
    _set_cached(cache_key, result)
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


# ── API: Get article ──────────────────────────────
@epaper_bp.route("/api/epaper/article/<article_id>")
def api_article(article_id):
    col = _get_editions_col()
    for ed in col.find({}, {"_id": 0}):
        for page in ed.get("pages", []):
            for art in page.get("articles", []):
                if str(art.get("id")) == str(article_id):
                    return jsonify(art)
    return jsonify({"error": "Article not found."}), 404


# ── API: Create / Update edition (Admin) ───────────
@epaper_bp.route("/api/epaper/admin/edition", methods=["POST"])
@admin_required
def api_create_edition():
    data = request.get_json(silent=True) or {}
    date_str = data.get("date", "")
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date_str):
        return jsonify({"error": "date required (YYYY-MM-DD)."}), 400

    col = _get_editions_col()
    existing = col.find_one({"date": date_str})

    if existing:
        update = {
            "name": data.get("name", existing.get("name", "")),
            "language": data.get("language", existing.get("language", "Hindi")),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if "pages" in data:
            update["pages"] = data["pages"]
        col.update_one({"date": date_str}, {"$set": update})
    else:
        col.insert_one({
            "date": date_str,
            "name": data.get("name", f"Edition {date_str}"),
            "language": data.get("language", "Hindi"),
            "pages": data.get("pages", []),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Invalidate cache after save
    _invalidate_cache()

    return jsonify({"success": True}), 201


# ── API: Delete edition ───────────────────────────
@epaper_bp.route("/api/epaper/admin/edition/<date>", methods=["DELETE"])
@admin_required
def api_delete_edition(date):
    col = _get_editions_col()
    col.delete_one({"date": date})
    _invalidate_cache()  # Clear cache after delete
    return jsonify({"success": True})


# ── API: Upload article image → Cloudinary ─────────
@epaper_bp.route("/api/epaper/admin/upload-image", methods=["POST"])
@admin_required
def api_upload_image():
    photo = request.files.get("image")
    if not photo or photo.filename == "":
        return jsonify({"error": "No image file provided."}), 400

    allowed = {"png", "jpg", "jpeg", "webp", "gif"}
    ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
    if ext not in allowed:
        return jsonify({"error": "Invalid file type."}), 400

    try:
        from app.utils.cloudinary_util import upload_epaper_image
        result = upload_epaper_image(photo)
        if result and result.get("url"):
            return jsonify({"url": result["url"], "public_id": result["public_id"]})
        return jsonify({"error": "Upload failed."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── AI: Translate ──────────────────────────────────
@epaper_bp.route("/api/epaper/translate", methods=["POST"])
def api_translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    target = data.get("target_lang", "en")

    if not text:
        return jsonify({"error": "No text provided."}), 400

    try:
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


# ── AI: LLM Script Optimization ────────────────────
@epaper_bp.route("/api/epaper/tts-script", methods=["POST"])
def api_tts_script():
    """Use Groq LLM to process raw text into an optimized script for TTS."""
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
   Hindi: JEE→जे ई ई | NEET→नीट | IIT→आई आई टी | UP→उत्तर प्रदेश | CM→मुख्यमंत्री | PM→प्रधानमंत्री | BJP→बी जे पी | MH→महाराष्ट्र
   Marathi: JEE→जे ई ई | CM→मुख्यमंत्री | PM→पंतप्रधान | MH→महाराष्ट्र
   English: JEE→J-E-E | IIT→I-I-T | CM→Chief Minister | PM→Prime Minister

5. ANCHOR TONE BY LANGUAGE:
   Hindi (Aaj Tak style): आदरपूर्ण, स्पष्ट उच्चारण, थोड़ी urgency। वाक्य छोटे और प्रभावशाली। 'है' and 'हैं' pronounced clearly.
   Marathi (Zee 24 Taas style): स्पष्ट मराठी उच्चारण, Mumbaiya नाही। 'आहे' not 'आये', 'होते' clearly. Standard Pune-style Marathi diction.
   English (NDTV style): Crisp neutral Indian English. Measured pace. Proper stress on key words.

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
            messages=[
               {"role": "user", "content": f"Raw News Article:\n\n{text[:4000]}"}
            ],
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=2000,
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
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
    import tempfile
    from flask import send_file

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    voice = data.get("voice", "")  # optional override
    rate = data.get("rate", "+0%")  # e.g. "+10%", "-5%"
    pitch = data.get("pitch", "+0Hz") # e.g. "+5Hz", "-5Hz"

    if not text:
        return jsonify({"error": "No text provided."}), 400

    # Limit text length to prevent abuse (max ~5000 chars)
    text = text[:5000]

# ── Language detection ───────────────────────────────────────────────────
    devanagari_chars = len(re.findall(r'[\u0900-\u097F]', text))
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
                if rate == "+0%": rate = "-5%"
                if pitch == "+0Hz": pitch = "-2Hz"
            else:
                voice = "hi-IN-MadhurNeural"
                if rate == "+0%": rate = "-5%"
                if pitch == "+0Hz": pitch = "-3Hz"
        else:
            voice = "en-IN-PrabhatNeural"
            if rate == "+0%": rate = "-5%"
            if pitch == "+0Hz": pitch = "-2Hz"
    else:
        _voice_defaults = {
            "hi-IN-MadhurNeural":  ("-5%", "-3Hz"),
            "hi-IN-SwaraNeural":   ("-3%", "+0Hz"),
            "mr-IN-ManoharNeural": ("-5%", "-2Hz"),
            "mr-IN-AarohiNeural":  ("-3%", "+0Hz"),
            "en-IN-PrabhatNeural": ("-5%", "-2Hz"),
            "en-IN-NeerjaNeural":  ("-3%", "+0Hz"),
        }
        if voice in _voice_defaults and rate == "+0%" and pitch == "+0Hz":
            rate, pitch = _voice_defaults[voice]

    # Convert rate from number to Edge TTS format
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
        # Run async edge-tts in sync context
        loop = asyncio.new_event_loop()
        audio_bytes = loop.run_until_complete(_generate_audio())
        loop.close()

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


# ── API: Available TTS voices ──────────────────────
@epaper_bp.route("/api/epaper/tts/voices")
def api_tts_voices():
    """Return available Indian voice options for the frontend voice selector."""
    return jsonify({"voices": [
        {"id": "hi-IN-MadhurNeural",  "name": "माधुर (Hindi Male)",     "lang": "hi", "gender": "male",   "style": "News Anchor"},
        {"id": "hi-IN-SwaraNeural",   "name": "स्वरा (Hindi Female)",   "lang": "hi", "gender": "female", "style": "News Anchor"},
        {"id": "mr-IN-ManoharNeural", "name": "मनोहर (Marathi Male)",   "lang": "mr", "gender": "male",   "style": "News Anchor"},
        {"id": "mr-IN-AarohiNeural",  "name": "आरोही (Marathi Female)", "lang": "mr", "gender": "female", "style": "Professional"},
        {"id": "en-IN-PrabhatNeural", "name": "Prabhat (English Male)",  "lang": "en", "gender": "male",   "style": "News Anchor"},
        {"id": "en-IN-NeerjaNeural",  "name": "Neerja (English Female)", "lang": "en", "gender": "female", "style": "Professional"},
    ]})