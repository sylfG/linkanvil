import re
with open('src/scraper/strategy.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_extract = '''    async def extract(self, url: str) -> str:
        logger.info(f"Simulando extracci\xf3n asistida por AI Proxy con Zero-Defect: {url}")
        
        system_prompt = (
            "You are a web scraper analyzer. You MUST output ONLY valid JSON "
            "that strictly conforms to this schema, with no markdown code blocks:\\n"
            f"{json.dumps(ScrapedDataSchema.model_json_schema())}"
        )

        payload = {
            "model": "cerebro-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract key information from this url or content: {url}"}
            ],
            "response_format": {"type": "json_object"},
            "metadata": {
                "trace_id": self.trace_id,
                "tenant_id": self.tenant_id
            }
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(self.llm_gateway_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content_str = data["choices"][0]["message"]["content"]
                
                # Zero-Defect Pipeline: Zod/Pydantic validation
                validated_data = ScrapedDataSchema.model_validate_json(content_str)
                return validated_data.model_dump_json()

            except ValidationError as ve:
                logger.error(f"F-02.3 Fallo Pydantic Zero-Defect JSON: {ve.errors()}")
                raise ValueError(f"Invalid JSON structure returned by LLM: {str(ve)}")
            except Exception as e:
                logger.error(f"Error procesando AI Proxy Strategy: {str(e)}")
                raise'''

pattern = re.compile(r'    async def extract\(self, url: str\) -> str:.*?return data\["choices"\]\[0\]\["message"\]\["content"\]', re.DOTALL)
text = pattern.sub(new_extract, text)

with open('src/scraper/strategy.py', 'w', encoding='utf-8') as f:
    f.write(text)
