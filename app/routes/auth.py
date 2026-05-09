"""
Authentication routes: register (with OTP), login (no OTP), forgot/reset password,
profile, change password, delete account, logout.
"""
import re
import time

from flask import Blueprint, flash, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.services.auth_service import (
    create_auth_session_user,
    create_user,
    delete_user,
    find_user_by_email,
    get_logged_in_user,
    get_otp_provider,
    get_pending_registration_otp,
    is_admin_user,
    login_required,
    mark_email_verified,
    normalize_auth_role,
    remember_post_auth_redirect,
    render_auth_page,
    resolve_post_auth_redirect,
    resolve_registration_role,
    store_pending_registration_otp,
    update_last_login,
    update_user_password,
    update_user_profile,
)
from app.services.email_service import (
    get_twilio_verify_config,
    send_registration_otp_email,
    send_twilio_verify_code,
    verify_twilio_code,
)

auth_bp = Blueprint("auth", __name__)


# ══════════════════════════════════════════════════════════════════════════
# REGISTER  (OTP required for email verification)
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        requested_role = request.form.get("account_type", "user")
        admin_access_code = request.form.get("admin_access_code", "").strip()

        if not name or not email or not password or not confirm_password:
            flash("Please fill in all registration fields.", "error")
            return render_auth_page("register", "Register")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_auth_page("register", "Register")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_auth_page("register", "Register")

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Please enter a valid email address.", "error")
            return render_auth_page("register", "Register")

        # Check if user already exists
        existing = find_user_by_email(email)
        if existing is not None:
            flash("An account with this email already exists.", "error")
            return render_auth_page("register", "Register")

        # Resolve role
        role, role_error = resolve_registration_role(requested_role, admin_access_code)
        if role_error:
            flash(role_error, "error")
            return render_auth_page("register", "Register")

        # Store pending registration data and generate OTP
        otp_code = store_pending_registration_otp({
            "name": name,
            "email": email,
            "phone": phone,
            "role": role,
            "password_hash": generate_password_hash(password),
        })

        # Try sending OTP via Twilio Verify first
        provider = get_otp_provider()
        otp_sent = False

        if provider == "twilio_verify" and get_twilio_verify_config() is not None:
            try:
                otp_sent = send_twilio_verify_code(email)
            except Exception:
                otp_sent = False

            if otp_sent:
                pending = session.get("pending_reg_otp", {})
                pending["provider"] = "twilio_verify"
                session["pending_reg_otp"] = pending
                session["otp_delivery_mode"] = "email"
                session.pop("pending_otp_preview", None)
                flash("Verification code sent to your email. Enter it to complete registration.", "success")
                return redirect(url_for("auth.verify_email"))

        # Fallback: send via SMTP
        try:
            otp_sent = send_registration_otp_email(email, name, otp_code)
        except Exception:
            pass

        session["otp_delivery_mode"] = "email" if otp_sent else "screen"
        if not otp_sent:
            session["pending_otp_preview"] = otp_code
        else:
            session.pop("pending_otp_preview", None)

        flash(
            "Verification code sent to your email." if otp_sent
            else "Verification code is ready. Enter the code shown on the next screen.",
            "success",
        )
        return redirect(url_for("auth.verify_email"))

    return render_auth_page("register", "Register")


