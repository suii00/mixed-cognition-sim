#!/usr/bin/env python3
"""Read-only content validation for the Gate 4 Ollama endpoint-reuse smoke.

The generic Gate 4 publisher intentionally validates only publication
structure.  This module derives the workload result from the captured
endpoint-reuse bytes.  It does not import the orchestrator and it never calls
Ollama, NVIDIA tools, sudo, or the network.
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Optional, Sequence

from tools.validate_run import validate_run


SPEC_VERSION = "gate4-ollama-endpoint-reuse-v1.0.0"
APPROVAL_SCHEMA_VERSION = "gate4-ollama-endpoint-reuse-approval-v1.0.0"
OBSERVATION_SCHEMA_VERSION = "gate4-ollama-endpoint-reuse-observations-v1.0.0"
RESULT_SCHEMA_VERSION = "gate4-ollama-endpoint-reuse-result-v1.0.0"
INDEX_SCHEMA_VERSION = "gate4-ollama-endpoint-reuse-artifact-index-v1.0.0"
VALIDATION_SCHEMA_VERSION = "gate4-ollama-endpoint-reuse-validation-v1.0.0"
PUBLISHER_APPROVAL_SCHEMA_VERSION = "gate4-gpu-run-approval-v1.0.0"

APPROVAL_FILENAME = "endpoint-reuse-approval.json"
APPROVAL_SHA_FILENAME = "endpoint-reuse-approval.sha256"
PUBLISHER_APPROVAL_FILENAME = "approval.json"
CAPTURE_START_FILENAME = "capture-start.json"
CONFIG_FILENAME = "effective-config.json"
TRANSCRIPT_FILENAME = "orchestrator-transcript.jsonl"
OBSERVATIONS_FILENAME = "workload-observations.json"
RESULT_FILENAME = "orchestrator-result.json"
INDEX_FILENAME = "artifact-index.json"
VALIDATION_FILENAME = "workload-validation.json"

SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
GPU_UUID_RE = re.compile(r"GPU-[0-9A-Fa-f-]{8,}\Z")

ROLE_ORDER = ("qwen", "llama", "gemma")
EXPECTED_MODELS = {
    "qwen": (11440, "qwen2.5:7b-instruct-fp16"),
    "llama": (11441, "llama3.1:8b-instruct-fp16"),
    "gemma": (11442, "gemma2:9b-instruct-fp16"),
}
EXPECTED_STATES = [
    "planned",
    "preflight_passed",
    "servers_started",
    "initial_generation_passed",
    "models_unloaded",
    "unload_verified",
    "reload_generation_passed",
    "reload_verified",
    "cleanup_passed",
]
APPROVAL_LIMITS = {
    "maximum_wall_seconds": 3600,
    "request_timeout_seconds": 300,
    "cleanup_timeout_seconds": 300,
    "stability_wait_seconds": 120,
    "idle_memory_threshold_mib": 1024,
}
PUBLISHER_OWNED_TOP_LEVEL = {
    "capture-manifest.json",
    "files.sha256",
    "run-summary.json",
}
REQUIRED_STOP_CONDITIONS = sorted(
    [
        "cleanup_failure",
        "existing_service_changed",
        "generation_failure",
        "gpu_assignment_changed",
        "model_identity_changed",
        "oom_or_crash",
        "parse_failure",
        "retry_observed",
        "timeout",
        "unknown_warning",
    ]
)

APPROVAL_FIELDS = {
    "schema_version",
    "approval_id",
    "approval_reference",
    "approved",
    "evidence_bundle_id",
    "approved_final_path",
    "source_commit_sha",
    "source_dirty",
    "publisher_spec_sha256",
    "publisher_sha256",
    "independent_verifier_sha256",
    "workload_spec_sha256",
    "workload_validator_sha256",
    "orchestrator_sha256",
    "evidence_root",
    "endpoints",
    "num_ctx",
    "num_predict",
    "temperature",
    "parallel_per_endpoint",
    "maximum_generation_calls",
    "maximum_wall_seconds",
    "request_timeout_seconds",
    "cleanup_timeout_seconds",
    "stability_wait_seconds",
    "idle_memory_threshold_mib",
    "required_cleanup",
    "existing_ollama_port",
    "existing_ollama_pid_before",
    "ollama_binary",
    "server_user",
    "allowed_warning_patterns",
    "stop_conditions",
}
ENDPOINT_FIELDS = {
    "port",
    "gpu_uuid",
    "model_role",
    "model_tag",
    "model_digest",
}
PUBLISHER_APPROVAL_FIELDS = {
    "schema_version",
    "evidence_bundle_id",
    "approved_final_path",
    "logical_generation_limit",
    "wall_clock_limit_seconds",
    "gpu_uuids",
    "stop_conditions",
    "approved",
    "approval_reference",
}


class EndpointReuseValidationError(ValueError):
    """The captured workload cannot be validated safely."""


@dataclass(frozen=True)
class ValidationReport:
    operational_backend_result: str
    publication_eligible: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    value: Dict[str, Any]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _reject_nonfinite(value: Any, context: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise EndpointReuseValidationError(f"{context} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_nonfinite(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_nonfinite(child, f"{context}[{index}]")


def decode_canonical_json(data: bytes, context: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EndpointReuseValidationError(f"{context} is not UTF-8") from error

    def pairs(items):
        result: Dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise EndpointReuseValidationError(
                    f"{context} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    def bad_constant(token: str) -> None:
        raise EndpointReuseValidationError(
            f"{context} contains invalid numeric constant {token}"
        )

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=bad_constant,
        )
    except EndpointReuseValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise EndpointReuseValidationError(f"{context} is not valid JSON") from error
    _reject_nonfinite(value, context)
    if canonical_json_bytes(value) != data:
        raise EndpointReuseValidationError(f"{context} is not canonical JSON")
    return value


def _exact_object(value: Any, fields: set[str], context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EndpointReuseValidationError(f"{context} must be an object")
    actual = set(value)
    if actual != fields:
        raise EndpointReuseValidationError(
            f"{context} fields differ; missing={sorted(fields-actual)}, "
            f"unknown={sorted(actual-fields)}"
        )
    return value


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise EndpointReuseValidationError(f"{context} must be a non-empty string")
    return value


def _positive_int(value: Any, context: str) -> int:
    if type(value) is not int or value <= 0:
        raise EndpointReuseValidationError(f"{context} must be a positive integer")
    return value


def _nonnegative_int(value: Any, context: str) -> int:
    if type(value) is not int or value < 0:
        raise EndpointReuseValidationError(
            f"{context} must be a non-negative integer"
        )
    return value


def _canonical_absolute(value: Any, context: str) -> Path:
    text = _string(value, context)
    if not os.path.isabs(text) or text.startswith("//") or os.path.normpath(text) != text:
        raise EndpointReuseValidationError(f"{context} must be canonical absolute")
    return Path(text)


def _sorted_unique_strings(value: Any, context: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise EndpointReuseValidationError(
            f"{context} must be an array of non-empty strings"
        )
    if value != sorted(set(value)):
        raise EndpointReuseValidationError(f"{context} must be sorted and unique")
    return value


def validate_approval(value: Any) -> Mapping[str, Any]:
    approval = _exact_object(value, APPROVAL_FIELDS, "approval")
    if approval["schema_version"] != APPROVAL_SCHEMA_VERSION:
        raise EndpointReuseValidationError("approval schema_version differs")
    approval_id = _string(approval["approval_id"], "approval.approval_id")
    if SAFE_ID_RE.fullmatch(approval_id) is None or ".." in approval_id:
        raise EndpointReuseValidationError("approval_id is unsafe")
    if approval["evidence_bundle_id"] != approval_id:
        raise EndpointReuseValidationError("approval and bundle IDs must be identical")
    _string(approval["approval_reference"], "approval.approval_reference")
    if approval["approved"] is not True or approval["source_dirty"] is not False:
        raise EndpointReuseValidationError("approval must be approved and source-clean")
    if not isinstance(approval["source_commit_sha"], str) or GIT_SHA_RE.fullmatch(
        approval["source_commit_sha"]
    ) is None:
        raise EndpointReuseValidationError("source_commit_sha must be full lowercase SHA")
    for field in (
        "publisher_spec_sha256",
        "publisher_sha256",
        "independent_verifier_sha256",
        "workload_spec_sha256",
        "workload_validator_sha256",
        "orchestrator_sha256",
    ):
        if not isinstance(approval[field], str) or SHA256_RE.fullmatch(approval[field]) is None:
            raise EndpointReuseValidationError(f"approval.{field} is invalid")

    evidence_root = _canonical_absolute(approval["evidence_root"], "evidence_root")
    final_path = _canonical_absolute(
        approval["approved_final_path"], "approved_final_path"
    )
    if final_path != evidence_root / "published" / approval_id:
        raise EndpointReuseValidationError("approved_final_path differs from fixed layout")

    endpoints = approval["endpoints"]
    if not isinstance(endpoints, list) or len(endpoints) != 3:
        raise EndpointReuseValidationError("approval must contain exactly three endpoints")
    gpu_uuids: list[str] = []
    digests: list[str] = []
    for index, role in enumerate(ROLE_ORDER):
        endpoint = _exact_object(endpoints[index], ENDPOINT_FIELDS, f"endpoint[{index}]")
        expected_port, expected_model = EXPECTED_MODELS[role]
        if endpoint["model_role"] != role:
            raise EndpointReuseValidationError("endpoint role order differs")
        if endpoint["port"] != expected_port or endpoint["model_tag"] != expected_model:
            raise EndpointReuseValidationError(f"{role} endpoint port/model differs")
        if not isinstance(endpoint["gpu_uuid"], str) or GPU_UUID_RE.fullmatch(
            endpoint["gpu_uuid"]
        ) is None:
            raise EndpointReuseValidationError(f"{role} GPU UUID is invalid")
        if not isinstance(endpoint["model_digest"], str) or SHA256_RE.fullmatch(
            endpoint["model_digest"]
        ) is None:
            raise EndpointReuseValidationError(f"{role} digest is invalid")
        gpu_uuids.append(endpoint["gpu_uuid"])
        digests.append(endpoint["model_digest"])
    if len(set(gpu_uuids)) != 3 or len(set(digests)) != 3:
        raise EndpointReuseValidationError("endpoint UUIDs and digests must be distinct")

    if approval["num_ctx"] != 4096 or approval["num_predict"] != 256:
        raise EndpointReuseValidationError("num_ctx/num_predict differs from v1")
    if approval["parallel_per_endpoint"] != 1:
        raise EndpointReuseValidationError("parallel_per_endpoint must be one")
    if approval["maximum_generation_calls"] != 6:
        raise EndpointReuseValidationError("generation budget must be exactly six")
    temperature = approval["temperature"]
    if type(temperature) not in {int, float} or not math.isfinite(float(temperature)):
        raise EndpointReuseValidationError("temperature must be finite")
    if not 0 <= float(temperature) <= 2:
        raise EndpointReuseValidationError("temperature is outside the approved range")
    for field in (
        "maximum_wall_seconds",
        "request_timeout_seconds",
        "cleanup_timeout_seconds",
        "stability_wait_seconds",
        "idle_memory_threshold_mib",
    ):
        observed = _positive_int(approval[field], f"approval.{field}")
        if observed > APPROVAL_LIMITS[field]:
            raise EndpointReuseValidationError(f"approval.{field} exceeds the v1 limit")
    _positive_int(approval["existing_ollama_port"], "approval.existing_ollama_port")
    _positive_int(
        approval["existing_ollama_pid_before"],
        "approval.existing_ollama_pid_before",
    )
    if approval["existing_ollama_port"] != 11434:
        raise EndpointReuseValidationError("existing Ollama port must be 11434")
    if approval["required_cleanup"] is not True:
        raise EndpointReuseValidationError("required_cleanup must be true")
    binary = _canonical_absolute(approval["ollama_binary"], "ollama_binary")
    if binary != Path("/usr/local/bin/ollama"):
        raise EndpointReuseValidationError("ollama_binary differs from the v1 path")
    if approval["server_user"] != "ollama":
        raise EndpointReuseValidationError("server_user must be ollama")
    patterns = _sorted_unique_strings(
        approval["allowed_warning_patterns"], "allowed_warning_patterns"
    )
    if any(len(pattern) > 512 for pattern in patterns):
        raise EndpointReuseValidationError("warning pattern is too long")
    conditions = _sorted_unique_strings(approval["stop_conditions"], "stop_conditions")
    if conditions != REQUIRED_STOP_CONDITIONS:
        raise EndpointReuseValidationError("stop_conditions differs from v1")
    return approval


def publisher_approval_projection(approval: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": PUBLISHER_APPROVAL_SCHEMA_VERSION,
        "evidence_bundle_id": approval["evidence_bundle_id"],
        "approved_final_path": approval["approved_final_path"],
        "logical_generation_limit": approval["maximum_generation_calls"],
        "wall_clock_limit_seconds": approval["maximum_wall_seconds"],
        "gpu_uuids": sorted(endpoint["gpu_uuid"] for endpoint in approval["endpoints"]),
        "stop_conditions": list(approval["stop_conditions"]),
        "approved": True,
        "approval_reference": (
            f"{approval['approval_reference']}#endpoint-reuse:{approval['approval_id']}"
        ),
    }


def _safe_relative(value: Any, context: str) -> str:
    text = _string(value, context)
    path = PurePosixPath(text)
    if path.is_absolute() or text.startswith("./") or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise EndpointReuseValidationError(f"{context} is unsafe")
    return text


def _read_file(root: Path, relative: str) -> bytes:
    safe = _safe_relative(relative, "artifact path")
    path = root / safe
    if path.is_symlink() or not path.is_file():
        raise EndpointReuseValidationError(f"artifact is not a regular file: {safe}")
    if path.stat().st_nlink != 1:
        raise EndpointReuseValidationError(f"artifact is hard-linked: {safe}")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    stable = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_nlink,
    )
    if stable(before) != stable(after) or len(data) != after.st_size:
        raise EndpointReuseValidationError(f"artifact changed while read: {safe}")
    return data


def _regular_files(root: Path) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise EndpointReuseValidationError("attempt tree contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file() or path.stat().st_nlink != 1:
            raise EndpointReuseValidationError("attempt tree contains an unsafe file")
        relative = path.relative_to(root).as_posix()
        data = _read_file(root, relative)
        records[relative] = {
            "sha256": _sha256(data),
            "bytes": len(data),
            "lines": data.count(b"\n"),
        }
    return records


def _load_json(root: Path, relative: str) -> Any:
    return decode_canonical_json(_read_file(root, relative), relative)


def _parse_transcript(data: bytes) -> list[Dict[str, Any]]:
    events: list[Dict[str, Any]] = []
    for line_number, line in enumerate(data.splitlines(keepends=True), start=1):
        value = decode_canonical_json(line, f"transcript line {line_number}")
        event = _exact_object(
            value,
            {"sequence", "state", "event", "utc", "monotonic_ns", "details"},
            f"transcript line {line_number}",
        )
        if event["sequence"] != line_number:
            raise EndpointReuseValidationError("transcript sequence is not contiguous")
        _string(event["state"], "transcript.state")
        _string(event["event"], "transcript.event")
        _string(event["utc"], "transcript.utc")
        _nonnegative_int(event["monotonic_ns"], "transcript.monotonic_ns")
        if not isinstance(event["details"], dict):
            raise EndpointReuseValidationError("transcript details must be an object")
        events.append(dict(event))
    if not events:
        raise EndpointReuseValidationError("transcript is empty")
    return events


def _validate_snapshot(
    snapshot: Any,
    endpoint: Mapping[str, Any],
    server_pid: int,
    context: str,
    errors: list[str],
) -> None:
    required = {
        "role",
        "port",
        "server_pid",
        "runner_pid",
        "gpu_uuid",
        "model_tag",
        "model_digest",
        "quantization",
        "context_length",
        "size",
        "size_vram",
        "processor",
        "loaded_models",
        "runner_gpu_uuids",
        "api_ps",
        "api_show",
        "ollama_ps",
        "gpu_observation",
        "runner_process",
    }
    try:
        value = _exact_object(snapshot, required, context)
    except EndpointReuseValidationError as error:
        errors.append(str(error))
        return
    expected = {
        "role": endpoint["model_role"],
        "port": endpoint["port"],
        "server_pid": server_pid,
        "gpu_uuid": endpoint["gpu_uuid"],
        "model_tag": endpoint["model_tag"],
        "model_digest": endpoint["model_digest"],
        "quantization": "F16",
        "context_length": 4096,
        "processor": "100% GPU",
        "loaded_models": 1,
        "runner_gpu_uuids": [endpoint["gpu_uuid"]],
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            errors.append(f"{context}:{field}_mismatch")
    if type(value.get("runner_pid")) is not int or value["runner_pid"] <= 0:
        errors.append(f"{context}:runner_pid_invalid")
    size = value.get("size")
    if type(size) is not int or size <= 0 or value.get("size_vram") != size:
        errors.append(f"{context}:cpu_offload_or_size_invalid")
    api_ps = value.get("api_ps")
    models = api_ps.get("models") if isinstance(api_ps, dict) else None
    if not isinstance(models, list) or len(models) != 1:
        errors.append(f"{context}:api_ps_model_count_mismatch")
    else:
        model = models[0]
        if not isinstance(model, dict) or any(
            model.get(field) != value.get(snapshot_field)
            for field, snapshot_field in (
                ("name", "model_tag"),
                ("digest", "model_digest"),
                ("context_length", "context_length"),
                ("size", "size"),
                ("size_vram", "size_vram"),
            )
        ):
            errors.append(f"{context}:api_ps_binding_mismatch")
    api_show = value.get("api_show")
    details = api_show.get("details") if isinstance(api_show, dict) else None
    if (
        not isinstance(details, dict)
        or details.get("quantization_level") != "F16"
        or not isinstance(api_show.get("template"), str)
        or not api_show["template"]
    ):
        errors.append(f"{context}:api_show_f16_or_template_mismatch")
    ollama_ps = value.get("ollama_ps")
    if (
        not isinstance(ollama_ps, dict)
        or ollama_ps.get("exit_code") != 0
        or endpoint["model_tag"] not in str(ollama_ps.get("stdout", ""))
        or "100% GPU" not in str(ollama_ps.get("stdout", ""))
    ):
        errors.append(f"{context}:ollama_ps_binding_mismatch")
    runner = value.get("runner_process")
    if (
        not isinstance(runner, dict)
        or runner.get("pid") != value.get("runner_pid")
        or runner.get("ppid") != server_pid
        or "llama-server" not in str(runner.get("args", ""))
    ):
        errors.append(f"{context}:runner_process_binding_mismatch")
    gpu = value.get("gpu_observation")
    compute_rows = gpu.get("compute_rows") if isinstance(gpu, dict) else None
    if not isinstance(compute_rows, list):
        errors.append(f"{context}:gpu_compute_rows_missing")
    else:
        runner_rows = [
            row
            for row in compute_rows
            if isinstance(row, dict) and row.get("pid") == value.get("runner_pid")
        ]
        if (
            len(runner_rows) != 1
            or runner_rows[0].get("gpu_uuid") != endpoint["gpu_uuid"]
        ):
            errors.append(f"{context}:runner_gpu_binding_mismatch")


def _validate_generation(
    record: Any,
    ordinal: int,
    endpoint: Mapping[str, Any],
    phase: str,
    server_pid: int,
    temperature: float,
    errors: list[str],
) -> None:
    fields = {
        "ordinal",
        "phase",
        "role",
        "request_id",
        "server_pid",
        "port",
        "gpu_uuid",
        "model_tag",
        "model_digest",
        "quantization",
        "num_ctx",
        "request_payload",
        "prompt_sha256",
        "status_code",
        "raw_body_base64",
        "raw_body_sha256",
        "envelope",
        "parsed",
        "raw_output",
        "telemetry",
        "snapshot",
        "start_monotonic_ns",
        "end_monotonic_ns",
    }
    context = f"generation[{ordinal}]"
    try:
        value = _exact_object(record, fields, context)
    except EndpointReuseValidationError as error:
        errors.append(str(error))
        return
    expected_scalars = {
        "ordinal": ordinal,
        "phase": phase,
        "role": endpoint["model_role"],
        "server_pid": server_pid,
        "port": endpoint["port"],
        "gpu_uuid": endpoint["gpu_uuid"],
        "model_tag": endpoint["model_tag"],
        "model_digest": endpoint["model_digest"],
        "quantization": "F16",
        "num_ctx": 4096,
        "status_code": 200,
    }
    for field, expected_value in expected_scalars.items():
        if value.get(field) != expected_value:
            errors.append(f"{context}:{field}_mismatch")
    expected_agent = ordinal - 1 if phase == "phase1" else ordinal - 4
    expected_request_id = f"step-000001:{phase}:agent-{expected_agent:06d}"
    if value.get("request_id") != expected_request_id:
        errors.append(f"{context}:request_id_mismatch")
    if not isinstance(value.get("prompt_sha256"), str) or SHA256_RE.fullmatch(
        value["prompt_sha256"]
    ) is None:
        errors.append(f"{context}:prompt_hash_invalid")
    payload = value.get("request_payload")
    if not isinstance(payload, dict):
        errors.append(f"{context}:payload_invalid")
    else:
        if payload.get("model") != endpoint["model_tag"]:
            errors.append(f"{context}:payload_model_mismatch")
        if payload.get("stream") is not False or payload.get("keep_alive") != -1:
            errors.append(f"{context}:payload_stream_or_keepalive_mismatch")
        options = payload.get("options")
        expected_options = {
            "temperature": temperature,
            "num_predict": 256,
            "num_ctx": 4096,
        }
        if not isinstance(options, dict) or set(options) != set(expected_options):
            errors.append(f"{context}:payload_context_mismatch")
        else:
            if options != expected_options:
                errors.append(f"{context}:payload_generation_options_mismatch")
        messages = payload.get("messages")
        if (
            not isinstance(messages, list)
            or len(messages) != 1
            or not isinstance(messages[0], dict)
            or messages[0].get("role") != "user"
            or not isinstance(messages[0].get("content"), str)
        ):
            errors.append(f"{context}:payload_messages_invalid")
        elif _sha256(messages[0]["content"].encode("utf-8")) != value.get(
            "prompt_sha256"
        ):
            errors.append(f"{context}:prompt_hash_mismatch")
    try:
        raw_body = base64.b64decode(value.get("raw_body_base64"), validate=True)
    except (TypeError, ValueError) as error:
        errors.append(f"{context}:raw_body_base64_invalid:{type(error).__name__}")
        raw_body = b""
    if _sha256(raw_body) != value.get("raw_body_sha256"):
        errors.append(f"{context}:raw_body_hash_mismatch")
    try:
        decoded = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{context}:raw_body_json_invalid")
        decoded = None
    if decoded != value.get("envelope"):
        errors.append(f"{context}:raw_body_envelope_mismatch")
    envelope = value.get("envelope")
    if not isinstance(envelope, dict):
        errors.append(f"{context}:envelope_invalid")
    else:
        if envelope.get("model") != endpoint["model_tag"]:
            errors.append(f"{context}:response_model_mismatch")
        if envelope.get("done") is not True:
            errors.append(f"{context}:response_not_done")
        message = envelope.get("message")
        if not isinstance(message, dict) or message.get("content") != value.get("raw_output"):
            errors.append(f"{context}:response_content_mismatch")
    if not isinstance(value.get("parsed"), dict):
        errors.append(f"{context}:parsed_output_missing")
    telemetry = value.get("telemetry")
    expected_telemetry = {
        "http_attempts": 1,
        "generation_retries": 0,
        "transport_failures": 0,
        "syntax_parse_failures": 0,
    }
    if telemetry != expected_telemetry:
        errors.append(f"{context}:telemetry_mismatch")
    start = value.get("start_monotonic_ns")
    end = value.get("end_monotonic_ns")
    if type(start) is not int or type(end) is not int or end < start:
        errors.append(f"{context}:timing_invalid")
    _validate_snapshot(value.get("snapshot"), endpoint, server_pid, context, errors)


def _warning_result(
    observed: Any,
    patterns: Sequence[str],
    errors: list[str],
) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    unknown: list[str] = []
    if not isinstance(observed, list):
        errors.append("warnings_not_array")
        return accepted, unknown
    for index, warning in enumerate(observed):
        if not isinstance(warning, dict) or set(warning) != {"role", "level", "message"}:
            errors.append(f"warning[{index}]:shape_invalid")
            continue
        role = warning.get("role")
        level = warning.get("level")
        message = warning.get("message")
        if role not in ROLE_ORDER or not isinstance(level, str) or not isinstance(message, str):
            errors.append(f"warning[{index}]:value_invalid")
            continue
        rendered = f"{role}:{level}:{message}"
        if level.upper() in {"ERROR", "FATAL"} or any(
            token in message.upper()
            for token in (
                "OOM",
                "OUT OF MEMORY",
                "PANIC",
                "CRASH",
                "SEGFAULT",
                "CUDA ERROR",
                "XID",
            )
        ):
            errors.append(f"fatal_backend_diagnostic:{rendered}")
        elif any(fnmatch.fnmatchcase(rendered, pattern) for pattern in patterns):
            accepted.append(rendered)
        else:
            unknown.append(rendered)
    return accepted, unknown


def _publisher_owned(relative: str) -> bool:
    first = relative.split("/", 1)[0]
    return first in PUBLISHER_OWNED_TOP_LEVEL or first == "publication"


def _load_loose_json(root: Path, relative: str) -> Any:
    data = _read_file(root, relative)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EndpointReuseValidationError(f"{relative} is not valid JSON") from error


def _load_jsonl(root: Path, relative: str) -> list[Any]:
    data = _read_file(root, relative)
    rows: list[Any] = []
    for line_number, line in enumerate(data.splitlines(), start=1):
        try:
            rows.append(json.loads(line.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EndpointReuseValidationError(
                f"{relative}:{line_number} is not valid JSON"
            ) from error
    return rows


def _validate_run_binding(
    root: Path,
    approval: Mapping[str, Any],
    result: Mapping[str, Any],
    generations: Sequence[Mapping[str, Any]],
    errors: list[str],
) -> None:
    expected_relative = f"runs/output_{approval['approval_id']}"
    if result.get("run_relative_path") != expected_relative:
        errors.append("run_relative_path_mismatch")
        return
    run_dir = root / expected_relative
    if not run_dir.is_dir() or run_dir.is_symlink():
        errors.append("simulation_run_directory_missing")
        return
    strict_report = validate_run(run_dir, strict=True)
    independently_observed = {
        "valid": strict_report.valid,
        "errors": list(strict_report.errors),
        "unverifiable": list(strict_report.unverifiable),
    }
    if result.get("strict_validation") != independently_observed:
        errors.append("strict_validation_recomputation_mismatch")
    if not strict_report.valid:
        errors.append("independent_strict_validation_not_valid")

    run_meta = _load_loose_json(root, f"{expected_relative}/run_meta.json")
    effective = _load_json(root, CONFIG_FILENAME)
    if not isinstance(run_meta, dict):
        errors.append("run_meta_invalid")
        return
    expected_meta = {
        "run_id": approval["approval_id"],
        "protocol_version": SPEC_VERSION,
        "metric_version": "metric-v2.0.0",
        "status": "completed",
        "aborted": False,
        "expected_steps": 1,
        "completed_steps": 1,
        "expected_agents": 3,
        "observed_agents": 3,
        "logical_llm_calls": 6,
        "http_attempts": 6,
        "generation_retries": 0,
        "transport_failures": 0,
        "syntax_parse_attempt_failures": 0,
        "syntax_parse_failures": 0,
        "schema_validation_failures": 0,
        "git_sha": approval["source_commit_sha"],
        "git_dirty": False,
    }
    for field, expected in expected_meta.items():
        if run_meta.get(field) != expected:
            errors.append(f"run_meta_{field}_mismatch")
    if run_meta.get("config") != effective:
        errors.append("run_meta_effective_config_mismatch")
    prompt_hash = run_meta.get("prompt_hash")
    if not isinstance(prompt_hash, str) or SHA256_RE.fullmatch(prompt_hash) is None:
        errors.append("run_meta_prompt_hash_invalid")

    phase1 = _load_jsonl(root, f"{expected_relative}/phase1_raw.jsonl")
    memory = _load_jsonl(root, f"{expected_relative}/memory_reasoning.jsonl")
    if len(phase1) != 3 or len(memory) != 3 or len(generations) != 6:
        errors.append("simulation_raw_coverage_mismatch")
        return
    bloc_order = ("alpha", "beta", "neutral")
    for index, endpoint in enumerate(approval["endpoints"]):
        phase1_row = phase1[index]
        phase1_generation = generations[index]
        if (
            not isinstance(phase1_row, dict)
            or phase1_row.get("step") != 1
            or phase1_row.get("agent_id") != index
            or phase1_row.get("bloc") != bloc_order[index]
            or phase1_row.get("model") != endpoint["model_tag"]
            or phase1_row.get("parsed") != phase1_generation.get("parsed")
            or phase1_row.get("raw_output") != phase1_generation.get("raw_output")
        ):
            errors.append(f"phase1_raw_binding_mismatch:{endpoint['model_role']}")
        memory_row = memory[index]
        phase3_generation = generations[index + 3]
        parsed = phase3_generation.get("parsed")
        if (
            not isinstance(memory_row, dict)
            or not isinstance(parsed, dict)
            or memory_row.get("step") != 1
            or memory_row.get("agent_id") != index
            or memory_row.get("bloc") != bloc_order[index]
            or memory_row.get("model") != endpoint["model_tag"]
            or any(
                memory_row.get(field) != parsed.get(field)
                for field in ("action", "direction", "memory", "reasoning")
            )
        ):
            errors.append(f"phase3_raw_binding_mismatch:{endpoint['model_role']}")


def _expected_launch_command(
    approval: Mapping[str, Any], endpoint: Mapping[str, Any]
) -> list[str]:
    return [
        "sudo",
        "-n",
        "-H",
        "-u",
        "ollama",
        "env",
        f"CUDA_VISIBLE_DEVICES={endpoint['gpu_uuid']}",
        "OLLAMA_VULKAN=0",
        f"OLLAMA_HOST=127.0.0.1:{endpoint['port']}",
        "OLLAMA_NO_CLOUD=1",
        "OLLAMA_NUM_PARALLEL=1",
        "OLLAMA_MAX_LOADED_MODELS=1",
        "OLLAMA_CONTEXT_LENGTH=4096",
        "OLLAMA_KEEP_ALIVE=-1",
        approval["ollama_binary"],
        "serve",
    ]


def validate_attempt(
    attempt_dir: Path | str,
    *,
    expected_approval_sha256: Optional[str] = None,
) -> ValidationReport:
    root = Path(attempt_dir).resolve()
    errors: list[str] = []
    accepted_warnings: list[str] = []
    unknown_warnings: list[str] = []
    observed_aborted = False
    approval: Mapping[str, Any] = {}
    try:
        if not root.is_dir() or root.is_symlink():
            raise EndpointReuseValidationError("attempt path is not a safe directory")
        first_tree = _regular_files(root)
        approval_bytes = _read_file(root, APPROVAL_FILENAME)
        approval_sha = _sha256(approval_bytes)
        if expected_approval_sha256 is not None and approval_sha != expected_approval_sha256:
            raise EndpointReuseValidationError("approval SHA differs from expected pin")
        approval = validate_approval(
            decode_canonical_json(approval_bytes, APPROVAL_FILENAME)
        )
        sha_text = _read_file(root, APPROVAL_SHA_FILENAME).decode("ascii")
        if sha_text != approval_sha + "\n":
            raise EndpointReuseValidationError("approval SHA sidecar differs")
        projected = decode_canonical_json(
            _read_file(root, PUBLISHER_APPROVAL_FILENAME),
            PUBLISHER_APPROVAL_FILENAME,
        )
        _exact_object(projected, PUBLISHER_APPROVAL_FIELDS, "publisher approval")
        if projected != publisher_approval_projection(approval):
            raise EndpointReuseValidationError("publisher approval projection differs")

        index = _load_json(root, INDEX_FILENAME)
        index = _exact_object(index, {"schema_version", "files"}, "artifact index")
        if index["schema_version"] != INDEX_SCHEMA_VERSION or not isinstance(index["files"], dict):
            raise EndpointReuseValidationError("artifact index schema differs")
        excluded = {INDEX_FILENAME, VALIDATION_FILENAME}
        actual_indexed = {
            path: record
            for path, record in first_tree.items()
            if path not in excluded and not _publisher_owned(path)
        }
        if index["files"] != actual_indexed:
            raise EndpointReuseValidationError("artifact index differs from captured files")

        capture_start = _load_json(root, CAPTURE_START_FILENAME)
        capture_start = _exact_object(
            capture_start,
            {
                "schema_version",
                "approval_sha256",
                "source_commit_sha",
                "source_dirty",
                "started_utc",
                "artifact_hashes",
            },
            "capture start",
        )
        if capture_start["approval_sha256"] != approval_sha:
            errors.append("capture_start_approval_hash_mismatch")
        if capture_start["source_commit_sha"] != approval["source_commit_sha"]:
            errors.append("capture_start_source_commit_mismatch")
        if capture_start["source_dirty"] is not False:
            errors.append("capture_start_source_dirty")
        expected_hashes = {
            "publisher_spec_sha256": approval["publisher_spec_sha256"],
            "publisher_sha256": approval["publisher_sha256"],
            "independent_verifier_sha256": approval["independent_verifier_sha256"],
            "workload_spec_sha256": approval["workload_spec_sha256"],
            "workload_validator_sha256": approval["workload_validator_sha256"],
            "orchestrator_sha256": approval["orchestrator_sha256"],
        }
        if capture_start["artifact_hashes"] != expected_hashes:
            errors.append("capture_start_artifact_hashes_mismatch")

        transcript = _parse_transcript(_read_file(root, TRANSCRIPT_FILENAME))
        state_history = [
            event["state"] for event in transcript if event["event"] == "state_entered"
        ]
        result = _load_json(root, RESULT_FILENAME)
        result = _exact_object(
            result,
            {
                "schema_version",
                "approval_sha256",
                "status",
                "terminal_state",
                "state_history",
                "failure_kind",
                "failure_reasons",
                "started_utc",
                "ended_utc",
                "elapsed_seconds",
                "generation_calls",
                "administrative_unloads",
                "cleanup_passed",
                "run_id",
                "run_relative_path",
                "strict_validation",
                "gate4_formal_pass",
                "research_eligible",
                "backend_freeze",
            },
            "orchestrator result",
        )
        if result["schema_version"] != RESULT_SCHEMA_VERSION:
            errors.append("result_schema_mismatch")
        if result["approval_sha256"] != approval_sha:
            errors.append("result_approval_hash_mismatch")
        if result["state_history"] != state_history:
            errors.append("result_state_history_mismatch")
        if state_history != EXPECTED_STATES:
            errors.append("state_machine_incomplete_or_out_of_order")
        if result["terminal_state"] != "cleanup_passed":
            errors.append("terminal_state_not_cleanup_passed")
        if result["status"] != "completed" or result["failure_kind"] is not None:
            errors.append("orchestrator_not_completed")
        observed_aborted = (
            result.get("status") == "aborted"
            and result.get("failure_kind") == "KeyboardInterrupt"
        )
        if result["failure_reasons"] != []:
            errors.append("orchestrator_failure_reasons_present")
        elapsed = result["elapsed_seconds"]
        if type(elapsed) not in {int, float} or not math.isfinite(float(elapsed)):
            errors.append("elapsed_time_invalid")
        elif elapsed < 0 or elapsed > approval["maximum_wall_seconds"]:
            errors.append("wall_time_ceiling_exceeded")
        if result["generation_calls"] != 6:
            errors.append("generation_call_count_mismatch")
        if result["administrative_unloads"] != 6:
            errors.append("administrative_unload_count_mismatch")
        if result["cleanup_passed"] is not True:
            errors.append("cleanup_not_passed")
        if result["gate4_formal_pass"] is not False or result["research_eligible"] is not False:
            errors.append("formal_or_research_boundary_mismatch")
        if result["backend_freeze"] != {"status": "not_frozen"}:
            errors.append("backend_freeze_boundary_mismatch")
        strict = result["strict_validation"]
        if not isinstance(strict, dict) or strict.get("valid") is not True or strict.get("errors") != []:
            errors.append("strict_validation_not_valid")

        observations = _load_json(root, OBSERVATIONS_FILENAME)
        observations = _exact_object(
            observations,
            {
                "schema_version",
                "approval_sha256",
                "preflight",
                "servers",
                "generation_attempts",
                "generations",
                "unloads",
                "stability_snapshots",
                "warnings",
                "cleanup",
            },
            "observations",
        )
        if observations["schema_version"] != OBSERVATION_SCHEMA_VERSION:
            errors.append("observation_schema_mismatch")
        if observations["approval_sha256"] != approval_sha:
            errors.append("observation_approval_hash_mismatch")

        preflight = observations["preflight"]
        if not isinstance(preflight, dict) or preflight.get("passed") is not True:
            errors.append("preflight_not_passed")
        else:
            if preflight.get("selected_gpu_uuids") != [
                endpoint["gpu_uuid"] for endpoint in approval["endpoints"]
            ]:
                errors.append("preflight_gpu_uuid_mismatch")
            if preflight.get("ports_free") != [11440, 11441, 11442]:
                errors.append("preflight_ports_mismatch")
            for field in ("sudo_check", "ollama_cli_version"):
                command_result = preflight.get(field)
                if (
                    not isinstance(command_result, dict)
                    or command_result.get("exit_code") != 0
                ):
                    errors.append(f"preflight_{field}_missing")
            cli_version = preflight.get("ollama_cli_version")
            if isinstance(cli_version, dict) and not str(
                cli_version.get("stdout", "")
            ).strip():
                errors.append("preflight_ollama_cli_version_empty")
            nvidia_list = preflight.get("nvidia_smi_L")
            if (
                not isinstance(nvidia_list, dict)
                or nvidia_list.get("exit_code") != 0
                or not isinstance(nvidia_list.get("stdout"), str)
            ):
                errors.append("preflight_nvidia_smi_L_missing")
            gpu_observation = preflight.get("gpu_observation")
            gpu_rows = (
                gpu_observation.get("gpu_rows")
                if isinstance(gpu_observation, dict)
                else None
            )
            compute_rows = (
                gpu_observation.get("compute_rows")
                if isinstance(gpu_observation, dict)
                else None
            )
            if not isinstance(gpu_rows, list) or len(gpu_rows) != 8:
                errors.append("preflight_gpu_rows_missing")
            elif not isinstance(compute_rows, list):
                errors.append("preflight_compute_rows_missing")
            else:
                rows_by_uuid = {
                    row.get("uuid"): row for row in gpu_rows if isinstance(row, dict)
                }
                for endpoint in approval["endpoints"]:
                    row = rows_by_uuid.get(endpoint["gpu_uuid"])
                    if (
                        not isinstance(row, dict)
                        or type(row.get("memory_used_mib")) is not int
                        or row["memory_used_mib"]
                        > approval["idle_memory_threshold_mib"]
                        or row.get("utilization_gpu") != 0
                        or any(
                            isinstance(item, dict)
                            and item.get("gpu_uuid") == endpoint["gpu_uuid"]
                            for item in compute_rows
                        )
                    ):
                        errors.append(
                            f"preflight_selected_gpu_not_idle:{endpoint['model_role']}"
                        )
            artifacts = preflight.get("model_artifacts")
            if not isinstance(artifacts, list) or len(artifacts) != 3:
                errors.append("preflight_model_artifacts_missing")
            else:
                for endpoint, artifact in zip(approval["endpoints"], artifacts):
                    expected_artifact = {
                        "role": endpoint["model_role"],
                        "model_tag": endpoint["model_tag"],
                        "model_digest": endpoint["model_digest"],
                        "quantization": "F16",
                    }
                    if not isinstance(artifact, dict) or any(
                        artifact.get(key) != expected for key, expected in expected_artifact.items()
                    ) or not isinstance(artifact.get("template"), str) or not artifact["template"]:
                        errors.append(f"preflight_model_artifact_mismatch:{endpoint['model_role']}")
            existing = preflight.get("existing_service")
            if not isinstance(existing, dict):
                errors.append("preflight_existing_service_missing")
            else:
                if existing.get("port") != 11434 or existing.get("pid") != approval["existing_ollama_pid_before"]:
                    errors.append("preflight_existing_service_identity_mismatch")
                if not isinstance(existing.get("version"), str) or not existing["version"]:
                    errors.append("preflight_existing_service_version_missing")
                if existing.get("ps_models") != []:
                    errors.append("preflight_existing_service_not_empty")
                if (
                    type(existing.get("start_time_ticks")) is not int
                    or existing["start_time_ticks"] <= 0
                    or "ollama serve" not in str(existing.get("command", ""))
                ):
                    errors.append("preflight_existing_service_process_mismatch")

        servers = observations["servers"]
        server_by_role: Dict[str, Mapping[str, Any]] = {}
        if not isinstance(servers, list) or len(servers) != 3:
            errors.append("server_count_mismatch")
        else:
            for endpoint, server in zip(approval["endpoints"], servers):
                if not isinstance(server, dict):
                    errors.append("server_record_invalid")
                    continue
                role = endpoint["model_role"]
                expected_server_fields = {
                    "role",
                    "port",
                    "gpu_uuid",
                    "launcher_pid",
                    "server_pid",
                    "start_time_ticks",
                    "server_command",
                    "version",
                    "launch_command",
                    "initial_ps_models",
                    "model_artifact",
                }
                if (
                    set(server) != expected_server_fields
                    or server.get("role") != role
                    or server.get("port") != endpoint["port"]
                    or server.get("gpu_uuid") != endpoint["gpu_uuid"]
                    or type(server.get("launcher_pid")) is not int
                    or server["launcher_pid"] <= 0
                    or type(server.get("server_pid")) is not int
                    or server["server_pid"] <= 0
                    or type(server.get("start_time_ticks")) is not int
                    or server["start_time_ticks"] <= 0
                    or "ollama serve" not in str(server.get("server_command", ""))
                    or server.get("version") != preflight.get("existing_service", {}).get("version")
                    or server.get("launch_command")
                    != _expected_launch_command(approval, endpoint)
                    or server.get("initial_ps_models") != []
                ):
                    errors.append(f"server_binding_mismatch:{role}")
                else:
                    artifacts = preflight.get("model_artifacts", [])
                    expected_artifact = next(
                        (
                            artifact
                            for artifact in artifacts
                            if isinstance(artifact, dict)
                            and artifact.get("role") == role
                        ),
                        None,
                    )
                    if server.get("model_artifact") != expected_artifact:
                        errors.append(f"server_model_artifact_mismatch:{role}")
                    server_by_role[role] = server
        if len({server.get("server_pid") for server in server_by_role.values()}) != 3:
            errors.append("distinct_server_pid_count_mismatch")

        generations = observations["generations"]
        generation_attempts = observations["generation_attempts"]
        if not isinstance(generation_attempts, list) or len(generation_attempts) != 6:
            errors.append("generation_attempt_record_count_mismatch")
        else:
            attempt_fields = {
                "ordinal",
                "phase",
                "role",
                "request_id",
                "request_payload",
                "prompt_sha256",
                "status_code",
                "raw_body_base64",
                "raw_body_sha256",
                "telemetry",
                "error_type",
                "error_message",
                "start_monotonic_ns",
                "end_monotonic_ns",
            }
            for index, attempt_record in enumerate(generation_attempts):
                if not isinstance(attempt_record, dict) or set(attempt_record) != attempt_fields:
                    errors.append(f"generation_attempt[{index + 1}]:shape_invalid")
                    continue
                if (
                    attempt_record.get("ordinal") != index + 1
                    or attempt_record.get("status_code") != 200
                    or attempt_record.get("error_type") is not None
                    or attempt_record.get("error_message") is not None
                ):
                    errors.append(f"generation_attempt[{index + 1}]:outcome_invalid")
        if not isinstance(generations, list) or len(generations) != 6:
            errors.append("generation_record_count_mismatch")
        else:
            ordinal = 1
            for phase in ("phase1", "phase3"):
                for endpoint in approval["endpoints"]:
                    role = endpoint["model_role"]
                    server = server_by_role.get(role, {})
                    _validate_generation(
                        generations[ordinal - 1],
                        ordinal,
                        endpoint,
                        phase,
                        server.get("server_pid", -1),
                        float(approval["temperature"]),
                        errors,
                    )
                    ordinal += 1
            if isinstance(generation_attempts, list) and len(generation_attempts) == 6:
                for index, (attempt_record, generation) in enumerate(
                    zip(generation_attempts, generations), start=1
                ):
                    if not isinstance(attempt_record, dict) or not isinstance(generation, dict):
                        continue
                    for field in (
                        "ordinal",
                        "phase",
                        "role",
                        "request_id",
                        "request_payload",
                        "prompt_sha256",
                        "status_code",
                        "raw_body_base64",
                        "raw_body_sha256",
                        "telemetry",
                        "start_monotonic_ns",
                    ):
                        if attempt_record.get(field) != generation.get(field):
                            errors.append(
                                f"generation_attempt[{index}]:{field}_binding_mismatch"
                            )
            for offset, phase in ((0, "phase1"), (3, "phase3")):
                runner_pids = {
                    record.get("snapshot", {}).get("runner_pid")
                    for record in generations[offset : offset + 3]
                    if isinstance(record, dict)
                    and isinstance(record.get("snapshot"), dict)
                }
                if len(runner_pids) != 3:
                    errors.append(f"{phase}_distinct_runner_pid_count_mismatch")

        stability = observations["stability_snapshots"]
        if not isinstance(stability, list) or len(stability) != 3:
            errors.append("stability_snapshot_count_mismatch")
        else:
            stability_runner_pids: set[Any] = set()
            for index, (endpoint, snapshot) in enumerate(
                zip(approval["endpoints"], stability)
            ):
                role = endpoint["model_role"]
                server_pid = server_by_role.get(role, {}).get("server_pid", -1)
                _validate_snapshot(
                    snapshot,
                    endpoint,
                    server_pid,
                    f"stability[{index + 1}]",
                    errors,
                )
                if isinstance(snapshot, dict):
                    stability_runner_pids.add(snapshot.get("runner_pid"))
                    if (
                        isinstance(generations, list)
                        and len(generations) == 6
                        and snapshot.get("runner_pid")
                        != generations[index + 3].get("snapshot", {}).get("runner_pid")
                    ):
                        errors.append(f"stability_runner_changed:{role}")
            if len(stability_runner_pids) != 3:
                errors.append("stability_distinct_runner_pid_count_mismatch")

        unloads = observations["unloads"]
        if not isinstance(unloads, list) or len(unloads) != 3:
            errors.append("between_phase_unload_count_mismatch")
        else:
            for endpoint, unload in zip(approval["endpoints"], unloads):
                expected = {
                    "role": endpoint["model_role"],
                    "port": endpoint["port"],
                    "model_tag": endpoint["model_tag"],
                    "status_code": 200,
                    "done": True,
                    "done_reason": "unload",
                    "ps_models_after": [],
                }
                if not isinstance(unload, dict) or unload != expected:
                    errors.append(f"unload_not_verified:{endpoint['model_role']}")

        cleanup = observations["cleanup"]
        if not isinstance(cleanup, dict) or cleanup.get("passed") is not True:
            errors.append("cleanup_observation_not_passed")
        else:
            expected_ports = [endpoint["port"] for endpoint in approval["endpoints"]]
            expected_pids = sorted(server["server_pid"] for server in server_by_role.values())
            if cleanup.get("temporary_ports_closed") != expected_ports:
                errors.append("cleanup_ports_not_closed")
            if cleanup.get("temporary_server_pids_absent") != expected_pids:
                errors.append("cleanup_server_pids_not_absent")
            if cleanup.get("temporary_runner_pids_absent") is not True:
                errors.append("cleanup_runner_pids_not_absent")
            if cleanup.get("prohibited_operations") != []:
                errors.append("prohibited_operation_observed")
            existing = cleanup.get("existing_service")
            pre_existing = preflight.get("existing_service", {}) if isinstance(preflight, dict) else {}
            if not isinstance(existing, dict) or (
                existing.get("port") != 11434
                or existing.get("pid") != approval["existing_ollama_pid_before"]
                or existing.get("pid") != pre_existing.get("pid")
                or existing.get("version") != pre_existing.get("version")
                or existing.get("start_time_ticks")
                != pre_existing.get("start_time_ticks")
                or existing.get("command") != pre_existing.get("command")
                or existing.get("ps_models") != []
            ):
                errors.append("existing_service_changed_during_cleanup")
            gpu_idle = cleanup.get("gpu_idle")
            if not isinstance(gpu_idle, list) or len(gpu_idle) != 8:
                errors.append("cleanup_gpu_idle_rows_missing")
            else:
                for row in gpu_idle:
                    if (
                        not isinstance(row, dict)
                        or type(row.get("memory_used_mib")) is not int
                        or row["memory_used_mib"] > approval["idle_memory_threshold_mib"]
                        or row.get("utilization_gpu") != 0
                        or row.get("compute_pids") != []
                    ):
                        errors.append("cleanup_gpu_not_idle")
                        break
            final_unloads = cleanup.get("final_unloads")
            if not isinstance(final_unloads, list) or len(final_unloads) != 3 or any(
                not isinstance(item, dict)
                or item.get("status_code") != 200
                or item.get("done") is not True
                or item.get("done_reason") != "unload"
                for item in final_unloads
            ):
                errors.append("final_unload_not_verified")

        if isinstance(generations, list):
            _validate_run_binding(root, approval, result, generations, errors)

        accepted_warnings, unknown_warnings = _warning_result(
            observations["warnings"],
            approval["allowed_warning_patterns"],
            errors,
        )
        second_tree = _regular_files(root)
        if second_tree != first_tree:
            raise EndpointReuseValidationError("attempt tree changed during validation")
    except EndpointReuseValidationError as error:
        errors.append(str(error))
        approval_sha = expected_approval_sha256
        approval_id = None
        source_commit = None
    else:
        approval_id = approval["approval_id"]
        source_commit = approval["source_commit_sha"]

    errors = list(dict.fromkeys(errors))
    accepted_warnings = list(dict.fromkeys(accepted_warnings))
    unknown_warnings = list(dict.fromkeys(unknown_warnings))
    if observed_aborted:
        operational = "ABORTED"
    elif errors:
        operational = "FAIL"
    elif unknown_warnings:
        operational = "MANUAL_REVIEW_REQUIRED"
    elif accepted_warnings:
        operational = "PASS_WITH_WARNINGS"
    else:
        operational = "PASS"
    eligible = operational in {"PASS", "PASS_WITH_WARNINGS"} and not errors
    value = {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "spec_version": SPEC_VERSION,
        "approval_id": approval_id,
        "approval_sha256": approval_sha,
        "source_commit_sha": source_commit,
        "operational_backend_result": operational,
        "evidence_publication_eligible": eligible,
        "accepted_warnings": accepted_warnings,
        "unknown_warnings": unknown_warnings,
        "errors": errors,
        "checks": {
            "generation_calls_exactly_six": "PASS" if "generation_call_count_mismatch" not in errors else "FAIL",
            "cleanup": "PASS" if not any("cleanup" in item for item in errors) else "FAIL",
            "publication_scope": "STRUCTURE_ONLY_GENERIC_PUBLISHER",
        },
        "gate4_formal_pass": False,
        "research_eligible": False,
        "backend_freeze": {"status": "not_frozen"},
    }
    return ValidationReport(
        operational_backend_result=operational,
        publication_eligible=eligible,
        errors=tuple(errors),
        warnings=tuple(accepted_warnings + unknown_warnings),
        value=value,
    )


def write_validation_report(path: Path | str, report: ValidationReport) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(canonical_json_bytes(report.value))
        handle.flush()
        os.fsync(handle.fileno())
    return destination


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise EndpointReuseValidationError(message)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("attempt_dir")
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--output")
    try:
        args = parser.parse_args(argv)
        if SHA256_RE.fullmatch(args.approval_sha256) is None:
            raise EndpointReuseValidationError("--approval-sha256 is invalid")
        report = validate_attempt(
            args.attempt_dir,
            expected_approval_sha256=args.approval_sha256,
        )
        if args.output:
            write_validation_report(args.output, report)
        sys.stdout.buffer.write(canonical_json_bytes(report.value))
        return 0 if report.publication_eligible else 1
    except EndpointReuseValidationError as error:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                {
                    "schema_version": VALIDATION_SCHEMA_VERSION,
                    "operational_backend_result": "FAIL",
                    "evidence_publication_eligible": False,
                    "errors": [str(error)],
                    "gate4_formal_pass": False,
                    "research_eligible": False,
                    "backend_freeze": {"status": "not_frozen"},
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
