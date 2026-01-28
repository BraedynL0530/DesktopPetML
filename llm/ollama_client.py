import ollama

class LLMClient:
    def __init__(self, model_name="NONE"):
        self.model_name = model_name

    def chat(self, messages):
        response = ollama.chat(
            model=self.model_name,
            messages=messages
        )
        return response.choices[0].message.content
