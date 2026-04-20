"""
courses_route.py  —  Vidyarthi Mitra
------------------------------------
Add this file to your Flask project, then register the blueprint in your
main app factory / app.py:

    from courses_route import courses_bp
    app.register_blueprint(courses_bp)

Dependencies (add to requirements.txt):
    psycopg2-binary>=2.9
    python-dotenv>=1.0      # only if you load .env manually

Environment variable required (put in your .env):
    SUPABASE_POSTGRES_URL=postgresql://...
"""

from __future__ import annotations

import os
import json
from collections import defaultdict

import psycopg2
import psycopg2.extras
from flask import Blueprint, render_template, current_app

courses_bp = Blueprint("courses", __name__)

# ── Database URL ───────────────────────────────────────────────────────────────
DB_URL = os.environ.get(
    "SUPABASE_POSTGRES_URL",
    os.environ.get("DATABASE_URL", ""),
)

# ── Column list we actually need (matches your table exactly) ──────────────────
SELECT_COLS = (
    "course_id, course_name, short_name, level, stream, sub_stream, "
    "duration_years, eligibility, entrance_exams, top_institutes, avg_fee_inr_per_year"
)

# ── Level display metadata ─────────────────────────────────────────────────────
LEVEL_META = {
    "undergraduate":   {"icon": "🎓", "label": "Undergraduate",    "color": "#4f46e5", "num": "01"},
    "postgraduate":    {"icon": "📚", "label": "Postgraduate",     "color": "#7c3aed", "num": "02"},
    "doctoral":        {"icon": "🔭", "label": "Doctoral / PhD",   "color": "#db2777", "num": "03"},
    "integrated":      {"icon": "🔗", "label": "Integrated",       "color": "#0891b2", "num": "04"},
    "diploma":         {"icon": "📜", "label": "Diploma",          "color": "#d97706", "num": "05"},
    "certificate":     {"icon": "🏅", "label": "Certificate",      "color": "#059669", "num": "06"},
    "vocational":      {"icon": "🔧", "label": "Vocational / ITI", "color": "#dc2626", "num": "07"},
    "professional":    {"icon": "🏆", "label": "Professional",     "color": "#9333ea", "num": "08"},
    "online/distance": {"icon": "🌐", "label": "Online & Distance","color": "#0369a1", "num": "09"},
}

LEVEL_ORDER = [
    "undergraduate", "postgraduate", "doctoral", "integrated",
    "diploma", "certificate", "vocational", "professional", "online/distance",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_connection():
    """Open a fresh psycopg2 connection (no pool — works fine for Flask dev)."""
    if not DB_URL or not str(DB_URL).strip():
        raise RuntimeError("SUPABASE_POSTGRES_URL or DATABASE_URL is not configured.")
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _fetch_courses() -> list[dict]:
    """Fetch all rows from the courses table, ordered by level then course_name."""
    sql = f"""
        SELECT {SELECT_COLS}
        FROM   courses
        ORDER  BY level, short_name, course_name
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        # Convert RealDictRow → plain dict, replace None → ""
        return [
            {k: (v if v is not None else "") for k, v in row.items()}
            for row in rows
        ]
    finally:
        conn.close()


def _build_level_index(courses: list[dict]) -> dict:
    """
    Build a nested structure the template uses to render sections + cards.

    Returns:
        {
            level_str: {
                "meta":   LEVEL_META[level],
                "count":  int,
                "shorts": [
                    {
                        "name":   short_name str,
                        "count":  int,
                        "stream": str  (first stream found for this short_name)
                    },
                    ...
                ]
            },
            ...
        }
    """
    # Track order of first appearance per level
    level_short_order: dict[str, list] = {lvl: [] for lvl in LEVEL_ORDER}
    level_short_seen:  dict[str, set]  = {lvl: set() for lvl in LEVEL_ORDER}
    short_stream:      dict[str, str]  = {}
    short_count:       dict            = defaultdict(lambda: defaultdict(int))
    level_count:       dict[str, int]  = defaultdict(int)

    for row in courses:
        lvl = row.get("level", "")
        sn  = row.get("short_name", "")
        if lvl not in level_short_seen:
            continue
        level_count[lvl] += 1
        short_count[lvl][sn] += 1
        if sn not in level_short_seen[lvl]:
            level_short_seen[lvl].add(sn)
            level_short_order[lvl].append(sn)
        if sn not in short_stream:
            short_stream[sn] = row.get("stream", "")

    index = {}
    for lvl in LEVEL_ORDER:
        if lvl not in LEVEL_META:
            continue
        shorts_data = [
            {
                "name":   sn,
                "count":  short_count[lvl][sn],
                "stream": short_stream.get(sn, ""),
            }
            for sn in level_short_order[lvl]
        ]
        index[lvl] = {
            "meta":   LEVEL_META[lvl],
            "count":  level_count[lvl],
            "shorts": shorts_data,
        }
    return index


# ── Route ──────────────────────────────────────────────────────────────────────

@courses_bp.route("/courses")
def courses():
    """Main courses page — fetches live data from Supabase Postgres."""
    try:
        all_courses = _fetch_courses()
        error = None
    except Exception as exc:
        current_app.logger.error("courses DB error: %s", exc)
        all_courses = []
        error = str(exc)

    level_index  = _build_level_index(all_courses)
    level_order  = LEVEL_ORDER
    level_meta   = LEVEL_META
    total_courses = len(all_courses)

    # Serialise for inline JS (the JS search + panel use this)
    courses_json = json.dumps(
        [
            {
                "course_id":           r.get("course_id", ""),
                "course_name":         r.get("course_name", ""),
                "short_name":          r.get("short_name", ""),
                "level":               r.get("level", ""),
                "stream":              r.get("stream", ""),
                "sub_stream":          r.get("sub_stream", ""),
                "duration_years":      str(r.get("duration_years", "")),
                "eligibility":         r.get("eligibility", ""),
                "entrance_exams":      r.get("entrance_exams", ""),
                "top_institutes":      r.get("top_institutes", ""),
                "avg_fee_inr_per_year":r.get("avg_fee_inr_per_year", ""),
            }
            for r in all_courses
        ],
        ensure_ascii=False,
    )

    return render_template(
        "courses.html",
        level_index   = level_index,
        level_order   = level_order,
        level_meta    = level_meta,
        total_courses = total_courses,
        courses_json  = courses_json,
        error         = error,
    )