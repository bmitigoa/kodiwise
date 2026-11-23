"""Minimal Gemini REST client (generateContent with function calling). The key goes in a header,
never in a URL or a log line."""
from __future__ import annotations

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiBusy(Exception):
    """429 or a temporary overload: the free quota is used up for now."""


class GeminiError(Exception):
    """Any other failure. The message never contains the key or the prompt."""


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None, max_output_tokens: int = 400) -> None:
        api_key = (api_key or "").strip()      # a piped secret may carry a trailing newline
        if not api_key:
            raise GeminiError("no Gemini key configured")
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._http = httpx.Client(timeout=timeout, transport=transport,
                                  headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})

    def generate(self, system: str, contents: list[dict], function_declarations: list[dict]) -> dict:
        """One request. Returns the first candidate's content: {"role": "model", "parts": [...]}."""
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": function_declarations}],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": self.max_output_tokens},
        }
        try:
            r = self._http.post(f"{BASE}/models/{self.model}:generateContent", json=body)
        except httpx.HTTPError as exc:
            raise GeminiError(f"network error ({type(exc).__name__})") from exc
        if r.status_code in (429, 503):
            raise GeminiBusy(f"HTTP {r.status_code}")
        if r.status_code != 200:
            raise GeminiError(f"HTTP {r.status_code}")
        try:
            cand = r.json()["candidates"][0]
            content = cand["content"]
            content.setdefault("role", "model")
            content.setdefault("parts", [])
            return content
        except (KeyError, IndexError, ValueError) as exc:
            raise GeminiError("unexpected response") from exc
