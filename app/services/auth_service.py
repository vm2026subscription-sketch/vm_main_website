"""
Authentication service: MongoDB user store, session helpers, OTP management.
"""
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timezone
from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.utils.helpers import get_env_value, sanitize_next_url
from app.utils.mongo import get_users_collection

# ── User CRUD ─────────────────────────────────────────────────────────────


def find_user_by_email(email):
    """Find a user document by email (case-insensitive)."""
    users = get_users_collection()
    return users.find_one({"email": email.strip().lower()})


def create_user(name, email, password, role="user"):
    """Insert a new user into MongoDB. Returns the inserted document."""
    users = get_users_collection()
    now = datetime.now(timezone.utc)
    doc = {
        "name": name.strip(),
        "email": email.strip().lower(),
        "password_hash": generate_password_hash(password),
        "role": normalize_auth_role(role),
        "email_verified": False,
        "profile": {
            "education_level": "",
            "stream": "",
            "target_exams": [],
            "target_year": None,
            "state": "",
            "city": "",
            "college": "",
            "interests": [],
        },
        "password_reset_token": None,
        "password_reset_expires": None,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    result = users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def update_user_profile(email, profile_data):
    """Update profile fields for a user."""
    users = get_users_collection()
    update_fields = {"updated_at": datetime.now(timezone.utc)}
    for key in ("education_level", "stream", "target_exams", "target_year",
                "state", "city", "college", "interests"):
        if key in profile_data:
            update_fields[f"profile.{key}"] = profile_data[key]
    # Allow updating top-level name/phone
    if "name" in profile_data:
        update_fields["name"] = profile_data["name"].strip()
    if "phone" in profile_data:
        update_fields["phone"] = profile_data["phone"].strip()
    users.update_one({"email": email.strip().lower()}, {"$set": update_fields})


def update_user_password(email, new_password):
    """Update password for a user."""
    users = get_users_collection()
    users.update_one(
        {"email": email.strip().lower()},
        {"$set": {
            "password_hash": generate_password_hash(new_password),
            "updated_at": datetime.now(timezone.utc),
        }},
    )


def mark_email_verified(email):
    """Set email_verified=True for a user."""
    users = get_users_collection()
    users.update_one(
        {"email": email.strip().lower()},
        {"$set": {
            "email_verified": True,
            "updated_at": datetime.now(timezone.utc),
        }},
    )


def update_last_login(email):
    """Stamp last_login_at for a user."""
    users = get_users_collection()
    users.update_one(
        {"email": email.strip().lower()},
        {"$set": {"last_login_at": datetime.now(timezone.utc)}},
    )


def delete_user(email):
    """Permanently delete a user document."""
    users = get_users_collection()
    users.delete_one({"email": email.strip().lower()})


# ── Password reset ────────────────────────────────────────────────────────


def set_password_reset_token(email):
    """Generate a secure reset token, store it, and return it."""
    token = secrets.token_urlsafe(48)
    users = get_users_collection()
    expires = datetime.now(timezone.utc).timestamp() + 3600  # 1 hour
    users.update_one(
        {"email": email.strip().lower()},
        {"$set": {
            "password_reset_token": token,
            "password_reset_expires": expires,
        }},
    )
    return token


def verify_reset_token(token):
    """Find user by reset token. Returns user doc or None if expired/invalid."""
    users = get_users_collection()
    user = users.find_one({"password_reset_token": token})
    if user is None:
        return None
    expires = user.get("password_reset_expires")
    if expires is None or expires < time.time():
        # Token expired — clear it
        users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_reset_token": None, "password_reset_expires": None}},
        )
        return None
    return user


def clear_reset_token(email):
    """Remove reset token after successful password change."""
    users = get_users_collection()
    users.update_one(
        {"email": email.strip().lower()},
        {"$set": {"password_reset_token": None, "password_reset_expires": None}},
    )


# ── Role helpers ──────────────────────────────────────────────────────────


def normalize_auth_role(value):
    return "admin" if str(value or "").strip().lower() == "admin" else "user"


def create_auth_session_user(name, email, role="user"):
    return {
        "name": str(name or "").strip(),
        "email": str(email or "").strip().lower(),
        "role": normalize_auth_role(role),
    }


def get_logged_in_user():
    user = session.get("auth_user")
    if isinstance(user, dict) and user.get("email"):
        return create_auth_session_user(
            user.get("name", ""),
            user.get("email", ""),
            user.get("role", "user"),
        )
    return None


