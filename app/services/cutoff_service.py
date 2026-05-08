"""
B.Tech cutoff data loading, filtering, prediction, and formatting.
"""
import os
import re

try:
    import pandas as pd
except ImportError:
    pd = None

from app.utils.helpers import clean_college_text
from app.constants.upload_tables import CUTOFF_GENDER_LABELS

_btech_cutoff_cache = None
_btech_cutoff_error = None
_college_website_cache = None


def _get_btech_cutoff_dir():
    from flask import current_app
    return os.path.join(current_app.root_path, "..", "data", "btech")


def normalize_cutoff_columns(dataframe):
    dataframe = dataframe.copy()
    dataframe.columns = (
        dataframe.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("(", "", regex=False)
        .str.replace(")", "", regex=False)
    )
    return dataframe


def load_btech_cutoff_data():
    global _btech_cutoff_cache, _btech_cutoff_error

    if _btech_cutoff_cache is not None or _btech_cutoff_error is not None:
        return _btech_cutoff_cache, _btech_cutoff_error

    if pd is None:
        _btech_cutoff_error = "pandas is not installed. Install requirements to read cutoff data."
        return None, _btech_cutoff_error

    cutoff_dir = _get_btech_cutoff_dir()
    if not os.path.isdir(cutoff_dir):
        _btech_cutoff_error = "B.Tech cutoff data folder is missing."
        return None, _btech_cutoff_error

    frames = []
    for cap_round in (1, 2, 3, 4):
        file_path = os.path.join(cutoff_dir, f"BTECH_OUTPUT_CAP{cap_round}.csv")
        if not os.path.exists(file_path):
            continue
        try:
            frame = pd.read_csv(file_path)
        except Exception as exc:
            _btech_cutoff_error = f"Unable to read {os.path.basename(file_path)}: {exc}"
            return None, _btech_cutoff_error

        frame = normalize_cutoff_columns(frame)
        frame["cap_round_source"] = cap_round
        frames.append(frame)

    if not frames:
        _btech_cutoff_error = "No B.Tech cutoff CSV files were found."
        return None, _btech_cutoff_error

    data = pd.concat(frames, ignore_index=True)
    data["percentile"] = pd.to_numeric(data.get("percentile"), errors="coerce")
    data["rank"] = pd.to_numeric(data.get("rank"), errors="coerce")

    required = ["institute_name", "course_name", "category1", "gender", "percentile"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        _btech_cutoff_error = f"Cutoff data is missing required columns: {', '.join(missing)}"
        return None, _btech_cutoff_error

    group_columns = [
        "institute_code", "institute_name", "course_name",
        "category1", "gender", "status", "university",
    ]
    group_columns = [column for column in group_columns if column in data.columns]
    final_cutoffs = (
        data.dropna(subset=["percentile"])
        .groupby(group_columns, as_index=False)
        .agg(
            final_cutoff=("percentile", "max"),
            best_round_cutoff=("percentile", "min"),
            average_cutoff=("percentile", "mean"),
            volatility=("percentile", "std"),
            best_rank=("rank", "min"),
            cap_rounds=("cap_round_source", lambda values: ", ".join(str(int(v)) for v in sorted(set(values)))),
        )
    )
    round_cutoffs = (
        data.dropna(subset=["percentile"])
        .groupby(group_columns + ["cap_round_source"], as_index=False)["percentile"]
        .max()
        .pivot(index=group_columns, columns="cap_round_source", values="percentile")
        .reset_index()
    )
    round_cutoffs.columns = [
        f"cap_{int(column)}_cutoff" if isinstance(column, (int, float)) else column
        for column in round_cutoffs.columns
    ]
    final_cutoffs = final_cutoffs.merge(round_cutoffs, on=group_columns, how="left")
    final_cutoffs["volatility"] = final_cutoffs["volatility"].fillna(0)
    final_cutoffs["college_key"] = final_cutoffs["institute_name"].astype(str).str.lower()
    final_cutoffs = final_cutoffs.sort_values(["final_cutoff", "institute_name"], ascending=[False, True])

    _btech_cutoff_cache = final_cutoffs
    return _btech_cutoff_cache, None


def cutoff_gender_label(value):
    cleaned = clean_college_text(value).upper()
    return CUTOFF_GENDER_LABELS.get(cleaned, cleaned)


def risk_label_for_gap(gap):
    if gap >= 1:
        return "Safe"
    if gap >= -1:
        return "Borderline"
    if gap >= -3:
        return "Risky"
    return "Reach"


def get_cutoff_options():
    data, error = load_btech_cutoff_data()
    if error or data is None:
        gender_options = [{"value": v, "label": CUTOFF_GENDER_LABELS.get(v, v)} for v in ["G", "L"]]
        return [], ["OPEN", "OBC", "SC", "ST", "EWS", "SEBC"], gender_options, error

    branches = sorted(data["course_name"].dropna().astype(str).unique().tolist())
    categories = sorted(data["category1"].dropna().astype(str).unique().tolist())
    genders = sorted(data["gender"].dropna().astype(str).unique().tolist())
    gender_options = [
        {"value": gender, "label": CUTOFF_GENDER_LABELS.get(gender, gender)}
        for gender in genders
    ]
    return branches, categories, gender_options, None


def format_cutoff_recommendations(rows, student_percentile=None, include_websites=True):
    from app.services.college_service import get_college_website_lookup, find_college_website
    website_lookup = get_college_website_lookup() if include_websites else {}
    recommendations = []
    for _, row in rows.iterrows():
        final_cutoff = float(row.get("final_cutoff") or 0)
        gap = None if student_percentile is None else float(student_percentile) - final_cutoff
        college_name = clean_college_text(row.get("institute_name"))
        recommendations.append({
            "college": college_name,
            "college_code": clean_college_text(row.get("institute_code")),
            "branch": clean_college_text(row.get("course_name")),
            "category": clean_college_text(row.get("category1")),
            "gender": clean_college_text(row.get("gender")),
            "gender_label": cutoff_gender_label(row.get("gender")),
            "status": clean_college_text(row.get("status")),
            "university": clean_college_text(row.get("university")),
            "website": find_college_website(college_name, website_lookup),
            "final_cutoff": round(final_cutoff, 4),
            "cap_1_cutoff": round(float(row.get("cap_1_cutoff")), 4) if not pd.isna(row.get("cap_1_cutoff")) else None,
            "cap_2_cutoff": round(float(row.get("cap_2_cutoff")), 4) if not pd.isna(row.get("cap_2_cutoff")) else None,
            "cap_3_cutoff": round(float(row.get("cap_3_cutoff")), 4) if not pd.isna(row.get("cap_3_cutoff")) else None,
            "cap_4_cutoff": round(float(row.get("cap_4_cutoff")), 4) if not pd.isna(row.get("cap_4_cutoff")) else None,
            "best_round_cutoff": round(float(row.get("best_round_cutoff") or 0), 4),
            "average_cutoff": round(float(row.get("average_cutoff") or 0), 4),
            "best_rank": int(row.get("best_rank")) if not pd.isna(row.get("best_rank")) else None,
            "cap_rounds": clean_college_text(row.get("cap_rounds")),
            "gap": round(gap, 4) if gap is not None else None,
            "risk_label": risk_label_for_gap(gap) if gap is not None else "Top Cutoff",
        })
    return recommendations


def get_top_cutoff_colleges(limit=20, branch=None, category=None, gender=None):
    data, error = load_btech_cutoff_data()
    if error or data is None:
        return [], error

    filtered = data.copy()
    if branch:
        filtered = filtered[filtered["course_name"].astype(str) == branch]
    if category:
        filtered = filtered[filtered["category1"].astype(str).str.upper() == category.upper()]
    if gender:
        filtered = filtered[filtered["gender"].astype(str).str.upper() == gender.upper()]

    if filtered.empty:
        return [], "No cutoff rows matched those filters."

    top_rows = (
        filtered.sort_values(["final_cutoff", "institute_name"], ascending=[False, True])
        .drop_duplicates(subset=["college_key"])
        .head(limit)
    )
    return format_cutoff_recommendations(top_rows), None


def get_full_cutoff_colleges(branch=None, category=None, gender=None, page=1, per_page=100):
    data, error = load_btech_cutoff_data()
    if error or data is None:
        return [], 0, error

    filtered = data.copy()
    if branch:
        filtered = filtered[filtered["course_name"].astype(str) == branch]
    if category:
        filtered = filtered[filtered["category1"].astype(str).str.upper() == category.upper()]
    if gender:
        filtered = filtered[filtered["gender"].astype(str).str.upper() == gender.upper()]

    if filtered.empty:
        return [], 0, "No cutoff rows matched those filters."

    ranked = filtered.sort_values(["final_cutoff", "institute_name"], ascending=[False, True])
    total = len(ranked)
    page = max(1, int(page or 1))
    per_page = int(per_page or 100)
    start = (page - 1) * per_page
    end = start + per_page

    return format_cutoff_recommendations(ranked.iloc[start:end]), total, None


def predict_colleges_from_cutoffs(percentile, category, gender, branch, page=1, per_page=20):
    data, error = load_btech_cutoff_data()
    if error or data is None:
        return [], 0, error

    filtered = data.copy()
    if branch:
        filtered = filtered[filtered["course_name"].astype(str) == branch]
    if category:
        filtered = filtered[filtered["category1"].astype(str).str.upper() == category.upper()]
    if gender:
        filtered = filtered[filtered["gender"].astype(str).str.upper() == gender.upper()]

    if filtered.empty:
        return [], 0, "No cutoff rows matched those filters."

    filtered = filtered.copy()
    filtered["gap"] = float(percentile) - filtered["final_cutoff"]
    filtered["sort_bucket"] = filtered["gap"].apply(lambda v: 0 if v >= 0 else 1)
    filtered["below_gap"] = filtered["gap"].apply(lambda v: v if v < 0 else 0)
    ranked = filtered.sort_values(
        ["sort_bucket", "final_cutoff", "below_gap"],
        ascending=[True, False, False],
    ).drop_duplicates(subset=["college_key"])

    total = len(ranked)
    page = max(1, int(page or 1))
    per_page = int(per_page or 20)
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = ranked.iloc[start:end]

    return format_cutoff_recommendations(page_rows, student_percentile=percentile), total, None