# ══════════════════════════════════════════════════════════════════════════
# VERIFY EMAIL  (OTP step during registration)
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    pending = get_pending_registration_otp()
    if pending is None:
        flash("Please register again to get a new verification code.", "error")
        return redirect(url_for("auth.register"))

    otp_preview = None
    if session.get("otp_delivery_mode") == "screen":
        otp_preview = session.get("pending_otp_preview")

    if request.method == "POST":
        otp_code = request.form.get("otp_code", "").strip()

        if not re.fullmatch(r"\d{6}", otp_code):
            flash("Enter the 6-digit verification code.", "error")
            return render_auth_page("verify_email", "Verify Email",
                otp_email=pending["email"], otp_preview=otp_preview,
                otp_expires_at=pending["expires_at"])

        if pending.get("attempts", 0) >= 5:
            session.pop("pending_reg_otp", None)
            session.pop("otp_delivery_mode", None)
            session.pop("pending_otp_preview", None)
            flash("Too many invalid attempts. Please register again.", "error")
            return redirect(url_for("auth.register"))

        verified = False

        if pending.get("provider") == "twilio_verify":
            try:
                verified = verify_twilio_code(pending["email"], otp_code)
            except Exception:
                pass
        elif check_password_hash(pending["otp_hash"], otp_code):
            verified = True

        if verified:
            # Create user in MongoDB
            try:
                from app.services.auth_service import create_user as _create_user
                from app.utils.mongo import get_users_collection

                users = get_users_collection()
                # Double-check no duplicate
                if users.find_one({"email": pending["email"]}):
                    flash("An account with this email already exists. Please login.", "error")
                    session.pop("pending_reg_otp", None)
                    return redirect(url_for("auth.login"))

                now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                doc = {
                    "name": pending["name"],
                    "email": pending["email"],
                    "phone": pending.get("phone", ""),
                    "password_hash": pending["password_hash"],
                    "role": pending.get("role", "user"),
                    "email_verified": True,
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
                    "last_login_at": now,
                }
                users.insert_one(doc)
            except Exception as exc:
                flash(f"Account creation failed: {exc}", "error")
                return redirect(url_for("auth.register"))

            # Auto-login
            role = pending.get("role", "user")
            session["auth_user"] = create_auth_session_user(pending["name"], pending["email"], role)
            session.pop("pending_reg_otp", None)
            session.pop("otp_delivery_mode", None)
            session.pop("pending_otp_preview", None)
            flash("Email verified! Your account has been created.", "success")
            default_endpoint = "admin.admin_panel" if role == "admin" else "main.index"
            return redirect(resolve_post_auth_redirect(default_endpoint=default_endpoint))

        # Invalid OTP
        pending["attempts"] = pending.get("attempts", 0) + 1
        session["pending_reg_otp"] = pending
        flash("Invalid verification code. Please try again.", "error")

    return render_auth_page("verify_email", "Verify Email",
        otp_email=pending["email"], otp_preview=otp_preview,
        otp_expires_at=pending["expires_at"])


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    pending = get_pending_registration_otp()
    if pending is None:
        flash("Please register again to get a new verification code.", "error")
        return redirect(url_for("auth.register"))

    otp_sent = False
    if pending.get("provider") == "twilio_verify" and get_twilio_verify_config() is not None:
        try:
            otp_sent = send_twilio_verify_code(pending["email"])
        except Exception:
            otp_sent = False
        if otp_sent:
            session["pending_reg_otp"] = {
                **pending,
                "provider": "twilio_verify",
                "expires_at": int(time.time()) + 300,
                "attempts": 0,
            }
            session["otp_delivery_mode"] = "email"
            session.pop("pending_otp_preview", None)
            flash("A new verification code has been sent to your email.", "success")
            return redirect(url_for("auth.verify_email"))

    # Fallback SMTP
    from app.services.auth_service import generate_registration_otp
    otp_code = generate_registration_otp()
    pending["otp_hash"] = generate_password_hash(otp_code)
    pending["expires_at"] = int(time.time()) + 300
    pending["attempts"] = 0
    session["pending_reg_otp"] = pending

    try:
        otp_sent = send_registration_otp_email(pending["email"], pending["name"], otp_code)
    except Exception:
        pass

    session["otp_delivery_mode"] = "email" if otp_sent else "screen"
    if not otp_sent:
        session["pending_otp_preview"] = otp_code
    else:
        session.pop("pending_otp_preview", None)
    flash(
        "A new verification code has been sent to your email." if otp_sent
        else f"New verification code generated.",
        "success",
    )
    return redirect(url_for("auth.verify_email"))


