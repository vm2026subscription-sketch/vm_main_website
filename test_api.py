import urllib.request
import json

try:
    url = 'http://127.0.0.1:5000/api/news?limit=3'
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as response:
        data = json.loads(response.read().decode('utf-8'))
        print(f"Success: {data.get('success')}")
        print(f"Count: {data.get('count')}")
        print(f"Articles: {len(data.get('articles', []))}")
        if data.get('articles'):
            print(f"First article category: {data['articles'][0].get('category')}")
except Exception as e:
    print(f"Error: {e}")
