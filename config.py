"""
Centralized application configuration.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""

    SECRET_KEY = (
        os.getenv("FLASK_SECRET_KEY", "").strip()
        or os.getenv("SECRET_KEY", "").strip()
        or "vidyarthi-mitra-dev-key"
    )
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB upload limit
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # MongoDB
    MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "vm_main").strip()

    # External services
    VMADMIN_BASE_URL = os.getenv("VMADMIN_BASE_URL", "").strip().rstrip("/")

    # Database
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
    SUPABASE_POSTGRES_URL = (
        os.getenv("SUPABASE_POSTGRES_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )

    # Cutoff pricing
    FULL_CUTOFF_PRICE_RUPEES = 100
    FULL_CUTOFF_PRICE_PAISE = FULL_CUTOFF_PRICE_RUPEES * 100

    # Courses cache
    COURSES_CACHE_TTL_SECONDS = int(os.getenv("COURSES_CACHE_TTL_SECONDS", "300") or 300)
