"""
Register all route blueprints with the Flask app.
"""


def register_blueprints(app):
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.articles import articles_bp
    from app.routes.colleges import colleges_bp
    from app.routes.cutoffs import cutoffs_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(colleges_bp)
    app.register_blueprint(cutoffs_bp)

    # Courses blueprint (requires DB)
    try:
        from app.routes.courses import courses_bp
        app.register_blueprint(courses_bp)
    except Exception as exc:
        app.logger.warning("Skipping courses blueprint: %s", exc)

    # News blueprint
    try:
        from app.routes.news import news_bp
        app.register_blueprint(news_bp)
    except Exception as exc:
        app.logger.warning("Skipping news blueprint: %s", exc)

    # E-Paper blueprint
    try:
        from app.routes.epaper import epaper_bp
        app.register_blueprint(epaper_bp)
    except Exception as exc:
        app.logger.warning("Skipping epaper blueprint: %s", exc)
