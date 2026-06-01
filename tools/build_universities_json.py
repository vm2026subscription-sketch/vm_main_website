import os
import sys
import json
import re
import urllib.request
import base64

# Ensure we can import from app.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import UNIVERSITIES_DATA

OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data", "universities.json")

# State and City mapping rules for normalization
STATES_MAP = {
    "andhra pradesh": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chhattisgarh": "Chhattisgarh",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "jammu and kashmir": "Jammu & Kashmir",
    "jammu & kashmir": "Jammu & Kashmir",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "madhya pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "west bengal": "West Bengal",
    "delhi": "Delhi",
    "chandigarh": "Punjab",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry"
}

CITIES_TO_STATES = {
    "mumbai": ("Mumbai", "Maharashtra"),
    "pune": ("Pune", "Maharashtra"),
    "nagpur": ("Nagpur", "Maharashtra"),
    "aurangabad": ("Aurangabad", "Maharashtra"),
    "kolhapur": ("Kolhapur", "Maharashtra"),
    "solapur": ("Solapur", "Maharashtra"),
    "amravati": ("Amravati", "Maharashtra"),
    "nashik": ("Nashik", "Maharashtra"),
    "delhi": ("Delhi", "Delhi"),
    "new delhi": ("Delhi", "Delhi"),
    "noida": ("Noida", "Uttar Pradesh"),
    "greater noida": ("Noida", "Uttar Pradesh"),
    "ghaziabad": ("Ghaziabad", "Uttar Pradesh"),
    "bangalore": ("Bangalore", "Karnataka"),
    "bengaluru": ("Bangalore", "Karnataka"),
    "manipal": ("Manipal", "Karnataka"),
    "chennai": ("Chennai", "Tamil Nadu"),
    "vellore": ("Vellore", "Tamil Nadu"),
    "coimbatore": ("Coimbatore", "Tamil Nadu"),
    "jaipur": ("Jaipur", "Rajasthan"),
    "pilani": ("Pilani", "Rajasthan"),
    "indore": ("Indore", "Madhya Pradesh"),
    "bhopal": ("Bhopal", "Madhya Pradesh"),
    "kolkata": ("Kolkata", "West Bengal"),
    "ahmedabad": ("Ahmedabad", "Gujarat"),
    "gandhinagar": ("Gandhinagar", "Gujarat"),
    "hyderabad": ("Hyderabad", "Telangana"),
    "secunderabad": ("Hyderabad", "Telangana"),
    "amritsar": ("Amritsar", "Punjab"),
    "ludhiana": ("Ludhiana", "Punjab"),
    "jalandhar": ("Jalandhar", "Punjab"),
    "patiala": ("Patiala", "Punjab"),
    "kurukshetra": ("Kurukshetra", "Haryana"),
    "gurgaon": ("Gurugram", "Haryana"),
    "gurugram": ("Gurugram", "Haryana"),
    "varanasi": ("Varanasi", "Uttar Pradesh"),
    "aligarh": ("Aligarh", "Uttar Pradesh"),
    "lucknow": ("Lucknow", "Uttar Pradesh"),
    "kanpur": ("Kanpur", "Uttar Pradesh"),
    "dehradun": ("Dehradun", "Uttarakhand"),
    "roorkee": ("Roorkee", "Uttarakhand"),
    "patna": ("Patna", "Bihar"),
    "ranchi": ("Ranchi", "Jharkhand"),
    "bhubaneswar": ("Bhubaneswar", "Odisha"),
    "guwahati": ("Guwahati", "Assam"),
    "trivandrum": ("Trivandrum", "Kerala"),
    "kochi": ("Kochi", "Kerala"),
    "calicut": ("Calicut", "Kerala")
}

def get_initials(name):
    # Remove Dr. or common starting prefixes
    cleaned = re.sub(r'^dr\.\s+', '', name, flags=re.IGNORECASE).strip()
    
    # 1. Look for capital letters in the cleaned name
    capitals = "".join([c for c in cleaned if c.isupper()])
    
    # Filter out U (University), I (Institute), T (Technology) from capitals if we have other letters
    if len(capitals) >= 2:
        filtered_caps = "".join([c for c in capitals if c not in ('U', 'I', 'T')])
        if len(filtered_caps) >= 2:
            return filtered_caps[:3]
        return capitals[:3]
        
    # 2. Fallback: split by words
    words = [w for w in re.split(r'[^a-zA-Z]+', cleaned) if w]
    stop_words = {"of", "and", "the", "for", "university", "institute", "technology", "sciences", "management", "science", "college", "school"}
    filtered = [w for w in words if w.lower() not in stop_words]
    if not filtered:
        filtered = words
    
    initials = "".join([w[0].upper() for w in filtered[:3]])
    return initials if initials else cleaned[:2].upper()

