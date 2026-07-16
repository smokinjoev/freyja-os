import httpx

from freyja.config import settings
from freyja.system_prompt import FREYJA_SYSTEM_PROMPT


class OllamaClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = settings.ollama_model if model is None else model

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception:
            return False

    async def tags(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            return {"error": str(exc)}

    async def chat(self, prompt: str, model: str | None = None, stream: bool = False) -> dict:
        target_model = model or self.model
        if not target_model:
            return {"error": "No Ollama model configured"}

        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": FREYJA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": stream,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            return {"error": str(exc)}

    def list_local_models(self) -> list[str]:
        import asyncio

        tags = asyncio.run(self.tags())
        if "error" in tags:
            return []
        return [model.get("name", "") for model in tags.get("models", [])]
