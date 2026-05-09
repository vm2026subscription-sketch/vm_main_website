"""
Career articles routes.
"""
from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from app.constants.articles_data import ARTICLES, CATEGORIES, get_article_by_id
from app.utils.helpers import build_article_teaser, build_article_paragraphs

articles_bp = Blueprint("articles", __name__)


@articles_bp.route("/articles")
@articles_bp.route("/career-articles")
def articles():
    category = request.args.get("category", "all").strip()
    query = request.args.get("q", "").strip().lower()

    valid_categories = {item["value"] for item in CATEGORIES}
    if category not in valid_categories:
        category = "all"

    filtered_articles = ARTICLES
    if category != "all":
        filtered_articles = [a for a in filtered_articles if a["category"] == category]
    if query:
        filtered_articles = [
            a for a in filtered_articles
            if query in a["title"].lower() or query in a["desc"].lower()
        ]

    list_articles = [{**a, "desc": build_article_teaser(a.get("desc", ""))} for a in filtered_articles]

    return render_template(
        "pages/articles.html",
        articles=list_articles, categories=CATEGORIES,
        active_category=category, query=query, total=len(filtered_articles),
    )


@articles_bp.route("/articles/<int:article_id>")
def article_detail(article_id):
    article = get_article_by_id(article_id)
    if article is None:
        return redirect(url_for("articles.articles"))
    article_detail_data = {**article, "paragraphs": build_article_paragraphs(article.get("desc", ""))}
    return render_template("pages/article_detail.html", article=article_detail_data)


@articles_bp.route("/api/articles")
def api_articles():
    category = request.args.get("category", "all").strip()
    query = request.args.get("q", "").strip().lower()

    valid_categories = {item["value"] for item in CATEGORIES}
    if category not in valid_categories:
        category = "all"

    result = ARTICLES
    if category != "all":
        result = [a for a in result if a["category"] == category]
    if query:
        result = [a for a in result if query in a["title"].lower() or query in a["desc"].lower()]

    return jsonify({"count": len(result), "articles": result})
