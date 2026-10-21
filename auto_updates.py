"""Automatic live updates for Exam Updates + Govt Jobs.

Fetches fresh notifications from official-source-backed feeds (Google News
RSS queries targeting NTA/UPSC/SSC/Railway/Banking/Defence boards) and
persists them in Postgres so the site shows real-time items without
redeploys. A background thread in app.py re-syncs every 45 minutes;
admins can force a sync from the dashboard.

Design notes:
- Uses Google News RSS (no API key, reliable). Official Indian boards rarely
  publish stable RSS; their notifications surface via news wires within
  minutes, which Google News indexes. Source config is pluggable — direct
  official feeds can be added to *_SOURCES later.
- All fetch/parse work is fault-tolerant: any failing source is skipped and
  reported in status; page routes always fall back to curated JSON data.
"""

import hashlib
import json
import os
import re
import threading
import time
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

try:  # feedparser is in requirements; stdlib fallback below
    import feedparser as _feedparser
except Exception:  # pragma: no cover
    _feedparser = None

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_FETCH_TIMEOUT = 8
_MAX_PER_FEED = 12
_SYNC_INTERVAL_SECONDS = 45 * 60
_SYNC_FIRST_DELAY_SECONDS = 20
_KEEP_DAYS = 90
_TTL_SECONDS = 300  # page-route read cache

# ── Source config ────────────────────────────────────────────────────────────
# Exam updates: (category, Google News query). Category must match the
# values used by exam-updates.html filter dropdown.
EXAM_SOURCES = [
    ("engineering", "JEE Main registration"),
    ("engineering", "JEE Advanced notification"),
    ("engineering", "MHT CET registration"),
    ("engineering", "BITSAT notification"),
    ("medical", "NEET UG registration"),
    ("medical", "NEET PG notification"),
    ("law", "CLAT notification"),
    ("management", "CAT exam registration"),
    ("government", "UPSC notification"),
    ("government", "SSC CGL notification"),
    ("banking", "IBPS PO notification"),
    ("banking", "SBI PO notification"),
    ("research", "UGC NET notification"),
    ("research", "CSIR NET notification"),
    ("school", "CBSE date sheet"),
    ("school", "CBSE result declaration"),
    ("university", "CUET UG registration"),
]

# Govt jobs: (category, Google News query). Category matches
# GOVT_JOB_CATEGORIES in app.py.
JOB_SOURCES = [
    ("ssc", "SSC CGL notification"),
    ("ssc", "SSC CHSL notification"),
    ("ssc", "SSC MTS recruitment"),
    ("railway", "RRB NTPC notification"),
    ("railway", "RRB Group D recruitment"),
    ("banking", "IBPS PO recruitment"),
    ("banking", "SBI PO recruitment"),
    ("psc", "UPSC civil services notification"),
    ("psc", "UPSC CDS notification"),
    ("defence", "Indian Army rally recruitment"),
    ("defence", "AFCAT notification"),
    ("teaching", "CTET notification"),
    ("teaching", "KVS recruitment"),
    ("police", "state police recruitment notification"),
]

# ── Status (module-level, refreshed by sync) ─────────────────────────────────
_STATUS_LOCK = threading.Lock()
_STATUS = {
    "running": False,
    "last_run": None,          # ISO string
    "last_error": None,
    "exam_items": 0,
    "job_items": 0,
    "sources_ok": 0,
    "sources_failed": 0,
    "db_ok": False,
}

# ── Read cache for page routes ───────────────────────────────────────────────
_CACHE = {"exam": ([], 0.0), "job": ([], 0.0)}
_CACHE_LOCK = threading.Lock()

