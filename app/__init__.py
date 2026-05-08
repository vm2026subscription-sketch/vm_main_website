"""
Vidyarthi Mitra — Flask Application Factory
"""
from flask import Flask

from config import Config
from app.routes import register_blueprints


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize MongoDB indexes
    with app.app_context():
        try:
            from app.utils.mongo import ensure_indexes
            ensure_indexes()
        except Exception as e:
            app.logger.warning(f"MongoDB index setup skipped: {e}")

    # Register all blueprints
    register_blueprints(app)

    return app
