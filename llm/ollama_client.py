import ollama


class LLMClient:
    """
    Thin wrapper around the Ollama Python client.

    Builds a client with a configurable HTTP timeout so that slow or
    unavailable LLM calls don't block threads indefinitely.
    """

    def __init__(self, model_name: str = "NONE"):
        self.model_name = model_name

        try:
            from core.config import LLM_TIMEOUT
            # Use explicit numeric check: 0.0 is falsy but is a valid value meaning "no timeout"
            _timeout = float(LLM_TIMEOUT) if LLM_TIMEOUT is not None and LLM_TIMEOUT > 0 else None
        except Exception:
            _timeout = 30.0

        # ollama.Client accepts the same keyword arguments as httpx.Client,
        # so passing timeout= here sets a connect+read timeout for every call.
        if _timeout:
            self._client = ollama.Client(timeout=_timeout)
        else:
            self._client = ollama.Client()

    def chat(self, messages: list) -> str:
        response = self._client.chat(
            model=self.model_name,
            messages=messages,
        )
        return response["message"]["content"]
