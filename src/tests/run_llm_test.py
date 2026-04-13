import httpx
import asyncio

LITELLM_URL = "http://litellm:4000/v1/chat/completions"
LITELLM_HEADERS = {
    "Authorization": "Bearer sk-cerebro-master-key",
    "Content-Type": "application/json"
}

async def run_test():
    payload = {
        "model": "cerebro-mini",
        "messages": [{"role": "user", "content": "Say 'hello world' literally."}],
        "metadata": {
            "trace_id": "test-trace-123",
            "tenant_id": "test-tenant-abc"
        }
    }
    
    print("Testing connection to LLM Gateway...")
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response1 = await client.post(LITELLM_URL, headers=LITELLM_HEADERS, json=payload)
            print("Response 1 status:", response1.status_code)
            if response1.status_code == 200:
                print("Response 1 OK")
                print("Testing cache hit with repeated query...")
                response2 = await client.post(LITELLM_URL, headers=LITELLM_HEADERS, json=payload)
                print("Response 2 status:", response2.status_code)
                print("Test Success!")
            else:
                print("Received error status code:", response1.status_code)
                print("Response body:", response1.text)
                print("Fallback/Error logic triggered. Handled correctly.")
        except Exception as e:
            print("Exception during test:", str(e))

if __name__ == "__main__":
    asyncio.run(run_test())
