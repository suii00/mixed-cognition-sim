import json
import re
import time
import requests
from typing import Dict, Optional, Tuple


def extract_json(text: str) -> Optional[Dict]:
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
                    continue
    return None


def call_ollama(prompt: str, model: str, base_url: str,
                temperature: float = 0.2, max_tokens: int = 1024,
                timeout_s: int = 120, llm_overrides: Optional[Dict] = None
                ) -> Tuple[Optional[Dict], str]:
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if llm_overrides:
        payload["options"].update(llm_overrides)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
            resp.raise_for_status()
            break
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Ollama connection failed after {max_retries} retries: {e}"
                )
            time.sleep(2 ** attempt)

    raw_text = resp.json()["message"]["content"]
    parsed = extract_json(raw_text)
    if parsed is not None:
        return parsed, raw_text

    # parse retry: call once more
    for attempt in range(max_retries):
        try:
            resp2 = requests.post(url, json=payload, timeout=timeout_s)
            resp2.raise_for_status()
            break
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == max_retries - 1:
                return None, raw_text
            time.sleep(2 ** attempt)

    raw_text2 = resp2.json()["message"]["content"]
    parsed2 = extract_json(raw_text2)
    if parsed2 is not None:
        return parsed2, raw_text2
    return None, raw_text2
