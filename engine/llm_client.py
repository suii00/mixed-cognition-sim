import json
import re
import time
import requests
from typing import Callable, Dict, Optional, Tuple


TelemetryCallback = Callable[[str, int], None]


class LLMTransportError(RuntimeError):
    """A terminal HTTP/transport failure that must abort the run."""


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


def _emit(telemetry: Optional[TelemetryCallback], event: str) -> None:
    if telemetry is not None:
        telemetry(event, 1)


def _post_with_retries(url: str, payload: Dict, timeout_s: int,
                       telemetry: Optional[TelemetryCallback]):
    max_retries = 3
    for attempt in range(max_retries):
        _emit(telemetry, "http_attempt")
        try:
            response = requests.post(url, json=payload, timeout=timeout_s)
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout) as error:
            _emit(telemetry, "transport_failure")
            if attempt == max_retries - 1:
                raise LLMTransportError(
                    f"Ollama transport failed after {max_retries} attempts"
                ) from error
            time.sleep(2 ** attempt)
        except requests.HTTPError as error:
            _emit(telemetry, "transport_failure")
            raise LLMTransportError("Ollama returned an HTTP error") from error
        except requests.RequestException as error:
            _emit(telemetry, "transport_failure")
            raise LLMTransportError("Ollama request failed") from error
    raise LLMTransportError("Ollama transport retry loop ended unexpectedly")


def call_ollama(prompt: str, model: str, base_url: str,
                temperature: float = 0.2, max_tokens: int = 1024,
                timeout_s: int = 120, llm_overrides: Optional[Dict] = None,
                telemetry: Optional[TelemetryCallback] = None,
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

    resp = _post_with_retries(url, payload, timeout_s, telemetry)
    raw_text = resp.json()["message"]["content"]
    parsed = extract_json(raw_text)
    if parsed is not None:
        return parsed, raw_text

    _emit(telemetry, "syntax_parse_attempt_failure")
    _emit(telemetry, "generation_retry")

    # parse retry: call once more
    resp2 = _post_with_retries(url, payload, timeout_s, telemetry)
    raw_text2 = resp2.json()["message"]["content"]
    parsed2 = extract_json(raw_text2)
    if parsed2 is not None:
        return parsed2, raw_text2
    _emit(telemetry, "syntax_parse_attempt_failure")
    return None, raw_text2
