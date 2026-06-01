import json
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import time

def search_bing_image(query):
    url = f"https://www.bing.com/images/search?q={query.replace(' ', '+')}+logo"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for a in soup.find_all('a', class_='iusc'):
            m = a.get('m')
            if m:
                try:
                    data = json.loads(m)
                    if data.get('murl'):
                        return data['murl']
                except Exception:
                    pass
    except Exception as e:
        return None
    return None

def run():
    print("Reading missing logos list...")
    with open('missing_logos.txt', 'r') as f:
        missing_names = set(line.strip() for line in f if line.strip())

    print("Reading universities.json...")
    with open('data/universities.json', 'r') as f:
        data = json.load(f)

    unis_to_process = [u for u in data if u['name'] in missing_names and "gstatic" in u.get('logo_url', '')]
    print(f"Starting Bing Image scrape for {len(unis_to_process)} universities...")

    def process(uni):
        logo = search_bing_image(uni['name'])
        if logo:
            uni['logo_url'] = logo
            return True
        return False

    success_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process, u): u for u in unis_to_process}
        for future in concurrent.futures.as_completed(futures):
            uni = futures[future]
            try:
                if future.result():
                    success_count += 1
                    print(f"Found logo for {uni['name']}")
                else:
                    print(f"Failed to find logo for {uni['name']}")
            except Exception as e:
                print(f"Error on {uni['name']}: {e}")

    print(f"\nSuccessfully found {success_count} new logos from Bing!")
    
    with open('data/universities.json', 'w') as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    run()
