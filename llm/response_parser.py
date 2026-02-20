"""
llm/response_parser.py
Robust intent parser — handles all the ways LLMs format JSON output:
  - Plain JSON
  - ```json ... ``` markdown blocks
  - JSON embedded in prose ("Here is my response: {...}")
  - Single quotes instead of double quotes
  - Trailing commas
"""
import json
import re
import logging

logger = logging.getLogger(__name__)


def parse_intent(text: str) -> dict | None:
    if not text:
        return None

    text = text.strip()

    # 1. Try extracting from ```json ... ``` block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        result = _try_parse(match.group(1))
        if result:
            return result

    # 2. Try finding the first { ... } in the text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        result = _try_parse(match.group(0))
        if result:
            return result

    # 3. Try the whole text as JSON
    result = _try_parse(text)
    if result:
        return result

    logger.warning(f"parse_intent: could not extract JSON from: {repr(text[:200])}")
    return None


def _try_parse(s: str) -> dict | None:
    s = s.strip()
    try:
        data = json.loads(s)
        if isinstance(data, dict) and "intent" in data:
            # Ensure args key always exists
            if "args" not in data:
                data["args"] = {}
            return data
        return None
    except json.JSONDecodeError:
        pass

    # Try fixing common LLM JSON mistakes
    try:
        # Replace single quotes with double quotes (carefully)
        fixed = re.sub(r"(?<![\\])'", '"', s)
        # Remove trailing commas before } or ]
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        data = json.loads(fixed)
        if isinstance(data, dict) and "intent" in data:
            if "args" not in data:
                data["args"] = {}
            return data
    except Exception:
        pass

    return None