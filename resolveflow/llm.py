import httpx

from .config import settings


async def complete(system: str, user: str) -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM provider is not configured")
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={"model": settings.llm_model, "temperature": 0.2,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        response.raise_for_status()
        payload = response.json()
    return payload["choices"][0]["message"]["content"].strip()
