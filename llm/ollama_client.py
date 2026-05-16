import requests
import ollama


class LLMClient:
    """
    Provider abstraction:
    - Local Ollama by default for non-planning/non-coding style tasks
    - Gemini as optional provider for planning/coding or explicit config
    """

    def __init__(self, model_name: str = ""):
        try:
            from core.config import (
                LLM_TIMEOUT,
                LLM_PROVIDER,
                LLM_MODEL,
                GEMINI_API_KEY,
            )
            timeout = float(LLM_TIMEOUT) if LLM_TIMEOUT and LLM_TIMEOUT > 0 else None
            configured_provider = (LLM_PROVIDER or "gemini").lower()
            configured_model = LLM_MODEL or ""
            self.gemini_key = GEMINI_API_KEY
        except Exception:
            timeout = 30.0
            configured_provider = "gemini"
            configured_model = ""
            self.gemini_key = ""

        self.timeout = timeout
        self.provider = configured_provider
        self.model_name = model_name or configured_model

        # Keep local model default for general usage if none specified
        if not self.model_name:
            self.model_name = "gemma3:4b" if self.provider == "ollama" else "gemini-2.0-flash"

        # If a non-Gemini model name is passed (example: gemma3:4b), use local Ollama.
        if self.model_name and "gemini" not in self.model_name.lower():
            self.provider = "ollama"

        if self.provider == "ollama":
            self._ollama = ollama.Client(timeout=self.timeout) if self.timeout else ollama.Client()
        else:
            self._ollama = None

    def chat(self, messages: list) -> str:
        if self.provider == "ollama":
            return self._chat_ollama(messages)

        # Gemini path (default). If key missing, fall back to local Ollama to keep local behavior.
        if not self.gemini_key:
            if not self._ollama:
                self._ollama = ollama.Client(timeout=self.timeout) if self.timeout else ollama.Client()
                if not self.model_name or self.model_name.startswith("gemini"):
                    self.model_name = "gemma3:4b"
            return self._chat_ollama(messages)

        return self._chat_gemini(messages)

    def _chat_ollama(self, messages: list) -> str:
        response = self._ollama.chat(
            model=self.model_name,
            messages=messages,
        )
        return response["message"]["content"]

    def _chat_gemini(self, messages: list) -> str:
        prompt = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages])
        model = self.model_name or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.gemini_key}
        body = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        resp = requests.post(url, headers=headers, params=params, json=body, timeout=self.timeout or 30.0)
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return str(data)
