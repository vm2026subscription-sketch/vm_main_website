#!/usr/bin/env python3
"""
Weekly DB Backup - exports epaper tables to timestamped JSON files.

Usage:
    python tools/weekly_backup.py              # local backup only
    python tools/weekly_backup.py --drive      # local + Google Drive upload

Env vars (Google Drive is optional):
    GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON   service account JSON string
    GOOGLE_DRIVE_BACKUP_FOLDER_ID       target Drive folder ID
"""

import os
import sys
import json
import glob
import shutil
import hashlib
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras

# ── Config ────────────────────────────────────────────────────────────
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backups", "weekly")
WEEKS_TO_KEEP = 4

TABLES = [
    {
        "name": "epaper_editions_v2",
        "query": "SELECT edition_date, edition_language, data, updated_at FROM epaper_editions_v2 ORDER BY edition_date DESC, edition_language",
        "row_parser": lambda r: {
            "date": r["edition_date"],
            "language": r["edition_language"],
            "data": json.loads(r["data"]) if isinstance(r["data"], str) else r["data"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        },
    },
    {
        "name": "epaper_edition_backups",
        "query": "SELECT id, edition_date, edition_language, edition_name, pages_count, saved_at, snapshot FROM epaper_edition_backups ORDER BY saved_at DESC LIMIT 200",
        "row_parser": lambda r: {
            "id": r["id"],
            "date": r["edition_date"],
            "language": r["edition_language"],
            "name": r["edition_name"],
            "pages_count": r["pages_count"],
            "saved_at": r["saved_at"].isoformat() if r["saved_at"] else None,
            "snapshot": json.loads(r["snapshot"]) if isinstance(r["snapshot"], str) else r["snapshot"],
        },
    },
    {
        "name": "epaper_editions_store",
        "query": "SELECT id, data, updated_at FROM epaper_editions_store",
        "row_parser": lambda r: {
            "id": r["id"],
            "data": json.loads(r["data"]) if isinstance(r["data"], str) else r["data"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        },
    },
    {
        "name": "epaper_edition_views",
        "query": "SELECT edition_date, edition_language, view_count, updated_at FROM epaper_edition_views ORDER BY edition_date DESC",
        "row_parser": lambda r: {
            "date": r["edition_date"],
            "language": r["edition_language"],
            "view_count": r["view_count"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        },
    },
]


def _get_pg_url():
    url = os.getenv("SUPABASE_POSTGRES_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
    if url and "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _cleanup_old_backups(backup_dir, keep_weeks):
    """Delete backup folders older than keep_weeks."""
    if not os.path.isdir(backup_dir):
        return
    cutoff = datetime.now() - timedelta(weeks=keep_weeks)
    for name in os.listdir(backup_dir):
        folder = os.path.join(backup_dir, name)
        if not os.path.isdir(folder):
            continue
        try:
            folder_date = datetime.strptime(name, "backup_%Y%m%d_%H%M%S")
            if folder_date < cutoff:
                shutil.rmtree(folder)
                print(f"  [cleanup] Removed old backup: {name}")
        except ValueError:
            pass


def _upload_to_drive(folder_path, files):
    """Upload files to Google Drive. Returns list of (filename, drive_id) or empty list."""
    sa_json = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    folder_id = os.getenv("GOOGLE_DRIVE_BACKUP_FOLDER_ID", "").strip()
    if not sa_json or not folder_id:
        print("  [drive] Google Drive vars not set - skipping upload")
        return []

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("  [drive] google-api-python-client not installed - skipping upload")
        print("         Install: pip install google-api-python-client google-auth")
        return []

    try:
        creds_info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"  [drive] Auth failed: {e}")
        return []

    uploaded = []
    for fname in files:
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            file_meta = {"name": fname, "parents": [folder_id]}
            media = MediaFileUpload(fpath, mimetype="application/json", resumable=True)
            result = service.files().create(
                body=file_meta, media_body=media, fields="id"
            ).execute()
            uploaded.append((fname, result.get("id")))
            print(f"  [drive] Uploaded: {fname}")
        except Exception as e:
            print(f"  [drive] Upload failed for {fname}: {e}")

    return uploaded


def run_backup(upload_drive=False):
    """Run the full backup. Returns the backup folder path."""
    pg_url = _get_pg_url()
    if not pg_url:
        print("[backup] ERROR: No Postgres URL configured.")
        sys.exit(1)

    ts = datetime.now().strftime("backup_%Y%m%d_%H%M%S")
    backup_folder = os.path.join(BACKUP_DIR, ts)
    os.makedirs(backup_folder, exist_ok=True)
    print(f"[backup] Starting weekly backup -> {backup_folder}")

    conn = psycopg2.connect(pg_url, connect_timeout=15)
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "files": {},
    }

    try:
        for table_cfg in TABLES:
            name = table_cfg["name"]
            print(f"  [export] {name}...", end=" ", flush=True)
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(table_cfg["query"])
                    rows = cur.fetchall()
                data = [table_cfg["row_parser"](r) for r in rows]
                fname = f"{name}_{ts.replace('backup_', '')}.json"
                fpath = os.path.join(backup_folder, fname)
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                fsize = os.path.getsize(fpath)
                sha = _file_sha256(fpath)
                manifest["tables"][name] = {
                    "rows": len(data),
                    "file": fname,
                    "size_bytes": fsize,
                    "sha256": sha,
                }
                manifest["files"][fname] = {"size_bytes": fsize, "sha256": sha}
                size_kb = fsize / 1024
                print(f"{len(data)} rows -> {fname} ({size_kb:.1f} KB)")
            except Exception as e:
                print(f"FAILED: {e}")
                manifest["tables"][name] = {"error": str(e)}
    finally:
        conn.close()

    # Write manifest
    manifest_path = os.path.join(backup_folder, f"manifest_{ts.replace('backup_', '')}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
    manifest_size = os.path.getsize(manifest_path)
    print(f"  [manifest] {os.path.basename(manifest_path)} ({manifest_size} bytes)")

    # Summary
    total_rows = sum(t.get("rows", 0) for t in manifest["tables"].values())
    total_bytes = sum(t.get("size_bytes", 0) for t in manifest["tables"].values())
    print(f"\n[backup] Done - {total_rows} total rows, {total_bytes / 1024:.1f} KB exported")
    print(f"         Location: {backup_folder}")

    # Google Drive upload
    if upload_drive:
        print("\n[backup] Uploading to Google Drive...")
        files_to_upload = list(manifest["files"].keys()) + [os.path.basename(manifest_path)]
        uploaded = _upload_to_drive(backup_folder, files_to_upload)
        if uploaded:
            print(f"  [drive] {len(uploaded)} files uploaded successfully")
        else:
            print("  [drive] No files uploaded (check env vars or credentials)")

    # Cleanup old local backups
    _cleanup_old_backups(BACKUP_DIR, WEEKS_TO_KEEP)

    return backup_folder


if __name__ == "__main__":
    do_drive = "--drive" in sys.argv
    run_backup(upload_drive=do_drive)
