import urllib.request, json
req = urllib.request.Request('http://localhost:4000/v1/embeddings', headers={'Authorization': 'Bearer sk-cerebro-master-key-CHANGE_ME', 'Content-Type': 'application/json'}, data=json.dumps({'model': 'cerebro-embeddings', 'input': 'Hola'}).encode('utf-8'))
try:
    print(urllib.request.urlopen(req).read())
except Exception as e:
    print('Error:', e, e.read() if hasattr(e, 'read') else '')
