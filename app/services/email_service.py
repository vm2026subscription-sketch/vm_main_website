"""
Email and OTP delivery: SMTP and Twilio Verify.
"""
import base64
import json
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.utils.helpers import get_env_value


def get_twilio_verify_config():
    account_sid = get_env_value("TWILIO_ACCOUNT_SID")
    auth_token = get_env_value("TWILIO_AUTH_TOKEN")
    service_sid = get_env_value("TWILIO_VERIFY_SERVICE_SID")
    if not account_sid or not auth_token or not service_sid:
        return None
    return {"account_sid": account_sid, "auth_token": auth_token, "service_sid": service_sid}


def send_twilio_verify_code(to_email):
    config = get_twilio_verify_config()
    if config is None:
        return False

    endpoint = f"https://verify.twilio.com/v2/Services/{config['service_sid']}/Verifications"
    body = urlencode({"To": to_email, "Channel": "email"}).encode("utf-8")
    credentials = base64.b64encode(f"{config['account_sid']}:{config['auth_token']}".encode("utf-8")).decode("ascii")
    req = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=15) as response:
        response.read()
    return True


def verify_twilio_code(to_email, code):
    config = get_twilio_verify_config()
    if config is None:
        return False

    endpoint = f"https://verify.twilio.com/v2/Services/{config['service_sid']}/VerificationCheck"
    body = urlencode({"To": to_email, "Code": code}).encode("utf-8")
    credentials = base64.b64encode(f"{config['account_sid']}:{config['auth_token']}".encode("utf-8")).decode("ascii")
    req = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload.get("status", "")).lower() == "approved"


# ── SMTP helpers ──────────────────────────────────────────────────────────


def _get_smtp_config():
    """Return SMTP configuration dict or None if not configured."""
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
        return None

    return {
        "host": smtp_host,
        "port": smtp_port,
        "username": smtp_username,
        "password": smtp_password,
        "from_email": from_email,
        "use_tls": use_tls,
    }


def _send_email(to_email, subject, body_text):
    """Send a plain-text email via SMTP. Returns True on success."""
    config = _get_smtp_config()
    if config is None:
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["from_email"]
    message["To"] = to_email
    message.set_content(body_text)

    with smtplib.SMTP(config["host"], config["port"], timeout=15) as smtp:
        if config["use_tls"]:
            smtp.starttls()
        if config["username"]:
            smtp.login(config["username"], config["password"])
        smtp.send_message(message)

    return True


# ── Registration OTP email ────────────────────────────────────────────────


def send_registration_otp_email(to_email, user_name, otp_code):
    """Send email verification OTP during registration."""
    subject = "Verify your email — Vidyarthi Mitra"
    body = f"""Hello {user_name or 'Student'},

Welcome to Vidyarthi Mitra! Please verify your email address.

Your verification code is: {otp_code}

This code expires in 5 minutes. If you did not create an account, ignore this email.

— Vidyarthi Mitra Team
"""
    return _send_email(to_email, subject, body)


# ── Login OTP email (kept for backward compat) ───────────────────────────


def send_login_otp_email(to_email, user_name, otp_code):
    subject = "Your Vidyarthi Mitra login OTP"
    body = f"""Hello {user_name or 'Student'},

Your Vidyarthi Mitra login OTP is: {otp_code}

This code expires in 5 minutes.

If you did not request this, ignore this email.
"""
    return _send_email(to_email, subject, body)


# ── Password reset OTP email ──────────────────────────────────────────────


def send_password_reset_otp_email(to_email, user_name, otp_code):
    """Send password reset OTP email."""
    subject = "Reset your password — Vidyarthi Mitra"
    body = f"""Hello {user_name or 'Student'},

We received a request to reset your Vidyarthi Mitra password.

Your password reset code is: {otp_code}

This code expires in 5 minutes. If you did not request a password reset, ignore this email — your password will remain unchanged.

— Vidyarthi Mitra Team
"""
    return _send_email(to_email, subject, body)
