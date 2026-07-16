import httpx

from freyja.config import settings
from freyja.system_prompt import FREYJA_SYSTEM_PROMPT


class OpenRouterClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.api_key = settings.openrouter_api_key if api_key is None else api_key
        self.model = settings.openrouter_model if model is None else model

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": "Freyja-OS Director",
        }
        return headers

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return response.status_code == 200
        except Exception:
            return False

    async def chat(self, prompt: str, model: str | None = None) -> dict:
        target_model = model or self.model
        if not self.api_key:
            return {"error": "OpenRouter API key not configured"}
        if not target_model:
            return {"error": "No OpenRouter model configured"}

        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": FREYJA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            return {"error": f"OpenRouter HTTP {exc.response.status_code}"}
        except Exception as exc:
            return {"error": str(exc)}

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return {
            "model": data.get("model", target_model),
            "response": message.get("content", ""),
            "usage": usage,
        }