# ══════════════════════════════════════════════════════════════════════════
# LOGIN  (simple email + password, NO OTP)
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        remember_post_auth_redirect()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.", "error")
            return render_auth_page("login", "Login")

        user = find_user_by_email(email)

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_auth_page("login", "Login")

        if not user.get("email_verified", False):
            flash("Please verify your email first. Check your inbox for the verification code.", "error")
            return render_auth_page("login", "Login")

        # Successful login — set session directly (no OTP)
        role = normalize_auth_role(user.get("role", "user"))
        session["auth_user"] = create_auth_session_user(user["name"], user["email"], role)
        update_last_login(user["email"])

        flash("Login successful. Welcome back!", "success")
        default_endpoint = "admin.admin_panel" if role == "admin" else "main.index"
        return redirect(resolve_post_auth_redirect(default_endpoint=default_endpoint))

    return render_auth_page("login", "Login")


# ══════════════════════════════════════════════════════════════════════════
# FORGOT PASSWORD  (OTP-based)
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your email address.", "error")
            return render_auth_page("forgot_password", "Forgot Password")

        user = find_user_by_email(email)

        # Always show same message to prevent email enumeration
        if user is None:
            flash("If an account with that email exists, a reset code has been sent.", "success")
            return render_auth_page("forgot_password", "Forgot Password")

        # Generate OTP and store in session
        from app.services.auth_service import generate_registration_otp
        otp_code = generate_registration_otp()
        session["pending_reset_otp"] = {
            "email": user["email"],
            "name": user.get("name", ""),
            "otp_hash": generate_password_hash(otp_code),
            "expires_at": int(time.time()) + 300,
            "attempts": 0,
            "verified": False,
        }

        # Try sending OTP
        otp_sent = False
        try:
            from app.services.email_service import send_password_reset_otp_email
            otp_sent = send_password_reset_otp_email(email, user.get("name", ""), otp_code)
        except Exception:
            pass

        session["reset_otp_delivery"] = "email" if otp_sent else "screen"
        if not otp_sent:
            session["reset_otp_preview"] = otp_code
        else:
            session.pop("reset_otp_preview", None)

        flash(
            "Reset code sent to your email." if otp_sent
            else "Reset code is ready. Use the code shown on the next screen.",
            "success",
        )
        return redirect(url_for("auth.verify_reset_otp"))

    return render_auth_page("forgot_password", "Forgot Password")


