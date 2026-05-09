"""
College and university routes.
"""
import re

from flask import Blueprint, redirect, render_template, request, url_for

from app.constants.colleges_data import UNIVERSITIES_DATA
from app.services.college_service import (
    fetch_college_state_counts,
    fetch_colleges_by_states,
    fetch_colleges_search,
)

colleges_bp = Blueprint("colleges", __name__)


@colleges_bp.route("/universities")
def universities():
    states = sorted({item["state"] for item in UNIVERSITIES_DATA})
    cities = sorted({item["location"] for item in UNIVERSITIES_DATA})
    types = sorted({item["type"] for item in UNIVERSITIES_DATA})
    streams = sorted({item["stream"] for item in UNIVERSITIES_DATA})
    return render_template(
        "pages/universities.html",
        universities=UNIVERSITIES_DATA,
        states=states, cities=cities, types=types, streams=streams,
    )


@colleges_bp.route("/universities/<slug>")
def university_detail(slug):
    university = next((item for item in UNIVERSITIES_DATA if item["slug"] == slug), None)
    if university is None:
        return redirect(url_for("colleges.universities"))
    return render_template("pages/universities.html", universities=[university], states=[], cities=[], types=[], streams=[])


@colleges_bp.route("/colleges")
def colleges():
    from flask import current_app
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
        current_app.logger.warning("colleges DB error: %s", state_err)

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
            query_page, query_per_page, q=q or None, alpha=alpha or None, state=state_filter or None)
        if db_error:
            current_app.logger.warning("colleges DB error: %s", db_error)
            error = db_error
        if paginate_results:
            total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
            if page > total_pages:
                page = total_pages
                colleges_rows, total, db_error = fetch_colleges_search(
                    page, per_page, q=q or None, alpha=alpha or None, state=state_filter or None)
                if db_error:
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
            current_app.logger.warning("colleges DB error: %s", db_error)
            error = db_error
        buckets = {name: [] for name in state_names}
        for college in colleges_rows:
            buckets.setdefault(college.get("state") or "", []).append(college)
        grouped_states = [
            {"state": row.get("state"), "count": row.get("count", 0), "colleges": buckets.get(row.get("state"), [])}
            for row in page_states
        ]
        pagination_label = "states"
        pagination_start = 1 if state_counts else 0
        pagination_end = len(state_counts)
        total = len(state_counts)

    return render_template(
        "pages/colleges.html",
        colleges=colleges_rows, grouped_states=grouped_states,
        state_counts=state_counts, total_colleges=total_colleges,
        total=total, page=page, per_page=per_page,
        total_pages=total_pages, has_prev=page > 1, has_next=page < total_pages,
        prev_page=page - 1, next_page=page + 1,
        pagination_label=pagination_label,
        pagination_start=pagination_start, pagination_end=pagination_end,
        search_mode=search_mode, query=q, alpha=alpha,
        alphabet=list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        state_filter=state_filter, per_page_options=per_page_options,
        paginate_results=paginate_results, error=error,
    )
