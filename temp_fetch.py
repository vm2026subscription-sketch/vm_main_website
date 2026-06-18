import urllib.request, json
base='https://epaper.aajtak.in/api/public'
urls=[base+'/sites', base+'/editions?site=epaper-aajtak', base+'/edition?site=epaper-aajtak&date=2026-06-09']
for u in urls:
    print('\nURL', u)
    with urllib.request.urlopen(u) as r:
        data = json.load(r)
    print('TYPE', type(data).__name__, 'LEN', len(data) if isinstance(data, list) else 'N/A')
    print(json.dumps(data, ensure_ascii=False)[:4000])