_SYNC_LOCK = threading.Lock()
_SYNC_THREAD_STARTED = False

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Org keyword → (organization, short_org, apply_url, category_hint)
_ORG_PATTERNS = [
    ("bihar public service", "BPSC", "BPSC", "https://bpsc.bih.nic.in", "psc"),
    ("bpsc", "BPSC", "BPSC", "https://bpsc.bih.nic.in", "psc"),
    ("dsssb", "DSSSB", "DSSSB", "https://dsssb.delhi.gov.in", "teaching"),
    ("navodaya vidyalaya", "Navodaya Vidyalaya Sangathan", "NVS", "https://nvs.gov.in", "teaching"),
    ("nvs", "Navodaya Vidyalaya Sangathan", "NVS", "https://nvs.gov.in", "teaching"),
    ("staff selection commission", "Staff Selection Commission", "SSC", "https://ssc.gov.in", "ssc"),
    ("ssc", "Staff Selection Commission", "SSC", "https://ssc.gov.in", "ssc"),
    ("union public service", "UPSC", "UPSC", "https://upsc.gov.in", "psc"),
    ("upsc", "UPSC", "UPSC", "https://upsc.gov.in", "psc"),
    ("railway recruitment board", "Railway Recruitment Board", "RRB", "https://www.rrbcdg.gov.in", "railway"),
    ("rrb", "Railway Recruitment Board", "RRB", "https://www.rrbcdg.gov.in", "railway"),
    ("indian railways", "Indian Railways", "RAIL", "https://indianrailways.gov.in", "railway"),
    ("institute of banking personnel", "IBPS", "IBPS", "https://www.ibps.in", "banking"),
    ("ibps", "IBPS", "IBPS", "https://www.ibps.in", "banking"),
    ("state bank of india", "State Bank of India", "SBI", "https://sbi.co.in", "banking"),
    ("sbi", "State Bank of India", "SBI", "https://sbi.co.in", "banking"),
    ("reserve bank", "Reserve Bank of India", "RBI", "https://rbi.org.in", "banking"),
    ("rbi", "Reserve Bank of India", "RBI", "https://rbi.org.in", "banking"),
    ("indian army", "Indian Army", "ARMY", "https://joinindianarmy.nic.in", "defence"),
    ("indian navy", "Indian Navy", "NAVY", "https://joinindiannavy.gov.in", "defence"),
    ("air force", "Indian Air Force", "IAF", "https://indianairforce.nic.in", "defence"),
    ("afcat", "Indian Air Force", "IAF", "https://indianairforce.nic.in", "defence"),
    ("central teacher eligibility", "CBSE (CTET)", "CTET", "https://ctet.nic.in", "teaching"),
    ("ctet", "CBSE (CTET)", "CTET", "https://ctet.nic.in", "teaching"),
    ("kendriya vidyalaya", "Kendriya Vidyalaya Sangathan", "KVS", "https://kvsangathan.nic.in", "teaching"),
    ("kvs", "Kendriya Vidyalaya Sangathan", "KVS", "https://kvsangathan.nic.in", "teaching"),
    ("delhi police", "Delhi Police", "DPOL", "https://delhipolice.gov.in", "police"),
    ("police", "State Police", "POL", "", "police"),
]

_STATES = [
    "maharashtra", "delhi", "uttar pradesh", "up", "bihar", "rajasthan",
    "madhya pradesh", "mp", "gujarat", "west bengal", "bengal", "karnataka",
    "tamil nadu", "telangana", "andhra pradesh", "kerala", "punjab",
    "haryana", "jharkhand", "odisha", "assam", "chhattisgarh", "uttarakhand",
    "himachal pradesh", "goa", "manipur", "meghalaya", "nagaland", "tripura",
    "arunachal pradesh", "mizoram", "sikkim", "jammu",
]


# ── DB helpers ───────────────────────────────────────────────────────────────

