import urllib.request
import json
import sys

def test_model(model):
    print(f'\n--- Probando modelo: {model} ---')
    try:
        data = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': 'Hello, identify which AI model you are in a short sentence.'}], 'max_tokens': 50}).encode('utf-8')
        req = urllib.request.Request('http://localhost:4000/v1/chat/completions', headers={'Authorization': 'Bearer sk-cerebro-master-key-CHANGE_ME', 'Content-Type': 'application/json'}, data=data)
        resp = urllib.request.urlopen(req, timeout=30)
        res_json = json.loads(resp.read())
        print(f'Respuesta: {res_json["choices"][0]["message"]["content"].strip()}')
        print(f'Modelo real devuelto por OpenRouter: {res_json.get("model", "Desconocido")}')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    test_model('cerebro-lite')
    test_model('cerebro-pro')
