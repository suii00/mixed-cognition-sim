"""Three-model, six-call Ollama-native prompt smoke.

This is a deliberately small diagnostic between backend residency preflight and
the twelve-agent Gate 4A simulations.  It runs the real :class:`Simulation`
coordinator for one step with one agent per model.  Consequently the normal
path contains exactly three Phase 1 and three Phase 3 logical LLM calls.

The runner is not a Gate 3 matrix runner and never claims research eligibility.
It adds an observational transport wrapper around ``engine.sim.call_ollama`` so
the exact prompts, native payloads, response envelopes, and worker-local
telemetry can be retained without changing prompt or phase semantics.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

import requests

from engine import provenance
from engine import sim as sim_module
from engine.config import load_config
from engine.llm_client import build_ollama_chat_payload
from engine.provenance import (
    canonical_json_bytes,
    collect_git_info,
    compute_config_hash,
    compute_prompt_hash,
    file_manifest,
    sha256_bytes,
    utc_now_iso,
)
from engine.sim import Simulation
from tools.validate_run import ValidationReport, validate_run


SCHEMA_VERSION = "ollama-three-model-prompt6-smoke-v1.0.0"
PROTOCOL_VERSION = "gate4-ollama-prompt6-smoke-v1.0.0"
EXPECTED_PROMPT_SHA256 = (
    "f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d"
)
AUXILIARY_SPEC_PATH = "docs/GATE4A_FP16_THREE_ENDPOINT_PROMPT_SMOKE_SPEC.md"
EXPECTED_AUXILIARY_SPEC_SHA256 = (
    "0e24765e78b858a0cbf27e6f66a0cc745aa188c3fb52ab1dafa51559352c6cee"
)
EVIDENCE_LEDGER_PATH = "docs/GATE4_BACKEND_EVIDENCE_LEDGER.md"
EXPECTED_EVIDENCE_LEDGER_SHA256 = (
    "a3b9d45d852d7f34e06a808e52e4aca40c0ae35cd76b4ea109470ae330ef2479"
)
TEMPERATURE = 0.2
NUM_PREDICT = 256
NUM_CTX = 4096
TIMEOUT_S = 120
KEEP_ALIVE = -1
MAX_CONCURRENCY = 1
EXPECTED_LOGICAL_CALLS = 6


@dataclass(frozen=True)
class ModelBinding:
    slot: str
    bloc: str
    model: str
    base_url: str
    digest: str
    quantization: str
    template_sha256: str
    gpu_uuid: str


# The bloc order follows the first frozen Gate 3 HET rotation.  Endpoint/GPU
# mapping follows the separately retained UUID-pinned residency evidence.
MODEL_BINDINGS = (
    ModelBinding(
        slot="qwen",
        bloc="alpha",
        model="qwen2.5:7b-instruct-fp16",
        base_url="http://127.0.0.1:11440",
        digest="59805ce4a4046be2d8f63231a78daacd2e66f5dccf1a64d0d138ebeeb26ff16c",
        quantization="F16",
        template_sha256="eb4402837c7829a690fa845de4d7f3fd842c2adee476d5341da8a46ea9255175",
        gpu_uuid="GPU-720e6563-7e95-65c4-659e-189ba0c7bac5",
    ),
    ModelBinding(
        slot="gemma",
        bloc="beta",
        model="gemma2:9b-instruct-fp16",
        base_url="http://127.0.0.1:11442",
        digest="28e6684b085085f78551db7c96a9daa546161b1da9d055ea01b84cb1163013cf",
        quantization="F16",
        template_sha256="109037bec39c0becc8221222ae23557559bc594290945a2c4221ab4f303b8871",
        gpu_uuid="GPU-af1ef9b0-329f-ff38-d4dd-062e2beca9e0",
    ),
    ModelBinding(
        slot="llama",
        bloc="neutral",
        model="llama3.1:8b-instruct-fp16",
        base_url="http://127.0.0.1:11441",
        digest="4aacac4194543ff7f70dab3f2ebc169c132d5319bb36f7a7e99c4ff525ebcc09",
        quantization="F16",
        template_sha256="948af2743fc78a328dcb3b0f5a31b3d75f415840fdb699e8b1235978392ecf85",
        gpu_uuid="GPU-2964f342-8734-a701-a2c6-4344579b03ee",
    ),
)

EXPECTED_REQUEST_IDS = tuple(
    f"step-000001:{phase}:agent-{agent_id:06d}"
    for phase in ("phase1", "phase3")
    for agent_id in range(3)
)

ZERO_COUNTERS = (
    "generation_retries",
    "transport_failures",
    "syntax_parse_attempt_failures",
    "syntax_parse_failures",
    "schema_validation_failures",
)


class Prompt6CollisionError(FileExistsError):
    """The requested evidence directory already exists."""


class Prompt6InvocationError(ValueError):
    """The invocation is invalid before an evidence directory is claimed."""


class Prompt6ExecutionError(RuntimeError):
    """The attempt was retained but did not satisfy prompt-smoke acceptance."""

    def __init__(self, message: str, evidence_dir: Path):
        super().__init__(message)
        self.evidence_dir = evidence_dir


@dataclass(frozen=True)
class HttpJson:
    status_code: int
    value: Dict[str, Any]
    raw: bytes


ApiClient = Callable[[str, str, Optional[Dict[str, Any]], int], HttpJson]


def _json_file_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()


def _write_json(path: Path, value: Any) -> None:
    _write_exclusive(path, _json_file_bytes(value))


def _request_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]],
    timeout_s: int,
) -> HttpJson:
    response = requests.request(
        method,
        url,
        json=payload,
        timeout=timeout_s,
    )
    raw = bytes(response.content)
    response.raise_for_status()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Ollama metadata response was not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("Ollama metadata response root must be an object")
    return HttpJson(int(response.status_code), value, raw)


def _find_exact_model(models: Any, name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(models, list):
        return None
    matches = [
        item
        for item in models
        if isinstance(item, dict) and item.get("name", item.get("model")) == name
    ]
    return matches[0] if len(matches) == 1 else None


def _capture_api(
    directory: Path,
    filename: str,
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]],
    api_client: ApiClient,
) -> HttpJson:
    observation = api_client(method, url, payload, TIMEOUT_S)
    _write_exclusive(directory / filename, observation.raw)
    _write_json(
        directory / f"{filename}.http.json",
        {"method": method, "url": url, "status_code": observation.status_code},
    )
    return observation


def _validate_run_id(run_id: str) -> None:
    try:
        provenance.normalize_run_id(run_id)
    except (TypeError, ValueError) as error:
        raise Prompt6InvocationError(str(error)) from error


def _preflight_binding(
    binding: ModelBinding,
    preflight_dir: Path,
    api_client: ApiClient,
    failures: list[str],
) -> str:
    prefix = binding.slot
    version = _capture_api(
        preflight_dir,
        f"{prefix}-api-version.json",
        "GET",
        f"{binding.base_url}/api/version",
        None,
        api_client,
    )
    tags = _capture_api(
        preflight_dir,
        f"{prefix}-api-tags.json",
        "GET",
        f"{binding.base_url}/api/tags",
        None,
        api_client,
    )
    show = _capture_api(
        preflight_dir,
        f"{prefix}-api-show.json",
        "POST",
        f"{binding.base_url}/api/show",
        {"model": binding.model},
        api_client,
    )
    ps = _capture_api(
        preflight_dir,
        f"{prefix}-api-ps-before.json",
        "GET",
        f"{binding.base_url}/api/ps",
        None,
        api_client,
    )

    for label, observation in (
        ("version", version),
        ("tags", tags),
        ("show", show),
        ("ps_before", ps),
    ):
        if observation.status_code != 200:
            failures.append(f"{prefix}:{label}:http_status_not_200")

    if not isinstance(version.value.get("version"), str) or not version.value["version"]:
        failures.append(f"{prefix}:server_version_missing")
    tag = _find_exact_model(tags.value.get("models"), binding.model)
    if tag is None:
        failures.append(f"{prefix}:exact_model_tag_missing_or_duplicated")
    else:
        if tag.get("digest") != binding.digest:
            failures.append(f"{prefix}:model_digest_mismatch")
        details = tag.get("details")
        if not isinstance(details, dict) or details.get("quantization_level") != binding.quantization:
            failures.append(f"{prefix}:quantization_mismatch")

    template = show.value.get("template")
    if not isinstance(template, str) or not template:
        failures.append(f"{prefix}:chat_template_missing")
        template = ""
    elif sha256_bytes(template.encode("utf-8")) != binding.template_sha256:
        failures.append(f"{prefix}:chat_template_mismatch")

    loaded = ps.value.get("models")
    if loaded != []:
        failures.append(f"{prefix}:ps_before_not_empty")
    return template


def _build_config(run_id: str, templates: Dict[str, str]) -> Dict[str, Any]:
    blocs = []
    for binding in MODEL_BINDINGS:
        blocs.append({
            "name": binding.bloc,
            "provider": "ollama",
            "model": binding.model,
            "base_url": binding.base_url,
            "num_agents": 1,
            "llm_overrides": {"num_ctx": NUM_CTX},
            "model_digest": binding.digest,
            "quantization": binding.quantization,
            "chat_template": templates[binding.slot],
        })
    return {
        "simulation": {
            "duration": 1,
            "half_space_size": 1,
            "seed": 42,
            "run_name": run_id,
            "run_id": run_id,
            "protocol_version": PROTOCOL_VERSION,
            "metric_version": "metric-v2.0.0",
            "execution_mode": "reference_ollama",
            "research_eligible": False,
            "failure_thresholds": {
                "transport_failures": 0,
                "syntax_parse_failures": 0,
                "schema_validation_failures": 0,
            },
        },
        "blocs": blocs,
        "agents": {
            "edge_policy": "full",
            "communication_radius": 3,
            "memory_limit": 20,
            "memory_size": 5,
            "message_history_limit": 10,
            "message_context_size": 3,
        },
        "places": [],
        "llm_defaults": {
            "temperature": TEMPERATURE,
            "max_tokens": NUM_PREDICT,
            "timeout_s": TIMEOUT_S,
            "max_concurrency": MAX_CONCURRENCY,
        },
    }


def _schema_errors(phase: str, parsed: Any) -> list[str]:
    if not isinstance(parsed, dict):
        return ["parsed_output_is_not_object"]
    if phase == "phase1":
        return [
            f"phase1_{key}_is_not_string"
            for key in ("message", "reasoning")
            if not isinstance(parsed.get(key), str)
        ]
    errors = [
        f"phase3_{key}_is_not_string"
        for key in ("action", "direction", "memory", "reasoning")
        if not isinstance(parsed.get(key), str)
    ]
    action = parsed.get("action")
    direction = parsed.get("direction")
    if isinstance(action, str) and action not in {"move", "stay"}:
        errors.append("phase3_action_is_invalid")
    if action == "move" and direction not in {"up", "down", "left", "right"}:
        errors.append("phase3_move_direction_is_invalid")
    return errors


class InstrumentedNativeTransport:
    """Observe native calls while preserving the worker telemetry contract."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: list[Dict[str, Any]] = []

    def __call__(self, request, telemetry):
        local: Counter[str] = Counter()
        envelopes: list[Dict[str, Any]] = []
        http_responses: list[Dict[str, Any]] = []
        parsed = None
        raw_output = ""
        exception_type = None
        start_time_utc = utc_now_iso()
        start_monotonic_ns = time.monotonic_ns()
        payload = build_ollama_chat_payload(
            prompt=request.prompt,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            llm_overrides=copy.deepcopy(request.llm_overrides),
            keep_alive=KEEP_ALIVE,
        )

        def observe_telemetry(event: str, amount: int = 1) -> None:
            local[event] += amount
            telemetry(event, amount)

        def observe_http_response(status: int, raw_body: bytes) -> None:
            http_responses.append({
                "status_code": status,
                "raw_body": bytes(raw_body),
            })

        try:
            parsed, raw_output = sim_module.call_ollama(
                prompt=request.prompt,
                model=request.model,
                base_url=request.base_url,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout_s=request.timeout_s,
                llm_overrides=copy.deepcopy(request.llm_overrides),
                telemetry=observe_telemetry,
                keep_alive=KEEP_ALIVE,
                response_observer=envelopes.append,
                http_response_observer=observe_http_response,
            )
            return parsed, raw_output
        except BaseException as error:
            exception_type = type(error).__name__
            raise
        finally:
            end_monotonic_ns = time.monotonic_ns()
            record = {
                "request_id": request.request_id,
                "step": request.step,
                "phase": request.phase,
                "agent_id": request.agent_id,
                "model": request.model,
                "base_url": request.base_url,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "timeout_s": request.timeout_s,
                "llm_overrides": copy.deepcopy(request.llm_overrides),
                "prompt": request.prompt,
                "payload": payload,
                "envelopes": copy.deepcopy(envelopes),
                "http_responses": copy.deepcopy(http_responses),
                "parsed": copy.deepcopy(parsed),
                "raw_output": raw_output,
                "telemetry": dict(sorted(local.items())),
                "exception_type": exception_type,
                "timing": {
                    "start_time_utc": start_time_utc,
                    "end_time_utc": utc_now_iso(),
                    "start_monotonic_ns": start_monotonic_ns,
                    "end_monotonic_ns": end_monotonic_ns,
                    "elapsed_ns": end_monotonic_ns - start_monotonic_ns,
                },
            }
            with self._lock:
                self.records.append(record)