def _db_url():
    url = os.getenv("SUPABASE_POSTGRES_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
    if url and "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _connect():
    import psycopg2
    return psycopg2.connect(_db_url())


def _ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_updates (
                id serial PRIMARY KEY,
                uid text NOT NULL UNIQUE,
                kind text NOT NULL,
                category text,
                title text NOT NULL,
                description text,
                link text,
                source text,
                payload jsonb,
                published_at timestamptz,
                fetched_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS auto_updates_kind_idx "
            "ON auto_updates (kind, published_at DESC NULLS LAST)"
        )
    conn.commit()


# ── Fetch + parse ────────────────────────────────────────────────────────────

def _clean_text(raw, limit=280):
    """Strip HTML tags/entities and collapse whitespace."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = (
        text.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _parse_pubdate(raw):
    """RFC822 / ISO pubDate → datetime (naive, UTC-ish)."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt.replace(tzinfo=None)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _fetch_feed(query, timeout=_FETCH_TIMEOUT):
    """Fetch one Google News RSS query → list of {title, link, desc, pub_dt, source}."""
    url = GOOGLE_NEWS_RSS.format(q=quote_plus(query))
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    items = []

    def _add(title, link, desc, pub, source):
        title = _clean_text(title, 200)
        if not title:
            return
        # Google News appends " - Source Name"; strip it for display.
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
        items.append({
            "title": title,
            "link": (link or "").strip(),
            "desc": _clean_text(desc),
            "pub_dt": _parse_pubdate(pub),
            "source": (source or "").strip(),
        })

    if _feedparser is not None:
        data = _feedparser.parse(url)
        for entry in data.entries[:_MAX_PER_FEED]:
            source = ""
            if getattr(entry, "source", None) and getattr(entry.source, "title", None):
                source = entry.source.title
            _add(
                entry.get("title", ""),
                entry.get("link", ""),
                entry.get("summary", entry.get("description", "")),
                entry.get("published", entry.get("updated", "")),
                source,
            )
        return items

    # Stdlib fallback (RSS 2.0 as served by Google News)
    with urlopen(req, timeout=timeout) as resp:
        content = resp.read()
    root = ET.fromstring(content)
    for node in root.findall(".//item")[:_MAX_PER_FEED]:
        src_el = node.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        _add(
            node.findtext("title", default=""),
            node.findtext("link", default=""),
            node.findtext("description", default=""),
            node.findtext("pubDate", default=""),
            source,
        )
    return items


# ── Heuristics for structured job fields ─────────────────────────────────────

def _norm_title(title):
    t = re.sub(r"[^a-z0-9]+", " ", (title or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def _uid(kind, title):
    return hashlib.sha1((kind + "|" + _norm_title(title)).encode("utf-8")).hexdigest()


def _detect_org(text):
    low = (text or "").lower()
    for needle, org, short, site, cat in _ORG_PATTERNS:
        if needle in low:
            return org, short, site, cat
    return None, None, None, None


def _extract_last_date(text):
    """Best-effort last-date extraction → 'YYYY-MM-DD' or ''."""
    if not text:
        return ""
    low = text.lower()
    # dd/mm/yyyy or dd-mm-yyyy or dd.mm.yyyy
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", low)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 2000 if y < 100 else 0
        if 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                pass
    # dd Month yyyy  |  Month dd, yyyy
    m = re.search(r"\b(\d{1,2})\s+([a-z]{3,9})\.?,?\s+(\d{4})\b", low)
    if m and m.group(2) in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat()
        except ValueError:
            pass
    m = re.search(r"\b([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", low)
    if m and m.group(1) in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2))).isoformat()
        except ValueError:
            pass
    return ""


def _extract_vacancy(text):
    if not text:
        return 0
    m = re.search(r"(\d[\d,]{1,7})\s*(?:posts?|vacanc(?:y|ies))", text, re.I)
    if not m:
        m = re.search(r"(?:for|of|total|has)\s+(\d[\d,]{2,8})\s+posts?", text, re.I)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return 0
    return 0


def _detect_state(text):
    low = (text or "").lower()
    for st in _STATES:
        if re.search(r"\b" + re.escape(st) + r"\b", low):
            return st.title()
    return "Central"


def _guess_qualification(text):
    low = (text or "").lower()
    if re.search(r"\b(class\s*12|12th|intermediate|hsc)\b", low):
        return "Class 12 / Intermediate"
    if re.search(r"\b(graduation|bachelor|b\.?tech|b\.?e\.?|degree)\b", low):
        return "Graduation in any stream"
    if re.search(r"\b(class\s*10|matric|10th)\b", low):
        return "Class 10 / Matric"
    if re.search(r"\b(ph\.?d|post graduate|m\.?sc|m\.?a\.?|masters)\b", low):
        return "Post Graduation / Equivalent"
    return "As per official notification"


