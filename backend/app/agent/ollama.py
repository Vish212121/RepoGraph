"""Small standard-library Ollama client; no paid model API is required."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when the local Ollama service cannot produce an answer."""


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc
        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama returned no message content")
        return content.strip()
