"""
ePaper End-to-End Diagnostic Script
====================================
Tests: login -> create -> save -> fetch -> publish -> verify visibility
Run: .venv\Scripts\python.exe tools\epaper_diagnostic.py
"""
import sys, json, time, re, requests

BASE = "http://127.0.0.1:5000"
SESSION = requests.Session()
TEST_DATE = "2026-07-10"
TEST_LANG = "Hindi"
TEST_NAME = "Diagnostic Test Edition"
results = {}

def sep(t=""):
    print("\n" + "=" * 60)
    if t:
        print("  " + t)
        print("=" * 60)

def ok(m):    print("  [PASS] " + m)
def fail(m):  print("  [FAIL] " + m)
def warn(m):  print("  [WARN] " + m)
def step(m):  print("\n  >>> " + m)

# ── Step 0: health ──────────────────────────────────────────────────────────
sep("STEP 0 - Server Health")
try:
    r = SESSION.get(BASE + "/", timeout=5)
    ok("Server up HTTP " + str(r.status_code))
except Exception as e:
    fail("Server down: " + str(e))
    sys.exit(1)

# ── Step 1: Login ────────────────────────────────────────────────────────────
sep("STEP 1 - Admin Login")
step("Get CSRF from login page")
lp = SESSION.get(BASE + "/epaper-admin/login", timeout=5)
print("  Login page HTTP " + str(lp.status_code))

csrf_pat = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
m = csrf_pat.search(lp.text)
csrf = m.group(1) if m else None
print("  CSRF found: " + str(bool(csrf)))

step("POST login")
r = SESSION.post(
    BASE + "/epaper-admin/login",
    data={"username": "admin123@gmail.com", "password": "vm@2026", "csrf_token": csrf or ""},
    timeout=10, allow_redirects=True,
)
print("  Final URL: " + r.url + "  HTTP " + str(r.status_code))
logged_in = "/epaper-admin" in r.url and "login" not in r.url.split("?")[0]
if logged_in:
    ok("Login successful")
else:
    warn("Login uncertain, URL: " + r.url)

# Get API CSRF from admin page meta tag
admin_pg = SESSION.get(BASE + "/epaper-admin", timeout=5)
csrf_meta_pat = re.compile(r'name="csrf-token"\s+content="([^"]+)"')
m2 = csrf_meta_pat.search(admin_pg.text)
api_csrf = m2.group(1) if m2 else csrf
print("  API CSRF: " + str(bool(api_csrf)))
hdrs = {"X-CSRFToken": api_csrf} if api_csrf else {}

# ── Step 2: Existing editions ────────────────────────────────────────────────
sep("STEP 2 - Existing Editions")
r = SESSION.get(BASE + "/api/epaper/editions", timeout=10)
print("  HTTP " + str(r.status_code))
eds = r.json().get("editions", []) if r.ok else []
ok("Total editions: " + str(len(eds)))
for e in eds[:3]:
    print("    " + str(e.get("date")) + " [" + str(e.get("language")) + "] pub=" + str(e.get("published")) + " pages=" + str(e.get("total_pages", 0)))

# ── Step 3: Create draft edition ─────────────────────────────────────────────
sep("STEP 3 - Create Draft Edition")
payload = {
    "date": TEST_DATE,
    "name": TEST_NAME,
    "language": TEST_LANG,
    "published": False,
    "masthead_image_url": "",
    "footer_links": [],
    "pages": [
        {
            "page_number": 1,
            "category": "Test Front Page",
            "date_range": "10 July 2026",
            "image_path": "",
            "page_image_url": "",
            "blocks": [
                {
                    "id": 999001, "type": "article",
                    "x": 50, "y": 100, "w": 300, "h": 150,
                    "width": 300, "height": 150,
                    "article_id": 999001,
                    "headline": "Diagnostic Test Headline",
                    "sub_headline": "Sub headline text",
                    "body_text": "Test body text.",
                    "body_html": "<p>Test body text.</p>",
                    "author": "Diagnostic Bot",
                    "category_label": "Test",
                    "image_url": "", "gallery": [],
                    "border_width": 0, "border_radius": 0,
                    "border_color": "#e41e26", "border_style": "solid",
                    "goto_page": None,
                }
            ],
        }
    ],
}

r = SESSION.post(BASE + "/api/epaper/admin/edition", json=payload, headers=hdrs, timeout=15)
print("  HTTP " + str(r.status_code))
try:
    rj = r.json()
    print("  Response: " + str(rj))
    if r.status_code in (200, 201) and rj.get("success"):
        ok("Edition created!")
        results["created"] = True
    else:
        fail("Creation failed: " + str(rj))
        results["created"] = False
except Exception as ex:
    fail("Parse error: " + str(ex) + "  raw: " + r.text[:300])
    results["created"] = False