# Keyword remap for exam items — Google News returns loosely-related stories
# under each query, so re-check the title against known exam keywords.
_EXAM_KEYWORD_REMAP = [
    (r"\b(jee|bitsat|viteee|srmjee|eamcet|cet|comedk|kcet|wbjee|cuet[^ ]*eng)\b", "engineering"),
    (r"\b(neet|aiims|nursing entrance)\b", "medical"),
    (r"\b(clat|ailet|law entrance|slat)\b", "law"),
    (r"\b(cat exam|xat|mat exam|cmat|mba entrance|snap)\b", "management"),
    (r"\b(upsc|ssc|civil services|bpsc|state psc|mpsc|uppsc)\b", "government"),
    (r"\b(ibps|sbi po|rbi grade|bank po|bank clerk)\b", "banking"),
    (r"\b(ugc net|csir net|gate exam|iit jam|research fellowship|jrf)\b", "research"),
    (r"\b(cbse|class 10|class 12|10th board|12th board|state board|tet|ctet|stet|date sheet)\b", "school"),
    (r"\b(cuet|university admission|du admission|cuet ug)\b", "university"),
]


def _remap_exam_category(title, default):
    low = (title or "").lower()
    for pattern, cat in _EXAM_KEYWORD_REMAP:
        if re.search(pattern, low):
            return cat
    return default or "other"


def _job_category(query_cat, text, org_cat):
    if org_cat:
        return org_cat
    return query_cat or "others"


def _build_job(rec, query_cat):
    """RSS record → govt-jobs.json-shaped dict."""
    title = rec["title"]
    blob = title + " " + rec.get("desc", "")
    org, short, site, org_cat = _detect_org(blob)
    if not org:
        # Try an uppercase acronym from the title itself (DSSSB, BPSC, RRB…)
        acr = re.search(r"\b([A-Z][A-Z0-9]{2,9})\b", title)
        _acr_stop = {"PDF", "OUT", "NEW", "LIVE", "EXAM", "RESULT", "CARD", "LIST",
                     "VIA", "THE", "AND", "FOR", "NOT", "ALL", "SBI".upper()}
        if acr and acr.group(1) not in _acr_stop:
            org = acr.group(1)
            short = acr.group(1)
            site = rec["link"]
        else:
            org = rec.get("source") or "Government of India"
            short = "".join(w[0] for w in org.split()[:3]).upper() or "GOVT"
            site = rec["link"]
    published = rec.get("pub_dt") or datetime.now()
    age_days = max((datetime.now() - published).days, 0)
    return {
        "id": 1000000,  # offset replaced with row id by caller
        "title": title,
        "organization": org,
        "short_org": short,
        "post": title,
        "category": _job_category(query_cat, blob, org_cat),
        "vacancy": _extract_vacancy(blob),
        "last_date": _extract_last_date(blob),
        "qualification": _guess_qualification(blob),
        "salary": "As per notification",
        "age": "As per notification",
        "apply_url": site or rec["link"],
        "badge": "new" if age_days <= 14 else None,
        "state": _detect_state(blob),
        "_link": rec["link"],
        "_source": rec.get("source") or "",
        "_published": published.isoformat(),
    }


# ── Sync ─────────────────────────────────────────────────────────────────────