def generate_svg_logo(name, stream, slug):
    initials = get_initials(name)
    
    # Gradients colored by Stream focus
    gradients = {
        "Technology": ("#1e3a8a", "#06b6d4"), # Blue to Cyan
        "Management": ("#581c87", "#ec4899"), # Purple to Pink
        "Medical": ("#0f766e", "#10b981"),    # Teal to Emerald
        "Law": ("#7f1d1d", "#f59e0b"),        # Burgundy to Gold
        "Creative": ("#9d174d", "#f97316"),   # Rose to Orange
        "Aviation": ("#312e81", "#38bdf8"),   # Indigo to Sky
        "General": ("#ea580c", "#eab308")     # Orange to Yellow
    }
    
    color1, color2 = gradients.get(stream, gradients["General"])
    
    # Set font size dynamically based on length of initials
    if len(initials) == 1:
        font_size = "48px"
    elif len(initials) == 2:
        font_size = "40px"
    elif len(initials) == 3:
        font_size = "34px"
    else:
        font_size = "28px"
        
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
  <defs>
    <linearGradient id="grad-{slug}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{color1};stop-opacity:1" />
      <stop offset="100%" style="stop-color:{color2};stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="20" fill="url(#grad-{slug})" />
  <path d="M0 0 L60 0 L0 60 Z" fill="white" opacity="0.05" />
  <circle cx="100" cy="100" r="40" fill="white" opacity="0.04" />
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#ffffff" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="{font_size}" font-weight="800" letter-spacing="0.5">{initials}</text>
</svg>"""

    encoded = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{encoded}"

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def guess_location_and_state(name, raw_state):
    name_lower = name.lower()
    
    # 1. Search in CITIES_TO_STATES using name text
    for city, (city_name, state_name) in CITIES_TO_STATES.items():
        if city in name_lower:
            return city_name, state_name
            
    # 2. Inspect raw_state if present
    if raw_state:
        raw_state_lower = str(raw_state).lower().strip()
        # Check if it is a known city
        if raw_state_lower in CITIES_TO_STATES:
            return CITIES_TO_STATES[raw_state_lower]
        # Check if it is a known state
        if raw_state_lower in STATES_MAP:
            return "General", STATES_MAP[raw_state_lower]
            
    # 3. Default fallbacks
    return "General", "India"

def guess_stream(name):
    n = name.lower()
    if any(x in n for x in ["technology", "tech", "science", "engineering", "iit", "iiit", "nit", "computer"]):
        return "Technology"
    if any(x in n for x in ["management", "business", "iim", "mba", "economics", "commerce", "administration"]):
        return "Management"
    if any(x in n for x in ["medical", "health", "dental", "pharm", "aiims", "nursing", "ayurved", "homeopath"]):
        return "Medical"
    if any(x in n for x in ["law", "legal", "nlu"]):
        return "Law"
    if any(x in n for x in ["fashion", "design", "art", "music", "fine arts"]):
        return "Creative"
    if any(x in n for x in ["aviation", "aeronaut"]):
        return "Aviation"
    return "General"

def guess_type(name):
    n = name.lower()
    if any(x in n for x in ["indian institute of", "national institute of", "central", "government", "state", "all india institute"]):
        return "Government"
    if any(x in n for x in ["private", "deemed", "symbiosis", "amity", "christ", "manipal", "nirma"]):
        if "deemed" in n:
            return "Deemed"
        return "Private"
    return "Government"

def fetch_and_merge():
    # Build dictionary of existing universities by slug for quick lookup
    merged = {}
    
    # Load and upgrade existing universities
    for u in UNIVERSITIES_DATA:
        slug = u["slug"]
        stream = u["stream"]
        # Generate SVG initials-based logo as fallback
        fallback_logo = generate_svg_logo(u["name"], stream, slug)
        
        source_url = u.get("source_url", "")
        domain = ""
        if source_url:
            from urllib.parse import urlparse
            domain = urlparse(source_url).netloc
            if domain.startswith('www.'):
                domain = domain[4:]
        
        # Use gstatic API that 404s on missing icons so we can use onerror
        if domain:
            logo = f"https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://{domain}&size=256"
        else:
            logo = fallback_logo
            
        merged[slug] = {
            "slug": slug,
            "name": u["name"],
            "location": u["location"],
            "state": u["state"],
            "type": u["type"],
            "stream": stream,
            "nirf": u["nirf"],
            "source_url": source_url,
            "logo_url": logo,
            "fallback_logo": fallback_logo
        }
        
    print(f"Loaded and verified {len(merged)} existing university profiles.")

    # Fetch from HipoLabs API
    api_url = "http://universities.hipolabs.com/search?country=india"
    print(f"Fetching from: {api_url}")
    
    try:
        with urllib.request.urlopen(api_url, timeout=30) as response:
            external_data = json.loads(response.read().decode('utf-8'))
        print(f"Fetched {len(external_data)} university profiles from public API.")
    except Exception as e:
        print(f"Error fetching from API: {e}")
        return

    added_count = 0
    for item in external_data:
        name = item.get("name")
        if not name:
            continue
            
        slug = slugify(name)
        
        # Skip if already exists in our detailed data
        if slug in merged:
            continue
            
        # Parse fields
        web_pages = item.get("web_pages", [])
        source_url = web_pages[0] if web_pages else ""
        
        raw_state = item.get("state-province")
        city, state = guess_location_and_state(name, raw_state)
        
        stream = guess_stream(name)
        utype = guess_type(name)
        
        # Generate SVG initials-based logo as fallback
        fallback_logo = generate_svg_logo(name, stream, slug)
        
        domain = ""
        if source_url:
            from urllib.parse import urlparse
            domain = urlparse(source_url).netloc
            if domain.startswith('www.'):
                domain = domain[4:]
        
        # Use gstatic API that 404s on missing icons so we can use onerror
        if domain:
            logo_url = f"https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://{domain}&size=256"
        else:
            logo_url = fallback_logo
        
        new_uni = {
            "slug": slug,
            "name": name,
            "location": city,
            "state": state,
            "type": utype,
            "stream": stream,
            "nirf": "N/A",
            "source_url": source_url,
            "logo_url": logo_url,
            "fallback_logo": fallback_logo
        }
        
        merged[slug] = new_uni
        added_count += 1
        
    print(f"Added {added_count} new university records.")
    
    # Save output sorted by name
    sorted_universities = sorted(merged.values(), key=lambda x: x["name"])
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted_universities, f, indent=4)
        
    print(f"Successfully saved {len(sorted_universities)} total universities to {OUTPUT_PATH}")

if __name__ == "__main__":
    fetch_and_merge()
