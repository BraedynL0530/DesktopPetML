from typing import List

from llm.ollama_client import LLMClient


class LocalAgentService:
    """Internal local service for heavier agentic note/planning tasks."""

    def __init__(self):
        self.llm = LLMClient()

    def _chat(self, prompt: str) -> str:
        return self.llm.chat([
            {"role": "system", "content": "You are a concise assistant for coding and notes."},
            {"role": "user", "content": prompt},
        ])

    def daily_summary(self, items: List[str]) -> str:
        joined = "\n".join(f"- {i}" for i in items if i)
        return self._chat(
            "Summarize today's work in a compact daily note and list what to do next day.\n"
            f"Work items:\n{joined if joined else '- No items provided'}"
        )

    def create_outline(self, topic: str) -> str:
        return self._chat(
            "Create a practical step-by-step plan as a simple outline. "
            "Use short bullets only.\n"
            f"Topic: {topic}"
        )

    def create_graph(self, topic: str) -> str:
        return self._chat(
            "Create a tiny Mermaid graph for this plan and then include a 3-6 bullet summary. "
            "Return plain text.\n"
            f"Topic: {topic}"
        )