def _fetch_all(queries):
    """Fetch all queries in parallel → (records, ok, failed)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    ok = failed = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_feed, q): (cat, q) for cat, q in queries}
        for fut in as_completed(futures):
            cat, q = futures[fut]
            try:
                items = fut.result()
                for it in items:
                    it["category"] = cat
                    it["query"] = q
                results.extend(items)
                ok += 1
            except Exception:
                failed += 1
    return results, ok, failed


def sync_all(force=False):
    """Fetch all sources and upsert into Postgres. Returns status dict."""
    if os.getenv("AUTO_UPDATES_DISABLED") == "1":
        return get_status()
    if not _SYNC_LOCK.acquire(blocking=False):
        # Already running
        return get_status()
    try:
        if not force:
            # Basic throttle: skip if synced < 10 min ago
            last = _STATUS.get("last_run")
            if last:
                try:
                    if (datetime.now() - datetime.fromisoformat(last)).seconds < 600:
                        return get_status()
                except Exception:
                    pass

        exam_recs, e_ok, e_fail = _fetch_all(EXAM_SOURCES)
        job_recs, j_ok, j_fail = _fetch_all(JOB_SOURCES)

        with _STATUS_LOCK:
            _STATUS["running"] = True

        db_ok = False
        exam_count = job_count = 0
        url = _db_url()
        if url:
            try:
                conn = _connect()
                try:
                    _ensure_table(conn)
                    now = datetime.now()

                    def _upsert(rows, kind, builder=None):
                        count = 0
                        with conn.cursor() as cur:
                            for rec in rows:
                                if builder:
                                    item = builder(rec)
                                    uid = _uid(kind, item["title"])
                                    payload = json.dumps({
                                        "org": item["organization"],
                                        "short_org": item["short_org"],
                                        "category": item["category"],
                                        "vacancy": item["vacancy"],
                                        "last_date": item["last_date"],
                                        "qualification": item["qualification"],
                                        "state": item["state"],
                                        "badge": item["badge"],
                                        "apply_url": item["apply_url"],
                                        "link": item["_link"],
                                        "source": item["_source"],
                                        "published": item["_published"],
                                    }, ensure_ascii=False)
                                    title = item["title"]
                                    category = item["category"]
                                    desc = rec.get("desc") or ""
                                    link = item["_link"]
                                    source = item["_source"]
                                    pub = item["_published"]
                                else:
                                    uid = _uid(kind, rec["title"])
                                    payload = None
                                    title = rec["title"]
                                    category = _remap_exam_category(title, rec.get("category"))
                                    desc = rec.get("desc") or ""
                                    link = rec["link"]
                                    source = rec.get("source") or ""
                                    pub = rec["pub_dt"].isoformat() if rec.get("pub_dt") else None
                                cur.execute(
                                    """
                                    INSERT INTO auto_updates
                                        (uid, kind, category, title, description, link,
                                         source, payload, published_at, fetched_at)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                                    ON CONFLICT (uid) DO UPDATE SET
                                        category = EXCLUDED.category,
                                        description = EXCLUDED.description,
                                        link = EXCLUDED.link,
                                        payload = EXCLUDED.payload,
                                        fetched_at = EXCLUDED.fetched_at
                                    """,
                                    (uid, kind, category, title, desc or None, link or None,
                                     source or None, payload, pub, now),
                                )
                                count += 1
                        return count

                        # Dedup by uid handled by ON CONFLICT

                    exam_count = _upsert(exam_recs, "exam")
                    job_count = _upsert(job_recs, "job", builder=lambda r: _build_job(r, r.get("category")))

                    # Prune stale rows (constant interval, no user input)
                    with conn.cursor() as cur:
                        cur.execute(
                            f"DELETE FROM auto_updates WHERE fetched_at < now() - interval '{_KEEP_DAYS} days'"
                        )
                    conn.commit()
                    db_ok = True
                finally:
                    conn.close()
            except Exception as exc:
                app_log_warning("auto_updates DB write failed: %s" % exc)

        # Refresh caches
        with _CACHE_LOCK:
            _CACHE["exam"] = ([], 0.0)
            _CACHE["job"] = ([], 0.0)

        with _STATUS_LOCK:
            _STATUS.update({
                "running": False,
                "last_run": datetime.now().isoformat(),
                "last_error": None if db_ok else "database write failed",
                "exam_items": exam_count,
                "job_items": job_count,
                "sources_ok": e_ok + j_ok,
                "sources_failed": e_fail + j_fail,
                "db_ok": db_ok,
            })
        return get_status()
    except Exception as exc:
        with _STATUS_LOCK:
            _STATUS.update({
                "running": False,
                "last_run": datetime.now().isoformat(),
                "last_error": str(exc)[:300],
            })
        app_log_warning("auto_updates sync failed: %s" % exc)
        return get_status()
    finally:
        _SYNC_LOCK.release()


def app_log_warning(msg):
    """Best-effort logger (app.py injects Flask logger via set_logger)."""
    fn = getattr(app_log_warning, "logger", None)
    if fn:
        try:
            fn(msg)
            return
        except Exception:
            pass
    print("[auto_updates] " + str(msg))


def set_logger(logger):
    app_log_warning.logger = logger


# ── Read APIs (used by app.py routes) ────────────────────────────────────────

def get_status():
    with _STATUS_LOCK:
        return dict(_STATUS)


def _read_rows(kind, limit):
    """Latest N rows for kind from DB (cached _TTL_SECONDS)."""
    now = time.time()
    with _CACHE_LOCK:
        cached, ts = _CACHE.get(kind, ([], 0.0))
        if cached and now - ts < _TTL_SECONDS:
            return cached
    rows = []
    url = _db_url()
    if url:
        try:
            conn = _connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT category, title, description, link, source, payload, published_at
                        FROM auto_updates
                        WHERE kind = %s
                        ORDER BY published_at DESC NULLS LAST, id DESC
                        LIMIT %s
                        """,
                        (kind, limit),
                    )
                    for r in cur.fetchall():
                        rows.append({
                            "category": r[0] or "other",
                            "title": r[1],
                            "desc": r[2] or "",
                            "link": r[3] or "",
                            "source": r[4] or "",
                            "payload": r[5] if isinstance(r[5], dict) else {},
                            "published_at": r[6],
                        })
            finally:
                conn.close()
        except Exception as exc:
            app_log_warning("auto_updates read failed (%s): %s" % (kind, exc))
    with _CACHE_LOCK:
        _CACHE[kind] = (rows, now)
    return rows


