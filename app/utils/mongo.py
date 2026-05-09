"""
MongoDB connection utility — lazy singleton using pymongo.
"""
import os

_client = None
_db = None


def get_mongo_client():
    """Return a shared MongoClient instance (lazy init)."""
    global _client
    if _client is None:
        from pymongo import MongoClient

        uri = os.getenv("MONGODB_URI", "").strip()
        if not uri:
            raise RuntimeError(
                "MONGODB_URI is not set. Add it to your .env file."
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _client


def get_mongo_db(db_name=None):
    """Return the application database."""
    global _db
    if _db is None or db_name:
        name = db_name or os.getenv("MONGODB_DB_NAME", "vm_main").strip()
        _db = get_mongo_client()[name]
    return _db


def get_users_collection():
    """Return the users collection with indexes ensured."""
    db = get_mongo_db()
    collection = db["users"]
    return collection


def get_epaper_editions_collection():
    """Return the epaper_editions collection (E-Paper Studio data)."""
    return get_mongo_db()["epaper_editions"]


def get_epaper_legacy_collection():
    """Return the epaper_legacy collection (Legacy VM Admin uploads)."""
    return get_mongo_db()["epaper_legacy"]


def get_upload_collection(table_name):
    """Return a MongoDB collection for Excel upload data."""
    return get_mongo_db()[table_name]


def ensure_indexes():
    """Create required indexes on all collections."""
    users = get_users_collection()
    users.create_index("email", unique=True)
    users.create_index("password_reset_token", sparse=True)

    editions = get_epaper_editions_collection()
    editions.create_index("date", unique=True)

    legacy = get_epaper_legacy_collection()
    legacy.create_index("created_at", unique=False)
