import io
import base64
import hashlib
import hmac
import os
import re
import json
import html
import sqlite3
import secrets
import smtplib
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse, urlencode
from urllib.request import Request, urlopen
from email.message import EmailMessage

try:
    import pandas as pd
except ImportError:
    pd = None

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
try:
    from flask_compress import Compress as _FlaskCompress
    _has_compress = True
except ImportError:
    _has_compress = False
try:
    from psycopg2 import connect
    from psycopg2.extras import Json, execute_values
except ImportError:
    connect = None
    Json = None
    execute_values = None
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from supabase import create_client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vidyarthi-mitra-dev-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB upload limit
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Enable SECURE cookies only when not running locally
if os.environ.get("FLASK_ENV") == "production" or os.environ.get("RENDER"):
    app.config["SESSION_COOKIE_SECURE"] = True
if _has_compress:
    _FlaskCompress(app)

@app.errorhandler(413)
def request_too_large(e):
    return jsonify({
        'success': False,
        'error': 'File too large. Maximum upload size is 200 MB. Please compress your PDF and try again.'
    }), 413

AUTH_DB_PATH = os.path.join(app.root_path, "auth_users.db")

COURSES_DB_URL = (
    os.getenv("SUPABASE_POSTGRES_URL", "").strip()
    or os.getenv("DATABASE_URL", "").strip()
)
if COURSES_DB_URL:
    try:
        from courses_routes import courses_bp

        app.register_blueprint(courses_bp)
    except Exception as exc:
        app.logger.warning("Skipping courses blueprint registration: %s", exc)

# Register news blueprint
try:
    from news_routes import news_bp

    app.register_blueprint(news_bp)
except Exception as exc:
    app.logger.warning("Skipping news blueprint registration: %s", exc)

# Register e-paper viewer blueprint
try:
    from epaper_routes import epaper_bp

    app.register_blueprint(epaper_bp)
except Exception as exc:
    app.logger.warning("Skipping epaper blueprint registration: %s", exc)

VMADMIN_BASE_URL = (
    os.getenv("VMADMIN_BASE_URL", "https://vmadmin-production.up.railway.app").strip().rstrip("/")
)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def fetch_remote_json(url, timeout=12):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "vm-main-website/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            if not body:
                return []
            return json.loads(body.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError):
        return None


