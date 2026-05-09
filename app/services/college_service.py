"""
College database query service: search, state counts, column resolution.
Now uses MongoDB instead of PostgreSQL.
"""
import re

from app.utils.helpers import clean_college_text, normalize_external_url, normalize_college_match_key


def _get_colleges_col():
    from app.utils.mongo import get_upload_collection
    return get_upload_collection("colleges")


def _extract_field(doc, candidates, default=""):
    """Extract a field from a college document's payload."""
    payload = doc.get("payload", {})
    for c in candidates:
        val = payload.get(c)
        if val is not None and str(val).strip():
            return str(val).strip()
    # Also check top-level keys
    for c in candidates:
        val = doc.get(c)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def _fmt(doc):
    return {
        "name": clean_college_text(_extract_field(doc, ["name", "Name", "college_name", "college", "title"])),
        "state": clean_college_text(_extract_field(doc, ["state", "State", "state_name", "province"])),
        "city": clean_college_text(_extract_field(doc, ["district", "District", "city", "city_name", "location", "Location"])),
        "type": clean_college_text(_extract_field(doc, ["college type", "College Type", "college_type", "institution_type", "type"])),
        "management": clean_college_text(_extract_field(doc, ["manegement", "Manegement", "management", "Management", "ownership"])),
        "nirf": clean_college_text(_extract_field(doc, ["nirf", "nirf_rank", "rank", "nirf_ranking"])),
        "year": clean_college_text(_extract_field(doc, ["year of establishment", "Year Of Establishment", "established", "established_year"])),
        "university_name": clean_college_text(_extract_field(doc, ["university name", "University Name", "university_name", "university"])),
        "logo_url": _extract_field(doc, ["logo_url", "logo", "logo_link", "logo_path"]),
        "source_url": normalize_external_url(_extract_field(doc, ["website", "Website", "website_url", "source_url", "url"])),
    }


def _build_query(q=None, alpha=None, state=None):
    """Build a MongoDB query filter."""
    conditions = []

    # State filter
    if state:
        conditions.append({"$or": [
            {"payload.state": {"$regex": f"^{re.escape(state)}$", "$options": "i"}},
            {"payload.State": {"$regex": f"^{re.escape(state)}$", "$options": "i"}},
            {"payload.state_name": {"$regex": f"^{re.escape(state)}$", "$options": "i"}},
        ]})

    # Alpha filter (first letter)
    if alpha:
        conditions.append({"$or": [
            {"payload.name": {"$regex": f"^{re.escape(alpha)}", "$options": "i"}},
            {"payload.Name": {"$regex": f"^{re.escape(alpha)}", "$options": "i"}},
            {"payload.college_name": {"$regex": f"^{re.escape(alpha)}", "$options": "i"}},
        ]})

    # Full-text search
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        search_fields = [
            {"payload.name": regex}, {"payload.Name": regex},
            {"payload.college_name": regex},
            {"payload.state": regex}, {"payload.State": regex},
            {"payload.district": regex}, {"payload.District": regex},
            {"payload.city": regex},
            {"payload.college type": regex}, {"payload.College Type": regex},
            {"payload.management": regex}, {"payload.Management": regex},
            {"payload.university name": regex}, {"payload.University Name": regex},
        ]
        conditions.append({"$or": search_fields})

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def fetch_colleges_search(page, per_page, q=None, alpha=None, state=None):
    try:
        col = _get_colleges_col()
    except Exception as e:
        return [], 0, f"DB connection failed: {e}"

    query = _build_query(q=q, alpha=alpha, state=state)
    offset = (page - 1) * per_page if per_page else 0

    try:
        total = col.count_documents(query)
        cursor = col.find(query).sort("payload.name", 1)
        if per_page:
            cursor = cursor.skip(offset).limit(per_page)
        rows = list(cursor)
    except Exception as e:
        return [], 0, f"Query failed: {e}"

    return [_fmt(r) for r in rows], total, None


def fetch_college_state_counts():
    try:
        col = _get_colleges_col()
    except Exception as e:
        return [], 0, f"DB connection failed: {e}"

    try:
        # Try multiple state field names
        state_fields = ["payload.state", "payload.State", "payload.state_name"]
        results = []

        for field in state_fields:
            pipeline = [
                {"$match": {field: {"$exists": True, "$ne": "", "$ne": None}}},
                {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
            agg_results = list(col.aggregate(pipeline))
            if agg_results:
                results = [{"state": r["_id"], "count": r["count"]} for r in agg_results if r["_id"]]
                break

        total = sum(r.get("count", 0) for r in results)
        return results, total, None
    except Exception as e:
        return [], 0, f"Query failed: {e}"


def fetch_colleges_by_states(states, limit_per_state=None):
    if not states:
        return [], None

    try:
        col = _get_colleges_col()
    except Exception as e:
        return [], f"DB connection failed: {e}"

    try:
        query = {"$or": [
            {"payload.state": {"$in": states}},
            {"payload.State": {"$in": states}},
            {"payload.state_name": {"$in": states}},
        ]}

        if limit_per_state:
            # Fetch all then limit per state in Python
            rows = list(col.find(query).sort("payload.name", 1))
            state_counts = {}
            filtered = []
            for r in rows:
                fmt = _fmt(r)
                s = fmt["state"]
                state_counts[s] = state_counts.get(s, 0) + 1
                if state_counts[s] <= limit_per_state:
                    filtered.append(fmt)
            return filtered, None
        else:
            rows = list(col.find(query).sort("payload.name", 1))
            return [_fmt(r) for r in rows], None
    except Exception as e:
        return [], f"Query failed: {e}"


def get_college_website_lookup():
    try:
        col = _get_colleges_col()
    except Exception:
        return {}

    result = {}
    try:
        for doc in col.find({}, {"payload": 1}):
            name = _extract_field(doc, ["name", "Name", "college_name", "college", "title"])
            url = normalize_external_url(_extract_field(doc, ["website", "Website", "website_url", "source_url", "url"]))
            key = normalize_college_match_key(name)
            if key and url:
                result.setdefault(key, url)
    except Exception:
        pass
    return result


def find_college_website(college_name, website_lookup):
    key = normalize_college_match_key(college_name)
    if not key:
        return ""
    if key in website_lookup:
        return website_lookup[key]
    key_parts = set(key.split())
    if len(key_parts) < 3:
        return ""
    best_url, best_score = "", 0
    for ck, url in website_lookup.items():
        cp = set(ck.split())
        if not cp:
            continue
        score = len(key_parts & cp) / max(len(key_parts), len(cp))
        if score > best_score:
            best_score = score
            best_url = url
    return best_url if best_score >= 0.68 else ""
