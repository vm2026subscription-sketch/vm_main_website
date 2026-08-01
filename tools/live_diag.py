import requests, re, json

BASE = "https://www.vidyarthimitra.org"
s = requests.Session()

# Step 1: Login page + CSRF
print("=== Step 1: Login Page ===")
lp = s.get(BASE + "/epaper-admin/login", timeout=10)
print("HTTP:", lp.status_code)
csrf_pat = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
m = csrf_pat.search(lp.text)
csrf = m.group(1) if m else None
print("CSRF found:", bool(csrf))

# Step 2: POST login
print("\n=== Step 2: Login POST ===")
r = s.post(BASE + "/epaper-admin/login",
    data={"username": "admin123@gmail.com", "password": "vm@2026", "csrf_token": csrf or ""},
    timeout=10, allow_redirects=True)
print("Final URL:", r.url, "| HTTP:", r.status_code)

# Step 3: Admin page CSRF
print("\n=== Step 3: Admin Page ===")
admin_pg = s.get(BASE + "/epaper-admin", timeout=10)
print("Admin page HTTP:", admin_pg.status_code)
csrf_meta = re.compile(r'name="csrf-token"\s+content="([^"]+)"')
m2 = csrf_meta.search(admin_pg.text)
api_csrf = m2.group(1) if m2 else csrf
print("API CSRF found:", bool(api_csrf))

# Step 4: cloudinary-sign endpoint
print("\n=== Step 4: cloudinary-sign API ===")
hdrs = {"Content-Type": "application/json"}
if api_csrf:
    hdrs["X-CSRFToken"] = api_csrf
sign_r = s.post(BASE + "/api/epaper/admin/cloudinary-sign",
    headers=hdrs, json={"resource_type": "image"}, timeout=15)
print("HTTP:", sign_r.status_code)
try:
    print("Response:", json.dumps(sign_r.json(), indent=2))
except Exception:
    print("Raw response:", sign_r.text[:500])
