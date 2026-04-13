import httpx
import asyncio

async def test():
    LITELLM_URL = 'http://127.0.0.1:4000/v1/chat/completions'
    LITELLM_HEADERS = {
        'Authorization': 'Bearer sk-cerebro-master-key-CHANGE_ME',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'cerebro-gpt',
        'messages': [{'role': 'user', 'content': 'Say "hello world" literally.'}],
        'metadata': {
            'trace_id': 'test-trace-abc',
            'tenant_id': 'test-tenant-123'
        }
    }
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(LITELLM_URL, headers=LITELLM_HEADERS, json=payload, timeout=20.0)
            print('Status:', r.status_code)
            print('Content:', r.text)
    except Exception as e:
        print('Error:', e)

asyncio.run(test())