# ── Step 4: Admin fetch verification ─────────────────────────────────────────
sep("STEP 4 - Admin Fetch Verification")
r = SESSION.get(BASE + "/api/epaper/admin/edition/" + TEST_DATE + "?lang=" + TEST_LANG, timeout=10)
print("  HTTP " + str(r.status_code))
if r.ok:
    d = r.json()
    pg_count = len(d.get("pages", []))
    ok("Admin fetch OK - date=" + str(d.get("date")) + " pub=" + str(d.get("published")) + " pages=" + str(pg_count))
    blks = d.get("pages", [{}])[0].get("blocks", []) if d.get("pages") else []
    if blks:
        b = blks[0]
        headline = b.get("headline", "")
        print("  Block[0] headline: " + headline)
        if headline == "Diagnostic Test Headline":
            ok("Block content correct!")
            results["persist"] = True
        else:
            fail("Block headline MISMATCH: got '" + headline + "'")
            results["persist"] = False
    else:
        fail("Page 1 has no blocks after save!")
        results["persist"] = False
elif r.status_code == 404:
    fail("Edition NOT FOUND (404) after save!")
    results["persist"] = False
else:
    fail("HTTP " + str(r.status_code) + ": " + r.text[:200])
    results["persist"] = False

# ── Step 5: Draft visibility ──────────────────────────────────────────────────
sep("STEP 5 - Draft Visibility")
r = SESSION.get(BASE + "/api/epaper/editions", timeout=10)
eds2 = r.json().get("editions", []) if r.ok else []
found = None
for e in eds2:
    if e.get("date") == TEST_DATE and e.get("language") == TEST_LANG:
        found = e
        break
if found:
    ok("Draft in editions list: published=" + str(found.get("published")))
else:
    fail("Draft NOT in editions list!")

r2 = SESSION.get(BASE + "/api/epaper/edition/" + TEST_DATE + "?lang=" + TEST_LANG, timeout=10)
print("  Public API HTTP " + str(r2.status_code))
if r2.status_code == 404:
    ok("Draft correctly hidden on public API (404)")
elif r2.ok:
    warn("Draft EXPOSED on public API (should be hidden)")
else:
    warn("Unexpected HTTP " + str(r2.status_code))

# ── Step 6: Update with 2 pages ──────────────────────────────────────────────
sep("STEP 6 - Update With 2 Pages")
page2 = {
    "page_number": 2,
    "category": "Education",
    "date_range": "10 July 2026",
    "image_path": "", "page_image_url": "",
    "blocks": [
        {
            "id": 999002, "type": "article",
            "x": 10, "y": 10, "w": 400, "h": 200,
            "width": 400, "height": 200,
            "article_id": 999002,
            "headline": "Education Article",
            "sub_headline": "Edu sub",
            "body_text": "Page 2 body.",
            "body_html": "<p>Page 2 body.</p>",
            "author": "Bot", "category_label": "Education",
            "image_url": "", "gallery": [],
            "border_width": 0, "border_radius": 0,
            "border_color": "#e41e26", "border_style": "solid",
            "goto_page": None,
        }
    ],
}
payload2 = dict(payload)
payload2["pages"] = payload["pages"] + [page2]
r = SESSION.post(BASE + "/api/epaper/admin/edition", json=payload2, headers=hdrs, timeout=15)
print("  HTTP " + str(r.status_code))
if r.ok and r.json().get("success"):
    ok("Update with 2 pages OK")
else:
    fail("Update failed: " + r.text[:100])

r = SESSION.get(BASE + "/api/epaper/admin/edition/" + TEST_DATE + "?lang=" + TEST_LANG, timeout=10)
if r.ok:
    pgs = r.json().get("pages", [])
    ok("After update: " + str(len(pgs)) + " pages")
    for i, pg in enumerate(pgs):
        print("  Page " + str(i + 1) + " (" + pg.get("category", "") + "): blocks=" + str(len(pg.get("blocks", []))))
    results["multi_page"] = len(pgs) >= 2
else:
    fail("Re-fetch failed HTTP " + str(r.status_code))
    results["multi_page"] = False

# ── Step 7: Publish ───────────────────────────────────────────────────────────
sep("STEP 7 - Publish Edition")
r = SESSION.post(
    BASE + "/api/epaper/admin/edition/" + TEST_DATE + "/publish?lang=" + TEST_LANG,
    json={"published": True}, headers=hdrs, timeout=10,
)
print("  HTTP " + str(r.status_code) + "  " + str(r.json()))
if r.ok and r.json().get("success"):
    ok("Published!")
else:
    fail("Publish failed")

