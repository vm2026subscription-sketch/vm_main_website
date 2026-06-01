import json
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import time

def search_wiki(query):
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 1,
        "namespace": 0,
        "format": "json"
    }
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0 (Bot/1.0)"}, timeout=10)
        data = r.json()
        if len(data) > 1 and data[1]:
            return data[1][0]
    except Exception:
        pass
    return None

def get_wiki_logo(name):
    title = search_wiki(name)
    if not title:
        return None
    
    url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    headers = {"User-Agent": "Mozilla/5.0 (Bot/1.0)"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        infobox = soup.find('table', class_='infobox')
        if not infobox:
            return None
        
        img = infobox.find('img')
        if img and img.get('src'):
            src = img['src']
            if src.startswith('//'):
                src = 'https:' + src
            
            if '/thumb/' in src:
                src = src.replace('/thumb/', '/')
                src = src.rsplit('/', 1)[0]
                
            return src
    except Exception:
        return None
    return None

def run():
    print("Reading missing logos list...")
    with open('missing_logos.txt', 'r') as f:
        missing_names = set(line.strip() for line in f if line.strip())

    print(f"Reading universities.json...")
    with open('data/universities.json', 'r') as f:
        data = json.load(f)

    # Process only missing
    unis_to_process = [u for u in data if u['name'] in missing_names]
    print(f"Starting Wikipedia scrape for {len(unis_to_process)} universities...")

    def process(uni):
        logo = get_wiki_logo(uni['name'])
        if logo:
            uni['logo_url'] = logo
            return True
        return False

    success_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process, u): u for u in unis_to_process}
        for future in concurrent.futures.as_completed(futures):
            uni = futures[future]
            try:
                if future.result():
                    success_count += 1
                    print(f"Found logo for {uni['name']}")
            except Exception as e:
                print(f"Error on {uni['name']}: {e}")

    print(f"\nSuccessfully found {success_count} new logos from Wikipedia!")
    
    with open('data/universities.json', 'w') as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    run()
