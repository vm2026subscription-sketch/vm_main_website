"""
Pure utility / helper functions used across the application.
No Flask request/response objects — just data transformations.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def get_env_value(*names, default=""):
    """Return the first non-empty environment variable from *names*."""
    import os
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def fetch_remote_json(url, timeout=12):
    """GET a URL and return parsed JSON (list/dict) or None on failure."""
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "vm-main-website/1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            if not body:
                return []
            return json.loads(body.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError):
        return None


def extract_items(payload):
    """Pull a list of items from various API response shapes."""
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
    """Extract pagination 'next' URL from an API response."""
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


def clean_college_text(value):
    """Sanitize imported text: strip control chars, fix apostrophes, collapse whitespace."""
    text = str(value or "").strip()
    if not text:
        return ""

    text = re.sub(r"(?<=\w)[\x00-\x1f\x7f]+(?=s\b)", "'", text)
    text = re.sub(r"(?<=\w)[\uFFFD\u25A0\u25A1\u25AA\u25AB]+(?=s\b)", "'", text)
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"[\uFFFD\u25A0\u25A1\u25AA\u25AB]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_external_url(value):
    """Ensure a URL string has a scheme prefix."""
    url = str(value or "").strip()
    if not url:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*://", url, flags=re.IGNORECASE):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    return f"https://{url.lstrip('/')}"


def normalize_college_match_key(value):
    """Produce a fuzzy-matchable key from a college name."""
    text = clean_college_text(value).lower()
    text = re.sub(r"\b(college|institute|engineering|technology|of|and|the)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_article_teaser(text, max_len=120):
    """Truncate article text into a teaser string."""
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def build_article_paragraphs(text):
    """Split long text into readable paragraph chunks."""
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


def sanitize_next_url(candidate):
    """Validate a redirect URL is a safe relative path."""
    from urllib.parse import urlparse

    if not isinstance(candidate, str):
        return ""
    candidate = candidate.strip()
    if not candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return ""

    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return ""

    return candidate
