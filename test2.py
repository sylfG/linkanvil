import urllib.request, json
req = urllib.request.Request('http://localhost:4000/v1/embeddings', headers={'Authorization': 'Bearer sk-cerebro-master-key-CHANGE_ME', 'Content-Type': 'application/json'}, data=json.dumps({'model': 'cerebro-embeddings', 'input': 'Hola'}).encode('utf-8'))
try:
    res = urllib.request.urlopen(req).read().decode('utf-8')
    print('SUCCESS:', res[:200])
except Exception as e:
    err = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
    print('ERROR:', err[:200])