def is_admin_user(user=None):
    current_user = user or get_logged_in_user()
    return bool(current_user and normalize_auth_role(current_user.get("role")) == "admin")


# ── OTP helpers (for registration) ───────────────────────────────────────


def generate_registration_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def store_pending_registration_otp(user_data):
    """Store pending registration OTP in session."""
    otp_code = generate_registration_otp()
    session["pending_reg_otp"] = {
        "name": user_data["name"],
        "email": user_data["email"],
        "phone": user_data.get("phone", ""),
        "role": normalize_auth_role(user_data.get("role", "user")),
        "password_hash": user_data["password_hash"],
        "otp_hash": generate_password_hash(otp_code),
        "expires_at": int(time.time()) + 300,
        "attempts": 0,
    }
    return otp_code


def get_pending_registration_otp():
    """Get pending registration OTP from session."""
    pending = session.get("pending_reg_otp")
    if not isinstance(pending, dict):
        return None
    expires_at = pending.get("expires_at")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        session.pop("pending_reg_otp", None)
        return None
    return pending


# ── Registration helpers ──────────────────────────────────────────────────


def get_admin_registration_code():
    return get_env_value("ADMIN_REGISTRATION_CODE", "ADMIN_SIGNUP_CODE")


def allow_first_admin_bootstrap():
    value = get_env_value(
        "ALLOW_FIRST_ADMIN_BOOTSTRAP",
        "ALLOW_ADMIN_BOOTSTRAP",
        default="1",
    ).lower()
    return value not in {"0", "false", "no", "off"}


def count_admin_users():
    users = get_users_collection()
    return users.count_documents({"role": "admin"})


def get_admin_registration_context():
    admin_count = count_admin_users()
    admin_code_configured = bool(get_admin_registration_code())
    bootstrap_available = admin_count == 0 and allow_first_admin_bootstrap()
    return {
        "admin_registration_code_configured": admin_code_configured,
        "admin_bootstrap_available": bootstrap_available,
    }


def resolve_registration_role(requested_role, admin_access_code):
    normalized_role = normalize_auth_role(requested_role)
    if normalized_role != "admin":
        return "user", None

    admin_code = get_admin_registration_code()
    if admin_code:
        if admin_access_code and hmac.compare_digest(admin_access_code, admin_code):
            return "admin", None
        return None, "Enter a valid admin access code to create an admin account."

    if count_admin_users() == 0 and allow_first_admin_bootstrap():
        return "admin", None

    return None, "Admin registration is locked. Add ADMIN_REGISTRATION_CODE to your .env to create another admin account."


# ── Request helpers ───────────────────────────────────────────────────────


def get_otp_provider():
    return get_env_value("OTP_PROVIDER", default="email_smtp").lower()


def is_api_request():
    return (
        request.path.startswith("/api/")
        or request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def get_requested_next_url():
    return sanitize_next_url(request.form.get("next") or request.args.get("next"))


def remember_post_auth_redirect():
    next_url = get_requested_next_url()
    if next_url:
        session["post_auth_redirect"] = next_url
    else:
        session.pop("post_auth_redirect", None)


def resolve_post_auth_redirect(default_endpoint="main.index"):
    next_url = get_requested_next_url()
    if next_url:
        session.pop("post_auth_redirect", None)
        return next_url

    stored_next = sanitize_next_url(session.pop("post_auth_redirect", ""))
    if stored_next:
        return stored_next

    return url_for(default_endpoint)


def render_auth_page(mode, page_title, **context):
    payload = {
        "mode": mode,
        "page_title": page_title,
        "next_url": get_requested_next_url() or sanitize_next_url(session.get("post_auth_redirect", "")),
    }
    if mode == "register":
        payload.update(get_admin_registration_context())
    payload.update(context)
    return render_template("auth/auth.html", **payload)


# ── Decorators ────────────────────────────────────────────────────────────


def login_required(view):
    """Require any authenticated user."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        current_user = get_logged_in_user()
        if current_user is None:
            if is_api_request():
                return jsonify({"error": "Login required."}), 401
            next_url = request.full_path.rstrip("?") if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        current_user = get_logged_in_user()
        if current_user is None:
            if is_api_request():
                return jsonify({"error": "Login required."}), 401

            next_url = request.full_path.rstrip("?") if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))

        if not is_admin_user(current_user):
            if is_api_request():
                return jsonify({"error": "Admin access required."}), 403
            return "Admin access required.", 403

        return view(*args, **kwargs)

    return wrapped
