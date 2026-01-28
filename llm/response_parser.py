import json
import intents
def parse_intent(llm_text: str) -> dict:
    try:
        intent = json.loads(llm_text)
        # validate
        if intent["intent"] not in intents:
            return {"intent": "UNKNOWN", "args": {}}
        return intent
    except json.JSONDecodeError:
        return {"intent": "UNKNOWN", "args": {}}