r = SESSION.get(BASE + "/api/epaper/edition/" + TEST_DATE + "?lang=" + TEST_LANG, timeout=10)
print("  Public API after publish: HTTP " + str(r.status_code))
if r.ok:
    d = r.json()
    ok("Public visibility confirmed: name=" + str(d.get("name")) + " pages=" + str(len(d.get("pages", []))))
    results["publish"] = True
else:
    fail("Still not public after publish! HTTP " + str(r.status_code))
    results["publish"] = False

# ── Step 8: Viewer page HTML ───────────────────────────────────────────────────
sep("STEP 8 - Viewer Page HTML")
r = SESSION.get(BASE + "/epaper/" + TEST_DATE, timeout=15)
print("  HTTP " + str(r.status_code))
if r.ok:
    has_date = TEST_DATE in r.text
    has_data = "Diagnostic Test" in r.text or "initial_edition_json" in r.text
    if has_date: ok("Date found in viewer HTML")
    else: warn("Date NOT found in viewer HTML")
    if has_data: ok("Edition data embedded in viewer HTML")
    else: warn("Edition data NOT obviously embedded")
else:
    fail("Viewer returned HTTP " + str(r.status_code))

# ── Step 9: Simulated refresh ─────────────────────────────────────────────────
sep("STEP 9 - Simulated Refresh")
time.sleep(1)
r = SESSION.get(BASE + "/api/epaper/admin/edition/" + TEST_DATE + "?lang=" + TEST_LANG, timeout=10)
if r.ok:
    d = r.json()
    pgs = d.get("pages", [])
    total_blocks = sum(len(p.get("blocks", [])) for p in pgs)
    ok("After simulated refresh: " + str(len(pgs)) + " pages, " + str(total_blocks) + " total blocks")
    if total_blocks >= 2:
        ok("All blocks persisted correctly!")
        results["refresh"] = True
    else:
        fail("Block count mismatch: expected >=2, got " + str(total_blocks))
        results["refresh"] = False
else:
    fail("Edition MISSING after refresh! HTTP " + str(r.status_code))
    results["refresh"] = False

# ── Step 10: Logout + re-login ────────────────────────────────────────────────
sep("STEP 10 - Logout + Re-Login")
SESSION.get(BASE + "/epaper-admin/logout", timeout=5)
ok("Logged out")
lp2 = SESSION.get(BASE + "/epaper-admin/login", timeout=5)
m3 = csrf_pat.search(lp2.text)
csrf3 = m3.group(1) if m3 else csrf
r = SESSION.post(
    BASE + "/epaper-admin/login",
    data={"username": "admin123@gmail.com", "password": "vm@2026", "csrf_token": csrf3 or ""},
    timeout=10, allow_redirects=True,
)
relogged = "/epaper-admin" in r.url and "login" not in r.url.split("?")[0]
if relogged: ok("Re-login successful")
else: warn("Re-login uncertain: " + r.url)

r = SESSION.get(BASE + "/api/epaper/admin/edition/" + TEST_DATE + "?lang=" + TEST_LANG, timeout=10)
if r.ok:
    d = r.json()
    ok("Edition persists after logout+login: pages=" + str(len(d.get("pages", []))) + " pub=" + str(d.get("published")))
    results["session_persist"] = True
else:
    fail("Edition LOST after logout+login! HTTP " + str(r.status_code))
    results["session_persist"] = False

# ── Step 11: Cleanup ─────────────────────────────────────────────────────────
sep("STEP 11 - Cleanup")
admin_pg2 = SESSION.get(BASE + "/epaper-admin", timeout=5)
m4 = csrf_meta_pat.search(admin_pg2.text)
api_csrf2 = m4.group(1) if m4 else csrf3
h2 = {"X-CSRFToken": api_csrf2} if api_csrf2 else {}
r = SESSION.delete(BASE + "/api/epaper/admin/edition/" + TEST_DATE + "?lang=" + TEST_LANG, headers=h2, timeout=10)
print("  DELETE HTTP " + str(r.status_code))
if r.ok:
    ok("Deleted")
else:
    warn("Delete returned HTTP " + str(r.status_code) + ": " + r.text[:200])

r2 = SESSION.get(BASE + "/api/epaper/admin/edition/" + TEST_DATE + "?lang=" + TEST_LANG, timeout=10)
if r2.status_code == 404:
    ok("Test edition cleaned up (404)")
else:
    warn("Edition still exists? HTTP " + str(r2.status_code))

# ── Summary ───────────────────────────────────────────────────────────────────
sep("FINAL RESULTS")
all_ok = True
for k, v in results.items():
    status = "[PASS]" if v else "[FAIL]"
    print("  " + status + " " + k)
    if not v:
        all_ok = False

print()
print("  Overall: " + ("ALL PASSED" if all_ok else "SOME FAILURES - see above"))
