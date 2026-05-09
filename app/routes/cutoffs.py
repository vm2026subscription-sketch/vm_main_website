"""
Cutoff routes: predictor, top colleges, payment, full list.
"""
import secrets
import time

from flask import Blueprint, jsonify, render_template, request, session
from urllib.error import HTTPError, URLError

from app.services.cutoff_service import (
    cutoff_gender_label,
    get_cutoff_options,
    get_full_cutoff_colleges,
    get_top_cutoff_colleges,
    predict_colleges_from_cutoffs,
)
from app.services.payment_service import (
    create_razorpay_order,
    get_razorpay_config,
    verify_razorpay_payment_signature,
)

cutoffs_bp = Blueprint("cutoffs", __name__)

FULL_CUTOFF_PRICE_RUPEES = 100
FULL_CUTOFF_PRICE_PAISE = FULL_CUTOFF_PRICE_RUPEES * 100


@cutoffs_bp.route("/cutoffs")
def cutoffs():
    branches, categories, genders, options_error = get_cutoff_options()
    top_colleges, top_error = get_top_cutoff_colleges(limit=20)
    return render_template(
        "pages/cutoffs.html",
        branches=branches, categories=categories, genders=genders,
        top_colleges=top_colleges, error=options_error or top_error,
    )


@cutoffs_bp.route("/api/college-predictor", methods=["POST"])
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
        page = max(1, int(payload.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(payload.get("per_page", 20))
    except (TypeError, ValueError):
        per_page = 20
    per_page = per_page if per_page in {20, 50, 100} else 20

    recommendations, total_matches, error = predict_colleges_from_cutoffs(
        percentile=percentile, category=category, gender=gender,
        branch=branch, page=page, per_page=per_page,
    )
    if error:
        return jsonify({"success": False, "error": error, "recommendations": []}), 200

    total_pages = max(1, (total_matches + per_page - 1) // per_page) if total_matches else 1
    return jsonify({
        "success": True,
        "student_input": {
            "percentile": percentile, "category": category,
            "gender": gender, "gender_label": cutoff_gender_label(gender), "branch": branch,
        },
        "total_matches": total_matches,
        "pagination": {
            "page": page, "per_page": per_page, "total_pages": total_pages,
            "has_prev": page > 1, "has_next": page < total_pages,
        },
        "recommendations": recommendations,
    })


@cutoffs_bp.route("/api/top-cutoff-colleges", methods=["POST"])
def api_top_cutoff_colleges():
    payload = request.get_json(silent=True) or {}
    branch = str(payload.get("branch", "")).strip()
    category = str(payload.get("category", "")).strip().upper()
    gender = str(payload.get("gender", "")).strip().upper()

    recommendations, error = get_top_cutoff_colleges(
        limit=20, branch=branch or None, category=category or None, gender=gender or None)
    if error:
        return jsonify({"success": False, "error": error, "recommendations": []}), 200
    return jsonify({
        "success": True,
        "filters": {"branch": branch, "category": category, "gender": gender,
                     "gender_label": cutoff_gender_label(gender) if gender else ""},
        "locked_full_list": True,
        "recommendations": recommendations,
    })


@cutoffs_bp.route("/api/cutoff-payment/order", methods=["POST"])
def api_cutoff_payment_order():
    payload = request.get_json(silent=True) or {}
    filters = {
        "branch": str(payload.get("branch", "")).strip(),
        "category": str(payload.get("category", "")).strip().upper(),
        "gender": str(payload.get("gender", "")).strip().upper(),
    }
    receipt = f"cutoff_{secrets.token_hex(8)}"
    notes = {"product": "full_cutoff_list", "branch": filters["branch"][:200],
             "category": filters["category"][:50], "gender": filters["gender"][:20]}
    try:
        order = create_razorpay_order(FULL_CUTOFF_PRICE_PAISE, receipt, notes=notes)
    except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 200

    session["pending_cutoff_order"] = {
        "order_id": order.get("id"), "amount": FULL_CUTOFF_PRICE_PAISE,
        "filters": filters, "created_at": int(time.time()),
    }
    config = get_razorpay_config()
    return jsonify({
        "success": True, "key_id": config["key_id"] if config else "",
        "order": order, "amount_rupees": FULL_CUTOFF_PRICE_RUPEES, "filters": filters,
    })


@cutoffs_bp.route("/api/cutoff-payment/verify", methods=["POST"])
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

    session["full_cutoff_unlocked"] = {
        "payment_id": payment_id, "order_id": order_id,
        "filters": pending_order.get("filters", {}), "unlocked_at": int(time.time()),
    }
    session.pop("pending_cutoff_order", None)
    return jsonify({"success": True, "message": "Full cutoff list unlocked."})


@cutoffs_bp.route("/api/full-cutoff-colleges", methods=["POST"])
def api_full_cutoff_colleges():
    unlocked = session.get("full_cutoff_unlocked")
    if not unlocked:
        return jsonify({"success": False, "payment_required": True,
                        "error": "Please complete payment to unlock the full cutoff list."}), 402

    payload = request.get_json(silent=True) or {}
    branch = str(payload.get("branch", "")).strip()
    category = str(payload.get("category", "")).strip().upper()
    gender = str(payload.get("gender", "")).strip().upper()
    try:
        page = max(1, int(payload.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(payload.get("per_page", 100))
    except (TypeError, ValueError):
        per_page = 100
    per_page = per_page if per_page in {100, 250, 500} else 100

    recommendations, total_matches, error = get_full_cutoff_colleges(
        branch=branch or None, category=category or None, gender=gender or None,
        page=page, per_page=per_page)
    if error:
        return jsonify({"success": False, "error": error, "recommendations": []}), 200

    total_pages = max(1, (total_matches + per_page - 1) // per_page) if total_matches else 1
    return jsonify({
        "success": True, "unlocked": True, "total_matches": total_matches,
        "pagination": {"page": max(1, page), "per_page": per_page,
                        "total_pages": total_pages, "has_prev": page > 1, "has_next": page < total_pages},
        "recommendations": recommendations,
    })