def get_live_exam_items(limit=60):
    """Exam-updates page shape: [{category, title, desc, link, source}]."""
    items = []
    for r in _read_rows("exam", limit):
        desc = r["desc"] or "Latest official update"
        if r["source"]:
            desc += f" — Source: {r['source']}"
        items.append({
            "category": r["category"],
            "title": r["title"],
            "desc": desc,
            "link": r["link"],
            "source": r["source"],
            "is_live": True,
        })
    return items


def get_live_job_items(limit=50):
    """Govt-jobs page shape (matches data/govt_jobs.json fields)."""
    jobs = []
    for idx, r in enumerate(_read_rows("job", limit)):
        p = r["payload"] or {}
        published = r["published_at"]
        age_days = 999
        if published is not None:
            try:
                pub_dt = published if isinstance(published, datetime) else datetime.fromisoformat(str(published))
                age_days = max((datetime.now() - pub_dt.replace(tzinfo=None)).days, 0)
            except Exception:
                pass
        jobs.append({
            "id": 1000000 + idx,
            "title": r["title"],
            "organization": p.get("org") or "Government of India",
            "short_org": p.get("short_org") or "GOVT",
            "post": r["title"],
            "category": p.get("category") or r["category"] or "others",
            "vacancy": int(p.get("vacancy") or 0),
            "last_date": p.get("last_date") or "",
            "qualification": p.get("qualification") or "As per official notification",
            "salary": "As per notification",
            "age": "As per notification",
            "apply_url": p.get("apply_url") or r["link"] or "#",
            "badge": "new" if age_days <= 14 else None,
            "state": p.get("state") or "Central",
            "_live": True,
            "_source": r["source"],
            "_link": r["link"],
        })
    return jobs


# ── Background thread ────────────────────────────────────────────────────────

def start_background_sync(logger=None):
    """Start daemon thread: initial sync after short delay, then every 45 min."""
    global _SYNC_THREAD_STARTED
    if os.getenv("AUTO_UPDATES_DISABLED") == "1":
        return
    if _SYNC_THREAD_STARTED:
        return
    _SYNC_THREAD_STARTED = True
    if logger is not None:
        set_logger(logger)

    def _loop():
        time.sleep(_SYNC_FIRST_DELAY_SECONDS)
        while True:
            try:
                sync_all(force=True)
            except Exception as exc:  # pragma: no cover
                app_log_warning("background sync crashed: %s" % exc)
            time.sleep(_SYNC_INTERVAL_SECONDS)

    threading.Thread(target=_loop, daemon=True, name="auto-updates-sync").start()
