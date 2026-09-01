# Auto Push Notifications — New ePaper Edition 🔔

When an admin uploads a **new** edition, the backend automatically sends a push
notification to every phone subscribed to the FCM topic **`new_edition`** — no
manual step, no Firebase Console.

This is done **server-side** (the phone can't send pushes to other phones). The
mobile app's job is already done: it subscribes to the `new_edition` topic and
displays whatever notification arrives.

---

## What was added (backend)

In [`epaper_routes.py`](epaper_routes.py), the edition-save endpoint
(`POST /api/epaper/admin/edition`) now, after a successful save:

1. Checks it's a **new** edition (not an edit) and **published**.
2. Uses a `epaper_push_sent` table so all 3 languages of the same date trigger
   **one** notification, not three (dedupe per date).
3. Sends an FCM push to topic `new_edition`:
   > **New ePaper Available 📰** — Aaj ka edition ab padhne ke liye taiyaar hai

Everything is best-effort: if FCM isn't configured or fails, the edition still
saves normally (the push is skipped, never blocks the upload).

---

## One-time setup (2 steps)

### 1. Get the Firebase service-account key
Firebase Console → ⚙️ **Project settings** → **Service accounts** →
**Generate new private key** → download the JSON file.

### 2. Give the server the credentials (pick ONE)

**Option A — inline JSON (recommended for Vercel / serverless):**
Set an env var with the **contents** of the JSON:
```
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...", ... }
```

**Option B — file path (server / VM):**
Put the JSON on the server and point to it:
```
FIREBASE_SERVICE_ACCOUNT=/path/to/serviceKey.json
```

Also install the dependency (already added to `requirements.txt`):
```
pip install firebase-admin
```

That's it. Deploy → the next new edition upload sends a notification to all app
users automatically.

---

## Notes
- **Topic:** `new_edition` — make sure the app subscribes to exactly this string.
- **When it fires:** first time a **new, published** edition of a given date is
  saved. Editing an existing edition does **not** re-notify.
- **Dedupe:** the `epaper_push_sent` table (auto-created) records notified dates.
  To re-send for a date (testing), delete its row:
  `DELETE FROM epaper_push_sent WHERE edition_date = '2026-07-27';`
- **Payload data:** `{ "type": "new_edition", "date": "YYYY-MM-DD" }` — the app
  can use `date` to deep-link straight to that edition.
- **Customise text:** edit `_send_new_edition_notification()` in `epaper_routes.py`.