def extract_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("results", "items", "news", "editions", "articles"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    data_value = payload.get("data")
    if isinstance(data_value, list):
        return data_value

    if isinstance(data_value, dict):
        for key in ("results", "items", "news", "editions", "articles"):
            value = data_value.get(key)
            if isinstance(value, list):
                return value

    return []


def extract_next_url(payload, current_url):
    if not isinstance(payload, dict):
        return None

    candidate = payload.get("next")
    if not candidate and isinstance(payload.get("pagination"), dict):
        candidate = payload["pagination"].get("next")
    if not candidate and isinstance(payload.get("data"), dict):
        candidate = payload["data"].get("next")

    if not isinstance(candidate, str) or not candidate.strip():
        return None

    return urljoin(current_url, candidate.strip())

UPLOAD_TARGET_TABLES = [
    {"value": "universities", "label": "Universities"},
    {"value": "colleges", "label": "Colleges"},
    {"value": "courses", "label": "Courses"},
    {"value": "entrance_exams", "label": "Entrance Exams"},
]

BTECH_CUTOFF_DIR = os.path.join(app.root_path, "data", "btech")
_btech_cutoff_cache = None
_btech_cutoff_error = None
_college_website_cache = None
FULL_CUTOFF_PRICE_RUPEES = 100
FULL_CUTOFF_PRICE_PAISE = FULL_CUTOFF_PRICE_RUPEES * 100

CHATBOT_TEMPLATE_CACHE = None
CHATBOT_STOPWORDS = {
    "about", "what", "when", "where", "which", "please", "give", "tell",
    "show", "for", "with", "from", "this", "that", "have", "has", "are",
    "the", "and", "you", "your", "into", "mein", "about", "kya", "hai",
    "ke", "ki", "ka", "ko", "kaise", "please", "mujhe", "info", "details",
    "regarding", "need", "want", "exam", "exams",
}

CHATBOT_GREETINGS = {
    "hi", "hello", "hey", "hii", "hiii", "namaste", "namaskar", "salam", "good morning", "good evening"
}

CHATBOT_SMALLTALK = {
    "how are you", "how r u", "how r you", "kaise ho", "kaisi ho", "kaisa hai", "kaisi hai",
    "kya haal hai", "kya hal hai", "kasa ahes", "kashi ahes", "kay mhantos", "kay mhantays"
}

CHATBOT_THANKS = {
    "thanks", "thank you", "thx", "dhanyavad", "shukriya", "thanku"
}

CHATBOT_TOPIC_KEYWORDS = {
    "admissions": {"admission", "admissions", "eligibility", "deadline", "application", "documents", "fees", "seat"},
    "entrance_exams": {"entrance", "exam", "jee", "neet", "mht", "cet", "clat", "gate", "syllabus", "cutoff"},
    "colleges": {"college", "colleges", "campus", "placement", "hostel", "branch"},
    "courses": {"course", "courses", "btech", "mba", "bca", "bba", "syllabus", "duration"},
    "careers": {"career", "careers", "job", "scope", "salary", "future", "skills"},
}

CHATBOT_TOPIC_SOURCE_HINTS = {
    "admissions": {"/admissions", "/entrance-exams", "/cutoffs", "/courses", "/colleges"},
    "entrance_exams": {"/entrance-exams", "/cutoffs", "/exam-updates", "/mock-exams"},
    "colleges": {"/colleges", "/cutoffs", "/universities"},
    "courses": {"/courses", "/entrance-exams", "/colleges"},
    "careers": {"/blogs", "/articles", "/guideme", "/guide-me"},
}

CHATBOT_DDG_API_URL = "https://api.duckduckgo.com/"
CHATBOT_WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
CHATBOT_WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"

CUTOFF_GENDER_LABELS = {
    "G": "General",
    "L": "Ladies",
    "M": "Male",
    "F": "Female",
    "T": "TFWS",
    "E": "EWS",
    "D": "Defense",
    "O": "Orphan",
    "P": "PWD",
}


def normalize_cutoff_columns(dataframe):
    dataframe = dataframe.copy()
    dataframe.columns = (
        dataframe.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("(", "", regex=False)
        .str.replace(")", "", regex=False)
    )
    return dataframe


def load_btech_cutoff_data():
    global _btech_cutoff_cache, _btech_cutoff_error

    if _btech_cutoff_cache is not None or _btech_cutoff_error is not None:
        return _btech_cutoff_cache, _btech_cutoff_error

    if pd is None:
        _btech_cutoff_error = "pandas is not installed. Install requirements to read cutoff data."
        return None, _btech_cutoff_error

    if not os.path.isdir(BTECH_CUTOFF_DIR):
        _btech_cutoff_error = "B.Tech cutoff data folder is missing."
        return None, _btech_cutoff_error

    frames = []
    for cap_round in (1, 2, 3, 4):
        file_path = os.path.join(BTECH_CUTOFF_DIR, f"BTECH_OUTPUT_CAP{cap_round}.csv")
        if not os.path.exists(file_path):
            continue
        try:
            frame = pd.read_csv(file_path)
        except Exception as exc:
            _btech_cutoff_error = f"Unable to read {os.path.basename(file_path)}: {exc}"
            return None, _btech_cutoff_error

        frame = normalize_cutoff_columns(frame)
        frame["cap_round_source"] = cap_round
        frames.append(frame)

    if not frames:
        _btech_cutoff_error = "No B.Tech cutoff CSV files were found."
        return None, _btech_cutoff_error

    data = pd.concat(frames, ignore_index=True)
    data["percentile"] = pd.to_numeric(data.get("percentile"), errors="coerce")
    data["rank"] = pd.to_numeric(data.get("rank"), errors="coerce")

    required = ["institute_name", "course_name", "category1", "gender", "percentile"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        _btech_cutoff_error = f"Cutoff data is missing required columns: {', '.join(missing)}"
        return None, _btech_cutoff_error

    group_columns = [
        "institute_code",
        "institute_name",
        "course_name",
        "category1",
        "gender",
        "status",
        "university",
    ]
    group_columns = [column for column in group_columns if column in data.columns]
    final_cutoffs = (
        data.dropna(subset=["percentile"])
        .groupby(group_columns, as_index=False)
        .agg(
            final_cutoff=("percentile", "max"),
            best_round_cutoff=("percentile", "min"),
            average_cutoff=("percentile", "mean"),
            volatility=("percentile", "std"),
            best_rank=("rank", "min"),
            cap_rounds=("cap_round_source", lambda values: ", ".join(str(int(value)) for value in sorted(set(values)))),
        )
    )
    round_cutoffs = (
        data.dropna(subset=["percentile"])
        .groupby(group_columns + ["cap_round_source"], as_index=False)["percentile"]
        .max()
        .pivot(index=group_columns, columns="cap_round_source", values="percentile")
        .reset_index()
    )
    round_cutoffs.columns = [
        f"cap_{int(column)}_cutoff" if isinstance(column, (int, float)) else column
        for column in round_cutoffs.columns
    ]
    final_cutoffs = final_cutoffs.merge(round_cutoffs, on=group_columns, how="left")
    final_cutoffs["volatility"] = final_cutoffs["volatility"].fillna(0)
    final_cutoffs["college_key"] = final_cutoffs["institute_name"].astype(str).str.lower()
    final_cutoffs = final_cutoffs.sort_values(["final_cutoff", "institute_name"], ascending=[False, True])

    _btech_cutoff_cache = final_cutoffs
    return _btech_cutoff_cache, None


def get_cutoff_options():
    data, error = load_btech_cutoff_data()
    if error or data is None:
        gender_options = [{"value": value, "label": CUTOFF_GENDER_LABELS.get(value, value)} for value in ["G", "L"]]
        return [], ["OPEN", "OBC", "SC", "ST", "EWS", "SEBC"], gender_options, error

    branches = sorted(data["course_name"].dropna().astype(str).unique().tolist())
    categories = sorted(data["category1"].dropna().astype(str).unique().tolist())
    genders = sorted(data["gender"].dropna().astype(str).unique().tolist())
    gender_options = [
        {"value": gender, "label": CUTOFF_GENDER_LABELS.get(gender, gender)}
        for gender in genders
    ]
    return branches, categories, gender_options, None


def risk_label_for_gap(gap):
    if gap >= 1:
        return "Safe"
    if gap >= -1:
        return "Borderline"
    if gap >= -3:
        return "Risky"
    return "Reach"


def cutoff_gender_label(value):
    cleaned = clean_college_text(value).upper()
    return CUTOFF_GENDER_LABELS.get(cleaned, cleaned)


def normalize_college_match_key(value):
    text = clean_college_text(value).lower()
    text = re.sub(r"\b(college|institute|engineering|technology|of|and|the)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_college_website_lookup():
    global _college_website_cache

    if _college_website_cache is not None:
        return _college_website_cache

    _college_website_cache = {}

    if psycopg2 is None:
        return _college_website_cache

    db_url = get_postgres_connection_url()
    if not db_url:
        return _college_website_cache

    try:
        conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception:
        return _college_website_cache

    try:
        col_map = resolve_colleges_columns(conn)
        if not col_map.get("name") or not col_map.get("source_url"):
            return _college_website_cache

        sql = (
            f"SELECT \"{col_map['name']}\" AS name, \"{col_map['source_url']}\" AS source_url "
            f"FROM colleges WHERE \"{col_map['source_url']}\" IS NOT NULL "
            f"AND \"{col_map['source_url']}\" <> ''"
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            for row in cur.fetchall():
                key = normalize_college_match_key(row.get("name"))
                url = normalize_external_url(row.get("source_url"))
                if key and url:
                    _college_website_cache.setdefault(key, url)
    except Exception:
        return _college_website_cache
    finally:
        conn.close()

    return _college_website_cache


def find_college_website(college_name, website_lookup):
    key = normalize_college_match_key(college_name)
    if not key:
        return ""
    if key in website_lookup:
        return website_lookup[key]

    key_parts = set(key.split())
    if len(key_parts) < 3:
        return ""

    best_url = ""
    best_score = 0
    for candidate_key, url in website_lookup.items():
        candidate_parts = set(candidate_key.split())
        if not candidate_parts:
            continue
        score = len(key_parts & candidate_parts) / max(len(key_parts), len(candidate_parts))
        if score > best_score:
            best_score = score
            best_url = url

    return best_url if best_score >= 0.68 else ""


def format_cutoff_recommendations(rows, student_percentile=None, include_websites=True):
    website_lookup = get_college_website_lookup() if include_websites else {}
    recommendations = []
    for _, row in rows.iterrows():
        final_cutoff = float(row.get("final_cutoff") or 0)
        gap = None if student_percentile is None else float(student_percentile) - final_cutoff
        college_name = clean_college_text(row.get("institute_name"))
        recommendations.append(
            {
                "college": college_name,
                "college_code": clean_college_text(row.get("institute_code")),
                "branch": clean_college_text(row.get("course_name")),
                "category": clean_college_text(row.get("category1")),
                "gender": clean_college_text(row.get("gender")),
                "gender_label": cutoff_gender_label(row.get("gender")),
                "status": clean_college_text(row.get("status")),
                "university": clean_college_text(row.get("university")),
                "website": find_college_website(college_name, website_lookup),
                "final_cutoff": round(final_cutoff, 4),
                "cap_1_cutoff": round(float(row.get("cap_1_cutoff")), 4) if not pd.isna(row.get("cap_1_cutoff")) else None,
                "cap_2_cutoff": round(float(row.get("cap_2_cutoff")), 4) if not pd.isna(row.get("cap_2_cutoff")) else None,
                "cap_3_cutoff": round(float(row.get("cap_3_cutoff")), 4) if not pd.isna(row.get("cap_3_cutoff")) else None,
                "cap_4_cutoff": round(float(row.get("cap_4_cutoff")), 4) if not pd.isna(row.get("cap_4_cutoff")) else None,
                "best_round_cutoff": round(float(row.get("best_round_cutoff") or 0), 4),
                "average_cutoff": round(float(row.get("average_cutoff") or 0), 4),
                "best_rank": int(row.get("best_rank")) if not pd.isna(row.get("best_rank")) else None,
                "cap_rounds": clean_college_text(row.get("cap_rounds")),
                "gap": round(gap, 4) if gap is not None else None,
                "risk_label": risk_label_for_gap(gap) if gap is not None else "Top Cutoff",
            }
        )
    return recommendations


def get_top_cutoff_colleges(limit=20, branch=None, category=None, gender=None):
    data, error = load_btech_cutoff_data()
    if error or data is None:
        return [], error

    filtered = data.copy()
    if branch:
        filtered = filtered[filtered["course_name"].astype(str) == branch]
    if category:
        filtered = filtered[filtered["category1"].astype(str).str.upper() == category.upper()]
    if gender:
        filtered = filtered[filtered["gender"].astype(str).str.upper() == gender.upper()]

    if filtered.empty:
        return [], "No cutoff rows matched those filters."

    top_rows = (
        filtered.sort_values(["final_cutoff", "institute_name"], ascending=[False, True])
        .drop_duplicates(subset=["college_key"])
        .head(limit)
    )
    return format_cutoff_recommendations(top_rows), None


def get_full_cutoff_colleges(branch=None, category=None, gender=None, page=1, per_page=100):
    data, error = load_btech_cutoff_data()
    if error or data is None:
        return [], 0, error

    filtered = data.copy()
    if branch:
        filtered = filtered[filtered["course_name"].astype(str) == branch]
    if category:
        filtered = filtered[filtered["category1"].astype(str).str.upper() == category.upper()]
    if gender:
        filtered = filtered[filtered["gender"].astype(str).str.upper() == gender.upper()]

    if filtered.empty:
        return [], 0, "No cutoff rows matched those filters."

    ranked = filtered.sort_values(["final_cutoff", "institute_name"], ascending=[False, True])
    total = len(ranked)
    page = max(1, int(page or 1))
    per_page = int(per_page or 100)
    start = (page - 1) * per_page
    end = start + per_page

    return format_cutoff_recommendations(ranked.iloc[start:end]), total, None


def predict_colleges_from_cutoffs(percentile, category, gender, branch, page=1, per_page=20):
    data, error = load_btech_cutoff_data()
    if error or data is None:
        return [], 0, error

    filtered = data.copy()
    if branch:
        filtered = filtered[filtered["course_name"].astype(str) == branch]
    if category:
        filtered = filtered[filtered["category1"].astype(str).str.upper() == category.upper()]
    if gender:
        filtered = filtered[filtered["gender"].astype(str).str.upper() == gender.upper()]

    if filtered.empty:
        return [], 0, "No cutoff rows matched those filters."

    filtered = filtered.copy()
    filtered["gap"] = float(percentile) - filtered["final_cutoff"]
    filtered["sort_bucket"] = filtered["gap"].apply(lambda value: 0 if value >= 0 else 1)
    filtered["below_gap"] = filtered["gap"].apply(lambda value: value if value < 0 else 0)
    ranked = filtered.sort_values(
        ["sort_bucket", "final_cutoff", "below_gap"],
        ascending=[True, False, False],
    ).drop_duplicates(subset=["college_key"])

    total = len(ranked)
    page = max(1, int(page or 1))
    per_page = int(per_page or 20)
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = ranked.iloc[start:end]

    return format_cutoff_recommendations(page_rows, student_percentile=percentile), total, None


def get_supabase_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not url or not key:
        return None

    return create_client(url, key)


def get_razorpay_config():
    load_dotenv(override=True)
    key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    if not key_id or not key_secret:
        return None
    return {"key_id": key_id, "key_secret": key_secret}


def create_razorpay_order(amount_paise, receipt, notes=None):
    config = get_razorpay_config()
    if config is None:
        raise RuntimeError("Payment service is temporarily unavailable. Please try again later or contact support.")

    payload = json.dumps(
        {
            "amount": int(amount_paise),
            "currency": "INR",
            "receipt": receipt,
            "notes": notes or {},
        }
    ).encode("utf-8")
    credentials = base64.b64encode(
        f"{config['key_id']}:{config['key_secret']}".encode("utf-8")
    ).decode("ascii")
    req = Request(
        "https://api.razorpay.com/v1/orders",
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_razorpay_payment_signature(order_id, payment_id, signature):
    config = get_razorpay_config()
    if config is None:
        return False

    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(
        config["key_secret"].encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, str(signature or ""))


def get_postgres_connection_url():
    return os.getenv("SUPABASE_POSTGRES_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()


def resolve_colleges_columns(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'colleges'
            """
        )
        available = {row["column_name"] for row in cur.fetchall()}

    def pick_column(candidates):
        for candidate in candidates:
            if candidate in available:
                return candidate
        return None

    return {
        "name": pick_column(["name", "Name", "college_name", "college", "title"]),
        "state": pick_column(["state", "State", "state_name", "province"]),
        "city": pick_column(["district", "District", "city", "city_name", "location", "Location"]),
        "type": pick_column(["college type", "College Type", "college_type", "institution_type", "type"]),
        "management": pick_column(["manegement", "Manegement", "management", "Management", "ownership"]),
        "nirf": pick_column(["nirf", "nirf_rank", "rank", "nirf_ranking"]),
        "year": pick_column(["year of establishment", "Year Of Establishment", "established", "established_year"]),
        "university_name": pick_column(["university name", "University Name", "university_name", "university"]),
        "logo_url": pick_column(["logo_url", "logo", "logo_link", "logo_path"]),
        "source_url": pick_column(["website", "Website", "website_url", "source_url", "url"]),
    }


## --- Simple coupon storage and helpers (file-backed) ---
COUPONS_FILE = os.path.join(app.root_path, "data", "coupons.json")

def _load_coupons_raw():
    try:
        if not os.path.exists(COUPONS_FILE):
            return []
        with open(COUPONS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh) or []
    except Exception:
        return []

def _save_coupons_raw(items):
    try:
        os.makedirs(os.path.dirname(COUPONS_FILE), exist_ok=True)
        with open(COUPONS_FILE, "w", encoding="utf-8") as fh:
            json.dump(items, fh, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def find_coupon(code):
    if not code:
        return None
    code = str(code or "").strip()
    if not code:
        return None
    items = _load_coupons_raw()
    for it in items:
        if str(it.get("code", "")).strip().upper() == code.upper():
            return it
    return None

def consume_coupon(code):
    """Consume one use of a single-use coupon. Returns True if consumed."""
    if not code:
        return False
    items = _load_coupons_raw()
    changed = False
    for it in items:
        if str(it.get("code", "")).strip().upper() == str(code).strip().upper():
            uses = it.get("uses_remaining")
            if uses is None:
                return True
            try:
                uses = int(uses)
            except Exception:
                return True
            if uses <= 0:
                return False
            it["uses_remaining"] = uses - 1
            changed = True
            break
    if changed:
        return _save_coupons_raw(items)
    return False

def build_college_select(col_map):
    select_parts = []
    for alias in (
        "name",
        "state",
        "city",
        "type",
        "management",
        "nirf",
        "year",
        "university_name",
        "logo_url",
        "source_url",
    ):
        column = col_map.get(alias)
        if column:
            select_parts.append(f'"{column}" AS {alias}')
        else:
            select_parts.append(f"NULL AS {alias}")
    return ", ".join(select_parts)


def normalize_external_url(value):
    url = str(value or "").strip()
    if not url:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*://", url, flags=re.IGNORECASE):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    return f"https://{url.lstrip('/')}"


def clean_college_text(value):
    text = str(value or "").strip()
    if not text:
        return ""

    # Some imported Excel/database values contain control characters where
    # apostrophes were expected, which browsers render as square boxes.
    text = re.sub(r"(?<=\w)[\x00-\x1f\x7f]+(?=s\b)", "'", text)
    text = re.sub(r"(?<=\w)[\uFFFD\u25A0\u25A1\u25AA\u25AB]+(?=s\b)", "'", text)
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"[\uFFFD\u25A0\u25A1\u25AA\u25AB]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_colleges_search(page, per_page, q=None, alpha=None, state=None):
    if psycopg2 is None:
        return [], 0, "psycopg2-binary is not installed."

    db_url = get_postgres_connection_url()
    if not db_url:
        return [], 0, "SUPABASE_POSTGRES_URL or DATABASE_URL is not configured."

    offset = (page - 1) * per_page if per_page else 0

    try:
        conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as exc:
        return [], 0, f"Database connection failed: {exc}"

    try:
        col_map = resolve_colleges_columns(conn)
        if not col_map.get("name"):
            return [], 0, "Could not find a college name column in the colleges table."

        select_sql = build_college_select(col_map)

        filters = []
        params = []
        if state and col_map.get("state"):
            filters.append(f'"{col_map["state"]}" = %s')
            params.append(state)

        if alpha:
            filters.append(f'"{col_map["name"]}" ILIKE %s')
            params.append(f"{alpha}%")

        if q:
            like = f"%{q}%"
            parts = [f'"{col_map["name"]}" ILIKE %s']
            params.append(like)
            for key in ("state", "city", "type", "management"):
                if col_map.get(key):
                    parts.append(f'"{col_map[key]}" ILIKE %s')
                    params.append(like)
            if col_map.get("university_name"):
                parts.append(f'"{col_map["university_name"]}" ILIKE %s')
                params.append(like)
            filters.append("(" + " OR ".join(parts) + ")")

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        count_sql = f"SELECT COUNT(*) FROM colleges {where_clause}"
        data_sql = f"SELECT {select_sql} FROM colleges {where_clause} ORDER BY name"
        data_params = list(params)
        if per_page:
            data_sql += " LIMIT %s OFFSET %s"
            data_params.extend([per_page, offset])

        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()["count"]

            cur.execute(data_sql, data_params)
            rows = cur.fetchall()
    except Exception as exc:
        return [], 0, f"Database query failed: {exc}"
    finally:
        conn.close()

    colleges = [
        {
            "name": clean_college_text(row.get("name")),
            "state": clean_college_text(row.get("state")),
            "city": clean_college_text(row.get("city")),
            "type": clean_college_text(row.get("type")),
            "management": clean_college_text(row.get("management")),
            "nirf": clean_college_text(row.get("nirf")),
            "year": clean_college_text(row.get("year")),
            "university_name": clean_college_text(row.get("university_name")),
            "logo_url": row.get("logo_url") or "",
            "source_url": normalize_external_url(row.get("source_url")),
        }
        for row in rows
    ]

    return colleges, total, None


def fetch_college_state_counts():
    if psycopg2 is None:
        return [], 0, "psycopg2-binary is not installed."

    db_url = get_postgres_connection_url()
    if not db_url:
        return [], 0, "SUPABASE_POSTGRES_URL or DATABASE_URL is not configured."

    try:
        conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as exc:
        return [], 0, f"Database connection failed: {exc}"

    try:
        col_map = resolve_colleges_columns(conn)
        if not col_map.get("state"):
            return [], 0, "Could not find a state column in the colleges table."

        sql = (
            f"SELECT \"{col_map['state']}\" AS state, COUNT(*) AS count "
            f"FROM colleges WHERE \"{col_map['state']}\" IS NOT NULL "
            f"AND \"{col_map['state']}\" <> '' "
            f"GROUP BY \"{col_map['state']}\" ORDER BY \"{col_map['state']}\""
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    except Exception as exc:
        return [], 0, f"Database query failed: {exc}"
    finally:
        conn.close()

    total = sum(row.get("count", 0) or 0 for row in rows)
    return rows, total, None


def fetch_colleges_by_states(states, limit_per_state=None):
    if psycopg2 is None:
        return [], "psycopg2-binary is not installed."

    db_url = get_postgres_connection_url()
    if not db_url:
        return [], "SUPABASE_POSTGRES_URL or DATABASE_URL is not configured."

    if not states:
        return [], None

    try:
        conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as exc:
        return [], f"Database connection failed: {exc}"

    try:
        col_map = resolve_colleges_columns(conn)
        if not col_map.get("state") or not col_map.get("name"):
            return [], "Could not resolve required columns for colleges."

        select_sql = build_college_select(col_map)
        if limit_per_state:
            sql = (
                "SELECT * FROM ("
                f"SELECT {select_sql}, "
                f"ROW_NUMBER() OVER (PARTITION BY \"{col_map['state']}\" "
                f"ORDER BY \"{col_map['name']}\") AS row_num "
                f"FROM colleges WHERE \"{col_map['state']}\" = ANY(%s)"
                ") ranked WHERE row_num <= %s "
                "ORDER BY state, name"
            )
            query_params = (states, limit_per_state)
        else:
            sql = (
                f"SELECT {select_sql} FROM colleges "
                f"WHERE \"{col_map['state']}\" = ANY(%s) "
                f"ORDER BY name"
            )
            query_params = (states,)
        with conn.cursor() as cur:
            cur.execute(sql, query_params)
            rows = cur.fetchall()
    except Exception as exc:
        return [], f"Database query failed: {exc}"
    finally:
        conn.close()

    colleges = [
        {
            "name": clean_college_text(row.get("name")),
            "state": clean_college_text(row.get("state")),
            "city": clean_college_text(row.get("city")),
            "type": clean_college_text(row.get("type")),
            "management": clean_college_text(row.get("management")),
            "nirf": clean_college_text(row.get("nirf")),
            "year": clean_college_text(row.get("year")),
            "university_name": clean_college_text(row.get("university_name")),
            "logo_url": row.get("logo_url") or "",
            "source_url": normalize_external_url(row.get("source_url")),
        }
        for row in rows
    ]

    return colleges, None


def get_auth_db_connection():
    connection = sqlite3.connect(AUTH_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    return connection


def get_logged_in_user():
    user = session.get("auth_user")
    if isinstance(user, dict) and user.get("email"):
        return user
    return None


def generate_login_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def store_pending_login_otp(user):
    otp_code = generate_login_otp()
    session["pending_otp"] = {
        "name": user["name"],
        "email": user["email"],
        "provider": "local_email",
        "otp_hash": generate_password_hash(otp_code),
        "expires_at": int(time.time()) + 300,
        "attempts": 0,
    }
    return otp_code


def get_pending_login_otp():
    pending_otp = session.get("pending_otp")
    if not isinstance(pending_otp, dict):
        return None

    expires_at = pending_otp.get("expires_at")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        session.pop("pending_otp", None)
        return None

    return pending_otp


def get_env_value(*names, default=""):
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def get_otp_provider():
    return get_env_value("OTP_PROVIDER", default="email_smtp").lower()


def get_twilio_verify_config():
    account_sid = get_env_value("TWILIO_ACCOUNT_SID")
    auth_token = get_env_value("TWILIO_AUTH_TOKEN")
    service_sid = get_env_value("TWILIO_VERIFY_SERVICE_SID")

    if not account_sid or not auth_token or not service_sid:
        return None

    return {
        "account_sid": account_sid,
        "auth_token": auth_token,
        "service_sid": service_sid,
    }


def send_twilio_verify_code(to_email):
    config = get_twilio_verify_config()
    if config is None:
        return False

    endpoint = f"https://verify.twilio.com/v2/Services/{config['service_sid']}/Verifications"
    body = urlencode({"To": to_email, "Channel": "email"}).encode("utf-8")
    credentials = base64.b64encode(f"{config['account_sid']}:{config['auth_token']}".encode("utf-8")).decode("ascii")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    with urlopen(request, timeout=15) as response:
        response.read()

    return True


def verify_twilio_code(to_email, code):
    config = get_twilio_verify_config()
    if config is None:
        return False

    endpoint = f"https://verify.twilio.com/v2/Services/{config['service_sid']}/VerificationCheck"
    body = urlencode({"To": to_email, "Code": code}).encode("utf-8")
    credentials = base64.b64encode(f"{config['account_sid']}:{config['auth_token']}".encode("utf-8")).decode("ascii")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return str(payload.get("status", "")).lower() == "approved"


def send_login_otp_email(to_email, user_name, otp_code):
    smtp_host = get_env_value("OTP_SMTP_HOST", "SMTP_HOST")
    smtp_port_raw = get_env_value("OTP_SMTP_PORT", "SMTP_PORT", default="587")
    smtp_username = get_env_value("OTP_SMTP_USERNAME", "SMTP_USER")
    smtp_password = get_env_value("OTP_SMTP_PASSWORD", "SMTP_PASS")
    from_email = get_env_value("OTP_FROM_EMAIL", "SMTP_FROM_EMAIL", default=smtp_username)
    use_tls_raw = get_env_value("OTP_SMTP_USE_TLS", "SMTP_USE_TLS", default="1").lower()

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587

    use_tls = use_tls_raw not in {"0", "false", "no"}

    if not smtp_host or not from_email:
        return False

    message = EmailMessage()
    message["Subject"] = "Your Vidyarthi Mitra login OTP"
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(
        f"""Hello {user_name or 'Student'},

Your Vidyarthi Mitra login OTP is: {otp_code}

This code expires in 5 minutes.

If you did not request this, ignore this email.
"""
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if smtp_username:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)

    return True


def convert_excel_to_records(uploaded_file):
    if pd is None:
        raise RuntimeError("pandas is not installed. Install requirements to process Excel uploads.")

    excel_bytes = uploaded_file.read()
    if not excel_bytes:
        raise ValueError("The uploaded file is empty.")

    workbook = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=None)
    if not workbook:
        raise ValueError("No sheets found in the uploaded Excel file.")

    records = []
    for sheet_name, dataframe in workbook.items():
        cleaned_dataframe = dataframe.where(pd.notnull(dataframe), None)
        for row_index, row in cleaned_dataframe.iterrows():
            payload = {}
            for column_name, value in row.items():
                normalized_column = str(column_name).strip()
                if not normalized_column:
                    continue
                payload[normalized_column] = value

            if not payload:
                continue

            records.append(
                {
                    "file_name": uploaded_file.filename,
                    "sheet_name": str(sheet_name),
                    "row_number": int(row_index) + 2,
                    "payload": payload,
                }
            )

    if not records:
        raise ValueError("The uploaded Excel file has no data rows to store.")

    return records


def insert_records_in_batches(supabase_client, table_name, records, batch_size=500):
    inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        supabase_client.table(table_name).insert(batch).execute()
        inserted += len(batch)
    return inserted


def insert_records_via_postgres(connection_url, table_name, records):
    if connect is None or Json is None or execute_values is None:
        raise RuntimeError("psycopg2-binary is not installed. Install requirements to use Postgres upload.")

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("Invalid table name. Use letters, numbers, and underscore only.")

    rows = [
        (
            item["file_name"],
            item["sheet_name"],
            item["row_number"],
            Json(item["payload"]),
        )
        for item in records
    ]

    with connect(connection_url) as conn:
        with conn.cursor() as cursor:
            query = (
                f"INSERT INTO {table_name} (file_name, sheet_name, row_number, payload) "
                "VALUES %s"
            )
            execute_values(cursor, query, rows, page_size=500)

    return len(rows)


def ensure_upload_table_exists(connection_url, table_name):
    if connect is None:
        raise RuntimeError("psycopg2-binary is not installed. Install requirements to use Postgres upload.")

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("Invalid table name. Use letters, numbers, and underscore only.")

    with connect(connection_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id bigserial PRIMARY KEY,
                    file_name text NOT NULL,
                    sheet_name text NOT NULL,
                    row_number integer NOT NULL,
                    payload jsonb NOT NULL,
                    uploaded_at timestamptz DEFAULT now()
                )
                """
            )


def _favicon(domain):
    return f"https://www.google.com/s2/favicons?sz=128&domain={domain}"


UNIVERSITIES_DATA = [
    # Maharashtra
    {"slug": "savitribai-phule-pune-university", "name": "Savitribai Phule Pune University", "location": "Pune", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "19", "source_url": "https://www.unipune.ac.in", "logo_url": _favicon("unipune.ac.in")},
    {"slug": "university-of-mumbai", "name": "University of Mumbai", "location": "Mumbai", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "45", "source_url": "https://mu.ac.in", "logo_url": _favicon("mu.ac.in")},
    {"slug": "rtm-nagpur-university", "name": "Rashtrasant Tukadoji Maharaj Nagpur University", "location": "Nagpur", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "74", "source_url": "https://nagpuruniversity.ac.in", "logo_url": _favicon("nagpuruniversity.ac.in")},
    {"slug": "symbiosis-international", "name": "Symbiosis International (Deemed University)", "location": "Pune", "state": "Maharashtra", "type": "Deemed", "stream": "Management", "nirf": "17", "source_url": "https://siu.edu.in", "logo_url": _favicon("siu.edu.in")},
    {"slug": "mit-wpu", "name": "MIT World Peace University", "location": "Pune", "state": "Maharashtra", "type": "Private", "stream": "Technology", "nirf": "96", "source_url": "https://mitwpu.edu.in", "logo_url": _favicon("mitwpu.edu.in")},
    {"slug": "nmims-mumbai", "name": "NMIMS University", "location": "Mumbai", "state": "Maharashtra", "type": "Private", "stream": "Management", "nirf": "49", "source_url": "https://www.nmims.edu", "logo_url": _favicon("nmims.edu")},
    {"slug": "dr-babasaheb-ambedkar-marathwada", "name": "Dr. Babasaheb Ambedkar Marathwada University", "location": "Aurangabad", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://bamu.ac.in", "logo_url": _favicon("bamu.ac.in")},
    {"slug": "shivaji-university-kolhapur", "name": "Shivaji University Kolhapur", "location": "Kolhapur", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://www.unishivaji.ac.in", "logo_url": _favicon("unishivaji.ac.in")},
    {"slug": "solapur-university", "name": "Solapur University", "location": "Solapur", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://su.digitaluniversity.ac", "logo_url": _favicon("su.digitaluniversity.ac")},
    {"slug": "sant-gadge-baba-amravati", "name": "Sant Gadge Baba Amravati University", "location": "Amravati", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://www.sgbau.ac.in", "logo_url": _favicon("sgbau.ac.in")},
    {"slug": "dr-bamu-open", "name": "YCMOU (Yashwantrao Chavan Maharashtra Open University)", "location": "Nashik", "state": "Maharashtra", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://ycmou.ac.in", "logo_url": _favicon("ycmou.ac.in")},
    {"slug": "bharati-vidyapeeth", "name": "Bharati Vidyapeeth (Deemed University)", "location": "Pune", "state": "Maharashtra", "type": "Deemed", "stream": "General", "nirf": "N/A", "source_url": "https://www.bharatividyapeeth.edu", "logo_url": _favicon("bharatividyapeeth.edu")},
    # Delhi / NCR
    {"slug": "delhi-university", "name": "University of Delhi", "location": "Delhi", "state": "Delhi", "type": "Government", "stream": "General", "nirf": "11", "source_url": "https://www.du.ac.in", "logo_url": _favicon("du.ac.in")},
    {"slug": "jnu-delhi", "name": "Jawaharlal Nehru University", "location": "Delhi", "state": "Delhi", "type": "Government", "stream": "General", "nirf": "2", "source_url": "https://www.jnu.ac.in", "logo_url": _favicon("jnu.ac.in")},
    {"slug": "jamia-millia-islamia", "name": "Jamia Millia Islamia", "location": "Delhi", "state": "Delhi", "type": "Government", "stream": "General", "nirf": "12", "source_url": "https://www.jmi.ac.in", "logo_url": _favicon("jmi.ac.in")},
    {"slug": "amity-university-noida", "name": "Amity University", "location": "Noida", "state": "Uttar Pradesh", "type": "Private", "stream": "Technology", "nirf": "54", "source_url": "https://www.amity.edu", "logo_url": _favicon("amity.edu")},
    # Karnataka
    {"slug": "bangalore-university", "name": "Bangalore University", "location": "Bangalore", "state": "Karnataka", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://bangaloreuniversity.ac.in", "logo_url": _favicon("bangaloreuniversity.ac.in")},
    {"slug": "manipal-academy", "name": "Manipal Academy of Higher Education", "location": "Manipal", "state": "Karnataka", "type": "Deemed", "stream": "Medical", "nirf": "8", "source_url": "https://manipal.edu", "logo_url": _favicon("manipal.edu")},
    {"slug": "christ-university", "name": "CHRIST (Deemed University)", "location": "Bangalore", "state": "Karnataka", "type": "Deemed", "stream": "General", "nirf": "N/A", "source_url": "https://christuniversity.in", "logo_url": _favicon("christuniversity.in")},
    # Tamil Nadu
    {"slug": "anna-university", "name": "Anna University", "location": "Chennai", "state": "Tamil Nadu", "type": "Government", "stream": "Technology", "nirf": "7", "source_url": "https://www.annauniv.edu", "logo_url": _favicon("annauniv.edu")},
    {"slug": "vit-vellore", "name": "Vellore Institute of Technology", "location": "Vellore", "state": "Tamil Nadu", "type": "Deemed", "stream": "Technology", "nirf": "10", "source_url": "https://vit.ac.in", "logo_url": _favicon("vit.ac.in")},
    {"slug": "madras-university", "name": "University of Madras", "location": "Chennai", "state": "Tamil Nadu", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://www.unom.ac.in", "logo_url": _favicon("unom.ac.in")},
    # Rajasthan
    {"slug": "bits-pilani", "name": "Birla Institute of Technology & Science (BITS) Pilani", "location": "Pilani", "state": "Rajasthan", "type": "Deemed", "stream": "Technology", "nirf": "26", "source_url": "https://www.bits-pilani.ac.in", "logo_url": _favicon("bits-pilani.ac.in")},
    {"slug": "university-of-rajasthan", "name": "University of Rajasthan", "location": "Jaipur", "state": "Rajasthan", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://www.uniraj.ac.in", "logo_url": _favicon("uniraj.ac.in")},
    # Madhya Pradesh
    {"slug": "davv-indore", "name": "Devi Ahilya Vishwavidyalaya (DAVV)", "location": "Indore", "state": "Madhya Pradesh", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://www.dauniv.ac.in", "logo_url": _favicon("dauniv.ac.in")},
    # West Bengal
    {"slug": "jadavpur-university", "name": "Jadavpur University", "location": "Kolkata", "state": "West Bengal", "type": "Government", "stream": "Technology", "nirf": "5", "source_url": "https://jadavpuruniversity.in", "logo_url": _favicon("jadavpuruniversity.in")},
    {"slug": "university-of-calcutta", "name": "University of Calcutta", "location": "Kolkata", "state": "West Bengal", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://www.caluniv.ac.in", "logo_url": _favicon("caluniv.ac.in")},
    # Gujarat
    {"slug": "gujarat-university", "name": "Gujarat University", "location": "Ahmedabad", "state": "Gujarat", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://www.gujaratuniversity.ac.in", "logo_url": _favicon("gujaratuniversity.ac.in")},
    {"slug": "nirma-university", "name": "Nirma University", "location": "Ahmedabad", "state": "Gujarat", "type": "Private", "stream": "Technology", "nirf": "N/A", "source_url": "https://nirmauni.ac.in", "logo_url": _favicon("nirmauni.ac.in")},
    # Andhra Pradesh / Telangana
    {"slug": "osmania-university", "name": "Osmania University", "location": "Hyderabad", "state": "Telangana", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://osmania.ac.in", "logo_url": _favicon("osmania.ac.in")},
    {"slug": "university-of-hyderabad", "name": "University of Hyderabad", "location": "Hyderabad", "state": "Telangana", "type": "Government", "stream": "General", "nirf": "6", "source_url": "https://www.uohyd.ac.in", "logo_url": _favicon("uohyd.ac.in")},
    # Punjab / Haryana
    {"slug": "panjab-university", "name": "Panjab University", "location": "Chandigarh", "state": "Punjab", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://puchd.ac.in", "logo_url": _favicon("puchd.ac.in")},
    {"slug": "kurukshetra-university", "name": "Kurukshetra University", "location": "Kurukshetra", "state": "Haryana", "type": "Government", "stream": "General", "nirf": "N/A", "source_url": "https://kuk.ac.in", "logo_url": _favicon("kuk.ac.in")},
    # Uttar Pradesh
    {"slug": "bhu-varanasi", "name": "Banaras Hindu University", "location": "Varanasi", "state": "Uttar Pradesh", "type": "Government", "stream": "General", "nirf": "3", "source_url": "https://www.bhu.ac.in", "logo_url": _favicon("bhu.ac.in")},
    {"slug": "aligarh-muslim-university", "name": "Aligarh Muslim University", "location": "Aligarh", "state": "Uttar Pradesh", "type": "Government", "stream": "General", "nirf": "9", "source_url": "https://www.amu.ac.in", "logo_url": _favicon("amu.ac.in")},
    # Premier Institutes
    {"slug": "iit-bombay", "name": "IIT Bombay", "location": "Mumbai", "state": "Maharashtra", "type": "Government", "stream": "Technology", "nirf": "3", "source_url": "https://www.iitb.ac.in", "logo_url": _favicon("iitb.ac.in")},
    {"slug": "iit-delhi", "name": "IIT Delhi", "location": "Delhi", "state": "Delhi", "type": "Government", "stream": "Technology", "nirf": "2", "source_url": "https://home.iitd.ac.in", "logo_url": _favicon("iitd.ac.in")},
    {"slug": "iit-madras", "name": "IIT Madras", "location": "Chennai", "state": "Tamil Nadu", "type": "Government", "stream": "Technology", "nirf": "1", "source_url": "https://www.iitm.ac.in", "logo_url": _favicon("iitm.ac.in")},
    {"slug": "aiims-delhi", "name": "AIIMS New Delhi", "location": "Delhi", "state": "Delhi", "type": "Government", "stream": "Medical", "nirf": "1", "source_url": "https://www.aiims.edu", "logo_url": _favicon("aiims.edu")},
]


COLLEGES_DATA = [
    {
        "name": "COEP Technological University",
        "state": "Maharashtra",
        "city": "Pune",
        "type": "Government",
        "stream": "Engineering",
        "nirf": "73",
        "logo_url": "/static/logo.png",
        "source_url": "https://www.coep.org.in",
    },
    {
        "name": "VJTI Mumbai",
        "state": "Maharashtra",
        "city": "Mumbai",
        "type": "Government",
        "stream": "Engineering",
        "nirf": "101-150",
        "logo_url": "/static/logo.png",
        "source_url": "https://vjti.ac.in",
    },
    {
        "name": "Fergusson College",
        "state": "Maharashtra",
        "city": "Pune",
        "type": "Autonomous",
        "stream": "Arts & Science",
        "nirf": "58",
        "logo_url": "/static/logo.png",
        "source_url": "https://fergusson.edu",
    },
    {
        "name": "St. Xavier's College",
        "state": "Maharashtra",
        "city": "Mumbai",
        "type": "Private",
        "stream": "Arts & Science",
        "nirf": "89",
        "logo_url": "/static/logo.png",
        "source_url": "https://xaviers.edu",
    },
    {
        "name": "KJ Somaiya College of Engineering",
        "state": "Maharashtra",
        "city": "Mumbai",
        "type": "Private",
        "stream": "Engineering",
        "nirf": "151-200",
        "logo_url": "/static/logo.png",
        "source_url": "https://kjsit.somaiya.edu",
    },
    {
        "name": "Ness Wadia College",
        "state": "Maharashtra",
        "city": "Pune",
        "type": "Aided",
        "stream": "Commerce",
        "nirf": "101-150",
        "logo_url": "/static/logo.png",
        "source_url": "https://nesswadia.edu",
    },
]


ARTICLES = [
    {
        "id": 1,
        "title": "Career in Engineering After 12th",
        "desc": "Engineering is one of the most sought-after career paths for Science (PCM) students in India. After Class 12, you can pursue B.Tech or BE in branches like Computer Science, Mechanical, Civil, Electrical, or Electronics. Admission is through JEE Main for NITs and IITs (via JEE Advanced), and MHT-CET for Maharashtra colleges. Top branches by placement and salary include CSE, AI & Data Science, and Electronics. Starting salaries at top companies range from ₹6–25 LPA for fresh graduates. Choosing the right college and branch based on your percentile, interests, and placement records is key to a strong engineering career.",
        "category": "engineering",
        "href": "engineering-details.html",
    },
    {
        "id": 2,
        "title": "Medical Careers Without MBBS",
        "desc": "Not everyone who clears NEET gets into MBBS — but there are excellent healthcare careers available without it. BDS (Dentistry), BAMS (Ayurveda), BHMS (Homeopathy), B.Pharm (Pharmacy), B.Sc Nursing, BPT (Physiotherapy), and BMLT (Medical Lab Technology) are all respected professions with good job prospects. Many of these courses are available through NEET score-based admissions or state-level entrance exams. The Indian healthcare sector is growing rapidly, creating strong demand for paramedical and allied health professionals. Starting salaries range from ₹3–8 LPA and grow significantly with experience and specialization.",
        "category": "medical",
        "href": "medical-details.html",
    },
    {
        "id": 3,
        "title": "MBA vs PGDM - Which is Better?",
        "desc": "MBA (Master of Business Administration) is a university-affiliated degree, while PGDM (Post Graduate Diploma in Management) is offered by autonomous institutes like IIMs and XLRI. Both are highly valued by employers. IIM PGDMs are considered among the best management qualifications in India, with average placements of ₹20–35 LPA. MBA from top state universities or private colleges offers more affordable fees (₹2–10 lakh) compared to IIM PGDM (₹20–25 lakh). CAT is the primary entrance exam for IIMs; MAT, XAT, and CMAT are alternatives for other colleges. Choose based on your target college, career goal, and budget.",
        "category": "management",
        "href": "mba-details.html",
    },
    {
        "id": 4,
        "title": "Top Government Jobs After Graduation",
        "desc": "Government jobs in India offer job security, good pay, and prestige. After graduation, top opportunities include UPSC Civil Services (IAS, IPS, IFS), SSC CGL for central government posts, IBPS PO/Clerk for banking, State PSC exams, and Railways (RRB NTPC, Group D). SSC CGL salary starts at ₹25,000–50,000/month; IAS officers earn ₹56,000–2.5 lakh/month plus allowances. Preparation requires 1–2 years of dedicated study. Coaching is available in cities like Pune, Delhi, and Mumbai. Setting a clear target exam and following a structured study plan are the most important success factors.",
        "category": "government",
        "href": "government-details.html",
    },
    {
        "id": 5,
        "title": "Future Skills Engineers Must Learn",
        "desc": "The engineering job market is evolving rapidly, and technical degrees alone are no longer enough. Employers in 2025 prioritize engineers who can work with AI/ML tools, write Python or SQL, understand cloud platforms (AWS, Azure), and apply data analytics to real problems. Cybersecurity awareness is essential across all engineering domains as software enters physical systems. Communication, project management, and teamwork skills are consistently rated as differentiators in placement interviews. Certifications from platforms like Coursera, NPTEL, and Google are widely recognized. Engineers who pair domain expertise with these cross-disciplinary skills command 20–40% higher starting salaries.",
        "category": "engineering",
        "href": "future-skills-details.html",
    },
    {
        "id": 6,
        "title": "Careers in Digital Marketing",
        "desc": "Digital marketing is one of the fastest-growing career fields in India, with every business — from startups to corporates — investing heavily in online presence. Key roles include SEO Specialist, Social Media Manager, Performance Marketer (Google/Meta Ads), Content Strategist, and Email Marketing Manager. No specific degree is mandatory; certifications from Google, HubSpot, and Meta are widely accepted. Freelancers can earn ₹20,000–1 lakh/month; agency roles start at ₹3–5 LPA and grow to ₹15–25 LPA at senior levels. Short-term courses (3–6 months) from NIIT, UpGrad, or Coursera can launch a career quickly with a strong portfolio.",
        "category": "management",
        "href": "digital-marketing-details.html",
    },
    {
        "id": 7,
        "title": "Careers in Aviation",
        "desc": "Aviation offers exciting career paths beyond just piloting. Commercial Pilot License (CPL) training takes 18–24 months and costs ₹35–60 lakh, but offers starting salaries of ₹1.5–3 lakh/month. Cabin crew roles require Class 12 pass, good communication, and height/weight eligibility — starting at ₹25,000–60,000/month. Airport management, Air Traffic Control (ATC via AAI recruitment), aircraft maintenance engineering (AME), and aviation logistics are strong ground-based options. DGCA regulates all aviation training in India. Indigo, Air India, and IndiGo are major domestic recruiters. Growth in Indian aviation — India is set to be the world's 3rd largest aviation market — means strong long-term demand.",
        "category": "aviation",
        "href": "aviation-details.html",
    },
    {
        "id": 8,
        "title": "Careers in Law",
        "desc": "A career in law begins with a 5-year integrated BA LLB or BBA LLB after Class 12, or a 3-year LLB after graduation. CLAT is the national entrance exam for National Law Universities (NLUs) — top NLUs like NLSIU Bangalore and NLU Delhi have average placements of ₹12–20 LPA. Specializations include Corporate Law, Criminal Law, Intellectual Property Rights (IPR), Family Law, and Constitutional Law. Lawyers can work in litigation, corporate legal teams, law firms, judiciary (judicial services exam), or public policy. The Bar Council of India governs enrollment. Internships at law firms during college are critical to building a strong career foundation.",
        "category": "law",
        "href": "law-details.html",
    },
    {
        "id": 9,
        "title": "Careers in Hotel Management",
        "desc": "Hotel Management is a professional course that opens doors to the booming hospitality and tourism industry. The top entrance exam is NCHMCT JEE for central government hotel management institutes; state-level exams exist for other colleges. Specializations include Food & Beverage, Front Office, Housekeeping, and Event Management. Starting salaries at 5-star hotels range from ₹15,000–30,000/month, growing significantly with experience and international postings. Top recruiters include Taj Hotels, Marriott, Hyatt, OYO, and ITC Hotels. Tourism is a priority sector under India's government initiatives, creating sustained job growth. Soft skills, language proficiency, and presentation are as important as technical knowledge in this field.",
        "category": "management",
        "href": "hotel-management-details.html",
    },
    {
        "id": 10,
        "title": "Careers in Fashion Designing",
        "desc": "Fashion designing is a creative career that combines art, textiles, and business. In India, NIFT (National Institute of Fashion Technology) is the premier institution, with entrance through the NIFT entrance exam. Other top colleges include Pearl Academy, NID, and Symbiosis Institute of Design. Specializations include Apparel Design, Accessory Design, Textile Design, and Fashion Communication. Graduates work with brands like Fabindia, Myntra, and global luxury labels, or launch independent labels. Starting salaries range from ₹3–6 LPA; experienced designers and brand founders earn significantly more. A strong portfolio of original work is the most important asset for landing top roles in this industry.",
        "category": "creative",
        "href": "fashion-designing-details.html",
    },
    {
        "id": 11,
        "title": "Careers in Data Science",
        "desc": "Data Science is among the highest-paying tech careers in India, with demand far outpacing supply. The role involves analyzing large datasets to extract business insights using Python, R, SQL, and machine learning libraries like Scikit-learn and TensorFlow. Entry-level data analyst roles start at ₹4–8 LPA; senior data scientists and ML engineers earn ₹15–40 LPA at top companies like Google, Flipkart, and Razorpay. A B.Tech in CS, Statistics, or Mathematics is a common entry path, though many transition from other fields via online courses. IIT and IIM offer postgraduate programs in data science. Building projects on Kaggle and GitHub is the most effective way to stand out to employers.",
        "category": "technology",
        "href": "data-science-details.html",
    },
    {
        "id": 12,
        "title": "Careers in Blockchain",
        "desc": "Blockchain technology is expanding beyond cryptocurrency into supply chain, healthcare, finance, and digital identity. In India, companies like TCS, Infosys, and Wipro are building blockchain practices, alongside crypto startups. Key roles include Blockchain Developer (Solidity, Rust), Smart Contract Auditor, Blockchain Architect, and Web3 Product Manager. Salaries for blockchain developers start at ₹8–12 LPA and go up to ₹30+ LPA for experienced architects. Certifications from platforms like Coursera (IBM Blockchain) and ConsenSys Academy are recognized by employers. A foundation in computer science, cryptography, and distributed systems is essential. The sector is volatile, so diversifying skills across traditional software engineering and blockchain is a smart career strategy.",
        "category": "technology",
        "href": "blockchain-details.html",
    },
    {
        "id": 13,
        "title": "Careers in Machine Learning",
        "desc": "Machine Learning (ML) engineers build the AI systems powering everything from Google Search to medical diagnostics. Core skills include Python, linear algebra, statistics, and deep learning frameworks like PyTorch and TensorFlow. In India, top ML roles at companies like Google, Amazon, and unicorn startups pay ₹15–50 LPA. Entry paths include B.Tech/M.Tech in CS or AI, or transitioning via postgraduate programs at IITs or through intensive online bootcamps. MLOps — deploying and maintaining ML models in production — is a rapidly growing specialization. Kaggle competitions, research paper co-authorship, and open-source contributions significantly accelerate career growth. The field evolves quickly, making continuous learning non-negotiable.",
        "category": "technology",
        "href": "machine-learning-details.html",
    },
    {
        "id": 14,
        "title": "Careers in Cloud Computing",
        "desc": "Cloud computing skills are among the most in-demand in the Indian IT industry. Every major enterprise is migrating to AWS, Microsoft Azure, or Google Cloud, creating massive demand for Cloud Engineers, DevOps Engineers, and Cloud Architects. AWS certifications (Solutions Architect, SysOps) and Azure certifications are actively sought by recruiters at TCS, Infosys, HCL, and tech startups. Starting salaries range from ₹5–10 LPA; senior cloud architects earn ₹25–50 LPA. Skills in Kubernetes, Docker, Terraform, and CI/CD pipelines are baseline requirements for most roles. Cloud roles are largely remote-friendly. B.Tech graduates with cloud certifications frequently outpace peers who rely only on their degree in placement interviews.",
        "category": "technology",
        "href": "cloud-computing-details.html",
    },
    {
        "id": 15,
        "title": "Careers in Architecture",
        "desc": "Architecture blends creative design with structural engineering to shape buildings, cities, and public spaces. In India, a B.Arch degree (5 years) is the entry qualification, with admission through NATA or JEE Paper 2. Top colleges include SPA Delhi, CEPT Ahmedabad, and IIT Kharagpur Architecture. Architects work in construction firms, urban planning departments, real estate, interior design, and government bodies like CPWD. Starting salaries range from ₹3–6 LPA; experienced architects and firm partners earn significantly more. AutoCAD, Revit, SketchUp, and 3ds Max are essential software tools. India's rapid urbanization and smart cities mission are generating strong long-term demand for qualified architects.",
        "category": "creative",
        "href": "architecture-details.html",
    },
    {
        "id": 16,
        "title": "Careers in Robotics",
        "desc": "Robotics is a multidisciplinary field combining mechanical engineering, electronics, and computer science to design intelligent machines. In India, B.Tech programs in Robotics and Automation are offered at VIT, Amity, and several NITs. Core skills include embedded systems programming (C, Python, ROS), control systems, and computer vision. Job roles include Robotics Engineer, Automation Specialist, and Research Scientist at companies like ISRO, DRDO, Tata Motors, and multinational automation firms. Starting salaries range from ₹4–10 LPA in India; international roles pay significantly more. The manufacturing, agriculture, healthcare, and defence sectors are all rapidly adopting robotics. Participating in robotics competitions like e-Yantra and RoboSoft builds a strong portfolio for placements.",
        "category": "robotics",
        "href": "robotics-details.html",
    },
    {
        "id": 17,
        "title": "Careers in Cybersecurity",
        "desc": "Cybersecurity is one of the fastest-growing and highest-paying IT fields globally, with a massive talent shortage in India. Roles include Ethical Hacker (Penetration Tester), SOC Analyst, Security Architect, and Incident Responder. Certifications like CEH (Certified Ethical Hacker), CompTIA Security+, OSCP, and CISSP are widely recognized by employers. Top recruiters include TCS, Wipro, Infosys, banks, and government agencies like CERT-In and NIC. Starting salaries range from ₹5–10 LPA; senior professionals earn ₹20–50 LPA. B.Tech in CS or IT is a common entry path, with many professionals transitioning via online certifications. India's Digital India mission and banking sector digitization are driving sustained demand for cybersecurity talent.",
        "category": "cybersecurity",
        "href": "cybersecurity-details.html",
    },
    {
        "id": 18,
        "title": "Careers in UI/UX Design",
        "desc": "UI/UX Design focuses on creating intuitive and visually appealing digital experiences for apps and websites. It is one of the most accessible tech-adjacent careers — no coding degree required, though basic HTML/CSS knowledge helps. Core tools include Figma, Adobe XD, and Protopie; user research, wireframing, and usability testing are essential skills. In India, UI/UX designers are hired by startups, product companies, and agencies. Starting salaries range from ₹4–8 LPA; senior designers and design leads earn ₹15–30 LPA. Building a strong Behance or Dribbble portfolio with case studies is the primary path to getting hired. Short courses from Google, Coursera, and DesignBoat are widely respected alternatives to formal degrees.",
        "category": "ui-ux-design",
        "href": "ui-ux-design-details.html",
    },
    {
        "id": 19,
        "title": "Careers in Renewable Energy",
        "desc": "India aims to achieve 500 GW of renewable energy capacity by 2030, creating enormous job opportunities in solar, wind, and EV sectors. Careers include Solar Energy Engineer, Wind Turbine Technician, Energy Auditor, EV Systems Engineer, and Grid Integration Specialist. B.Tech in Electrical, Mechanical, or Environmental Engineering provides a strong foundation; specialized M.Tech in Renewable Energy is also available at IITs and NITs. Top recruiters include NTPC, Adani Green, Tata Power, ReNew Power, and Mahindra Electric. Starting salaries range from ₹4–8 LPA; project managers and engineers with international certifications earn ₹15–25 LPA. Government schemes like PM KUSUM and the National Solar Mission are creating both public and private sector opportunities across India.",
        "category": "renewable-energy",
        "href": "renewable-energy-details.html",
    },
    {
        "id": 20,
        "title": "Careers in Genetic Engineering",
        "desc": "Genetic Engineering is a cutting-edge field applying molecular biology and biotechnology to modify living organisms for medical, agricultural, and industrial applications. In India, B.Tech in Biotechnology or Genetic Engineering is offered at VIT, SRM, Amity, and IIT Madras. Core skills include molecular cloning, CRISPR gene editing, bioinformatics, and cell culture techniques. Career paths include Research Scientist, Bioprocess Engineer, Clinical Research Associate, and Regulatory Affairs Specialist. Top employers include CSIR labs, ICMR institutes, Biocon, Dr. Reddy's, and multinational pharma companies. Starting salaries range from ₹3–7 LPA; research positions at premier institutions and abroad pay significantly more. A Master's degree (M.Sc or M.Tech) or PhD significantly boosts career prospects in this research-intensive field.",
        "category": "genetic-engineering",
        "href": "genetic-engineering-details.html",
    },
]


CATEGORIES = [
    {"value": "all", "label": "All"},
    {"value": "engineering", "label": "Engineering"},
    {"value": "medical", "label": "Medical"},
    {"value": "management", "label": "Management"},
    {"value": "government", "label": "Government"},
    {"value": "aviation", "label": "Aviation"},
    {"value": "law", "label": "Law"},
    {"value": "creative", "label": "Creative"},
    {"value": "technology", "label": "Technology"},
    {"value": "robotics", "label": "Robotics"},
    {"value": "cybersecurity", "label": "Cybersecurity"},
    {"value": "ui-ux-design", "label": "UI/UX Design"},
    {"value": "renewable-energy", "label": "Renewable Energy"},
    {"value": "genetic-engineering", "label": "Genetic Engineering"},
]


def get_article_by_id(article_id):
    return next((article for article in ARTICLES if article["id"] == article_id), None)


def build_article_teaser(text, max_len=120):
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def build_article_paragraphs(text):
    # Turn long one-line content into readable chunks for detail page rendering.
    sentences = [part.strip() for part in (text or "").split(".") if part.strip()]
    if not sentences:
        return ["Content will be updated soon."]

    paragraphs = []
    bucket = []
    for idx, sentence in enumerate(sentences, start=1):
        bucket.append(sentence + ".")
        if len(bucket) == 3 or idx == len(sentences):
            paragraphs.append(" ".join(bucket))
            bucket = []
    return paragraphs


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/blog")
def blog():
    return render_template("blogs.html")  # Placeholder


@app.route("/epaper")
def epaper():
    return render_template("epaper.html")


@app.route("/api/epaper-feed")
def epaper_feed():
    base = VMADMIN_BASE_URL
    if not base:
        return jsonify([])

    # Prefer dedicated e-paper sources first so frontend gets PDF-enabled editions.
    source_paths = ["/api/epapers", "/api/editions", "/api/news", "/news"]

    for path in source_paths:
        current_url = f"{base}{path}"
        combined_items = []
        page_guard = 0

        while current_url and page_guard < 25:
            payload = fetch_remote_json(current_url)
            if payload is None:
                combined_items = []
                break

            items = extract_items(payload)
            if items:
                combined_items.extend(items)
                current_url = extract_next_url(payload, current_url)
            else:
                if isinstance(payload, list):
                    combined_items.extend(payload)
                current_url = None

            page_guard += 1

        if combined_items:
            return jsonify(combined_items)

    return jsonify([])


@app.route("/api/epaper-pdf-proxy")
def epaper_pdf_proxy():
    raw_url = (request.args.get("url") or "").strip()
    if not raw_url:
        return jsonify({"error": "Missing url parameter."}), 400

    _ALLOWED_HOSTS = {
        "drive.google.com", "docs.google.com",
        "drive.usercontent.google.com", "lh3.googleusercontent.com",
    }
    try:
        parsed = urlparse(raw_url)
        host = parsed.netloc.lower().lstrip("www.")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return jsonify({"error": "Invalid URL."}), 400
        if host not in _ALLOWED_HOSTS:
            return jsonify({"error": "Only Google Drive links are supported."}), 400
    except Exception:
        return jsonify({"error": "Invalid URL."}), 400

    def fetch_bytes(target_url):
        req = Request(
            target_url,
            headers={
                "Accept": "application/pdf,*/*",
                "User-Agent": "vm-main-website/1.0",
            },
        )
        with urlopen(req, timeout=25) as response:
            payload = response.read()
            ctype = (response.headers.get("Content-Type", "") or "").lower()
            return payload, ctype

    def extract_drive_file_id(url_value):
        parsed_url = urlparse(url_value)
        host = parsed_url.netloc.lower()
        if "drive.google.com" not in host and "docs.google.com" not in host:
            return None

        match = re.search(r"/file/d/([^/]+)", parsed_url.path)
        if match:
            return match.group(1)

        query_id = parse_qs(parsed_url.query).get("id", [None])[0]
        if query_id:
            return query_id

        return None

    candidate_urls = [raw_url]
    drive_file_id = extract_drive_file_id(raw_url)
    if drive_file_id:
        candidate_urls.append(f"https://drive.usercontent.google.com/uc?id={drive_file_id}&export=download")
        candidate_urls.append(f"https://drive.google.com/uc?export=download&id={drive_file_id}")

    tried = set()
    try:
        for candidate in candidate_urls:
            if candidate in tried:
                continue
            tried.add(candidate)
            payload, ctype = fetch_bytes(candidate)

            if payload.startswith(b"%PDF"):
                return payload, 200, {
                    "Content-Type": "application/pdf",
                    "Cache-Control": "no-store",
                    "Content-Disposition": "inline; filename=epaper.pdf",
                    "X-Frame-Options": "SAMEORIGIN",
                }

            if "text/html" in ctype and drive_file_id:
                html_text = html.unescape(unquote(payload.decode("utf-8", errors="ignore")))
                embedded = re.search(
                    r"https://drive\.usercontent\.google\.com/uc\?id=[^\"'\s&]+(?:&amp;|&)export=download",
                    html_text,
                )
                if embedded:
                    embedded_url = embedded.group(0).replace("&amp;", "&")
                    if embedded_url not in tried:
                        tried.add(embedded_url)
                        embedded_payload, embedded_ctype = fetch_bytes(embedded_url)
                        if embedded_payload.startswith(b"%PDF") or "application/pdf" in embedded_ctype:
                            return embedded_payload, 200, {
                                "Content-Type": "application/pdf",
                                "Cache-Control": "no-store",
                                "Content-Disposition": "inline; filename=epaper.pdf",
                                "X-Frame-Options": "SAMEORIGIN",
                            }

        return jsonify({
            "error": "Could not resolve a direct PDF stream from the provided link.",
            "hint": "Ensure the source file is public (Anyone with the link can view).",
        }), 502
    except (HTTPError, URLError, TimeoutError, ValueError):
        return jsonify({"error": "Unable to fetch PDF from source URL."}), 502

@app.route("/admin")
def admin():
    return render_template("epaper_admin_v2.html")


@app.route("/api/vmadmin/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def vmadmin_proxy(subpath):
    if not VMADMIN_BASE_URL:
        return jsonify({"error": "VMADMIN_BASE_URL is not configured."}), 500

    upstream_url = f"{VMADMIN_BASE_URL}/{subpath.lstrip('/')}"
    if request.query_string:
        upstream_url = f"{upstream_url}?{request.query_string.decode('utf-8', errors='ignore')}"

    passthrough_headers = {
        "Accept": request.headers.get("Accept", "application/json"),
        "User-Agent": "vm-main-website/1.0",
    }
    if request.headers.get("Authorization"):
        passthrough_headers["Authorization"] = request.headers["Authorization"]
    if request.headers.get("Content-Type"):
        passthrough_headers["Content-Type"] = request.headers["Content-Type"]

    body = request.get_data() if request.method in {"POST", "PUT", "PATCH"} else None
    proxy_request = Request(
        upstream_url,
        data=body,
        headers=passthrough_headers,
        method=request.method,
    )

    try:
        with urlopen(proxy_request, timeout=20) as response:
            payload = response.read()
            status_code = response.getcode()
            content_type = response.headers.get("Content-Type", "application/json")
            return payload, status_code, {"Content-Type": content_type}
    except HTTPError as exc:
        error_payload = exc.read()
        content_type = exc.headers.get("Content-Type", "application/json") if exc.headers else "application/json"
        return error_payload, exc.code, {"Content-Type": content_type}
    except URLError:
        return jsonify({"error": "Unable to reach VM admin service."}), 502



@app.route("/universities")
def universities():
    states = sorted({item["state"] for item in UNIVERSITIES_DATA})
    cities = sorted({item["location"] for item in UNIVERSITIES_DATA})
    types = sorted({item["type"] for item in UNIVERSITIES_DATA})
    streams = sorted({item["stream"] for item in UNIVERSITIES_DATA})
    return render_template(
        "universities.html",
        universities=UNIVERSITIES_DATA,
        states=states,
        cities=cities,
        types=types,
        streams=streams,
    )


@app.route("/universities/<slug>")
def university_detail(slug):
    university = next((item for item in UNIVERSITIES_DATA if item["slug"] == slug), None)
    if university is None:
        return redirect(url_for("universities"))
    return render_template("universities.html", universities=[university], states=[], cities=[], types=[], streams=[])


@app.route("/colleges")
def colleges():
    q = (request.args.get("q") or "").strip()
    alpha = (request.args.get("alpha") or "").strip().upper()
    if alpha and not re.fullmatch(r"[A-Z]", alpha):
        alpha = ""
    state_filter = (request.args.get("state") or "").strip()
    per_page_options = [25, 50, 100]
    try:
        requested_per_page = int(request.args.get("per_page", "25"))
    except ValueError:
        requested_per_page = 25
    per_page = requested_per_page if requested_per_page in per_page_options else 25

    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    page = max(1, page)

    state_counts, total_colleges, state_err = fetch_college_state_counts()
    if state_err:
        app.logger.warning("colleges DB error: %s", state_err)

    error = state_err
    grouped_states = []
    colleges_rows = []
    search_mode = bool(q or alpha or state_filter)
    total_pages = 1
    paginate_results = bool(state_filter)

    if search_mode:
        query_page = page if paginate_results else 1
        query_per_page = per_page if paginate_results else None
        colleges_rows, total, db_error = fetch_colleges_search(
            query_page,
            query_per_page,
            q=q or None,
            alpha=alpha or None,
            state=state_filter or None,
        )
        if db_error:
            app.logger.warning("colleges DB error: %s", db_error)
            error = db_error
        if paginate_results:
            total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
            if page > total_pages:
                page = total_pages
                colleges_rows, total, db_error = fetch_colleges_search(
                    page,
                    per_page,
                    q=q or None,
                    alpha=alpha or None,
                    state=state_filter or None,
                )
                if db_error:
                    app.logger.warning("colleges DB error: %s", db_error)
                    error = db_error
        pagination_label = "colleges"
        pagination_start = ((page - 1) * per_page + 1) if total and paginate_results else (1 if total else 0)
        pagination_end = min(page * per_page, total) if paginate_results else total
    else:
        page = 1
        per_page = None
        page_states = state_counts
        state_names = [row.get("state") for row in page_states if row.get("state")]

        colleges_rows, db_error = fetch_colleges_by_states(state_names, limit_per_state=12)
        if db_error:
            app.logger.warning("colleges DB error: %s", db_error)
            error = db_error

        buckets = {name: [] for name in state_names}
        for college in colleges_rows:
            buckets.setdefault(college.get("state") or "", []).append(college)

        grouped_states = [
            {
                "state": row.get("state"),
                "count": row.get("count", 0),
                "colleges": buckets.get(row.get("state"), []),
            }
            for row in page_states
        ]

        pagination_label = "states"
        pagination_start = 1 if state_counts else 0
        pagination_end = len(state_counts)
        total = len(state_counts)

    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "colleges.html",
        colleges=colleges_rows,
        grouped_states=grouped_states,
        state_counts=state_counts,
        total_colleges=total_colleges,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_page=page - 1,
        next_page=page + 1,
        pagination_label=pagination_label,
        pagination_start=pagination_start,
        pagination_end=pagination_end,
        search_mode=search_mode,
        query=q,
        alpha=alpha,
        alphabet=list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        state_filter=state_filter,
        per_page_options=per_page_options,
        paginate_results=paginate_results,
        error=error,
    )


@app.route("/courses")
def courses():
    return render_template("courses.html")


@app.route("/entrance-exams")
def exams():
    exams_data = {}
    total_exams = 0
    try:
        connection_url = get_postgres_connection_url()
        if connection_url and connect:
            import psycopg2.extras
            with connect(connection_url) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT payload FROM entrance_exams LIMIT 8208")
                    rows = cur.fetchall()
                    for row in rows:
                        payload = row.get("payload", {})
                        if isinstance(payload, dict):
                            category = payload.get("category", "general").lower()
                            if category not in exams_data:
                                exams_data[category] = []
                            exams_data[category].append(payload)
                            total_exams += 1
    except Exception as e:
        app.logger.warning("Failed to fetch entrance exams from Postgres: %s", e)
        import traceback
        app.logger.warning(traceback.format_exc())
    
    return render_template("entrance-exams.html", exams_data=exams_data, total_exams=total_exams)


@app.route("/mock-exams")
def mock_exams():
    # Dynamic lists to populate the Jinja2 loops
    exams = ["JEE", "NEET", "MHT-CET", "CAT", "GATE", "CLAT"]
    streams = [
        {"name": "Engineering", "class": "engineering", "icon": "fa-microchip"},
        {"name": "Medical", "class": "medical", "icon": "fa-user-md"},
        {"name": "Management", "class": "management", "icon": "fa-chart-pie"},
        {"name": "Banking", "class": "banking", "icon": "fa-university"}
    ]
    return render_template("mock_exams.html", exams=exams, streams=streams)


@app.route("/cutoffs")
def cutoffs():
    branches, categories, genders, options_error = get_cutoff_options()
    top_colleges, top_error = get_top_cutoff_colleges(limit=20)
    return render_template(
        "cutoffs.html",
        branches=branches,
        categories=categories,
        genders=genders,
        top_colleges=top_colleges,
        error=options_error or top_error,
    )


@app.route("/api/college-predictor", methods=["POST"])
def api_college_predictor():
    payload = request.get_json(silent=True) or {}

    try:
        percentile = float(payload.get("percentile", 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Enter a valid percentile."}), 400

    if percentile < 0 or percentile > 100:
        return jsonify({"success": False, "error": "Percentile must be between 0 and 100."}), 400

    branch = str(payload.get("branch", "")).strip()
    category = str(payload.get("category", "OPEN")).strip().upper() or "OPEN"
    gender = str(payload.get("gender", "G")).strip().upper() or "G"
    try:
        page = int(payload.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    try:
        per_page = int(payload.get("per_page", 20))
    except (TypeError, ValueError):
        per_page = 20
    per_page = per_page if per_page in {20, 50, 100} else 20

    recommendations, total_matches, error = predict_colleges_from_cutoffs(
        percentile=percentile,
        category=category,
        gender=gender,
        branch=branch,
        page=page,
        per_page=per_page,
    )

    if error:
        return jsonify({"success": False, "error": error, "recommendations": []}), 200

    total_pages = max(1, (total_matches + per_page - 1) // per_page) if total_matches else 1
    return jsonify(
        {
            "success": True,
            "student_input": {
                "percentile": percentile,
                "category": category,
                "gender": gender,
                "gender_label": cutoff_gender_label(gender),
                "branch": branch,
            },
            "total_matches": total_matches,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
            },
            "recommendations": recommendations,
        }
    )


@app.route("/api/top-cutoff-colleges", methods=["POST"])
def api_top_cutoff_colleges():
    payload = request.get_json(silent=True) or {}
    branch = str(payload.get("branch", "")).strip()
    category = str(payload.get("category", "")).strip().upper()
    gender = str(payload.get("gender", "")).strip().upper()

    recommendations, error = get_top_cutoff_colleges(
        limit=20,
        branch=branch or None,
        category=category or None,
        gender=gender or None,
    )

    if error:
        return jsonify({"success": False, "error": error, "recommendations": []}), 200

    return jsonify(
        {
            "success": True,
            "filters": {
                "branch": branch,
                "category": category,
                "gender": gender,
                "gender_label": cutoff_gender_label(gender) if gender else "",
            },
            "locked_full_list": True,
            "recommendations": recommendations,
        }
    )


@app.route("/api/coupons/validate", methods=["POST"])
def api_coupons_validate():
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip()
    if not code:
        return jsonify({"success": False, "error": "Coupon code is required."}), 200
    coupon = find_coupon(code)
    if not coupon:
        return jsonify({"success": False, "valid": False, "error": "Invalid coupon code."}), 200

    try:
        amount = int(float(coupon.get("amount_rupees", 0)))
    except Exception:
        amount = 0

    return jsonify({
        "success": True,
        "valid": True,
        "amount_rupees": amount,
        "uses_remaining": coupon.get("uses_remaining"),
        "message": coupon.get("message") or "Coupon valid.",
    }), 200


@app.route("/api/cutoff-payment/order", methods=["POST"])
def api_cutoff_payment_order():
    payload = request.get_json(silent=True) or {}
    filters = {
        "branch": str(payload.get("branch", "")).strip(),
        "category": str(payload.get("category", "")).strip().upper(),
        "gender": str(payload.get("gender", "")).strip().upper(),
    }
    # optional coupon code
    coupon_code = str(payload.get("coupon_code", "")).strip()

    # determine discount from coupon (if provided)
    discount_rupees = 0
    coupon_obj = None
    if coupon_code:
        coupon_obj = find_coupon(coupon_code)
        if not coupon_obj:
            return jsonify({"success": False, "error": "Invalid coupon code."}), 200
        # coupon may have an explicit amount_rupees key
        try:
            discount_rupees = int(float(coupon_obj.get("amount_rupees", 0)))
        except Exception:
            discount_rupees = 0

    amount_rupees = max(0, int(FULL_CUTOFF_PRICE_RUPEES - discount_rupees))
    amount_paise = int(amount_rupees * 100)

    # If the coupon makes the price zero, grant access immediately and consume coupon
    if amount_paise <= 0:
        if coupon_obj:
            consumed = consume_coupon(coupon_code)
            if not consumed:
                return jsonify({"success": False, "error": "Coupon could not be consumed or is exhausted."}), 200
        session["full_cutoff_unlocked"] = {
            "payment_id": None,
            "order_id": None,
            "filters": filters,
            "coupon_code": coupon_code or None,
            "unlocked_at": int(time.time()),
        }
        return jsonify({"success": True, "message": "Full cutoff list unlocked via coupon.", "unlocked": True}), 200

    # otherwise create a Razorpay order for the remaining amount
    receipt = f"cutoff_{secrets.token_hex(8)}"
    notes = {
        "product": "full_cutoff_list",
        "branch": filters["branch"][:200],
        "category": filters["category"][:50],
        "gender": filters["gender"][:20],
        "coupon_code": coupon_code or "",
        "discount_rupees": discount_rupees,
    }

    try:
        order = create_razorpay_order(amount_paise, receipt, notes=notes)
    except HTTPError as exc:
        try:
            details = exc.read().decode("utf-8")
        except Exception:
            details = str(exc)
        return jsonify({"success": False, "error": f"Razorpay order failed: {details}"}), 200
    except (URLError, TimeoutError) as exc:
        return jsonify({"success": False, "error": f"Could not connect to Razorpay: {exc}"}), 200
    except (RuntimeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 200

    session["pending_cutoff_order"] = {
        "order_id": order.get("id"),
        "amount": amount_paise,
        "filters": filters,
        "coupon_code": coupon_code or None,
        "created_at": int(time.time()),
    }
    config = get_razorpay_config()
    return jsonify(
        {
            "success": True,
            "key_id": config["key_id"] if config else "",
            "order": order,
            "amount_rupees": amount_rupees,
            "filters": filters,
        }
    )


@app.route("/api/cutoff-payment/verify", methods=["POST"])
def api_cutoff_payment_verify():
    payload = request.get_json(silent=True) or {}
    order_id = str(payload.get("razorpay_order_id", "")).strip()
    payment_id = str(payload.get("razorpay_payment_id", "")).strip()
    signature = str(payload.get("razorpay_signature", "")).strip()
    pending_order = session.get("pending_cutoff_order") or {}

    if not order_id or not payment_id or not signature:
        return jsonify({"success": False, "error": "Missing Razorpay payment details."}), 400

    if pending_order.get("order_id") != order_id:
        return jsonify({"success": False, "error": "Payment order mismatch. Please try again."}), 400

    if not verify_razorpay_payment_signature(order_id, payment_id, signature):
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    # consume coupon if any (for partial-discount orders)
    coupon_code = pending_order.get("coupon_code")
    if coupon_code:
        # consume only now that payment verified
        consume_coupon(coupon_code)

    session["full_cutoff_unlocked"] = {
        "payment_id": payment_id,
        "order_id": order_id,
        "filters": pending_order.get("filters", {}),
        "coupon_code": coupon_code or None,
        "unlocked_at": int(time.time()),
    }
    session.pop("pending_cutoff_order", None)
    return jsonify({"success": True, "message": "Full cutoff list unlocked."})


@app.route("/api/full-cutoff-colleges", methods=["POST"])
def api_full_cutoff_colleges():
    unlocked = session.get("full_cutoff_unlocked")
    if not unlocked:
        return jsonify({"success": False, "payment_required": True, "error": "Please complete payment to unlock the full cutoff list."}), 402

    payload = request.get_json(silent=True) or {}
    branch = str(payload.get("branch", "")).strip()
    category = str(payload.get("category", "")).strip().upper()
    gender = str(payload.get("gender", "")).strip().upper()
    try:
        page = int(payload.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(payload.get("per_page", 100))
    except (TypeError, ValueError):
        per_page = 100
    per_page = per_page if per_page in {100, 250, 500} else 100

    recommendations, total_matches, error = get_full_cutoff_colleges(
        branch=branch or None,
        category=category or None,
        gender=gender or None,
        page=page,
        per_page=per_page,
    )

    if error:
        return jsonify({"success": False, "error": error, "recommendations": []}), 200

    total_pages = max(1, (total_matches + per_page - 1) // per_page) if total_matches else 1
    return jsonify(
        {
            "success": True,
            "unlocked": True,
            "total_matches": total_matches,
            "pagination": {
                "page": max(1, page),
                "per_page": per_page,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
            },
            "recommendations": recommendations,
        }
    )


@app.route("/fyjc_rank")
def fyjc_rank():
    return render_template("fyjc_rank.html")


@app.route("/predict", methods=["POST"])
def fyjc_predict():
    import math

    payload = request.get_json(silent=True) or {}
    board = str(payload.get("board", "maharashtra")).strip()
    category = str(payload.get("category", "open")).strip()
    division = str(payload.get("division", "mumbai")).strip()
    pwd = str(payload.get("pwd", "no")).strip()
    stream = str(payload.get("stream", "science")).strip()
    marks_raw = payload.get("marks", [])

    try:
        marks = [float(m) for m in marks_raw]
        if len(marks) != 5 or any(m < 0 or m > 100 for m in marks):
            return jsonify({"error": "Invalid marks"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid marks"}), 400

    total = sum(marks)
    percentage = round(total / 500 * 100, 2)

    # Approximate total applicants per division (historical FYJC data)
    DIVISION_TOTALS = {
        "mumbai": 260000, "pune": 185000, "nashik": 82000,
        "aurangabad": 72000, "amravati": 42000, "nagpur": 92000,
        "konkan": 52000, "latur": 53000,
    }
    total_applicants = DIVISION_TOTALS.get(division, 100000)

    # Reserved category seat fraction
    CAT_FACTOR = {
        "open": 1.0, "obc": 0.27, "sc": 0.13, "st": 0.075,
        "nt": 0.11, "vj": 0.03, "sbc": 0.02, "ews": 0.10,
    }
    cat_factor = CAT_FACTOR.get(category, 1.0)

    # PWD/sports/ex-service get additional 3% seats bonus (smaller pool)
    if pwd and pwd != "no":
        cat_factor *= 0.05

    # Percentile using normal approximation: mean ~72%, SD ~12%
    z = (percentage - 72.0) / 12.0
    # erf approximation
    t = 1.0 / (1.0 + 0.3275911 * abs(z))
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf_approx = 1.0 - poly * math.exp(-(z * z))
    if z < 0:
        erf_approx = -erf_approx
    percentile_raw = 50.0 * (1.0 + erf_approx)
    percentile = round(min(99.9, max(0.1, percentile_raw)), 1)

    # Rank range
    rank_mid = max(1, int((1.0 - percentile / 100.0) * total_applicants * cat_factor))
    rank_low = max(1, int(rank_mid * 0.88))
    rank_high = max(rank_low + 50, int(rank_mid * 1.12))

    # College lists per stream (representative Maharashtra FYJC cut-offs)
    COLLEGE_DATA = {
        "science": [
            ("Jai Hind College", "Churchgate, Mumbai", 95.0),
            ("Mithibai College", "Vile Parle, Mumbai", 93.6),
            ("Ruia College", "Matunga, Mumbai", 92.8),
            ("Wilson College", "Chowpatty, Mumbai", 91.4),
            ("Bhavan's College", "Andheri, Mumbai", 90.2),
            ("KC College", "Churchgate, Mumbai", 89.6),
            ("Sathaye College", "Vile Parle, Mumbai", 88.0),
            ("Patkar College", "Goregaon, Mumbai", 86.4),
            ("NES Ratnam College", "Bhandup, Mumbai", 84.0),
            ("Guru Nanak Khalsa College", "Matunga, Mumbai", 82.6),
            ("VES College of Arts", "Chembur, Mumbai", 80.0),
            ("Kelkar College", "Mulund, Mumbai", 78.4),
            ("Saraswati College", "Kharghar, Navi Mumbai", 76.0),
            ("Fergusson College", "Shivajinagar, Pune", 91.2),
            ("SP College", "Sadashiv Peth, Pune", 89.4),
            ("Nowrosjee Wadia College", "Pune", 87.6),
            ("Brihan Maharashtra College", "Pune", 85.8),
            ("BMCC (Balmohan Vishramshetra)", "Paud Rd, Pune", 84.0),
            ("Abasaheb Garware College", "Karve Rd, Pune", 82.0),
            ("Sir Parashurambhau College", "Tilak Rd, Pune", 80.4),
        ],
        "commerce": [
            ("Jai Hind College (Commerce)", "Churchgate, Mumbai", 94.0),
            ("H.R. College of Commerce", "Churchgate, Mumbai", 93.0),
            ("N.M. College of Commerce", "Vile Parle, Mumbai", 92.0),
            ("Mithibai College (Commerce)", "Vile Parle, Mumbai", 91.0),
            ("Sydenham College", "Mumbai", 90.2),
            ("Lala Lajpat Rai College", "Matunga, Mumbai", 89.0),
            ("SIES College of Commerce", "Sion, Mumbai", 87.6),
            ("Mulund College of Commerce", "Mulund, Mumbai", 86.0),
            ("Thakur College of Science", "Kandivali, Mumbai", 84.4),
            ("VES College of Arts", "Chembur, Mumbai", 82.0),
            ("Nowrosjee Wadia College (Commerce)", "Pune", 90.0),
            ("Abasaheb Garware College (Commerce)", "Pune", 88.0),
            ("Brihan Maharashtra College (Commerce)", "Pune", 86.0),
            ("Modern College Shivajinagar (Commerce)", "Pune", 84.0),
            ("Shri Shivaji Science College", "Amravati", 82.0),
        ],
        "arts": [
            ("Elphinstone College", "Fort, Mumbai", 88.0),
            ("St. Xavier's College", "Fort, Mumbai", 87.0),
            ("Wilson College (Arts)", "Chowpatty, Mumbai", 85.4),
            ("Khalsa College", "Matunga, Mumbai", 83.0),
            ("R.D. National College", "Bandra, Mumbai", 80.6),
            ("K.J. Somaiya College", "Vidyavihar, Mumbai", 78.0),
            ("Gurukul College of Arts", "Ghantali, Thane", 75.0),
            ("Tilak College of Education", "Pune", 83.0),
            ("Fergusson College (Arts)", "Shivajinagar, Pune", 85.0),
            ("Modern College (Arts)", "Shivajinagar, Pune", 82.0),
            ("Maulana Azad College", "Aurangabad", 74.0),
            ("Hislop College (Arts)", "Nagpur", 76.0),
            ("Institute of Science (Arts)", "Nagpur", 78.0),
            ("S.M.T. Kasturbai College", "Nashik", 72.0),
            ("New Arts College", "Ahmednagar", 70.0),
        ],
    }

    college_list = COLLEGE_DATA.get(stream, COLLEGE_DATA["science"])
    # Sort by cutoff descending; last year's cutoff
    last_year_cutoff = percentage  # use student's % as reference
    eligible_colleges = 0
    colleges_out = []
    for name, loc, cutoff in college_list:
        diff = percentage - cutoff
        if diff >= 2:
            chance = "high"
        elif diff >= -1:
            chance = "moderate"
        elif diff >= -3:
            chance = "borderline"
        else:
            chance = "low"
        if chance != "low":
            eligible_colleges += 1
        colleges_out.append({"name": name, "loc": loc, "cutoff": cutoff, "chance": chance})

    # marks_vs_cutoff: student % minus median cutoff for the stream
    cutoffs = [c[2] for c in college_list]
    median_cutoff = sorted(cutoffs)[len(cutoffs) // 2]
    marks_vs_cutoff = round(percentage - median_cutoff, 1)

    return jsonify({
        "rank_low": rank_low,
        "rank_high": rank_high,
        "total_applicants": total_applicants,
        "board": board,
        "category": category,
        "division": division,
        "stream": stream,
        "percentage": percentage,
        "percentile": percentile,
        "eligible_colleges": eligible_colleges,
        "marks_vs_cutoff": marks_vs_cutoff,
        "colleges": colleges_out,
    })


@app.route("/admissions")
def admissions():
    return render_template("admissions.html")  # Placeholder

@app.route("/news")
def news():
    initial_articles = []
    category_labels = {
        "entrance": "Entrance Exams",
        "results": "Results",
        "admissions": "Admissions",
        "govtjobs": "Govt Jobs",
        "scholarship": "Scholarships",
    }

    try:
        from news_routes import _get_all_news

        initial_articles = _get_all_news()[:9]
    except Exception as exc:
        app.logger.warning("Unable to preload news cards: %s", exc)

    return render_template(
        "news.html",
        initial_articles=initial_articles,
        category_labels=category_labels,
    )

EXAM_UPDATES_DATA = [
    {"category": "engineering", "title": "JEE Main 2026 Session 1 Registration", "desc": "Application window open at jeemain.nta.nic.in. Eligibility: PCM in Class 12 with 75% (65% for SC/ST). Exam date: January 2026."},
    {"category": "engineering", "title": "MHT-CET 2026 Registration", "desc": "State-level PCM and PCB group registration open at cetcell.mahacet.org. Exam expected April–May 2026."},
    {"category": "engineering", "title": "JEE Advanced 2026 Eligibility", "desc": "Top 2.5 lakh JEE Main qualifiers eligible. Conducted by IIT Delhi. Registration opens post JEE Main result."},
    {"category": "engineering", "title": "GATE 2026 Notification", "desc": "Graduate Aptitude Test in Engineering for M.Tech admissions and PSU recruitment. 30 test papers across engineering disciplines."},
    {"category": "medical", "title": "NEET UG 2026 Information Bulletin", "desc": "Single entrance for MBBS, BDS, BAMS, BHMS. Registration at neet.nta.nic.in. Eligibility: 50% PCB in Class 12."},
    {"category": "medical", "title": "NEET PG 2026 Schedule", "desc": "Postgraduate medical entrance for MD/MS/PG Diploma. Conducted by NBE. Registration expected January 2026."},
    {"category": "law", "title": "CLAT 2026 Registration Open", "desc": "Common Law Admission Test for 24 National Law Universities. Online registration at consortiumofnlus.ac.in."},
    {"category": "law", "title": "LSAT India 2026", "desc": "Law School Admission Test for private law colleges. Multiple test windows available. Score valid for 1 year."},
    {"category": "management", "title": "CAT 2026 Registration", "desc": "Common Admission Test for IIMs and 1200+ B-schools. Conducted by IIM Calcutta. Application opens August 2026."},
    {"category": "management", "title": "MAT 2026 (May Session)", "desc": "Management Aptitude Test for MBA/PGDM admissions. CBT and PBT modes available. 600+ colleges accept MAT score."},
    {"category": "management", "title": "XAT 2026 Notification", "desc": "Xavier Aptitude Test for XLRI and 150+ B-schools. Conducted in January. Decision Making section unique to XAT."},
    {"category": "design", "title": "NID DAT 2026 Prelims", "desc": "National Institute of Design Design Aptitude Test for B.Des admissions. Paper-based studio test with practical assignments."},
    {"category": "design", "title": "UCEED 2026", "desc": "Undergraduate Common Entrance Exam for Design (IIT Bombay, IIT Delhi, IIT Guwahati, IIITDM Jabalpur). January exam."},
    {"category": "defense", "title": "NDA (I) 2026 Notification", "desc": "National Defence Academy exam for Army, Navy, Air Force after Class 12. Age: 16.5–19.5 years. UPSC conducts it twice a year."},
    {"category": "defense", "title": "CDS (I) 2026 Notification", "desc": "Combined Defence Services exam for IMA, INA, AFA, OTA. Eligibility: graduation. Conducted by UPSC in February."},
]


@app.route('/exam-updates')
def exam_updates():
    return render_template('exam-updates.html', exams=EXAM_UPDATES_DATA)

@app.route("/articles")
@app.route("/career-articles")
def articles():
    category = request.args.get("category", "all").strip()
    query = request.args.get("q", "").strip().lower()

    valid_categories = {item["value"] for item in CATEGORIES}
    if category not in valid_categories:
        category = "all"

    filtered_articles = ARTICLES
    if category != "all":
        filtered_articles = [
            article for article in filtered_articles if article["category"] == category
        ]
    if query:
        filtered_articles = [
            article
            for article in filtered_articles
            if query in article["title"].lower() or query in article["desc"].lower()
        ]

    list_articles = [
        {
            **article,
            "desc": build_article_teaser(article.get("desc", "")),
        }
        for article in filtered_articles
    ]

    return render_template(
        "articles.html",
        articles=list_articles,
        categories=CATEGORIES,
        active_category=category,
        query=query,
        total=len(filtered_articles),
    )


@app.route("/articles/<int:article_id>")
def article_detail(article_id):
    article = get_article_by_id(article_id)
    if article is None:
        return redirect(url_for("articles"))
    article_detail_data = {
        **article,
        "paragraphs": build_article_paragraphs(article.get("desc", "")),
    }
    return render_template("article_detail.html", article=article_detail_data)


@app.route("/api/articles")
def api_articles():
    category = request.args.get("category", "all").strip()
    query = request.args.get("q", "").strip().lower()

    valid_categories = {item["value"] for item in CATEGORIES}
    if category not in valid_categories:
        category = "all"

    result = ARTICLES
    if category != "all":
        result = [article for article in result if article["category"] == category]
    if query:
        result = [
            article
            for article in result
            if query in article["title"].lower() or query in article["desc"].lower()
        ]

    return jsonify({"count": len(result), "articles": result})


@app.route('/stories')
@app.route('/student-stories')
def student_stories():
    # Flask looks in the 'templates' folder by default
    return render_template('student-stories.html')


@app.route('/submit_story')
@app.route('/submit-story')
def submit_story():
    return render_template('submit_story.html')


# ── Shared notification email + JSON file helpers ─────────────────────────────
def _send_notification_email(subject, body, to_email=None):
    smtp_host     = get_env_value("OTP_SMTP_HOST", "SMTP_HOST")
    smtp_port_raw = get_env_value("OTP_SMTP_PORT", "SMTP_PORT", default="587")
    smtp_username = get_env_value("OTP_SMTP_USERNAME", "SMTP_USER")
    smtp_password = get_env_value("OTP_SMTP_PASSWORD", "SMTP_PASS")
    from_email    = get_env_value("OTP_FROM_EMAIL", "SMTP_FROM_EMAIL", default=smtp_username)
    admin_email   = get_env_value("ADMIN_EMAIL", default="vm2026.subscription@gmail.com")
    use_tls       = get_env_value("OTP_SMTP_USE_TLS", "SMTP_USE_TLS", default="1").lower() not in {"0", "false", "no"}
    if not smtp_host or not from_email:
        return False
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = from_email
    msg["To"]      = to_email or admin_email
    msg.set_content(body)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
        if use_tls:
            s.starttls()
        if smtp_username:
            s.login(smtp_username, smtp_password)
        s.send_message(msg)
    return True


_STORIES_FILE = os.path.join(os.path.dirname(__file__), 'data', 'stories.json')

def _load_stories():
    try:
        with open(_STORIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _save_stories(stories):
    os.makedirs(os.path.dirname(_STORIES_FILE), exist_ok=True)
    with open(_STORIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(stories, f, ensure_ascii=False, indent=2)

@app.route('/api/submit-story', methods=['POST'])
def api_submit_story():
    data = request.get_json(silent=True) or {}
    name  = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip()
    exam  = str(data.get('exam', '')).strip()
    story = str(data.get('story', '')).strip()

    if not name or not email or not exam or not story:
        return jsonify({'success': False, 'error': 'All fields are required.'}), 400
    if len(story) < 50:
        return jsonify({'success': False, 'error': 'Story must be at least 50 characters.'}), 400
    if len(story) > 2000:
        return jsonify({'success': False, 'error': 'Story must not exceed 2000 characters.'}), 400

    entry = {
        'id': int(datetime.utcnow().timestamp() * 1000),
        'name': name, 'email': email, 'exam': exam, 'story': story,
        'submitted_at': datetime.utcnow().isoformat() + 'Z',
        'status': 'pending',
    }
    try:
        stories = _load_stories()
        stories.append(entry)
        _save_stories(stories)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not save story: {e}'}), 500

    try:
        _send_notification_email(
            subject=f'New Student Story from {name}',
            body=f'Name: {name}\nEmail: {email}\nExam: {exam}\n\nStory:\n{story}'
        )
    except Exception:
        pass

    return jsonify({'success': True, 'message': 'Story submitted successfully!'}), 201


_FEEDBACK_FILE  = os.path.join(os.path.dirname(__file__), 'data', 'feedback.json')

def _append_json_file(filepath, entry):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = []
    data.append(entry)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        required_fields = ["u_name", "u_mobile", "u_email", "u_designation", "u_feedback"]
        missing_fields = [f for f in required_fields if not request.form.get(f, "").strip()]
        if missing_fields:
            flash("Please fill all required fields before submitting.", "error")
            return render_template("feedback.html")

        entry = {
            'submitted_at': datetime.utcnow().isoformat() + 'Z',
            'name':        request.form.get('u_name', '').strip(),
            'mobile':      request.form.get('u_mobile', '').strip(),
            'email':       request.form.get('u_email', '').strip(),
            'designation': request.form.get('u_designation', '').strip(),
            'feedback':    request.form.get('u_feedback', '').strip(),
        }
        try:
            _append_json_file(_FEEDBACK_FILE, entry)
        except Exception:
            pass
        try:
            _send_notification_email(
                subject=f"New Feedback from {entry['name']}",
                body=f"Name: {entry['name']}\nMobile: {entry['mobile']}\nEmail: {entry['email']}\nDesignation: {entry['designation']}\n\nFeedback:\n{entry['feedback']}"
            )
        except Exception:
            pass

        flash("Feedback submitted successfully. Thank you!", "success")
        return redirect(url_for("feedback"))

    return render_template("feedback.html")


def _clean_html_text(raw_html):
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\{[%#].*?[%#]\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\{\{.*?\}\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"[.#][a-zA-Z0-9_-]+\s*\{[^{}]{0,300}\}", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sanitize_snippet(value, max_len=280):
    text = str(value or "")
    text = re.sub(r"\{[%#].*?[%#]\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\{\{.*?\}\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"[.#][a-zA-Z0-9_-]+\s*\{[^{}]{0,300}\}", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,-|")
    return text[:max_len]


def _chatbot_tokens(query):
    parts = re.findall(r"[a-zA-Z0-9]{3,}", (query or "").lower())
    return [token for token in parts if token not in CHATBOT_STOPWORDS][:8]


def _chatbot_score(text, tokens):
    if not text or not tokens:
        return 0

    lower_text = text.lower()
    score = 0
    for token in tokens:
        occurrences = lower_text.count(token)
        if occurrences:
            score += min(occurrences, 6)
    return score


def _chatbot_template_route(filename):
    if filename == "index.html":
        return "/"
    if filename.endswith(".html"):
        return "/" + filename[:-5]
    return "/" + filename


def get_chatbot_template_corpus():
    global CHATBOT_TEMPLATE_CACHE

    if CHATBOT_TEMPLATE_CACHE is not None:
        return CHATBOT_TEMPLATE_CACHE

    templates_dir = os.path.join(app.root_path, "templates")
    corpus = []

    try:
        for filename in sorted(os.listdir(templates_dir)):
            if not filename.endswith(".html"):
                continue
            if filename.startswith("_"):
                continue
            if filename in {"base.html", "auth.html", "chatbot.html"}:
                continue

            file_path = os.path.join(templates_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                    raw_html = handle.read()
            except OSError:
                continue

            cleaned = _clean_html_text(raw_html)
            if len(cleaned) < 120:
                continue

            title = filename.replace(".html", "").replace("-", " ").replace("_", " ").title()
            corpus.append(
                {
                    "source": _chatbot_template_route(filename),
                    "title": title,
                    "text": cleaned[:5000],
                }
            )
    except OSError:
        CHATBOT_TEMPLATE_CACHE = []
        return CHATBOT_TEMPLATE_CACHE

    CHATBOT_TEMPLATE_CACHE = corpus
    return CHATBOT_TEMPLATE_CACHE


def _collect_entrance_exam_matches(tokens, limit=4):
    if not tokens:
        return []

    connection_url = get_postgres_connection_url()
    if not connection_url or not connect:
        return []

    max_tokens = tokens[:4]
    conditions = " OR ".join(["LOWER(payload::text) LIKE %s"] * len(max_tokens))
    params = [f"%{token}%" for token in max_tokens]

    sql = (
        "SELECT payload FROM entrance_exams "
        f"WHERE {conditions} "
        "LIMIT %s"
    )
    params.append(limit)

    matches = []
    try:
        import psycopg2.extras
        with connect(connection_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for row in rows:
                    payload = row.get("payload") if isinstance(row, dict) else None
                    if not isinstance(payload, dict):
                        continue
                    title = (
                        payload.get("exam_name")
                        or payload.get("name")
                        or payload.get("title")
                        or "Entrance Exam"
                    )
                    snippet = (
                        payload.get("description")
                        or payload.get("overview")
                        or payload.get("details")
                        or payload.get("eligibility")
                        or "Exam details available on the entrance exams section."
                    )
                    snippet = _sanitize_snippet(snippet)
                    matches.append(
                        {
                            "title": str(title).strip(),
                            "snippet": snippet,
                            "source": "/entrance-exams",
                            "score": _chatbot_score(f"{title} {snippet}", tokens) + 2,
                            "kind": "data",
                        }
                    )
    except Exception as exc:
        app.logger.warning("Chatbot entrance exam lookup failed: %s", exc)

    return matches


def _build_chatbot_sources(results):
    seen_sources = set()
    sources = []
    for item in results:
        source = str(item.get("source") or "").strip() or "/"
        if source in seen_sources:
            continue
        seen_sources.add(source)
        sources.append(source)
    return sources


def _build_context_lines(results, limit=5):
    lines = []
    for index, item in enumerate(results[:limit], start=1):
        title = str(item.get("title") or "Result").strip()
        snippet = _sanitize_snippet(item.get("snippet") or "", max_len=280)
        source = str(item.get("source") or "").strip() or "/"
        lines.append(f"{index}. {title}: {snippet} (Source: {source})")
    return lines


def _detect_info_topic(question):
    text = (question or "").lower()
    scores = {topic: 0 for topic in CHATBOT_TOPIC_KEYWORDS}
    for topic, words in CHATBOT_TOPIC_KEYWORDS.items():
        for word in words:
            if word in text:
                scores[topic] += 1

    best_topic = max(scores, key=scores.get)
    if scores[best_topic] <= 0:
        return "general"
    return best_topic


def _topic_relevance_bonus(item, topic):
    if topic == "general":
        return 0

    bonus = 0
    source = str(item.get("source") or "").strip().lower()
    text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()

    for hint in CHATBOT_TOPIC_SOURCE_HINTS.get(topic, set()):
        if source.startswith(hint):
            bonus += 4
            break

    for keyword in CHATBOT_TOPIC_KEYWORDS.get(topic, set()):
        if keyword in text:
            bonus += 1

    return bonus


def _get_groq_response(question, context_lines=None, language="en", topic="general"):
    if not GROQ_API_KEY:
        return None

    context_lines = context_lines or []

    if language == "hi":
        style_line = "Answer in simple Hindi (Devanagari), short and practical."
    elif language == "mr":
        style_line = "Answer in simple Marathi (Devanagari), short and practical."
    else:
        style_line = "Answer in simple English, short and practical."

    system_prompt = (
        "You are an education assistant and friendly conversational chatbot for Vidyarthi Mitra. "
        "Answer using your own knowledge and the user message only. Do not browse the internet or rely on retrieved context. "
        "If the user asks about Vidyarthi Mitra, explain it as an education and career guidance platform. "
        "Return only bullet points, no paragraphs. "
        "Use this exact format: "
        "- Summary: <one line> "
        "- Key Points: "
        "  - <point 1> "
        "  - <point 2> "
        "  - <point 3> "
        "- Next Step: "
        "  - <one actionable step>. "
        "Do not invent facts. Keep the reply concise. "
        f"{style_line}"
    )
    user_prompt = (
        "User question:\n"
        f"{question}\n\n"
        f"Target topic: {topic}\n\n"
        "No external context provided."
        f"{'\n'.join(context_lines)}"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }

    request = Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = response.read()
            result = json.loads(body.decode("utf-8"))
            choices = result.get("choices") if isinstance(result, dict) else None
            if not isinstance(choices, list) or not choices:
                return None
            message = choices[0].get("message", {})
            content = str(message.get("content") or "").strip()
            return content or None
    except Exception as exc:
        app.logger.warning("Groq API call failed: %s", exc)
        return None


def _detect_chat_intent(question):
    text = (question or "").strip().lower()
    if not text:
        return "empty"

    if text in CHATBOT_GREETINGS:
        return "greeting"

    if text in CHATBOT_SMALLTALK or any(phrase in text for phrase in CHATBOT_SMALLTALK):
        return "smalltalk"

    if text in CHATBOT_THANKS or any(phrase in text for phrase in CHATBOT_THANKS):
        return "thanks"

    if "who are you" in text or "tum kaun" in text or "tu kon" in text:
        return "intro"

    return "info"


def _smalltalk_reply(intent, language="en"):
    if language == "hi":
        replies = {
            "greeting": "नमस्ते! मैं Vidyarthi Mitra का AI assistant हूं. आप exam, college, course, admission या career के बारे में पूछ सकते हैं.",
            "smalltalk": "मैं ठीक हूं! आप कैसे हो? अगर चाहो तो exam, course या college के बारे में पूछ सकते हो.",
            "thanks": "खुशी हुई मदद करके. अगर चाहें तो मैं आपको exam dates, eligibility या college options भी बता सकता हूं.",
            "intro": "मैं Vidyarthi Mitra chatbot हूं. मैं education related जानकारी और हमारी website के content के आधार पर guidance देता हूं.",
            "empty": "नमस्ते! आप अपना सवाल लिखें, मैं मदद करता हूं.",
        }
    elif language == "mr":
        replies = {
            "greeting": "नमस्कार! मी Vidyarthi Mitra चा AI assistant आहे. तुम्ही exam, college, course, admission किंवा career बद्दल विचारू शकता.",
            "smalltalk": "मी ठीक आहे! तुम्ही कसे आहात? हवे असल्यास exam, course किंवा college बद्दल विचारू शकता.",
            "thanks": "मदत करून आनंद झाला. हवे असल्यास मी exam dates, eligibility किंवा college options सांगू शकतो.",
            "intro": "मी Vidyarthi Mitra chatbot आहे. मी education संदर्भातील माहिती आणि website content वर आधारित guidance देतो.",
            "empty": "नमस्कार! तुमचा प्रश्न लिहा, मी मदत करतो.",
        }
    else:
        replies = {
            "greeting": "Hi! I am the Vidyarthi Mitra AI assistant. You can ask me about exams, colleges, courses, admissions, or careers.",
            "smalltalk": "I am doing well! Ask me about exams, colleges, courses, admissions, or careers.",
            "thanks": "Glad to help. If you want, I can also share exam dates, eligibility, or college options.",
            "intro": "I am the Vidyarthi Mitra chatbot. I help with education guidance using our website information.",
            "empty": "Hi! Ask your education question and I will help.",
        }

    return replies.get(intent, replies["greeting"])


def _add_internet_result(results, title, snippet, source, tokens, topic):
    title = _sanitize_snippet(title, max_len=120)
    snippet = _sanitize_snippet(snippet, max_len=320)
    source = str(source or "").strip()
    if not title or not snippet or not source:
        return

    combined = f"{title} {snippet}"
    base_score = _chatbot_score(combined, tokens)
    topic_bonus = 0
    if topic != "general":
        for keyword in CHATBOT_TOPIC_KEYWORDS.get(topic, set()):
            if keyword in combined.lower():
                topic_bonus += 1

    results.append(
        {
            "title": title,
            "snippet": snippet,
            "source": source,
            "score": base_score + topic_bonus,
            "kind": "internet",
        }
    )


def _collect_duckduckgo_context(question, tokens, topic):
    params = {
        "q": question,
        "format": "json",
        "no_redirect": "1",
        "no_html": "1",
        "skip_disambig": "1",
    }
    url = f"{CHATBOT_DDG_API_URL}?{urlencode(params)}"
    payload = fetch_remote_json(url)
    if not isinstance(payload, dict):
        return []

    results = []
    abstract_text = payload.get("AbstractText")
    abstract_url = payload.get("AbstractURL")
    heading = payload.get("Heading") or "Internet result"
    if abstract_text and abstract_url:
        _add_internet_result(results, heading, abstract_text, abstract_url, tokens, topic)

    related = payload.get("RelatedTopics")
    if isinstance(related, list):
        for item in related[:12]:
            if isinstance(item, dict) and isinstance(item.get("Topics"), list):
                for nested in item.get("Topics", [])[:6]:
                    if not isinstance(nested, dict):
                        continue
                    text = nested.get("Text") or ""
                    first_url = nested.get("FirstURL") or ""
                    if text and first_url:
                        label = text.split(" - ", 1)[0]
                        _add_internet_result(results, label, text, first_url, tokens, topic)
            elif isinstance(item, dict):
                text = item.get("Text") or ""
                first_url = item.get("FirstURL") or ""
                if text and first_url:
                    label = text.split(" - ", 1)[0]
                    _add_internet_result(results, label, text, first_url, tokens, topic)

    return results


def _collect_wikipedia_context(question, tokens, topic):
    params = {
        "action": "query",
        "list": "search",
        "srsearch": question,
        "utf8": "1",
        "format": "json",
        "srlimit": "6",
    }
    search_url = f"{CHATBOT_WIKI_SEARCH_URL}?{urlencode(params)}"
    payload = fetch_remote_json(search_url)
    if not isinstance(payload, dict):
        return []

    search_items = (((payload.get("query") or {}).get("search")) or [])
    if not isinstance(search_items, list):
        return []

    results = []
    for item in search_items[:6]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        summary_url = f"{CHATBOT_WIKI_SUMMARY_URL}{quote(title.replace(' ', '_'))}"
        summary_payload = fetch_remote_json(summary_url)
        if isinstance(summary_payload, dict):
            snippet = summary_payload.get("extract") or item.get("snippet") or ""
            source = summary_payload.get("content_urls", {}).get("desktop", {}).get("page") or f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            _add_internet_result(results, title, snippet, source, tokens, topic)
        else:
            fallback_snippet = re.sub(r"<[^>]+>", " ", str(item.get("snippet") or ""))
            source = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            _add_internet_result(results, title, fallback_snippet, source, tokens, topic)

    return results


def _collect_internet_context(question, tokens, topic, limit=8):
    results = []
    results.extend(_collect_duckduckgo_context(question, tokens, topic))
    results.extend(_collect_wikipedia_context(question, tokens, topic))

    deduped = []
    seen = set()
    for item in results:
        key = (item.get("title"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(key=lambda item: item.get("score", 0), reverse=True)
    return deduped[:limit]


def build_chatbot_answer(question, language="en"):
    intent = _detect_chat_intent(question)
    if intent in {"empty", "greeting", "smalltalk", "thanks", "intro"}:
        return _smalltalk_reply(intent, language=language), []

    topic = _detect_info_topic(question)
    groq_answer = _get_groq_response(question, [], language=language, topic=topic)

    if groq_answer:
        return groq_answer, []

    lines = [
        "- Summary: I can help with education, careers, admissions, exams, colleges, and Vidyarthi Mitra.",
        "- Key Points:",
    ]
    lines.append("  - Ask me about courses, entrance exams, colleges, admissions, or career options.")
    lines.append("  - I can also explain Vidyarthi Mitra and help you explore options.")
    lines.append("- Next Step:")
    lines.append("  - Tell me the exact exam, course, college, or city you want to know about.")
    answer = "\n".join(lines)
    return answer, []


@app.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")


@app.route("/api/chatbot/query", methods=["POST"])
def api_chatbot_query():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    language = str(payload.get("language") or "en").strip().lower()
    if language not in {"en", "hi", "mr"}:
        language = "en"

    if len(message) < 2:
        return jsonify({"error": "Message is required."}), 400

    answer, sources = build_chatbot_answer(message, language=language)
    return jsonify(
        {
            "answer": answer,
            "sources": sources,
            "provider": "groq" if GROQ_API_KEY else "local-retrieval",
        }
    )


_GUIDEME_FILE = os.path.join(os.path.dirname(__file__), 'data', 'guideme_requests.json')

@app.route("/guideme", methods=["GET", "POST"])
@app.route("/guide-me", methods=["GET", "POST"])
def guide_me():
    if request.method == "POST":
        required_fields = ["full_name", "whatsapp", "email", "address", "requirement_type"]
        missing_fields = [f for f in required_fields if not request.form.get(f, "").strip()]
        if missing_fields:
            flash("Please complete all required Guide Me form fields.", "error")
            return render_template("GuideMe1.html")

        entry = {
            'submitted_at':    datetime.utcnow().isoformat() + 'Z',
            'name':            request.form.get('full_name', '').strip(),
            'whatsapp':        request.form.get('whatsapp', '').strip(),
            'email':           request.form.get('email', '').strip(),
            'address':         request.form.get('address', '').strip(),
            'requirement':     request.form.get('requirement_type', '').strip(),
            'details':         request.form.get('details', '').strip(),
        }
        try:
            _append_json_file(_GUIDEME_FILE, entry)
        except Exception:
            pass
        try:
            _send_notification_email(
                subject=f"New Guide Me Request from {entry['name']}",
                body=f"Name: {entry['name']}\nWhatsApp: {entry['whatsapp']}\nEmail: {entry['email']}\nAddress: {entry['address']}\nRequirement: {entry['requirement']}\n\nDetails:\n{entry['details']}"
            )
        except Exception:
            pass

        flash("Guide Me form submitted successfully.", "success")
        return redirect(url_for("guide_me"))

    return render_template("GuideMe1.html")

@app.route('/refund-policy')
def refund_policy():
    return render_template('refund.html')

@app.route('/terms')
@app.route('/terms-and-conditions')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
@app.route('/privacy-policy')
def privacy():
    return render_template('privacy.html')

@app.route('/about')
@app.route('/about-us')
def about():
    return render_template('about.html')

@app.route("/joinus")
@app.route("/join-us")
def join_us():
    return render_template("joinus VM.html")

@app.route("/contact")
@app.route("/contact-us")
def contact():
    return render_template("contact-us.html")

_CONTACT_FILE = os.path.join(os.path.dirname(__file__), 'data', 'contact_messages.json')

@app.route('/send-message', methods=['POST'])
def send_message():
    data    = request.get_json(silent=True) or {}
    name    = str(data.get('name', '')).strip()
    phone   = str(data.get('phone', '')).strip()
    email   = str(data.get('email', '')).strip()
    subject = str(data.get('subject', '')).strip()
    message = str(data.get('message', '')).strip()

    if not name or not email or not message:
        return jsonify({'success': False, 'error': 'Name, email, and message are required.'}), 400

    entry = {
        'submitted_at': datetime.utcnow().isoformat() + 'Z',
        'name': name, 'phone': phone, 'email': email,
        'subject': subject, 'message': message,
    }
    try:
        _append_json_file(_CONTACT_FILE, entry)
    except Exception:
        pass

    try:
        _send_notification_email(
            subject=f"[Contact] {subject or 'New message'} from {name}",
            body=f"Name: {name}\nPhone: {phone}\nEmail: {email}\nSubject: {subject}\n\nMessage:\n{message}",
            to_email=email  # also CC the sender's email as reply-to reference
        )
    except Exception:
        pass

    return jsonify({'success': True, 'message': 'Your message has been received. We will get back to you shortly.'}), 200


_SUBSCRIBERS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'subscribers.json')

@app.route('/subscribe', methods=['POST'])
def subscribe():
    name  = str(request.form.get('name',  '') or request.get_json(silent=True, force=True) and request.get_json(silent=True, force=True).get('name', '') or '').strip()
    email = str(request.form.get('email', '') or '').strip()
    if not email:
        data = request.get_json(silent=True) or {}
        name  = str(data.get('name',  name)).strip()
        email = str(data.get('email', '')).strip()
    if not email:
        return jsonify({'success': False, 'error': 'Email is required.'}), 400
    entry = {
        'subscribed_at': datetime.utcnow().isoformat() + 'Z',
        'name': name,
        'email': email,
    }
    try:
        _append_json_file(_SUBSCRIBERS_FILE, entry)
    except Exception:
        pass
    try:
        _send_notification_email(
            subject=f"[Subscribe] New subscriber: {email}",
            body=f"Name: {name}\nEmail: {email}",
        )
    except Exception:
        pass
    if request.is_json:
        return jsonify({'success': True, 'message': 'Thank you for subscribing!'})
    from flask import flash, redirect
    flash('Thank you for subscribing!', 'success')
    return redirect(request.referrer or '/')


_BLOGS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'blogs.json')

@app.route('/api/blogs')
def api_blogs():
    category = request.args.get('category', '').strip().lower()
    search = request.args.get('search', '').strip().lower()
    try:
        with open(_BLOGS_FILE, 'r', encoding='utf-8') as f:
            blogs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        blogs = []
    if category and category != 'all':
        blogs = [b for b in blogs if b.get('category', '').lower() == category]
    if search:
        blogs = [
            b for b in blogs
            if search in b.get('title', '').lower()
            or search in b.get('summary', '').lower()
            or search in b.get('full', '').lower()
        ]
    return jsonify(blogs)


_GOVT_JOBS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'govt_jobs.json')

GOVT_JOB_CATEGORIES = [
    {"value": "ssc",      "label": "SSC",      "icon": "fa-solid fa-file-alt"},
    {"value": "banking",  "label": "Banking",  "icon": "fa-solid fa-building-columns"},
    {"value": "railway",  "label": "Railway",  "icon": "fa-solid fa-train"},
    {"value": "defence",  "label": "Defence",  "icon": "fa-solid fa-shield-halved"},
    {"value": "teaching", "label": "Teaching", "icon": "fa-solid fa-chalkboard-teacher"},
    {"value": "psc",      "label": "PSC/UPSC", "icon": "fa-solid fa-landmark"},
    {"value": "police",   "label": "Police",   "icon": "fa-solid fa-shield"},
    {"value": "others",   "label": "Others",   "icon": "fa-solid fa-briefcase"},
]

@app.route('/govt-jobs')
def govt_jobs():
    try:
        with open(_GOVT_JOBS_FILE, 'r', encoding='utf-8') as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = []
    states = sorted({j['state'] for j in jobs})
    categories = []
    for cat in GOVT_JOB_CATEGORIES:
        count = sum(1 for j in jobs if j['category'] == cat['value'])
        if count > 0:
            categories.append({**cat, 'count': count})
    return render_template('govt-jobs.html', jobs=jobs, states=states, categories=categories)


@app.route('/govt-jobs/<int:job_id>')
def govt_job_detail(job_id):
    try:
        with open(_GOVT_JOBS_FILE, 'r', encoding='utf-8') as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = []
    job = next((j for j in jobs if j['id'] == job_id), None)
    if job is None:
        return redirect(url_for('govt_jobs'))
    related = [j for j in jobs if j['category'] == job['category'] and j['id'] != job_id][:3]
    return render_template('govt-job-detail.html', job=job, related=related)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm_password:
            flash("Please fill in all registration fields.", "error")
            return render_template("auth.html", mode="register", page_title="Register")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("auth.html", mode="register", page_title="Register")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("auth.html", mode="register", page_title="Register")

        with get_auth_db_connection() as connection:
            existing_user = connection.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            ).fetchone()

            if existing_user is not None:
                flash("An account with this email already exists.", "error")
                return render_template("auth.html", mode="register", page_title="Register")

            connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
            connection.commit()

        session["auth_user"] = {"name": name, "email": email}
        session.pop("pending_otp", None)
        return redirect(url_for("index"))

    return render_template("auth.html", mode="register", page_title="Register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.", "error")
            return render_template("auth.html", mode="login", page_title="Login")

        with get_auth_db_connection() as connection:
            user = connection.execute(
                "SELECT name, email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("auth.html", mode="login", page_title="Login")

        provider = get_otp_provider()
        otp_sent = False

        if provider == "twilio_verify" and get_twilio_verify_config() is not None:
            try:
                otp_sent = send_twilio_verify_code(user["email"])
            except Exception as exc:
                app.logger.warning("Twilio Verify delivery failed: %s", exc)
                otp_sent = False

            if otp_sent:
                session["pending_otp"] = {
                    "name": user["name"],
                    "email": user["email"],
                    "provider": "twilio_verify",
                    "expires_at": int(time.time()) + 600,
                    "attempts": 0,
                }
                session["otp_delivery_mode"] = "email"
                session.pop("pending_otp_preview", None)
                flash("OTP sent to your email. Enter it on the next screen.", "success")
                return redirect(url_for("verify_otp"))

        otp_code = store_pending_login_otp({"name": user["name"], "email": user["email"]})
        try:
            otp_sent = send_login_otp_email(user["email"], user["name"], otp_code)
        except Exception as exc:
            app.logger.warning("OTP email delivery failed: %s", exc)

        session["otp_delivery_mode"] = "email" if otp_sent else "screen"
        if not otp_sent:
            session["pending_otp_preview"] = otp_code
        else:
            session.pop("pending_otp_preview", None)
        flash(
            "OTP sent to your email. Enter it on the next screen." if otp_sent else "OTP is ready. Enter the code shown on the next screen.",
            "success",
        )
        return redirect(url_for("verify_otp"))

    return render_template("auth.html", mode="login", page_title="Login")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    pending_otp = get_pending_login_otp()
    if pending_otp is None:
        flash("Please login again to request a fresh OTP.", "error")
        return redirect(url_for("login"))

    otp_preview = None
    if session.get("otp_delivery_mode") == "screen":
        otp_preview = session.get("pending_otp_preview")

    if request.method == "POST":
        otp_code = request.form.get("otp_code", "").strip()

        if not re.fullmatch(r"\d{6}", otp_code):
            flash("Enter the 6-digit OTP.", "error")
            return render_template(
                "auth.html",
                mode="otp",
                page_title="Verify OTP",
                otp_email=pending_otp["email"],
                otp_preview=otp_preview,
                otp_expires_at=pending_otp["expires_at"],
            )

        if pending_otp.get("attempts", 0) >= 5:
            session.pop("pending_otp", None)
            session.pop("otp_delivery_mode", None)
            session.pop("pending_otp_preview", None)
            flash("Too many invalid attempts. Please login again.", "error")
            return redirect(url_for("login"))

        if pending_otp.get("provider") == "twilio_verify":
            try:
                if verify_twilio_code(pending_otp["email"], otp_code):
                    session["auth_user"] = {
                        "name": pending_otp["name"],
                        "email": pending_otp["email"],
                    }
                    session.pop("pending_otp", None)
                    session.pop("otp_delivery_mode", None)
                    session.pop("pending_otp_preview", None)
                    flash("Login successful.", "success")
                    return redirect(url_for("index"))
            except Exception as exc:
                app.logger.warning("Twilio Verify validation failed: %s", exc)

        elif check_password_hash(pending_otp["otp_hash"], otp_code):
            session["auth_user"] = {
                "name": pending_otp["name"],
                "email": pending_otp["email"],
            }
            session.pop("pending_otp", None)
            session.pop("otp_delivery_mode", None)
            session.pop("pending_otp_preview", None)
            flash("Login successful.", "success")
            return redirect(url_for("index"))

        pending_otp["attempts"] = pending_otp.get("attempts", 0) + 1
        session["pending_otp"] = pending_otp
        flash("Invalid OTP. Please try again.", "error")

    return render_template(
        "auth.html",
        mode="otp",
        page_title="Verify OTP",
        otp_email=pending_otp["email"],
        otp_preview=otp_preview,
        otp_expires_at=pending_otp["expires_at"],
    )


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    pending_otp = get_pending_login_otp()
    if pending_otp is None:
        flash("Please login again to request a new OTP.", "error")
        return redirect(url_for("login"))

    otp_sent = False
    if pending_otp.get("provider") == "twilio_verify" and get_twilio_verify_config() is not None:
        try:
            otp_sent = send_twilio_verify_code(pending_otp["email"])
        except Exception as exc:
            app.logger.warning("Twilio Verify resend failed: %s", exc)
            otp_sent = False

        if otp_sent:
            session["pending_otp"] = {
                "name": pending_otp["name"],
                "email": pending_otp["email"],
                "provider": "twilio_verify",
                "expires_at": int(time.time()) + 600,
                "attempts": 0,
            }
            session["otp_delivery_mode"] = "email"
            session.pop("pending_otp_preview", None)
            flash("A new OTP has been sent to your email.", "success")
            return redirect(url_for("verify_otp"))

    otp_code = store_pending_login_otp({"name": pending_otp["name"], "email": pending_otp["email"]})
    try:
        otp_sent = send_login_otp_email(pending_otp["email"], pending_otp["name"], otp_code)
    except Exception as exc:
        app.logger.warning("OTP resend failed: %s", exc)

    session["otp_delivery_mode"] = "email" if otp_sent else "screen"
    if not otp_sent:
        session["pending_otp_preview"] = otp_code
    else:
        session.pop("pending_otp_preview", None)

    flash(
        "A new OTP has been sent to your email." if otp_sent else f"New OTP generated: {otp_code}",
        "success",
    )
    return redirect(url_for("verify_otp"))


@app.route("/logout")
def logout():
    session.pop("auth_user", None)
    session.pop("pending_otp", None)
    session.pop("otp_delivery_mode", None)
    session.pop("pending_otp_preview", None)
    return redirect(url_for("index"))


@app.route("/excel-upload", methods=["GET", "POST"])
def excel_upload():
    allowed_tables = {item["value"] for item in UPLOAD_TARGET_TABLES}
    default_table = os.getenv("SUPABASE_EXCEL_TABLE", "universities").strip() or "universities"
    if default_table not in allowed_tables:
        default_table = "universities"

    supabase_client = get_supabase_client()
    postgres_connection_url = get_postgres_connection_url()
    configured = supabase_client is not None or bool(postgres_connection_url)
    connection_mode = "postgres-url" if postgres_connection_url else "supabase-api"
    selected_table = default_table

    if request.method == "POST":
        selected_table = request.form.get("target_table", default_table).strip()
        if selected_table not in allowed_tables:
            flash("Please choose a valid target table.", "error")
            return render_template(
                "excel_upload.html",
                configured=configured,
                table_name=default_table,
                selected_table=default_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        if not configured:
            flash(
                "Supabase is not configured. Set SUPABASE_POSTGRES_URL (or DATABASE_URL), or set SUPABASE_URL with SUPABASE_SERVICE_ROLE_KEY.",
                "error",
            )
            return render_template(
                "excel_upload.html",
                configured=False,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        uploaded_file = request.files.get("excel_file")
        if uploaded_file is None or not uploaded_file.filename:
            flash("Please choose an Excel file to upload.", "error")
            return render_template(
                "excel_upload.html",
                configured=True,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        if not uploaded_file.filename.lower().endswith((".xlsx", ".xls")):
            flash("Invalid file type. Please upload an .xlsx or .xls file.", "error")
            return render_template(
                "excel_upload.html",
                configured=True,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        try:
            records = convert_excel_to_records(uploaded_file)
            if postgres_connection_url:
                ensure_upload_table_exists(postgres_connection_url, selected_table)
                inserted_rows = insert_records_via_postgres(postgres_connection_url, selected_table, records)
            else:
                inserted_rows = insert_records_in_batches(supabase_client, selected_table, records)
        except Exception as exc:
            flash(f"Upload failed: {exc}", "error")
            return render_template(
                "excel_upload.html",
                configured=True,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        flash(f"Upload successful. Inserted {inserted_rows} row(s) into {selected_table}.", "success")
        return redirect(url_for("excel_upload"))

    return render_template(
        "excel_upload.html",
        configured=configured,
        table_name=selected_table,
        selected_table=selected_table,
        upload_targets=UPLOAD_TARGET_TABLES,
        connection_mode=connection_mode,
    )


@app.route('/robots.txt')
def robots_txt():
    from flask import Response
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        "Disallow: /excel-upload\n"
        "Disallow: /api/vmadmin/\n"
        f"Sitemap: https://vidyarthimitra.org/sitemap.xml\n"
    )
    return Response(content, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    from flask import Response
    from datetime import date
    today = date.today().isoformat()
    base = "https://vidyarthimitra.org"
    static_pages = [
        ('/', '1.0', 'daily'),
        ('/colleges', '0.9', 'weekly'),
        ('/universities', '0.9', 'weekly'),
        ('/cutoffs', '0.9', 'daily'),
        ('/entrance-exams', '0.9', 'weekly'),
        ('/mock-exams', '0.8', 'weekly'),
        ('/exam-updates', '0.8', 'weekly'),
        ('/articles', '0.8', 'weekly'),
        ('/blogs', '0.8', 'weekly'),
        ('/news', '0.8', 'daily'),
        ('/courses', '0.8', 'weekly'),
        ('/guide-me', '0.7', 'monthly'),
        ('/contact', '0.6', 'monthly'),
        ('/about', '0.6', 'monthly'),
        ('/epaper', '0.7', 'daily'),
    ]
    urls = '\n'.join(
        f'  <url><loc>{base}{path}</loc><lastmod>{today}</lastmod>'
        f'<changefreq>{freq}</changefreq><priority>{pri}</priority></url>'
        for path, pri, freq in static_pages
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>'
    return Response(xml, mimetype='application/xml')


if __name__ == "__main__":
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host='0.0.0.0', debug=debug)
