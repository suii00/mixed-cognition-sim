#!/usr/bin/env python3
"""Gate 4A-1 native Ollama single-request evidence probe.

The probe is deliberately separate from simulation runs.  It exercises the
existing ``engine.llm_client.call_ollama`` path once, captures the complete
native response envelope through a sidecar observer, and fails closed when the
declared model, context, or single-GPU contract is contradicted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import requests

from engine.llm_client import build_ollama_chat_payload, call_ollama
from engine.prompts import build_phase1_prompt
from engine.provenance import (
    canonical_json_bytes,
    collect_git_info,
    compute_prompt_hash,
    file_manifest,
    sha256_bytes,
    utc_now_iso,
    validate_base_url,
)


PROBE_SCHEMA_VERSION = "gate4-backend-evidence-manifest-v1.0.0"
BACKEND_SPEC_VERSION = "gate4-backend-smoke-v1.0.0"
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
REQUIRED_RESPONSE_INTS = (
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
)


class ProbeCollisionError(FileExistsError):
    """The requested evidence directory already exists."""


class ProbeFailure(RuntimeError):
    """A stop condition made the evidence candidate fail."""


class ProbeInvocationError(ValueError):
    """The requested probe contract is invalid."""


class ProbeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ProbeInvocationError(message)


def _json_file_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, value: Any) -> None:
    _write_exclusive(path, _json_file_bytes(value))


def _run_command(
    args: Sequence[str],
    *,
    timeout_s: float = 30.0,
    env_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    environment = os.environ.copy()
    if env_overrides:
        environment.update(env_overrides)
    try:
        completed = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            timeout=timeout_s,
            env=environment,
        )
    except FileNotFoundError:
        return {
            "argv": list(args),
            "exit_code": None,
            "stdout": b"",
            "stderr": b"",
            "error": "command_not_found",
        }
    except subprocess.TimeoutExpired as error:
        return {
            "argv": list(args),
            "exit_code": None,
            "stdout": error.stdout or b"",
            "stderr": error.stderr or b"",
            "error": "timeout",
        }
    except OSError:
        return {
            "argv": list(args),
            "exit_code": None,
            "stdout": b"",
            "stderr": b"",
            "error": "os_error",
        }
    return {
        "argv": list(args),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "error": None if completed.returncode == 0 else "nonzero_exit",
    }


def _capture_command(
    output_dir: Path,
    stem: str,
    args: Sequence[str],
    *,
    timeout_s: float = 30.0,
    env_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    result = _run_command(
        args,
        timeout_s=timeout_s,
        env_overrides=env_overrides,
    )
    _write_exclusive(output_dir / f"{stem}.txt", result.pop("stdout"))
    _write_exclusive(
        output_dir / f"{stem}.stderr.txt",
        result.pop("stderr"),
    )
    return result


def _request_json(
    method: str,
    url: str,
    *,
    timeout_s: int,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bytes]:
    try:
        response = requests.request(
            method,
            url,
            json=payload,
            timeout=timeout_s,
        )
        response.raise_for_status()
        raw = response.content
        value = response.json()
    except requests.RequestException as error:
        raise ProbeFailure(f"Ollama API probe failed: {type(error).__name__}") from error
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ProbeFailure("Ollama API probe returned invalid JSON") from error
    if not isinstance(value, dict):
        raise ProbeFailure("Ollama API probe response is not an object")
    return value, raw


def _capture_api(
    output_dir: Path,
    filename: str,
    method: str,
    url: str,
    *,
    timeout_s: int,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    value, raw = _request_json(
        method,
        url,
        timeout_s=timeout_s,
        payload=payload,
    )
    _write_exclusive(output_dir / filename, raw)
    return value


def _copy_server_log(source: Path, destination: Path) -> str:
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise ProbeFailure("server log cannot be read") from error
    _write_exclusive(destination, raw)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProbeFailure("server log is not UTF-8") from error


def _add_check(
    checks: list[Dict[str, Any]],
    failures: list[str],
    name: str,
    passed: bool,
    observed: Any,
) -> None:
    checks.append({"name": name, "passed": bool(passed), "observed": observed})
    if not passed:
        failures.append(name)


def _find_model(models: Any, model_name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(models, list):
        return None
    matches = [
        item
        for item in models
        if isinstance(item, dict)
        and (item.get("name") == model_name or item.get("model") == model_name)
    ]
    return matches[0] if len(matches) == 1 else None


def _validate_server_contract(
    server_log: str,
    base_url: str,
    expected_gpu_uuid: str,
    checks: list[Dict[str, Any]],
    failures: list[str],
) -> None:
    host_port = urlsplit(base_url).netloc
    compute_lines = [
        line for line in server_log.splitlines() if 'msg="inference compute"' in line
    ]
    cuda_lines = [line for line in compute_lines if "library=CUDA" in line]
    vulkan_lines = [line for line in compute_lines if "library=Vulkan" in line]
    _add_check(
        checks,
        failures,
        "server_loopback_binding",
        f"Listening on {host_port}" in server_log,
        host_port,
    )
    _add_check(
        checks,
        failures,
        "server_cloud_disabled",
        "OLLAMA_NO_CLOUD:true" in server_log,
        "OLLAMA_NO_CLOUD:true" in server_log,
    )
    _add_check(
        checks,
        failures,
        "server_context_4096",
        "OLLAMA_CONTEXT_LENGTH:4096" in server_log,
        "OLLAMA_CONTEXT_LENGTH:4096" in server_log,
    )
    _add_check(
        checks,
        failures,
        "server_parallel_one",
        "OLLAMA_NUM_PARALLEL:1" in server_log,
        "OLLAMA_NUM_PARALLEL:1" in server_log,
    )
    _add_check(
        checks,
        failures,
        "server_one_loaded_model",
        "OLLAMA_MAX_LOADED_MODELS:1" in server_log,
        "OLLAMA_MAX_LOADED_MODELS:1" in server_log,
    )
    _add_check(
        checks,
        failures,
        "server_vulkan_disabled",
        "OLLAMA_VULKAN:false" in server_log and not vulkan_lines,
        {"declared_false": "OLLAMA_VULKAN:false" in server_log, "vulkan_devices": len(vulkan_lines)},
    )
    _add_check(
        checks,
        failures,
        "server_single_cuda_gpu",
        len(cuda_lines) == 1 and expected_gpu_uuid in cuda_lines[0],
        {"cuda_devices": len(cuda_lines), "expected_gpu_uuid_seen": any(expected_gpu_uuid in line for line in cuda_lines)},
    )
    _add_check(
        checks,
        failures,
        "server_visible_gpu_uuid",
        f"CUDA_VISIBLE_DEVICES:{expected_gpu_uuid}" in server_log,
        expected_gpu_uuid,
    )


def _validate_response_envelope(
    envelope: Any,
    model: str,
    checks: list[Dict[str, Any]],
    failures: list[str],
) -> None:
    is_object = isinstance(envelope, dict)
    _add_check(checks, failures, "response_is_object", is_object, type(envelope).__name__)
    if not is_object:
        return
    message = envelope.get("message")
    _add_check(
        checks,
        failures,
        "response_model_matches",
        envelope.get("model") == model,
        envelope.get("model"),
    )
    _add_check(
        checks,
        failures,
        "response_done",
        envelope.get("done") is True,
        envelope.get("done"),
    )
    _add_check(
        checks,
        failures,
        "response_message_content",
        isinstance(message, dict) and isinstance(message.get("content"), str),
        isinstance(message, dict) and isinstance(message.get("content"), str),
    )
    for field in REQUIRED_RESPONSE_INTS:
        value = envelope.get(field)
        _add_check(
            checks,
            failures,
            f"response_{field}",
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            value,
        )


def _validate_compute_apps(
    raw_text: str,
    expected_gpu_uuid: str,
    checks: list[Dict[str, Any]],
    failures: list[str],
) -> None:
    ollama_rows = [
        line
        for line in raw_text.splitlines()
        if "ollama" in line.casefold() or "llama-server" in line.casefold()
    ]
    all_expected = bool(ollama_rows) and all(
        line.split(",", 1)[0].strip() == expected_gpu_uuid
        for line in ollama_rows
    )
    _add_check(
        checks,
        failures,
        "ollama_compute_process_on_expected_gpu_only",
        all_expected,
        {"ollama_process_rows": len(ollama_rows), "expected_gpu_uuid": expected_gpu_uuid},
    )


def _artifact_manifest(output_dir: Path) -> Dict[str, Any]:
    files = {}
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if (
            path.name == "backend_evidence_manifest.json"
            or not path.is_file()
            or path.is_symlink()
        ):
            continue
        files[path.name] = file_manifest(path)
    return files


def _validate_invocation(
    base_url: str,
    model: str,
    expected_digest: str,
    expected_quantization: str,
    expected_template_sha256: str,
    expected_gpu_uuid: str,
    num_ctx: int,
    max_tokens: int,
    timeout_s: int,
) -> None:
    try:
        validate_base_url(base_url)
    except ValueError as error:
        raise ProbeInvocationError(str(error)) from error
    if urlsplit(base_url).hostname not in LOOPBACK_HOSTS:
        raise ProbeInvocationError("Gate 4A-1 base URL must be loopback-only")
    if not isinstance(model, str) or not model.strip():
        raise ProbeInvocationError("model must be non-empty")
    if HEX64_RE.fullmatch(expected_digest) is None:
        raise ProbeInvocationError("expected digest must be lowercase SHA-256")
    if not expected_quantization:
        raise ProbeInvocationError("expected quantization must be non-empty")
    if HEX64_RE.fullmatch(expected_template_sha256) is None:
        raise ProbeInvocationError(
            "expected template hash must be lowercase SHA-256"
        )
    if not expected_gpu_uuid.startswith("GPU-"):
        raise ProbeInvocationError("expected GPU UUID must start with GPU-")
    for name, value in (("num_ctx", num_ctx), ("max_tokens", max_tokens), ("timeout_s", timeout_s)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ProbeInvocationError(f"{name} must be a positive integer")
    if num_ctx != 4096:
        raise ProbeInvocationError("Gate 4A-1 num_ctx must be exactly 4096")


def run_probe(
    output_dir: Path | str,
    *,
    server_log: Path | str,
    base_url: str,
    model: str,
    expected_digest: str,
    expected_quantization: str,
    expected_template_sha256: str,
    expected_gpu_uuid: str,
    temperature: float,
    max_tokens: int,
    num_ctx: int = 4096,
    timeout_s: int = 120,
    keep_alive: int = -1,
    repo_root: Optional[Path] = None,
) -> Path:
    """Run one native request and publish an immutable candidate evidence set."""
    _validate_invocation(
        base_url,
        model,
        expected_digest,
        expected_quantization,
        expected_template_sha256,
        expected_gpu_uuid,
        num_ctx,
        max_tokens,
        timeout_s,
    )
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise ProbeInvocationError("temperature must be numeric")
    if not isinstance(keep_alive, int) or isinstance(keep_alive, bool):
        raise ProbeInvocationError("keep_alive must be an integer")

    destination = Path(output_dir).resolve()
    try:
        destination.mkdir(mode=0o755, parents=False, exist_ok=False)
    except FileExistsError as error:
        raise ProbeCollisionError(f"evidence directory already exists: {destination}") from error
    repository = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    log_source = Path(server_log).resolve()
    started = utc_now_iso()
    checks: list[Dict[str, Any]] = []
    failures: list[str] = []
    command_results: Dict[str, Any] = {}
    telemetry: Counter[str] = Counter()
    envelopes: list[Dict[str, Any]] = []
    model_identity: Dict[str, Any] = {}
    status = "failed"
    failure_type: Optional[str] = None

    prompt = build_phase1_prompt(
        agent_id=0,
        x=0,
        y=0,
        half_space_size=25,
        places=[],
        place=None,
        agent_count=1,
        memories=[],
        messages=[],
    )
    request_payload = build_ollama_chat_payload(
        prompt=prompt,
        model=model,
        temperature=float(temperature),
        max_tokens=max_tokens,
        llm_overrides={"num_ctx": num_ctx},
        keep_alive=keep_alive,
    )
    _write_exclusive(destination / "prompt.txt", prompt.encode("utf-8"))
    _write_json(destination / "request.json", request_payload)

    try:
        command_results["nvidia_smi_L"] = _capture_command(
            destination,
            "nvidia-smi-L",
            ["nvidia-smi", "-L"],
        )
        command_results["nvidia_smi_before"] = _capture_command(
            destination,
            "nvidia-smi-before",
            ["nvidia-smi"],
        )
        command_results["ollama_cli_version"] = _capture_command(
            destination,
            "ollama-cli-version",
            ["ollama", "--version"],
        )
        for name, result in command_results.items():
            _add_check(
                checks,
                failures,
                f"command_{name}",
                result.get("exit_code") == 0,
                {"exit_code": result.get("exit_code"), "error": result.get("error")},
            )

        server_before = _copy_server_log(
            log_source,
            destination / "server-log-before.txt",
        )
        _validate_server_contract(
            server_before,
            base_url,
            expected_gpu_uuid,
            checks,
            failures,
        )

        version = _capture_api(
            destination,
            "api-version.json",
            "GET",
            f"{base_url}/api/version",
            timeout_s=timeout_s,
        )
        tags = _capture_api(
            destination,
            "api-tags.json",
            "GET",
            f"{base_url}/api/tags",
            timeout_s=timeout_s,
        )
        show = _capture_api(
            destination,
            "api-show.json",
            "POST",
            f"{base_url}/api/show",
            timeout_s=timeout_s,
            payload={"model": model},
        )
        tag = _find_model(tags.get("models"), model)
        _add_check(checks, failures, "model_present_once", tag is not None, model)
        if tag is not None:
            details = tag.get("details") if isinstance(tag.get("details"), dict) else {}
            digest = tag.get("digest")
            quantization = details.get("quantization_level")
            template = show.get("template")
            model_identity = {
                "model": model,
                "digest": digest,
                "quantization": quantization,
                "parameter_size": details.get("parameter_size"),
                "format": details.get("format"),
                "chat_template_sha256": (
                    sha256_bytes(template.encode("utf-8"))
                    if isinstance(template, str)
                    else None
                ),
            }
            _add_check(checks, failures, "model_digest_matches", digest == expected_digest, digest)
            _add_check(
                checks,
                failures,
                "model_quantization_matches",
                quantization == expected_quantization,
                quantization,
            )
            _add_check(
                checks,
                failures,
                "model_chat_template_present",
                isinstance(template, str) and bool(template),
                isinstance(template, str) and bool(template),
            )
            _add_check(
                checks,
                failures,
                "model_chat_template_matches",
                model_identity["chat_template_sha256"]
                == expected_template_sha256,
                model_identity["chat_template_sha256"],
            )
        server_version = version.get("version")
        _add_check(
            checks,
            failures,
            "server_version_present",
            isinstance(server_version, str) and bool(server_version),
            server_version,
        )

        if failures:
            raise ProbeFailure("pre-request stop condition")

        def record_telemetry(event: str, amount: int = 1) -> None:
            telemetry[event] += amount

        parsed, raw_output = call_ollama(
            prompt=prompt,
            model=model,
            base_url=base_url,
            temperature=float(temperature),
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            llm_overrides={"num_ctx": num_ctx},
            telemetry=record_telemetry,
            keep_alive=keep_alive,
            response_observer=envelopes.append,
        )
        _write_exclusive(destination / "raw-output.txt", raw_output.encode("utf-8"))
        _write_json(destination / "parsed-output.json", parsed)
        for index, envelope in enumerate(envelopes, start=1):
            _write_json(destination / f"native-response-{index:02d}.json", envelope)

        _add_check(checks, failures, "single_native_response", len(envelopes) == 1, len(envelopes))
        _add_check(checks, failures, "parsed_output_present", isinstance(parsed, dict), type(parsed).__name__)
        expected_telemetry = {
            "http_attempt": 1,
            "generation_retry": 0,
            "transport_failure": 0,
            "syntax_parse_attempt_failure": 0,
        }
        observed_telemetry = {
            key: telemetry.get(key, 0) for key in expected_telemetry
        }
        _add_check(
            checks,
            failures,
            "single_http_attempt_no_retry_or_failure",
            observed_telemetry == expected_telemetry,
            observed_telemetry,
        )
        if envelopes:
            _validate_response_envelope(envelopes[0], model, checks, failures)

        ps = _capture_api(
            destination,
            "api-ps-after.json",
            "GET",
            f"{base_url}/api/ps",
            timeout_s=timeout_s,
        )
        loaded = _find_model(ps.get("models"), model)
        _add_check(checks, failures, "model_loaded_once", loaded is not None, model)
        if loaded is not None:
            _add_check(
                checks,
                failures,
                "loaded_digest_matches",
                loaded.get("digest") == expected_digest,
                loaded.get("digest"),
            )
            _add_check(
                checks,
                failures,
                "allocated_context_matches",
                loaded.get("context_length") == num_ctx,
                loaded.get("context_length"),
            )
            size = loaded.get("size")
            size_vram = loaded.get("size_vram")
            _add_check(
                checks,
                failures,
                "api_ps_no_cpu_offload",
                isinstance(size, int) and size > 0 and size_vram == size,
                {"size": size, "size_vram": size_vram},
            )

        command_results["ollama_ps_after"] = _capture_command(
            destination,
            "ollama-ps-after",
            ["ollama", "ps"],
            env_overrides={"OLLAMA_HOST": base_url},
        )
        command_results["nvidia_compute_apps_after"] = _capture_command(
            destination,
            "nvidia-compute-apps-after",
            [
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
        )
        command_results["nvidia_smi_after"] = _capture_command(
            destination,
            "nvidia-smi-after",
            ["nvidia-smi"],
        )
        for name in ("ollama_ps_after", "nvidia_compute_apps_after", "nvidia_smi_after"):
            result = command_results[name]
            _add_check(
                checks,
                failures,
                f"command_{name}",
                result.get("exit_code") == 0,
                {"exit_code": result.get("exit_code"), "error": result.get("error")},
            )
        ollama_ps_text = (destination / "ollama-ps-after.txt").read_text(
            encoding="utf-8",
            errors="replace",
        )
        _add_check(
            checks,
            failures,
            "cli_ps_100_percent_gpu",
            model in ollama_ps_text and "100% GPU" in ollama_ps_text,
            model in ollama_ps_text and "100% GPU" in ollama_ps_text,
        )
        compute_apps_text = (destination / "nvidia-compute-apps-after.txt").read_text(
            encoding="utf-8",
            errors="replace",
        )
        _validate_compute_apps(
            compute_apps_text,
            expected_gpu_uuid,
            checks,
            failures,
        )

        server_after = _copy_server_log(
            log_source,
            destination / "server-log-after.txt",
        )
        _validate_server_contract(
            server_after,
            base_url,
            expected_gpu_uuid,
            checks,
            failures,
        )
        _add_check(
            checks,
            failures,
            "server_selected_cuda_backend",
            "library=CUDA" in server_after and "library=Vulkan" not in server_after,
            {"cuda_seen": "library=CUDA" in server_after, "vulkan_seen": "library=Vulkan" in server_after},
        )

        if failures:
            raise ProbeFailure("post-request stop condition")
        status = "passed"
    except ProbeFailure as error:
        failure_type = type(error).__name__
    except BaseException as error:
        failure_type = type(error).__name__
        failures.append("unexpected_probe_failure")

    ended = utc_now_iso()
    manifest_payload: Dict[str, Any] = {
        "schema_version": PROBE_SCHEMA_VERSION,
        "backend_spec_version": BACKEND_SPEC_VERSION,
        "backend_spec_sha256": sha256_bytes(
            (repository / "docs" / "GATE4_BACKEND_SMOKE_SPEC.md").read_bytes()
        ),
        "stage": "4A-1",
        "status": status,
        "research_eligible": False,
        "start_time_utc": started,
        "end_time_utc": ended,
        "failure_type": failure_type,
        "failures": failures,
        "checks": checks,
        "request_contract": {
            "provider": "ollama",
            "transport": "ollama_native",
            "endpoint": "/api/chat",
            "base_url": base_url,
            "model": model,
            "expected_model_digest": expected_digest,
            "expected_quantization": expected_quantization,
            "expected_chat_template_sha256": expected_template_sha256,
            "temperature": float(temperature),
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
            "keep_alive": keep_alive,
            "expected_gpu_uuid": expected_gpu_uuid,
        },
        "model_identity": model_identity,
        "telemetry": dict(sorted(telemetry.items())),
        "native_response_count": len(envelopes),
        "source_git": collect_git_info(repository),
        "prompt_source": "engine.prompts.build_phase1_prompt",
        "prompt_source_sha256": compute_prompt_hash(repository),
        "prompt_instance_sha256": sha256_bytes(prompt.encode("utf-8")),
        "request_sha256": sha256_bytes(_json_file_bytes(request_payload)),
        "command_results": command_results,
        "files": _artifact_manifest(destination),
    }
    evidence_id = "gate4a1-" + sha256_bytes(canonical_json_bytes(manifest_payload))
    manifest = {"evidence_id": evidence_id, **manifest_payload}
    _write_json(destination / "backend_evidence_manifest.json", manifest)
    if status != "passed":
        raise ProbeFailure(
            f"Gate 4A-1 failed; retained evidence {evidence_id}"
        )
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = ProbeArgumentParser(
        prog="python3 -m tools.ollama_reference_probe",
        description="Capture one Gate 4A-1 native Ollama request evidence set",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11440")
    parser.add_argument("--model", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--expected-quantization", required=True)
    parser.add_argument("--expected-template-sha256", required=True)
    parser.add_argument("--expected-gpu-uuid", required=True)
    parser.add_argument("--temperature", type=float, required=True)
    parser.add_argument("--max-tokens", type=int, required=True)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--timeout-s", type=int, default=120)
    parser.add_argument("--keep-alive", type=int, default=-1)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        output = run_probe(
            args.output_dir,
            server_log=args.server_log,
            base_url=args.base_url,
            model=args.model,
            expected_digest=args.expected_digest,
            expected_quantization=args.expected_quantization,
            expected_template_sha256=args.expected_template_sha256,
            expected_gpu_uuid=args.expected_gpu_uuid,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            num_ctx=args.num_ctx,
            timeout_s=args.timeout_s,
            keep_alive=args.keep_alive,
        )
    except ProbeCollisionError as error:
        print(f"COLLISION: {error}", file=sys.stderr)
        return 3
    except ProbeInvocationError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    except ProbeFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ABORTED: interrupted", file=sys.stderr)
        return 130
    print(f"PASS: Gate 4A-1 evidence captured at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
