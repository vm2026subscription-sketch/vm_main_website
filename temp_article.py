import urllib.request, json
u='https://epaper.aajtak.in/api/public/article/11252'
print(u)
with urllib.request.urlopen(u) as f:
    data = json.load(f)
print(json.dumps(data, ensure_ascii=False)[:8000])
