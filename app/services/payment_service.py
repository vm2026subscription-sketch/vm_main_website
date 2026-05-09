"""
Razorpay payment service: order creation and signature verification.
"""
import base64
import hashlib
import hmac
import json
from urllib.request import Request, urlopen

from app.utils.helpers import get_env_value


def get_razorpay_config():
    from dotenv import load_dotenv
    load_dotenv(override=True)
    key_id = get_env_value("RAZORPAY_KEY_ID")
    key_secret = get_env_value("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        return None
    return {"key_id": key_id, "key_secret": key_secret}


def create_razorpay_order(amount_paise, receipt, notes=None):
    config = get_razorpay_config()
    if config is None:
        raise RuntimeError("Razorpay test keys are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env.")

    payload = json.dumps({
        "amount": int(amount_paise),
        "currency": "INR",
        "receipt": receipt,
        "notes": notes or {},
    }).encode("utf-8")
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