# ══════════════════════════════════════════════════════════════════════════
# VERIFY RESET OTP
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/verify-reset-otp", methods=["GET", "POST"])
def verify_reset_otp():
    pending = session.get("pending_reset_otp")
    if not isinstance(pending, dict) or pending.get("verified"):
        flash("Please request a new password reset.", "error")
        return redirect(url_for("auth.forgot_password"))

    # Check expiry
    if pending.get("expires_at", 0) < int(time.time()):
        session.pop("pending_reset_otp", None)
        flash("Reset code expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))

    otp_preview = None
    if session.get("reset_otp_delivery") == "screen":
        otp_preview = session.get("reset_otp_preview")

    if request.method == "POST":
        otp_code = request.form.get("otp_code", "").strip()

        if not re.fullmatch(r"\d{6}", otp_code):
            flash("Enter the 6-digit reset code.", "error")
            return render_auth_page("verify_reset_otp", "Verify Reset Code",
                otp_email=pending["email"], otp_preview=otp_preview,
                otp_expires_at=pending["expires_at"])

        if pending.get("attempts", 0) >= 5:
            session.pop("pending_reset_otp", None)
            session.pop("reset_otp_delivery", None)
            session.pop("reset_otp_preview", None)
            flash("Too many invalid attempts. Please request a new reset code.", "error")
            return redirect(url_for("auth.forgot_password"))

        if check_password_hash(pending["otp_hash"], otp_code):
            # OTP verified — mark and redirect to set new password
            pending["verified"] = True
            session["pending_reset_otp"] = pending
            session.pop("reset_otp_delivery", None)
            session.pop("reset_otp_preview", None)
            return redirect(url_for("auth.reset_password"))

        pending["attempts"] = pending.get("attempts", 0) + 1
        session["pending_reset_otp"] = pending
        flash("Invalid reset code. Please try again.", "error")

    return render_auth_page("verify_reset_otp", "Verify Reset Code",
        otp_email=pending["email"], otp_preview=otp_preview,
        otp_expires_at=pending["expires_at"])


@auth_bp.route("/resend-reset-otp", methods=["POST"])
def resend_reset_otp():
    pending = session.get("pending_reset_otp")
    if not isinstance(pending, dict) or pending.get("verified"):
        flash("Please request a new password reset.", "error")
        return redirect(url_for("auth.forgot_password"))

    from app.services.auth_service import generate_registration_otp
    otp_code = generate_registration_otp()
    pending["otp_hash"] = generate_password_hash(otp_code)
    pending["expires_at"] = int(time.time()) + 300
    pending["attempts"] = 0
    session["pending_reset_otp"] = pending

    otp_sent = False
    try:
        from app.services.email_service import send_password_reset_otp_email
        otp_sent = send_password_reset_otp_email(pending["email"], pending["name"], otp_code)
    except Exception:
        pass

    session["reset_otp_delivery"] = "email" if otp_sent else "screen"
    if not otp_sent:
        session["reset_otp_preview"] = otp_code
    else:
        session.pop("reset_otp_preview", None)

    flash(
        "A new reset code has been sent to your email." if otp_sent
        else "New reset code generated.",
        "success",
    )
    return redirect(url_for("auth.verify_reset_otp"))


# ══════════════════════════════════════════════════════════════════════════
# RESET PASSWORD  (after OTP verified)
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    pending = session.get("pending_reset_otp")
    if not isinstance(pending, dict) or not pending.get("verified"):
        flash("Please verify your reset code first.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or not confirm_password:
            flash("Please fill in all fields.", "error")
            return render_auth_page("reset_password", "Reset Password")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_auth_page("reset_password", "Reset Password")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_auth_page("reset_password", "Reset Password")

        update_user_password(pending["email"], password)
        session.pop("pending_reset_otp", None)
        flash("Your password has been reset successfully. Please login with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_auth_page("reset_password", "Reset Password")


# ══════════════════════════════════════════════════════════════════════════
# PROFILE
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    current_user = get_logged_in_user()
    user_doc = find_user_by_email(current_user["email"])

    if user_doc is None:
        flash("User not found. Please login again.", "error")
        session.pop("auth_user", None)
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        profile_data = {
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "education_level": request.form.get("education_level", "").strip(),
            "stream": request.form.get("stream", "").strip(),
            "target_exams": request.form.getlist("target_exams"),
            "target_year": None,
            "state": request.form.get("state", "").strip(),
            "city": request.form.get("city", "").strip(),
            "college": request.form.get("college", "").strip(),
            "interests": request.form.getlist("interests"),
        }

        # Parse target_year
        try:
            year_raw = request.form.get("target_year", "").strip()
            if year_raw:
                profile_data["target_year"] = int(year_raw)
        except ValueError:
            pass

        update_user_profile(current_user["email"], profile_data)

        # Update session name if changed
        if profile_data.get("name"):
            session["auth_user"]["name"] = profile_data["name"]

        flash("Profile updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    from flask import render_template
    user_profile = user_doc.get("profile", {})
    return render_template("auth/profile.html",
        page_title="My Profile",
        auth_user=current_user,
        user_doc=user_doc,
        user_profile=user_profile,
    )


# ══════════════════════════════════════════════════════════════════════════
# UPLOAD PROFILE PHOTO
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/upload-photo", methods=["POST"])
@login_required
def upload_photo():
    current_user = get_logged_in_user()
    from flask import jsonify as _jsonify

    photo_file = request.files.get("photo")
    if not photo_file or photo_file.filename == "":
        flash("No photo selected.", "error")
        return redirect(url_for("auth.profile"))

    # Check file type
    allowed = {"png", "jpg", "jpeg", "webp", "gif"}
    ext = photo_file.filename.rsplit(".", 1)[-1].lower() if "." in photo_file.filename else ""
    if ext not in allowed:
        flash("Invalid file type. Use PNG, JPG, or WebP.", "error")
        return redirect(url_for("auth.profile"))

    # Check file size (max 5MB)
    photo_file.seek(0, 2)
    size = photo_file.tell()
    photo_file.seek(0)
    if size > 5 * 1024 * 1024:
        flash("Photo too large. Maximum 5MB.", "error")
        return redirect(url_for("auth.profile"))

    try:
        from app.utils.cloudinary_util import upload_profile_photo
        result = upload_profile_photo(photo_file, current_user["email"])
        if result and result.get("url"):
            from app.utils.mongo import get_users_collection
            from datetime import datetime, timezone
            get_users_collection().update_one(
                {"email": current_user["email"]},
                {"$set": {
                    "profile_photo_url": result["url"],
                    "profile_photo_id": result["public_id"],
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            flash("Profile photo updated!", "success")
        else:
            flash("Failed to upload photo.", "error")
    except RuntimeError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Upload failed: {e}", "error")

    return redirect(url_for("auth.profile"))


@auth_bp.route("/remove-photo", methods=["POST"])
@login_required
def remove_photo():
    current_user = get_logged_in_user()
    user_doc = find_user_by_email(current_user["email"])

    if user_doc and user_doc.get("profile_photo_id"):
        try:
            from app.utils.cloudinary_util import delete_profile_photo
            delete_profile_photo(user_doc["profile_photo_id"])
        except Exception:
            pass

    from app.utils.mongo import get_users_collection
    from datetime import datetime, timezone
    get_users_collection().update_one(
        {"email": current_user["email"]},
        {"$set": {
            "profile_photo_url": None,
            "profile_photo_id": None,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    flash("Profile photo removed.", "success")
    return redirect(url_for("auth.profile"))

# ══════════════════════════════════════════════════════════════════════════
# CHANGE PASSWORD
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_user = get_logged_in_user()
    user_doc = find_user_by_email(current_user["email"])

    if user_doc is None:
        flash("User not found.", "error")
        return redirect(url_for("auth.profile"))

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_new_password = request.form.get("confirm_new_password", "")

    if not current_password or not new_password or not confirm_new_password:
        flash("Please fill in all password fields.", "error")
        return redirect(url_for("auth.profile"))

    if not check_password_hash(user_doc["password_hash"], current_password):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("auth.profile"))

    if new_password != confirm_new_password:
        flash("New passwords do not match.", "error")
        return redirect(url_for("auth.profile"))

    if len(new_password) < 6:
        flash("New password must be at least 6 characters long.", "error")
        return redirect(url_for("auth.profile"))

    update_user_password(current_user["email"], new_password)
    flash("Password changed successfully.", "success")
    return redirect(url_for("auth.profile"))


# ══════════════════════════════════════════════════════════════════════════
# DELETE ACCOUNT
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    current_user = get_logged_in_user()
    user_doc = find_user_by_email(current_user["email"])

    if user_doc is None:
        flash("User not found.", "error")
        return redirect(url_for("auth.profile"))

    password = request.form.get("confirm_password", "")
    if not password:
        flash("Please enter your password to confirm account deletion.", "error")
        return redirect(url_for("auth.profile"))

    if not check_password_hash(user_doc["password_hash"], password):
        flash("Incorrect password. Account not deleted.", "error")
        return redirect(url_for("auth.profile"))

    delete_user(current_user["email"])
    session.clear()
    flash("Your account has been permanently deleted.", "success")
    return redirect(url_for("main.index"))


# ══════════════════════════════════════════════════════════════════════════
# LOGOUT
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/logout")
def logout():
    session.pop("auth_user", None)
    session.pop("pending_reg_otp", None)
    session.pop("pending_otp", None)
    session.pop("otp_delivery_mode", None)
    session.pop("pending_otp_preview", None)
    session.pop("post_auth_redirect", None)
    return redirect(url_for("main.index"))
