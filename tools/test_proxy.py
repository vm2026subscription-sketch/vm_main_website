import urllib.request, urllib.parse, sys

target = 'https://drive.google.com/file/d/1PrNmmGFVVnv7kx81jyc2pIgO8lKySu2F/view'
proxy = 'http://127.0.0.1:5000/api/epaper-pdf-proxy?url=' + urllib.parse.quote(target, safe='')
print('PROXY URL:', proxy)
req = urllib.request.Request(proxy, headers={'User-Agent':'vm-test/1.0','Accept':'*/*'})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print('STATUS', r.getcode())
        print('CONTENT-TYPE', r.getheader('Content-Type'))
        data = r.read(512)
        print('FIRST 512 BYTES (as bytes):', data[:64])
        try:
            text = data.decode('utf-8', errors='ignore')
            print('\nSAMPLE TEXT:\n', text[:400])
        except Exception as e:
            print('Could not decode sample bytes:', e)
except Exception as e:
    print('ERROR', repr(e))
    sys.exit(1)
