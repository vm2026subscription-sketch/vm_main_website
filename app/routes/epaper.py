"""
E-Paper routes — edition/page/article APIs + AI features
All data stored in MongoDB. Article images on Cloudinary.
"""
import json
import os
import re
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

epaper_bp = Blueprint("epaper", __name__)


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
    col = _get_editions_col()
    editions = list(col.find({}, {"_id": 0}).sort("date", -1))
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

    col = _get_editions_col()
    edition = col.find_one({"date": date}, {"_id": 0})

    if not edition:
        return jsonify({"error": "No edition for this date."}), 404

    return jsonify({
        "date": edition["date"],
        "name": edition.get("name", ""),
        "language": edition.get("language", "Hindi"),
        "pages": edition.get("pages", []),
    })


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

    return jsonify({"success": True}), 201


# ── API: Delete edition ───────────────────────────
@epaper_bp.route("/api/epaper/admin/edition/<date>", methods=["DELETE"])
@admin_required
def api_delete_edition(date):
    col = _get_editions_col()
    col.delete_one({"date": date})
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
        
        system_prompt = """You are an expert news script editor for Indian TV news. Your task is to take a raw news article and output an optimized script for a Text-to-Speech (TTS) engine.
Follow these rules strictly:
- Sound like a professional Indian TV news anchor.
- Support Hindi, Marathi, and English based on the input text.
- Preserve factual meaning exactly.
- Improve flow for speech listening. Break long sentences naturally.
- Add emotional pacing where appropriate (e.g. serious news = calm, breaking news = urgent).
- Add punctuation and pauses (like commas, periods, or ellipses) for narration.
- Convert symbols, abbreviations, dates, and numbers into spoken language (e.g., "$10" to "ten dollars", "UP" to "Uttar Pradesh").
- Keep tone formal, trustworthy, and engaging. Avoid robotic phrasing.
- Hindi pronunciation should feel native Indian. Marathi should feel authentic Marathi. English should use Indian news-anchor style.
- Add short pauses after important statements.

Return ONLY a valid JSON object matching this schema exactly:
{
  "language": "en/hi/mr",
  "title_script": "Optimized headline script here...",
  "body_script": "Optimized body script here...",
  "voice_style": {
    "speed": "A number representing speed multiplier (e.g., 1.0, 1.1, 0.95)",
    "pitch": "A string like '+0Hz', '+5Hz', '-5Hz'",
    "emotion": "A short description of the emotion",
    "pause_style": "Description of pauses"
  }
}"""
        
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Raw News Text:\n{text[:3000]}"}
            ],
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            response_format={"type": "json_object"},
            temperature=0.3,
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

    # Auto-detect language and pick the best Indian news anchor voice
    hindi_chars = len(re.findall(r'[\u0900-\u097F]', text))
    is_hindi = hindi_chars / max(len(text), 1) > 0.3

    if not voice:
        if is_hindi:
            # Male Hindi news anchor — deep, authoritative, natural
            voice = "hi-IN-MadhurNeural"
        else:
            # Male Indian English news anchor — crisp, professional
            voice = "en-IN-PrabhatNeural"

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
        {"id": "hi-IN-MadhurNeural", "name": "माधुर (Hindi Male)", "lang": "hi", "gender": "male", "style": "News Anchor"},
        {"id": "hi-IN-SwaraNeural", "name": "स्वरा (Hindi Female)", "lang": "hi", "gender": "female", "style": "News Anchor"},
        {"id": "en-IN-PrabhatNeural", "name": "Prabhat (English Male)", "lang": "en", "gender": "male", "style": "Professional"},
        {"id": "en-IN-NeerjaNeural", "name": "Neerja (English Female)", "lang": "en", "gender": "female", "style": "Professional"},
    ]})