def _request_stem(ordinal: int, request_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", request_id).strip("-")
    return f"{ordinal:02d}-{safe}"


def _publish_transport_records(
    evidence_dir: Path,
    records: Sequence[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    by_id: Dict[str, list[Dict[str, Any]]] = {}
    for record in records:
        by_id.setdefault(record["request_id"], []).append(record)
    ordered: list[Dict[str, Any]] = []
    for request_id in EXPECTED_REQUEST_IDS:
        ordered.extend(by_id.pop(request_id, []))
    for request_id in sorted(by_id):
        ordered.extend(by_id[request_id])

    transcript = []
    for ordinal, record in enumerate(ordered, start=1):
        stem = _request_stem(ordinal, record["request_id"])
        prompt_path = Path("prompts") / f"{stem}.txt"
        request_path = Path("requests") / f"{stem}.json"
        telemetry_path = Path("telemetry") / f"{stem}.json"
        parsed_path = Path("parsed") / f"{stem}.json"
        raw_path = Path("raw_outputs") / f"{stem}.txt"
        _write_exclusive(evidence_dir / prompt_path, record["prompt"].encode("utf-8"))
        _write_json(evidence_dir / request_path, record["payload"])
        _write_json(
            evidence_dir / telemetry_path,
            {
                "telemetry": record["telemetry"],
                "timing": record["timing"],
                "exception_type": record["exception_type"],
            },
        )
        _write_json(evidence_dir / parsed_path, record["parsed"])
        _write_exclusive(evidence_dir / raw_path, record["raw_output"].encode("utf-8"))
        response_paths = []
        for attempt, envelope in enumerate(record["envelopes"], start=1):
            response_path = Path("native_responses") / f"{stem}-attempt-{attempt:02d}.json"
            _write_json(evidence_dir / response_path, envelope)
            response_paths.append(response_path.as_posix())
        http_response_paths = []
        for attempt, response in enumerate(record["http_responses"], start=1):
            body_path = (
                Path("http_responses")
                / f"{stem}-attempt-{attempt:02d}.body"
            )
            meta_path = (
                Path("http_responses")
                / f"{stem}-attempt-{attempt:02d}.http.json"
            )
            raw_body = response["raw_body"]
            _write_exclusive(evidence_dir / body_path, raw_body)
            _write_json(
                evidence_dir / meta_path,
                {
                    "status_code": response["status_code"],
                    "body_path": body_path.as_posix(),
                    "body_sha256": sha256_bytes(raw_body),
                    "body_bytes": len(raw_body),
                },
            )
            http_response_paths.append({
                "body_path": body_path.as_posix(),
                "meta_path": meta_path.as_posix(),
            })
        transcript.append({
            "ordinal": ordinal,
            "request_id": record["request_id"],
            "step": record["step"],
            "phase": record["phase"],
            "agent_id": record["agent_id"],
            "model": record["model"],
            "base_url": record["base_url"],
            "prompt_path": prompt_path.as_posix(),
            "prompt_sha256": sha256_bytes(record["prompt"].encode("utf-8")),
            "request_path": request_path.as_posix(),
            "request_sha256": sha256_bytes(_json_file_bytes(record["payload"])),
            "telemetry_path": telemetry_path.as_posix(),
            "parsed_path": parsed_path.as_posix(),
            "raw_output_path": raw_path.as_posix(),
            "native_response_paths": response_paths,
            "native_response_count": len(response_paths),
            "http_response_paths": http_response_paths,
            "http_response_count": len(http_response_paths),
            "exception_type": record["exception_type"],
            "timing": copy.deepcopy(record["timing"]),
        })
    _write_exclusive(
        evidence_dir / "request_transcript.jsonl",
        b"".join(_json_file_bytes(item) for item in transcript),
    )
    return transcript


def _validation_report_value(report: ValidationReport) -> Dict[str, Any]:
    return {
        "valid": report.valid,
        "strict": report.strict,
        "errors": list(report.errors),
        "unverifiable": list(report.unverifiable),
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _validate_transport_records(
    records: Sequence[Dict[str, Any]],
    failures: list[str],
    schema_diagnostics: list[Dict[str, Any]],
) -> None:
    if len(records) != EXPECTED_LOGICAL_CALLS:
        failures.append(
            f"logical_transport_record_count:{len(records)}"
        )
    observed_ids = tuple(record.get("request_id") for record in records)
    if observed_ids != EXPECTED_REQUEST_IDS:
        failures.append("logical_request_sequence_mismatch")

    binding_by_model = {binding.model: binding for binding in MODEL_BINDINGS}
    previous_end_monotonic_ns: Optional[int] = None
    for record in records:
        request_id = str(record.get("request_id"))
        binding = binding_by_model.get(record.get("model"))
        if binding is None or record.get("base_url") != binding.base_url:
            failures.append(f"{request_id}:model_endpoint_mapping_mismatch")
        payload = record.get("payload")
        expected_payload = build_ollama_chat_payload(
            prompt=record.get("prompt", ""),
            model=record.get("model", ""),
            temperature=TEMPERATURE,
            max_tokens=NUM_PREDICT,
            llm_overrides={"num_ctx": NUM_CTX},
            keep_alive=KEEP_ALIVE,
        )
        if payload != expected_payload:
            failures.append(f"{request_id}:native_payload_mismatch")
        telemetry = record.get("telemetry")
        observed_telemetry = {
            key: telemetry.get(key, 0) if isinstance(telemetry, dict) else None
            for key in (
                "http_attempt",
                "generation_retry",
                "transport_failure",
                "syntax_parse_attempt_failure",
            )
        }
        if observed_telemetry != {
            "http_attempt": 1,
            "generation_retry": 0,
            "transport_failure": 0,
            "syntax_parse_attempt_failure": 0,
        }:
            failures.append(f"{request_id}:per_request_telemetry_not_zero_retry")
        envelopes = record.get("envelopes")
        if not isinstance(envelopes, list) or len(envelopes) != 1:
            failures.append(f"{request_id}:native_response_count_not_one")
        else:
            envelope = envelopes[0]
            if not isinstance(envelope, dict):
                failures.append(f"{request_id}:native_response_not_object")
            else:
                if envelope.get("model") != record.get("model"):
                    failures.append(f"{request_id}:native_response_model_mismatch")
                if envelope.get("done") is not True:
                    failures.append(f"{request_id}:native_response_not_done")
                message = envelope.get("message")
                if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                    failures.append(f"{request_id}:native_response_content_missing")
                elif message["content"] != record.get("raw_output"):
                    failures.append(
                        f"{request_id}:native_response_content_return_mismatch"
                    )
                for field in (
                    "total_duration",
                    "load_duration",
                    "prompt_eval_count",
                    "prompt_eval_duration",
                    "eval_count",
                    "eval_duration",
                ):
                    value = envelope.get(field)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        failures.append(f"{request_id}:native_response_{field}_invalid")
        http_responses = record.get("http_responses")
        if not isinstance(http_responses, list) or len(http_responses) != 1:
            failures.append(f"{request_id}:http_response_count_not_one")
        else:
            http_response = http_responses[0]
            if http_response.get("status_code") != 200:
                failures.append(f"{request_id}:http_status_not_200")
            raw_body = http_response.get("raw_body")
            if not isinstance(raw_body, bytes):
                failures.append(f"{request_id}:http_body_not_bytes")
            else:
                try:
                    decoded_body = json.loads(raw_body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    failures.append(f"{request_id}:http_body_not_utf8_json")
                else:
                    if not isinstance(envelopes, list) or len(envelopes) != 1:
                        failures.append(
                            f"{request_id}:http_body_envelope_comparison_unavailable"
                        )
                    elif decoded_body != envelopes[0]:
                        failures.append(f"{request_id}:http_body_envelope_mismatch")
        diagnostics = _schema_errors(
            str(record.get("phase")), record.get("parsed")
        )
        if diagnostics:
            schema_diagnostics.append({
                "request_id": request_id,
                "diagnostics": diagnostics,
                "acceptance_effect": "diagnostic_only",
            })
        if not isinstance(record.get("parsed"), dict):
            failures.append(f"{request_id}:parsed_output_is_null_or_non_object")
        if record.get("exception_type") is not None:
            failures.append(f"{request_id}:transport_exception")
        timing = record.get("timing")
        start_ns = timing.get("start_monotonic_ns") if isinstance(timing, dict) else None
        end_ns = timing.get("end_monotonic_ns") if isinstance(timing, dict) else None
        elapsed_ns = timing.get("elapsed_ns") if isinstance(timing, dict) else None
        if (
            not isinstance(start_ns, int)
            or isinstance(start_ns, bool)
            or not isinstance(end_ns, int)
            or isinstance(end_ns, bool)
            or end_ns < start_ns
            or elapsed_ns != end_ns - start_ns
        ):
            failures.append(f"{request_id}:invalid_monotonic_timing")
        else:
            if (
                previous_end_monotonic_ns is not None
                and start_ns < previous_end_monotonic_ns
            ):
                failures.append(f"{request_id}:request_overlap_or_order_violation")
            previous_end_monotonic_ns = end_ns


def _validate_run_artifacts(
    run_dir: Path,
    strict: Optional[ValidationReport],
    failures: list[str],
) -> Optional[Dict[str, Any]]:
    meta_path = run_dir / "run_meta.json"
    if not meta_path.is_file():
        failures.append("run_meta_missing")
        return None
    try:
        meta = _read_json(meta_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        failures.append("run_meta_unreadable")
        return None
    if not isinstance(meta, dict):
        failures.append("run_meta_not_object")
        return None
    if meta.get("status") != "completed" or meta.get("aborted") is not False:
        failures.append("run_lifecycle_not_completed")
    if meta.get("expected_steps") != 1 or meta.get("completed_steps") != 1:
        failures.append("run_step_coverage_mismatch")
    if meta.get("expected_agents") != 3 or meta.get("observed_agents") != 3:
        failures.append("run_agent_coverage_mismatch")
    if meta.get("logical_llm_calls") != EXPECTED_LOGICAL_CALLS:
        failures.append("run_logical_llm_calls_not_six")
    if meta.get("http_attempts") != EXPECTED_LOGICAL_CALLS:
        failures.append("run_http_attempts_not_six")
    for counter in ZERO_COUNTERS:
        if meta.get(counter) != 0:
            failures.append(f"run_{counter}_not_zero")
    if meta.get("raw_manifest_status") != "available":
        failures.append("run_raw_manifest_unavailable")
    if meta.get("prompt_hash") != EXPECTED_PROMPT_SHA256:
        failures.append("run_prompt_hash_mismatch")
    simulation = meta.get("config", {}).get("simulation", {})
    if simulation.get("execution_mode") != "reference_ollama":
        failures.append("run_execution_mode_mismatch")
    if simulation.get("research_eligible") is not False:
        failures.append("run_research_eligibility_mismatch")
    if strict is None or not strict.valid:
        failures.append("strict_validation_failed")
        if strict is not None:
            failures.extend(
                f"strict:{message}" for message in strict.errors
            )
    try:
        if len(_read_jsonl(run_dir / "phase1_raw.jsonl")) != 3:
            failures.append("phase1_row_count_not_three")
        if len(_read_jsonl(run_dir / "memory_reasoning.jsonl")) != 3:
            failures.append("phase3_row_count_not_three")
        if _read_jsonl(run_dir / "parse_errors.jsonl"):
            failures.append("parse_error_rows_not_zero")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        failures.append("scientific_raw_unreadable")
    return meta


def _capture_post_ps(
    evidence_dir: Path,
    api_client: ApiClient,
    failures: list[str],
) -> None:
    post_dir = evidence_dir / "postflight"
    for binding in MODEL_BINDINGS:
        try:
            observation = _capture_api(
                post_dir,
                f"{binding.slot}-api-ps-after.json",
                "GET",
                f"{binding.base_url}/api/ps",
                None,
                api_client,
            )
        except Exception as error:
            failures.append(f"{binding.slot}:post_ps_capture:{type(error).__name__}")
            continue
        if observation.status_code != 200:
            failures.append(f"{binding.slot}:post_ps_http_status_not_200")
        models = observation.value.get("models")
        if not isinstance(models, list) or len(models) != 1:
            failures.append(f"{binding.slot}:post_ps_loaded_model_count_not_one")
            continue
        model = _find_exact_model(models, binding.model)
        if model is None:
            failures.append(f"{binding.slot}:post_ps_expected_model_missing")
            continue
        if model.get("digest") != binding.digest:
            failures.append(f"{binding.slot}:post_ps_digest_mismatch")
        if model.get("context_length") != NUM_CTX:
            failures.append(f"{binding.slot}:post_ps_context_mismatch")
        size = model.get("size")
        if not isinstance(size, int) or size <= 0 or model.get("size_vram") != size:
            failures.append(f"{binding.slot}:post_ps_cpu_offload_or_size_invalid")


def _artifact_manifest(root: Path) -> Dict[str, Any]:
    files: Dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "prompt6_manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        files[relative] = file_manifest(path)
    return files


def run_prompt6(
    output_dir: Path | str,
    run_id: str,
    *,
    repo_root: Optional[Path] = None,
    api_client: Optional[ApiClient] = None,
) -> Path:
    """Execute and retain one three-model, six-logical-call prompt smoke."""
    _validate_run_id(run_id)
    repository = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    prompt_sha = compute_prompt_hash(repository)
    if prompt_sha != EXPECTED_PROMPT_SHA256:
        raise Prompt6InvocationError(
            "engine/prompts.py hash differs from the guarded prompt semantics"
        )
    guarded_documents = (
        (AUXILIARY_SPEC_PATH, EXPECTED_AUXILIARY_SPEC_SHA256),
        (EVIDENCE_LEDGER_PATH, EXPECTED_EVIDENCE_LEDGER_SHA256),
    )
    observed_document_hashes: Dict[str, str] = {}
    for relative_path, expected_sha256 in guarded_documents:
        document_path = repository / relative_path
        if not document_path.is_file() or document_path.is_symlink():
            raise Prompt6InvocationError(
                f"guarded document is missing or not a regular file: {relative_path}"
            )
        observed_sha256 = sha256_bytes(document_path.read_bytes())
        if observed_sha256 != expected_sha256:
            raise Prompt6InvocationError(
                f"guarded document hash differs: {relative_path}"
            )
        observed_document_hashes[relative_path] = observed_sha256
    destination = Path(output_dir).resolve()
    try:
        destination.mkdir(mode=0o755, parents=False, exist_ok=False)
    except FileExistsError as error:
        raise Prompt6CollisionError(
            f"prompt6 evidence directory already exists: {destination}"
        ) from error

    started = utc_now_iso()
    client = api_client or _request_json
    failures: list[str] = []
    failure_type: Optional[str] = None
    templates: Dict[str, str] = {}
    transport = InstrumentedNativeTransport()
    simulation: Optional[Simulation] = None
    strict: Optional[ValidationReport] = None
    transcript: list[Dict[str, Any]] = []
    schema_diagnostics: list[Dict[str, Any]] = []
    run_meta: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    interrupted: Optional[KeyboardInterrupt] = None

    try:
        preflight_dir = destination / "preflight"
        for binding in MODEL_BINDINGS:
            templates[binding.slot] = _preflight_binding(
                binding, preflight_dir, client, failures
            )
        if failures:
            raise RuntimeError("preflight acceptance failed")

        config = _build_config(run_id, templates)
        config_path = destination / "config.json"
        _write_json(config_path, config)
        # Route through the public loader so this diagnostic does not bypass
        # the normal config validation used by the CLI.
        effective = load_config(str(config_path))
        if compute_config_hash(effective) != compute_config_hash(config):
            failures.append("effective_config_hash_mismatch")
            raise RuntimeError("effective config differs")

        runs_dir = destination / "runs"
        runs_dir.mkdir(mode=0o755, parents=False, exist_ok=False)
        simulation = Simulation(
            effective,
            output_root=runs_dir,
            repo_root=repository,
            transport=transport,
        )
        simulation.run()
    except KeyboardInterrupt as error:
        interrupted = error
        failure_type = type(error).__name__
        failures.append("keyboard_interrupt")
    except BaseException as error:
        failure_type = type(error).__name__
        failures.append(f"execution_exception:{type(error).__name__}")

    try:
        transcript = _publish_transport_records(destination, transport.records)
    except BaseException as error:
        failures.append(f"transport_sidecar_publish:{type(error).__name__}")

    run_dir = destination / "runs" / f"output_{run_id}"
    if run_dir.is_dir():
        try:
            strict = validate_run(run_dir, strict=True)
            _write_json(
                destination / "strict-validation.json",
                _validation_report_value(strict),
            )
        except BaseException as error:
            failures.append(f"strict_validation_exception:{type(error).__name__}")

    _validate_transport_records(
        transport.records,
        failures,
        schema_diagnostics,
    )
    run_meta = _validate_run_artifacts(run_dir, strict, failures)
    _capture_post_ps(destination, client, failures)

    # Retain one occurrence of each mechanically named failure.  Repetition is
    # not additional evidence and makes comparisons needlessly unstable.
    failures = list(dict.fromkeys(failures))
    status = "passed" if not failures and interrupted is None else (
        "aborted" if interrupted is not None else "failed"
    )
    runner_source_bytes = Path(__file__).read_bytes()
    manifest_payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "status_scope": "core_simulation_prompt_path_only",
        "overall_backend_evidence_status": "not_evaluated",
        "external_evidence_required": [
            "GPU UUID/process mapping",
            "ollama ps 100% GPU placement",
            "temporary endpoint cleanup",
            "existing 11434 service continuity",
            "final all-GPU idle snapshot",
            "exact runner source bytes bound to the recorded runner hash",
        ],
        "research_eligible": False,
        "formal_gate4_status": "not_a_formal_gate4a_stage",
        "start_time_utc": started,
        "end_time_utc": utc_now_iso(),
        "failure_type": failure_type,
        "failures": failures,
        "source_git": collect_git_info(repository),
        "guarded_documents": observed_document_hashes,
        "runner_source": {
            "path": "tools/ollama_prompt6_runner.py",
            "sha256": sha256_bytes(runner_source_bytes),
            "bytes": len(runner_source_bytes),
            "evidence_boundary": (
                "hash recorded here; exact source bytes are retained by external "
                "orchestration and are not copied into this evidence leaf"
            ),
        },
        "prompt_source_sha256": prompt_sha,
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "config_sha256": compute_config_hash(config) if config is not None else None,
        "transport": "ollama_native_instrumented",
        "native_function": "engine.sim.call_ollama",
        "native_endpoint": "/api/chat",
        "native_http_status_observation": "client_callback_exact_status_and_raw_body",
        "sampling": {
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
            "num_ctx": NUM_CTX,
            "keep_alive": KEEP_ALIVE,
            "max_concurrency": MAX_CONCURRENCY,
        },
        "world": {
            "duration": 1,
            "agents": 3,
            "half_space_size": 1,
            "seed": 42,
            "places": [],
            "edge_policy": "full",
            "communication_radius": 3,
        },
        "expected_request_ids": list(EXPECTED_REQUEST_IDS),
        "observed_request_ids": [record.get("request_id") for record in transport.records],
        "logical_transport_records": len(transport.records),
        "native_response_envelopes": sum(
            len(record.get("envelopes", [])) for record in transport.records
        ),
        "http_response_observations": sum(
            len(record.get("http_responses", [])) for record in transport.records
        ),
        "schema_validation_supported_by_engine": False,
        "schema_diagnostics": schema_diagnostics,
        "strict_validation": (
            _validation_report_value(strict) if strict is not None else None
        ),
        "run_counters": (
            {
                key: run_meta.get(key)
                for key in (
                    "logical_llm_calls",
                    "http_attempts",
                    *ZERO_COUNTERS,
                    "expected_steps",
                    "completed_steps",
                    "expected_agents",
                    "observed_agents",
                )
            }
            if isinstance(run_meta, dict) else None
        ),
        "bindings": [
            {
                "slot": binding.slot,
                "bloc": binding.bloc,
                "model": binding.model,
                "base_url": binding.base_url,
                "expected_digest": binding.digest,
                "expected_quantization": binding.quantization,
                "expected_template_sha256": binding.template_sha256,
                "expected_gpu_uuid": binding.gpu_uuid,
            }
            for binding in MODEL_BINDINGS
        ],
        "request_transcript": transcript,
        "files": _artifact_manifest(destination),
    }
    evidence_id = "prompt6-" + sha256_bytes(canonical_json_bytes(manifest_payload))
    manifest = {"evidence_id": evidence_id, **manifest_payload}
    _write_json(destination / "prompt6_manifest.json", manifest)

    if interrupted is not None:
        raise interrupted
    if status != "passed":
        raise Prompt6ExecutionError(
            "prompt6 smoke failed ("
            + ", ".join(failures)
            + f"); retained evidence {evidence_id}",
            destination,
        )
    return destination


class Prompt6ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Prompt6InvocationError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = Prompt6ArgumentParser(
        prog="python -m tools.ollama_prompt6_runner",
        description="Run the three-model six-call native Ollama prompt smoke",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        output = run_prompt6(args.output_dir, args.run_id)
    except Prompt6CollisionError as error:
        print(f"COLLISION: {error}", file=sys.stderr)
        return 3
    except Prompt6InvocationError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    except Prompt6ExecutionError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ABORTED: interrupted", file=sys.stderr)
        return 130
    print(f"PASS: prompt6 smoke completed at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
