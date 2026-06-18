import urllib.request,re
u='https://epaper.aajtak.in/assets/index-DdcSVtY3.js'
text=urllib.request.urlopen(u).read().decode('utf-8','ignore')
patterns=[re.escape('fetch('), 'api/', 'editions', 'page-', 'thumbnail', 'article', 'news', 'epaper']
print('SEARCHING...')
for pat in patterns:
    print('\nPATTERN', pat)
    m=list(re.finditer(pat, text))
    if m:
        start=max(0,m[0].start()-120)
        end=min(len(text),m[0].end()+200)
        print(text[start:end].replace('\n',' '))
        print('---')
    else:
        print('NO MATCH')
