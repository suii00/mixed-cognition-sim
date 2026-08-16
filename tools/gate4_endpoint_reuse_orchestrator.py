#!/usr/bin/env python3
"""Approval-bound Gate 4 Ollama endpoint-reuse orchestrator.

The public CLI has exactly two execution inputs: a canonical approval artifact
and its expected SHA-256.  All workload settings come from that artifact.  CPU
tests inject a synthetic backend; the default backend is the local, loopback-
only Ollama/NVIDIA implementation and must be run outside the Codex sandbox
only after a separate explicit GPU approval.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import pwd
import re
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Sequence

import requests

from engine.config import load_config
from engine.llm_client import build_ollama_chat_payload, extract_json
from engine.provenance import compute_config_hash, sha256_bytes, utc_now_iso
from engine.sim import Simulation
from tools import gate4_evidence_publisher as publisher
from tools import verify_gate4_evidence_bundle as independent_verifier
from tools.validate_gate4_ollama_endpoint_reuse import (
    APPROVAL_FILENAME,
    APPROVAL_SHA_FILENAME,
    CAPTURE_START_FILENAME,
    CONFIG_FILENAME,
    EXPECTED_STATES,
    INDEX_FILENAME,
    INDEX_SCHEMA_VERSION,
    OBSERVATIONS_FILENAME,
    OBSERVATION_SCHEMA_VERSION,
    PUBLISHER_APPROVAL_FILENAME,
    RESULT_FILENAME,
    RESULT_SCHEMA_VERSION,
    ROLE_ORDER,
    SHA256_RE,
    SPEC_VERSION,
    TRANSCRIPT_FILENAME,
    VALIDATION_FILENAME,
    canonical_json_bytes,
    decode_canonical_json,
    publisher_approval_projection,
    validate_approval,
    validate_attempt,
    write_validation_report,
)
from tools.validate_run import validate_run


RECEIPT_SCHEMA_VERSION = "gate4-ollama-endpoint-reuse-receipt-v1.0.0"
CAPTURE_START_SCHEMA_VERSION = "gate4-ollama-endpoint-reuse-capture-start-v1.0.0"
METRIC_VERSION = "backend-smoke-observation-v1.0.0"

SPEC_PATH = "docs/GATE4_OLLAMA_ENDPOINT_REUSE_SPEC.md"
PUBLISHER_SPEC_PATH = "docs/GATE4_EVIDENCE_PUBLICATION_SPEC.md"
PUBLISHER_PATH = "tools/gate4_evidence_publisher.py"
INDEPENDENT_VERIFIER_PATH = "tools/verify_gate4_evidence_bundle.py"
VALIDATOR_PATH = "tools/validate_gate4_ollama_endpoint_reuse.py"
ORCHESTRATOR_PATH = "tools/gate4_endpoint_reuse_orchestrator.py"

EXPECTED_PHASE_ROLE_ORDER = tuple(
    (phase, role) for phase in ("phase1", "phase3") for role in ROLE_ORDER
)


class EndpointReuseError(RuntimeError):
    """Base class for a controlled endpoint-reuse failure."""


class EndpointReuseInvocationError(EndpointReuseError):
    """The approval or static execution envelope is invalid."""


class EndpointReuseCollisionError(EndpointReuseError):
    """The approval ID already owns an attempt, final bundle, or receipt."""


class EndpointReuseExecutionError(EndpointReuseError):
    """The approved workload failed or contradicted its evidence contract."""


class EndpointBackend(Protocol):
    """Administrative and generation boundary used by the orchestrator core."""

    def preflight(self, approval: Mapping[str, Any], attempt_dir: Path) -> Dict[str, Any]: ...

    def start_servers(
        self,
        approval: Mapping[str, Any],
        attempt_dir: Path,
        preflight: Mapping[str, Any],
    ) -> list[Dict[str, Any]]: ...

    def generate(
        self,
        approval: Mapping[str, Any],
        endpoint: Mapping[str, Any],
        server: Mapping[str, Any],
        request_payload: Mapping[str, Any],
    ) -> Dict[str, Any]: ...

    def snapshot(
        self,
        approval: Mapping[str, Any],
        endpoint: Mapping[str, Any],
        server: Mapping[str, Any],
        stage: str,
    ) -> Dict[str, Any]: ...

    def unload(
        self,
        approval: Mapping[str, Any],
        endpoint: Mapping[str, Any],
        server: Mapping[str, Any],
        stage: str,
    ) -> Dict[str, Any]: ...

    def cleanup(
        self,
        approval: Mapping[str, Any],
        attempt_dir: Path,
        preflight: Mapping[str, Any],
        servers: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]: ...

    def warnings(self) -> list[Dict[str, Any]]: ...


@dataclass(frozen=True)
class SourceState:
    commit_sha: str
    dirty: bool


@dataclass(frozen=True)
class OrchestrationReceipt:
    approval_id: str
    attempt_path: Path
    final_path: Optional[Path]
    receipt_path: Optional[Path]
    operational_backend_result: str
    publication_verified: bool


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, value: Any) -> None:
    _write_exclusive(path, canonical_json_bytes(value))


def _stable_read(path: Path, context: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise EndpointReuseInvocationError(f"{context} is not a regular file")
    before = path.stat()
    if before.st_nlink != 1:
        raise EndpointReuseInvocationError(f"{context} must have exactly one link")
    data = path.read_bytes()
    after = path.stat()
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_nlink,
    )
    if identity(before) != identity(after) or len(data) != after.st_size:
        raise EndpointReuseInvocationError(f"{context} changed while being read")
    return data


def _source_state(repository: Path) -> SourceState:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty_output = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return SourceState(commit_sha=commit, dirty=bool(dirty_output))


def _artifact_hashes(repository: Path) -> Dict[str, str]:
    paths = {
        "publisher_spec_sha256": PUBLISHER_SPEC_PATH,
        "publisher_sha256": PUBLISHER_PATH,
        "independent_verifier_sha256": INDEPENDENT_VERIFIER_PATH,
        "workload_spec_sha256": SPEC_PATH,
        "workload_validator_sha256": VALIDATOR_PATH,
        "orchestrator_sha256": ORCHESTRATOR_PATH,
    }
    return {
        field: _sha256(_stable_read(repository / relative, relative))
        for field, relative in paths.items()
    }


def load_approval(
    approval_path: Path | str,
    expected_sha256: str,
) -> tuple[Mapping[str, Any], bytes, str]:
    if SHA256_RE.fullmatch(expected_sha256) is None:
        raise EndpointReuseInvocationError("approval SHA pin is invalid")
    path = Path(approval_path)
    data = _stable_read(path, "endpoint-reuse approval")
    observed = _sha256(data)
    if observed != expected_sha256:
        raise EndpointReuseInvocationError("approval SHA differs from mandatory pin")
    try:
        approval = validate_approval(
            decode_canonical_json(data, "endpoint-reuse approval")
        )
    except Exception as error:
        raise EndpointReuseInvocationError(str(error)) from error
    return approval, data, observed


def validate_static_envelope(
    approval: Mapping[str, Any],
    approval_sha256: str,
    repository: Path,
    *,
    source_probe: Callable[[Path], SourceState] = _source_state,
) -> Dict[str, str]:
    source = source_probe(repository)
    if source.commit_sha != approval["source_commit_sha"]:
        raise EndpointReuseInvocationError("source commit differs from approval")
    if source.dirty or approval["source_dirty"] is not False:
        raise EndpointReuseInvocationError("source tree is dirty")
    observed_hashes = _artifact_hashes(repository)
    for field, observed in observed_hashes.items():
        if approval[field] != observed:
            raise EndpointReuseInvocationError(f"{field} differs from approval")
    if approval_sha256 != _sha256(canonical_json_bytes(dict(approval))):
        raise EndpointReuseInvocationError("approval canonical bytes changed after validation")
    return observed_hashes


class Transcript:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("xb")
        self._lock = threading.Lock()
        self._sequence = 0
        self._state_history: list[str] = []
        self._state = "planned"
        self.enter("planned", {})

    @property
    def state_history(self) -> list[str]:
        with self._lock:
            return list(self._state_history)

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def _append(self, state: str, event: str, details: Mapping[str, Any]) -> None:
        self._sequence += 1
        value = {
            "sequence": self._sequence,
            "state": state,
            "event": event,
            "utc": utc_now_iso(),
            "monotonic_ns": time.monotonic_ns(),
            "details": copy.deepcopy(dict(details)),
        }
        self._handle.write(canonical_json_bytes(value))
        self._handle.flush()
        os.fsync(self._handle.fileno())

    def enter(self, state: str, details: Mapping[str, Any]) -> None:
        with self._lock:
            expected_index = len(self._state_history)
            if expected_index >= len(EXPECTED_STATES) or EXPECTED_STATES[expected_index] != state:
                raise EndpointReuseExecutionError(
                    f"invalid state transition to {state!r}"
                )
            self._state = state
            self._state_history.append(state)
            self._append(state, "state_entered", details)

    def event(self, event: str, details: Mapping[str, Any]) -> None:
        with self._lock:
            self._append(self._state, event, details)

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.flush()
                os.fsync(self._handle.fileno())
                self._handle.close()


def _build_config(
    approval: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> Dict[str, Any]:
    templates = {
        artifact["role"]: artifact["template"]
        for artifact in preflight["model_artifacts"]
    }
    bloc_names = {"qwen": "alpha", "llama": "beta", "gemma": "neutral"}
    blocs = []
    for endpoint in approval["endpoints"]:
        role = endpoint["model_role"]
        blocs.append(
            {
                "name": bloc_names[role],
                "provider": "ollama",
                "model": endpoint["model_tag"],
                "base_url": f"http://127.0.0.1:{endpoint['port']}",
                "num_agents": 1,
                "llm_overrides": {"num_ctx": approval["num_ctx"]},
                "model_digest": endpoint["model_digest"],
                "quantization": "F16",
                "chat_template": templates[role],
            }
        )
    return {
        "simulation": {
            "duration": 1,
            "half_space_size": 1,
            "seed": 42,
            "run_name": approval["approval_id"],
            "run_id": approval["approval_id"],
            "protocol_version": SPEC_VERSION,
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
            "temperature": approval["temperature"],
            "max_tokens": approval["num_predict"],
            "timeout_s": approval["request_timeout_seconds"],
            "max_concurrency": 1,
        },
    }


class ReuseTransport:
    def __init__(
        self,
        approval: Mapping[str, Any],
        backend: EndpointBackend,
        servers: Sequence[Mapping[str, Any]],
        transcript: Transcript,
        deadline_monotonic: float,
    ) -> None:
        self.approval = approval
        self.backend = backend
        self.transcript = transcript
        self.endpoint_by_model = {
            endpoint["model_tag"]: endpoint for endpoint in approval["endpoints"]
        }
        self.server_by_role = {
            server["role"]: server for server in servers
        }
        self.records: list[Dict[str, Any]] = []
        self.attempts: list[Dict[str, Any]] = []
        self.unloads: list[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._phase3_prepared = False
        self._deadline_monotonic = deadline_monotonic

    def _check_deadline(self) -> None:
        if time.monotonic() > self._deadline_monotonic:
            raise EndpointReuseExecutionError("approved wall-time ceiling exceeded")

    def _prepare_phase3(self) -> None:
        if self._phase3_prepared:
            return
        for endpoint in self.approval["endpoints"]:
            self._check_deadline()
            role = endpoint["model_role"]
            unload = self.backend.unload(
                self.approval,
                endpoint,
                self.server_by_role[role],
                "between_phases",
            )
            self.unloads.append(copy.deepcopy(unload))
        self.transcript.enter("models_unloaded", {"count": len(self.unloads)})
        if any(
            unload
            != {
                "role": endpoint["model_role"],
                "port": endpoint["port"],
                "model_tag": endpoint["model_tag"],
                "status_code": 200,
                "done": True,
                "done_reason": "unload",
                "ps_models_after": [],
            }
            for endpoint, unload in zip(self.approval["endpoints"], self.unloads)
        ):
            raise EndpointReuseExecutionError("between-phase unload is incomplete")
        self.transcript.enter("unload_verified", {"endpoints": list(ROLE_ORDER)})
        self._phase3_prepared = True

    def __call__(self, request, telemetry):
        self._check_deadline()
        endpoint = self.endpoint_by_model.get(request.model)
        if endpoint is None:
            raise EndpointReuseExecutionError("request model is not approved")
        role = endpoint["model_role"]
        server = self.server_by_role[role]
        with self._lock:
            if request.phase == "phase3":
                self._prepare_phase3()
            ordinal = len(self.records) + 1
        payload = build_ollama_chat_payload(
            prompt=request.prompt,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            llm_overrides=copy.deepcopy(request.llm_overrides),
            keep_alive=-1,
        )
        started = time.monotonic_ns()
        result: Dict[str, Any]
        try:
            result = self.backend.generate(
                self.approval,
                endpoint,
                server,
                payload,
            )
            self._check_deadline()
            observed_telemetry = result.get(
                "telemetry",
                {
                    "http_attempts": 1,
                    "generation_retries": 0,
                    "transport_failures": 0,
                    "syntax_parse_failures": 0,
                },
            )
            for event, key in (
                ("http_attempt", "http_attempts"),
                ("generation_retry", "generation_retries"),
                ("transport_failure", "transport_failures"),
                ("syntax_parse_attempt_failure", "syntax_parse_failures"),
            ):
                amount = observed_telemetry.get(key, 0)
                if type(amount) is int and amount > 0:
                    telemetry(event, amount)
            raw_body = result["raw_body"]
            attempt_record = {
                "ordinal": ordinal,
                "phase": request.phase,
                "role": role,
                "request_id": request.request_id,
                "request_payload": payload,
                "prompt_sha256": sha256_bytes(request.prompt.encode("utf-8")),
                "status_code": result["status_code"],
                "raw_body_base64": base64.b64encode(raw_body).decode("ascii"),
                "raw_body_sha256": _sha256(raw_body),
                "telemetry": copy.deepcopy(observed_telemetry),
                "error_type": None,
                "error_message": None,
                "start_monotonic_ns": started,
                "end_monotonic_ns": time.monotonic_ns(),
            }
            with self._lock:
                self.attempts.append(attempt_record)
            if result["status_code"] != 200:
                raise EndpointReuseExecutionError("generation HTTP status is not 200")
            if observed_telemetry != {
                "http_attempts": 1,
                "generation_retries": 0,
                "transport_failures": 0,
                "syntax_parse_failures": 0,
            }:
                raise EndpointReuseExecutionError(
                    "generation telemetry violates zero-retry contract"
                )
            snapshot = self.backend.snapshot(
                self.approval,
                endpoint,
                server,
                request.phase,
            )
            self._check_deadline()
            record = {
                "ordinal": ordinal,
                "phase": request.phase,
                "role": role,
                "request_id": request.request_id,
                "server_pid": server["server_pid"],
                "port": endpoint["port"],
                "gpu_uuid": endpoint["gpu_uuid"],
                "model_tag": endpoint["model_tag"],
                "model_digest": endpoint["model_digest"],
                "quantization": "F16",
                "num_ctx": self.approval["num_ctx"],
                "request_payload": payload,
                "prompt_sha256": sha256_bytes(request.prompt.encode("utf-8")),
                "status_code": result["status_code"],
                "raw_body_base64": base64.b64encode(raw_body).decode("ascii"),
                "raw_body_sha256": _sha256(raw_body),
                "envelope": copy.deepcopy(result["envelope"]),
                "parsed": copy.deepcopy(result["parsed"]),
                "raw_output": result["raw_output"],
                "telemetry": copy.deepcopy(observed_telemetry),
                "snapshot": copy.deepcopy(snapshot),
                "start_monotonic_ns": started,
                "end_monotonic_ns": time.monotonic_ns(),
            }
            with self._lock:
                self.records.append(record)
                if len(self.records) == 3:
                    self.transcript.enter(
                        "initial_generation_passed", {"generation_calls": 3}
                    )
                elif len(self.records) == 6:
                    self.transcript.enter(
                        "reload_generation_passed", {"generation_calls": 6}
                    )
            return result["parsed"], result["raw_output"]
        except Exception as error:
            if not any(
                attempt.get("ordinal") == ordinal for attempt in self.attempts
            ):
                with self._lock:
                    self.attempts.append(
                        {
                            "ordinal": ordinal,
                            "phase": request.phase,
                            "role": role,
                            "request_id": request.request_id,
                            "request_payload": payload,
                            "prompt_sha256": sha256_bytes(
                                request.prompt.encode("utf-8")
                            ),
                            "status_code": None,
                            "raw_body_base64": None,
                            "raw_body_sha256": None,
                            "telemetry": None,
                            "error_type": type(error).__name__,
                            "error_message": str(error)[:1000],
                            "start_monotonic_ns": started,
                            "end_monotonic_ns": time.monotonic_ns(),
                        }
                    )
            if not any(
                attempt.get("ordinal") == ordinal
                and attempt.get("status_code") is not None
                for attempt in self.attempts
            ):
                telemetry("transport_failure", 1)
            raise


def _artifact_index(root: Path) -> Dict[str, Any]:
    files: Dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {INDEX_FILENAME, VALIDATION_FILENAME}:
            continue
        relative = path.relative_to(root).as_posix()
        data = _stable_read(path, relative)
        files[relative] = {
            "sha256": _sha256(data),
            "bytes": len(data),
            "lines": data.count(b"\n"),
        }
    return {"schema_version": INDEX_SCHEMA_VERSION, "files": files}


def _strict_value(report) -> Dict[str, Any]:
    return {
        "valid": bool(report.valid),
        "errors": list(report.errors),
        "unverifiable": list(report.unverifiable),
    }


def _summary_draft(approval: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": publisher.SUMMARY_SCHEMA_VERSION,
        "evidence_bundle_id": approval["evidence_bundle_id"],
        "run_id": approval["approval_id"],
        "protocol_version": SPEC_VERSION,
        "metric_version": METRIC_VERSION,
        "execution_mode": "reference_ollama",
        "operational_backend_result": "NOT_EVALUATED",
        "evidence_publication_conformance": "CONFORMING",
        "gate4_formal_pass": False,
        "research_eligible": False,
        "backend_freeze": {"status": "not_frozen"},
        "claim_scope": list(publisher.GENERIC_CLAIM_SCOPE),
        "warnings": [],
        "unverified_claims": list(publisher.GENERIC_UNVERIFIED_CLAIMS),
        "correction": {
            "kind": "original",
            "supersedes": None,
            "reason_code": None,
            "reason": None,
            "raw_artifacts_changed": False,
            "repaired_properties": [],
            "not_repaired": [],
        },
    }


def run_approved_endpoint_reuse(
    approval_path: Path | str,
    approval_sha256: str,
    *,
    repository: Optional[Path] = None,
    backend: Optional[EndpointBackend] = None,
    source_probe: Callable[[Path], SourceState] = _source_state,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> OrchestrationReceipt:
    repo = (repository or Path(__file__).resolve().parents[1]).resolve()
    approval, approval_bytes, observed_approval_sha = load_approval(
        approval_path,
        approval_sha256,
    )
    artifact_hashes = validate_static_envelope(
        approval,
        observed_approval_sha,
        repo,
        source_probe=source_probe,
    )
    evidence_root = Path(approval["evidence_root"])
    attempts_root = evidence_root / "attempts"
    publication_root = evidence_root / "published"
    receipts_root = evidence_root / "receipts"
    attempt = attempts_root / approval["approval_id"]
    final = publication_root / approval["evidence_bundle_id"]
    receipt_path = receipts_root / f"{approval['approval_id']}.json"
    evidence_root.mkdir(parents=True, exist_ok=True)
    attempts_root.mkdir(mode=0o755, exist_ok=True)
    publication_root.mkdir(mode=0o755, exist_ok=True)
    receipts_root.mkdir(mode=0o755, exist_ok=True)
    for path, label in (
        (attempt, "attempt"),
        (final, "final bundle"),
        (receipt_path, "receipt"),
    ):
        if os.path.lexists(path):
            raise EndpointReuseCollisionError(f"{label} already exists: {path}")
    attempt.mkdir(mode=0o755, exist_ok=False)
    _write_exclusive(attempt / APPROVAL_FILENAME, approval_bytes)
    _write_exclusive(
        attempt / APPROVAL_SHA_FILENAME,
        (observed_approval_sha + "\n").encode("ascii"),
    )
    _write_json(
        attempt / PUBLISHER_APPROVAL_FILENAME,
        publisher_approval_projection(approval),
    )
    started_utc = utc_now_iso()
    started_monotonic = time.monotonic()
    deadline_monotonic = started_monotonic + approval["maximum_wall_seconds"]

    def check_deadline() -> None:
        if time.monotonic() > deadline_monotonic:
            raise EndpointReuseExecutionError("approved wall-time ceiling exceeded")
    _write_json(
        attempt / CAPTURE_START_FILENAME,
        {
            "schema_version": CAPTURE_START_SCHEMA_VERSION,
            "approval_sha256": observed_approval_sha,
            "source_commit_sha": approval["source_commit_sha"],
            "source_dirty": False,
            "started_utc": started_utc,
            "artifact_hashes": artifact_hashes,
        },
    )
    transcript = Transcript(attempt / TRANSCRIPT_FILENAME)
    active_backend = backend or LocalOllamaBackend()
    preflight: Dict[str, Any] = {}
    servers: list[Dict[str, Any]] = []
    transport: Optional[ReuseTransport] = None
    cleanup: Dict[str, Any] = {"passed": False}
    run_id = approval["approval_id"]
    strict_value: Dict[str, Any] = {"valid": False, "errors": ["not_run"]}
    stability_snapshots: list[Dict[str, Any]] = []
    failure_kind: Optional[str] = None
    failure_reasons: list[str] = []
    interrupted = False
    try:
        preflight = active_backend.preflight(approval, attempt)
        check_deadline()
        if preflight.get("passed") is not True:
            raise EndpointReuseExecutionError("backend preflight failed")
        transcript.enter("preflight_passed", {})
        servers = active_backend.start_servers(approval, attempt, preflight)
        check_deadline()
        if len(servers) != 3:
            raise EndpointReuseExecutionError("server count differs from approval")
        transcript.enter(
            "servers_started",
            {"server_pids": [server["server_pid"] for server in servers]},
        )
        config = _build_config(approval, preflight)
        _write_json(attempt / CONFIG_FILENAME, config)
        effective = load_config(str(attempt / CONFIG_FILENAME))
        if compute_config_hash(effective) != compute_config_hash(config):
            raise EndpointReuseExecutionError("effective config hash differs")
        transport = ReuseTransport(
            approval,
            active_backend,
            servers,
            transcript,
            deadline_monotonic,
        )
        runs_root = attempt / "runs"
        runs_root.mkdir(mode=0o755, exist_ok=False)
        simulation = Simulation(
            effective,
            output_root=runs_root,
            repo_root=repo,
            transport=transport,
        )
        simulation.run()
        check_deadline()
        if len(transport.records) != 6 or transcript.state != "reload_generation_passed":
            raise EndpointReuseExecutionError("reload generation did not complete exactly six calls")
        sleep_fn(approval["stability_wait_seconds"])
        check_deadline()
        for endpoint in approval["endpoints"]:
            role = endpoint["model_role"]
            stability_snapshots.append(
                active_backend.snapshot(
                    approval,
                    endpoint,
                    transport.server_by_role[role],
                    "stability",
                )
            )
        transcript.enter("reload_verified", {"endpoints": list(ROLE_ORDER)})
        run_dir = runs_root / f"output_{run_id}"
        strict = validate_run(run_dir, strict=True)
        strict_value = _strict_value(strict)
        _write_json(attempt / "strict-validation.json", strict_value)
        if not strict.valid:
            raise EndpointReuseExecutionError("strict validator rejected Simulation run")
    except KeyboardInterrupt:
        interrupted = True
        failure_kind = "KeyboardInterrupt"
        failure_reasons.append("operator_interrupted")
    except Exception as error:
        failure_kind = type(error).__name__
        failure_reasons.append(str(error))
    finally:
        try:
            cleanup = active_backend.cleanup(
                approval,
                attempt,
                preflight,
                servers,
            )
        except Exception as error:
            cleanup = {"passed": False, "errors": [f"{type(error).__name__}:{error}"]}
        if cleanup.get("passed") is True and not failure_reasons and not interrupted:
            try:
                transcript.enter("cleanup_passed", {})
            except Exception as error:
                failure_kind = type(error).__name__
                failure_reasons.append(str(error))
        elif cleanup.get("passed") is not True:
            failure_kind = failure_kind or "CleanupFailure"
            failure_reasons.append("cleanup_failed")
        transcript.close()

    generations = transport.records if transport is not None else []
    generation_attempts = transport.attempts if transport is not None else []
    unloads = transport.unloads if transport is not None else []
    observations = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "approval_sha256": observed_approval_sha,
        "preflight": preflight,
        "servers": servers,
        "generation_attempts": generation_attempts,
        "generations": generations,
        "unloads": unloads,
        "stability_snapshots": stability_snapshots,
        "warnings": active_backend.warnings(),
        "cleanup": cleanup,
    }
    _write_json(attempt / OBSERVATIONS_FILENAME, observations)
    status = "aborted" if interrupted else (
        "completed" if not failure_reasons else "failed"
    )
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "approval_sha256": observed_approval_sha,
        "status": status,
        "terminal_state": transcript.state,
        "state_history": transcript.state_history,
        "failure_kind": failure_kind,
        "failure_reasons": list(dict.fromkeys(failure_reasons)),
        "started_utc": started_utc,
        "ended_utc": utc_now_iso(),
        "elapsed_seconds": time.monotonic() - started_monotonic,
        "generation_calls": len(generations),
        "administrative_unloads": len(unloads)
        + len(cleanup.get("final_unloads", [])),
        "cleanup_passed": cleanup.get("passed") is True,
        "run_id": run_id,
        "run_relative_path": f"runs/output_{run_id}",
        "strict_validation": strict_value,
        "gate4_formal_pass": False,
        "research_eligible": False,
        "backend_freeze": {"status": "not_frozen"},
    }
    _write_json(attempt / RESULT_FILENAME, result)
    _write_json(attempt / INDEX_FILENAME, _artifact_index(attempt))
    validation = validate_attempt(
        attempt,
        expected_approval_sha256=observed_approval_sha,
    )
    write_validation_report(attempt / VALIDATION_FILENAME, validation)
    if not validation.publication_eligible:
        return OrchestrationReceipt(
            approval_id=approval["approval_id"],
            attempt_path=attempt,
            final_path=None,
            receipt_path=None,
            operational_backend_result=validation.operational_backend_result,
            publication_verified=False,
        )

    def publication_failure_receipt(
        state: str,
        error: BaseException,
        observed_final: Optional[Path],
    ) -> OrchestrationReceipt:
        failure_value = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "approval_id": approval["approval_id"],
            "approval_sha256": observed_approval_sha,
            "source_commit_sha": approval["source_commit_sha"],
            "state_history": EXPECTED_STATES + [state],
            "status": state,
            "failure_type": type(error).__name__,
            "failure_message": str(error)[:1000],
            "operational_backend_result": validation.operational_backend_result,
            "publication_conforming": False,
            "workload_revalidated": False,
            "final_path": str(observed_final) if observed_final is not None else None,
            "gate4_formal_pass": False,
            "research_eligible": False,
            "backend_freeze": {"status": "not_frozen"},
        }
        _write_json(receipt_path, failure_value)
        return OrchestrationReceipt(
            approval_id=approval["approval_id"],
            attempt_path=attempt,
            final_path=observed_final,
            receipt_path=receipt_path,
            operational_backend_result=validation.operational_backend_result,
            publication_verified=False,
        )

    def staged_workload_check(checkpoint: str, staging: Path, _final: Path) -> None:
        if checkpoint != "after_inventory_verification_before_publish":
            return
        staged_validation = validate_attempt(
            staging,
            expected_approval_sha256=observed_approval_sha,
        )
        if (
            not staged_validation.publication_eligible
            or staged_validation.value != validation.value
        ):
            raise EndpointReuseExecutionError(
                "staged workload validation differs from approved attempt"
            )

    try:
        publication_receipt = publisher.publish_evidence(
            attempt,
            publication_root,
            _summary_draft(approval),
            checkpoint_hook=staged_workload_check,
        )
    except Exception as error:
        observed_final = final if final.is_dir() and not final.is_symlink() else None
        return publication_failure_receipt(
            "publication_failed", error, observed_final
        )
    try:
        verified = independent_verifier.verify_bundle(
            publication_receipt.final_path,
            expected_summary_sha256=publication_receipt.summary_sha256,
            expected_inventory_sha256=publication_receipt.inventory_sha256,
            expected_bundle_root_sha256=publication_receipt.bundle_root_sha256,
        )
        if not verified.valid:
            raise EndpointReuseExecutionError(
                "independent publication verification failed: "
                + ";".join(verified.errors)
            )
        final_workload_validation = validate_attempt(
            publication_receipt.final_path,
            expected_approval_sha256=observed_approval_sha,
        )
        if (
            not final_workload_validation.publication_eligible
            or final_workload_validation.value != validation.value
        ):
            raise EndpointReuseExecutionError(
                "published workload validation differs from approved attempt"
            )
    except Exception as error:
        return publication_failure_receipt(
            "verification_failed",
            error,
            publication_receipt.final_path,
        )
    receipt_value = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "approval_id": approval["approval_id"],
        "approval_sha256": observed_approval_sha,
        "source_commit_sha": approval["source_commit_sha"],
        "state_history": EXPECTED_STATES + ["evidence_published", "evidence_verified"],
        "status": "evidence_verified",
        "failure_type": None,
        "failure_message": None,
        "operational_backend_result": validation.operational_backend_result,
        "generic_publisher_operational_result": "NOT_EVALUATED",
        "summary_sha256": publication_receipt.summary_sha256,
        "inventory_sha256": publication_receipt.inventory_sha256,
        "bundle_root_sha256": publication_receipt.bundle_root_sha256,
        "final_path": str(publication_receipt.final_path),
        "publication_conforming": True,
        "workload_revalidated": True,
        "gate4_formal_pass": False,
        "research_eligible": False,
        "backend_freeze": {"status": "not_frozen"},
    }
    _write_json(receipt_path, receipt_value)
    return OrchestrationReceipt(
        approval_id=approval["approval_id"],
        attempt_path=attempt,
        final_path=publication_receipt.final_path,
        receipt_path=receipt_path,
        operational_backend_result=validation.operational_backend_result,
        publication_verified=True,
    )


class LocalOllamaBackend:
    """Local real backend. It is never instantiated by CPU fixtures."""

    def __init__(self) -> None:
        self._processes: Dict[str, subprocess.Popen] = {}
        self._logs: Dict[str, Any] = {}
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._warnings: list[Dict[str, Any]] = []

    @staticmethod
    def _run(command: Sequence[str], *, timeout: int = 30, env=None) -> Dict[str, Any]:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        value = {
            "command": list(command),
            "exit_code": completed.returncode,
            "stdout": completed.stdout.decode("utf-8", errors="replace"),
            "stderr": completed.stderr.decode("utf-8", errors="replace"),
        }
        if completed.returncode != 0:
            raise EndpointReuseExecutionError(
                f"command failed: {command[0]} exit={completed.returncode}"
            )
        return value

    @staticmethod
    def _api_json(method: str, url: str, *, payload=None, timeout=30) -> tuple[int, bytes, Any]:
        response = requests.request(method, url, json=payload, timeout=timeout)
        raw = bytes(response.content)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EndpointReuseExecutionError(f"API response is not JSON: {url}") from error
        return int(response.status_code), raw, value

    @staticmethod
    def _port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
            handle.settimeout(0.2)
            return handle.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def _pid_state(pid: int) -> tuple[int, str]:
        stat_fields = Path(f"/proc/{pid}/stat").read_text().split()
        start_ticks = int(stat_fields[21])
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8", errors="replace"
        ).strip()
        return start_ticks, command

    @staticmethod
    def _process_table() -> list[Dict[str, Any]]:
        output = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,user=,args="],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        rows = []
        for line in output.splitlines():
            parts = line.strip().split(None, 3)
            if len(parts) == 4:
                rows.append(
                    {
                        "pid": int(parts[0]),
                        "ppid": int(parts[1]),
                        "user": parts[2],
                        "args": parts[3],
                    }
                )
        return rows

    @classmethod
    def _descendants(cls, pid: int) -> list[Dict[str, Any]]:
        rows = cls._process_table()
        known = {pid}
        changed = True
        while changed:
            changed = False
            for row in rows:
                if row["ppid"] in known and row["pid"] not in known:
                    known.add(row["pid"])
                    changed = True
        return [row for row in rows if row["pid"] in known]

    @classmethod
    def _server_pid(cls, launcher_pid: int, user: str) -> int:
        candidates = [
            row
            for row in cls._descendants(launcher_pid)
            if row["user"] == user and re.search(r"(^|/)ollama serve(?:\s|$)", row["args"])
        ]
        if len(candidates) != 1:
            raise EndpointReuseExecutionError("temporary server PID is ambiguous")
        return candidates[0]["pid"]

    @staticmethod
    def _parse_gpu_rows(text: str) -> list[Dict[str, Any]]:
        rows = []
        for line in text.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) == 3:
                rows.append(
                    {
                        "uuid": parts[0],
                        "memory_used_mib": int(parts[1]),
                        "utilization_gpu": int(parts[2]),
                    }
                )
        return rows

    @staticmethod
    def _parse_compute_rows(text: str) -> list[Dict[str, Any]]:
        rows = []
        for line in text.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                rows.append(
                    {
                        "gpu_uuid": parts[0],
                        "pid": int(parts[1]),
                        "used_memory_mib": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                    }
                )
        return rows

    def _gpu_observation(self) -> Dict[str, Any]:
        gpu = self._run(
            [
                "nvidia-smi",
                "--query-gpu=uuid,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ]
        )
        compute = self._run(
            [
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ]
        )
        return {
            "gpu_rows": self._parse_gpu_rows(gpu["stdout"]),
            "compute_rows": self._parse_compute_rows(compute["stdout"]),
            "commands": [gpu, compute],
        }

    def preflight(self, approval: Mapping[str, Any], attempt_dir: Path) -> Dict[str, Any]:
        binary = Path(approval["ollama_binary"])
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise EndpointReuseExecutionError("approved Ollama binary is unavailable")
        sudo_check = self._run(
            ["sudo", "-n", "-H", "-u", approval["server_user"], "/usr/bin/true"]
        )
        cli_version = self._run([approval["ollama_binary"], "--version"])
        nvidia_list = self._run(["nvidia-smi", "-L"])
        gpu = self._gpu_observation()
        selected = [endpoint["gpu_uuid"] for endpoint in approval["endpoints"]]
        rows_by_uuid = {row["uuid"]: row for row in gpu["gpu_rows"]}
        if any(uuid not in rows_by_uuid for uuid in selected):
            raise EndpointReuseExecutionError("approved GPU UUID is absent")
        for uuid in selected:
            row = rows_by_uuid[uuid]
            if (
                row["memory_used_mib"] > approval["idle_memory_threshold_mib"]
                or row["utilization_gpu"] != 0
                or any(item["gpu_uuid"] == uuid for item in gpu["compute_rows"])
            ):
                raise EndpointReuseExecutionError("approved GPU is not idle")
        ports = [endpoint["port"] for endpoint in approval["endpoints"]]
        if any(self._port_open(port) for port in ports):
            raise EndpointReuseExecutionError("temporary endpoint port is already in use")
        system_url = f"http://127.0.0.1:{approval['existing_ollama_port']}"
        version_status, _, version = self._api_json("GET", system_url + "/api/version")
        ps_status, _, ps = self._api_json("GET", system_url + "/api/ps")
        if version_status != 200 or ps_status != 200 or ps.get("models") != []:
            raise EndpointReuseExecutionError("existing Ollama service preflight failed")
        start_ticks, command = self._pid_state(approval["existing_ollama_pid_before"])
        if "ollama serve" not in command:
            raise EndpointReuseExecutionError("approved existing PID is not ollama serve")
        tags_status, _, tags = self._api_json("GET", system_url + "/api/tags")
        if tags_status != 200:
            raise EndpointReuseExecutionError("system model catalog failed")
        catalog = {item.get("name"): item for item in tags.get("models", [])}
        artifacts = []
        for endpoint in approval["endpoints"]:
            item = catalog.get(endpoint["model_tag"])
            if not isinstance(item, dict) or item.get("digest") != endpoint["model_digest"]:
                raise EndpointReuseExecutionError("approved model digest is unavailable")
            details = item.get("details")
            if not isinstance(details, dict) or details.get("quantization_level") != "F16":
                raise EndpointReuseExecutionError("approved model is not F16")
            show_status, _, show = self._api_json(
                "POST",
                system_url + "/api/show",
                payload={"model": endpoint["model_tag"]},
            )
            if show_status != 200 or not isinstance(show.get("template"), str) or not show["template"]:
                raise EndpointReuseExecutionError("model template preflight failed")
            artifacts.append(
                {
                    "role": endpoint["model_role"],
                    "model_tag": endpoint["model_tag"],
                    "model_digest": endpoint["model_digest"],
                    "quantization": "F16",
                    "template": show["template"],
                }
            )
        return {
            "passed": True,
            "selected_gpu_uuids": selected,
            "ports_free": ports,
            "model_artifacts": artifacts,
            "existing_service": {
                "port": approval["existing_ollama_port"],
                "pid": approval["existing_ollama_pid_before"],
                "start_time_ticks": start_ticks,
                "command": command,
                "version": version["version"],
                "ps_models": [],
            },
            "nvidia_smi_L": nvidia_list,
            "gpu_observation": gpu,
            "sudo_check": sudo_check,
            "ollama_cli_version": cli_version,
        }

    def start_servers(
        self,
        approval: Mapping[str, Any],
        attempt_dir: Path,
        preflight: Mapping[str, Any],
    ) -> list[Dict[str, Any]]:
        servers = []
        for endpoint in approval["endpoints"]:
            role = endpoint["model_role"]
            log_path = attempt_dir / "server-logs" / f"{role}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_path.open("xb")
            command = [
                "sudo",
                "-n",
                "-H",
                "-u",
                approval["server_user"],
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
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                )
            except Exception:
                log_handle.close()
                raise
            self._processes[role] = process
            self._logs[role] = log_handle
            deadline = time.monotonic() + approval["cleanup_timeout_seconds"]
            version = None
            while time.monotonic() < deadline:
                try:
                    status, _, value = self._api_json(
                        "GET",
                        f"http://127.0.0.1:{endpoint['port']}/api/version",
                        timeout=2,
                    )
                    if status == 200:
                        version = value.get("version")
                        break
                except Exception:
                    pass
                time.sleep(0.25)
            if not version:
                raise EndpointReuseExecutionError(f"temporary server did not start: {role}")
            server_pid = self._server_pid(process.pid, approval["server_user"])
            start_ticks, server_command = self._pid_state(server_pid)
            base_url = f"http://127.0.0.1:{endpoint['port']}"
            ps_status, _, ps = self._api_json("GET", base_url + "/api/ps")
            tags_status, _, tags = self._api_json("GET", base_url + "/api/tags")
            show_status, _, show = self._api_json(
                "POST",
                base_url + "/api/show",
                payload={"model": endpoint["model_tag"]},
            )
            models = ps.get("models") if ps_status == 200 else None
            catalog = {
                item.get("name"): item
                for item in tags.get("models", [])
                if isinstance(item, dict)
            } if tags_status == 200 and isinstance(tags, dict) else {}
            catalog_item = catalog.get(endpoint["model_tag"])
            details = catalog_item.get("details") if isinstance(catalog_item, dict) else None
            model_artifact = {
                "role": role,
                "model_tag": endpoint["model_tag"],
                "model_digest": (
                    catalog_item.get("digest") if isinstance(catalog_item, dict) else None
                ),
                "quantization": (
                    details.get("quantization_level") if isinstance(details, dict) else None
                ),
                "template": show.get("template") if isinstance(show, dict) else None,
            }
            expected_artifact = next(
                item
                for item in preflight["model_artifacts"]
                if item["role"] == role
            )
            if (
                models != []
                or show_status != 200
                or model_artifact != expected_artifact
            ):
                raise EndpointReuseExecutionError(
                    f"temporary endpoint model binding failed: {role}"
                )
            server = {
                "role": role,
                "port": endpoint["port"],
                "gpu_uuid": endpoint["gpu_uuid"],
                "launcher_pid": process.pid,
                "server_pid": server_pid,
                "start_time_ticks": start_ticks,
                "server_command": server_command,
                "version": version,
                "launch_command": command,
                "initial_ps_models": models,
                "model_artifact": model_artifact,
            }
            self._servers[role] = server
            servers.append(server)
        return servers

    def generate(
        self,
        approval: Mapping[str, Any],
        endpoint: Mapping[str, Any],
        server: Mapping[str, Any],
        request_payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        url = f"http://127.0.0.1:{endpoint['port']}/api/chat"
        response = requests.post(
            url,
            json=dict(request_payload),
            timeout=approval["request_timeout_seconds"],
        )
        raw = bytes(response.content)
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            envelope = None
        message = envelope.get("message") if isinstance(envelope, dict) else None
        raw_output = message.get("content") if isinstance(message, dict) else ""
        parsed = extract_json(raw_output) if isinstance(raw_output, str) else None
        envelope_failure = not isinstance(envelope, dict)
        return {
            "status_code": int(response.status_code),
            "raw_body": raw,
            "envelope": envelope,
            "parsed": parsed,
            "raw_output": raw_output,
            "telemetry": {
                "http_attempts": 1,
                "generation_retries": 0,
                "transport_failures": 1 if envelope_failure else 0,
                "syntax_parse_failures": (
                    0 if envelope_failure or parsed is not None else 1
                ),
            },
        }

    def snapshot(
        self,
        approval: Mapping[str, Any],
        endpoint: Mapping[str, Any],
        server: Mapping[str, Any],
        stage: str,
    ) -> Dict[str, Any]:
        status, _, ps = self._api_json(
            "GET", f"http://127.0.0.1:{endpoint['port']}/api/ps"
        )
        models = ps.get("models") if status == 200 else None
        if not isinstance(models, list) or len(models) != 1:
            raise EndpointReuseExecutionError("endpoint residency model count differs")
        model = models[0]
        show_status, _, show = self._api_json(
            "POST",
            f"http://127.0.0.1:{endpoint['port']}/api/show",
            payload={"model": endpoint["model_tag"]},
        )
        details = show.get("details") if show_status == 200 and isinstance(show, dict) else None
        quantization = (
            details.get("quantization_level") if isinstance(details, dict) else None
        )
        cli_env = dict(os.environ)
        cli_env["OLLAMA_HOST"] = f"127.0.0.1:{endpoint['port']}"
        cli = self._run([approval["ollama_binary"], "ps"], env=cli_env)
        processor = "100% GPU" if "100% GPU" in cli["stdout"] else "not_100%_GPU"
        descendants = self._descendants(server["server_pid"])
        runners = [row for row in descendants if "llama-server" in row["args"]]
        if len(runners) != 1:
            raise EndpointReuseExecutionError("endpoint runner PID is ambiguous")
        gpu = self._gpu_observation()
        runner_pid = runners[0]["pid"]
        runner_uuids = sorted(
            {
                row["gpu_uuid"]
                for row in gpu["compute_rows"]
                if row["pid"] == runner_pid
            }
        )
        return {
            "role": endpoint["model_role"],
            "port": endpoint["port"],
            "server_pid": server["server_pid"],
            "runner_pid": runner_pid,
            "gpu_uuid": endpoint["gpu_uuid"],
            "model_tag": model.get("name"),
            "model_digest": model.get("digest"),
            "quantization": quantization,
            "context_length": model.get("context_length"),
            "size": model.get("size"),
            "size_vram": model.get("size_vram"),
            "processor": processor,
            "loaded_models": len(models),
            "runner_gpu_uuids": runner_uuids,
            "api_ps": ps,
            "api_show": show,
            "ollama_ps": cli,
            "gpu_observation": gpu,
            "runner_process": runners[0],
        }

    def unload(
        self,
        approval: Mapping[str, Any],
        endpoint: Mapping[str, Any],
        server: Mapping[str, Any],
        stage: str,
    ) -> Dict[str, Any]:
        status, _, response = self._api_json(
            "POST",
            f"http://127.0.0.1:{endpoint['port']}/api/generate",
            payload={
                "model": endpoint["model_tag"],
                "keep_alive": 0,
                "stream": False,
            },
            timeout=approval["request_timeout_seconds"],
        )
        deadline = time.monotonic() + approval["cleanup_timeout_seconds"]
        models = None
        while time.monotonic() < deadline:
            ps_status, _, ps = self._api_json(
                "GET", f"http://127.0.0.1:{endpoint['port']}/api/ps"
            )
            models = ps.get("models") if ps_status == 200 else None
            if models == []:
                break
            time.sleep(0.25)
        return {
            "role": endpoint["model_role"],
            "port": endpoint["port"],
            "model_tag": endpoint["model_tag"],
            "status_code": status,
            "done": response.get("done"),
            "done_reason": response.get("done_reason"),
            "ps_models_after": models,
        }

    def _stop_server(
        self,
        approval: Mapping[str, Any],
        server: Mapping[str, Any],
    ) -> Dict[str, Any]:
        pid = server["server_pid"]
        if pid == approval["existing_ollama_pid_before"]:
            raise EndpointReuseExecutionError("refusing to stop existing Ollama PID")
        start_ticks, command = self._pid_state(pid)
        if start_ticks != server["start_time_ticks"] or "ollama serve" not in command:
            raise EndpointReuseExecutionError("temporary server PID identity changed")
        expected_uid = pwd.getpwnam(approval["server_user"]).pw_uid
        if Path(f"/proc/{pid}").stat().st_uid != expected_uid:
            raise EndpointReuseExecutionError("temporary server UID changed")
        if not self._port_open(server["port"]):
            raise EndpointReuseExecutionError("temporary server port is not listening")
        termination = self._run(
            [
                "sudo",
                "-n",
                "-u",
                approval["server_user"],
                "/bin/kill",
                "-TERM",
                "--",
                str(pid),
            ],
            timeout=approval["cleanup_timeout_seconds"],
        )
        deadline = time.monotonic() + approval["cleanup_timeout_seconds"]
        while time.monotonic() < deadline:
            if not Path(f"/proc/{pid}").exists():
                return termination
            time.sleep(0.25)
        raise EndpointReuseExecutionError("temporary server did not stop after SIGTERM")

    def cleanup(
        self,
        approval: Mapping[str, Any],
        attempt_dir: Path,
        preflight: Mapping[str, Any],
        servers: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        errors: list[str] = []
        final_unloads: list[Dict[str, Any]] = []
        termination_commands: list[Dict[str, Any]] = []
        # start_servers can fail after launching only a prefix.  Retain and
        # clean those test-owned processes even when the caller never received
        # a complete return value.
        cleanup_servers = list(servers)
        known_roles = {server["role"] for server in cleanup_servers}
        cleanup_servers.extend(
            server
            for role, server in self._servers.items()
            if role not in known_roles
        )
        known_roles = {server["role"] for server in cleanup_servers}
        endpoints_by_role = {
            endpoint["model_role"]: endpoint for endpoint in approval["endpoints"]
        }
        unresolved_launchers: list[str] = []
        for role, process in self._processes.items():
            if role in known_roles or process.poll() is not None:
                continue
            endpoint = endpoints_by_role[role]
            try:
                server_pid = self._server_pid(process.pid, approval["server_user"])
                start_ticks, server_command = self._pid_state(server_pid)
                cleanup_servers.append(
                    {
                        "role": role,
                        "port": endpoint["port"],
                        "gpu_uuid": endpoint["gpu_uuid"],
                        "launcher_pid": process.pid,
                        "server_pid": server_pid,
                        "start_time_ticks": start_ticks,
                        "server_command": server_command,
                    }
                )
            except Exception as error:
                unresolved_launchers.append(role)
                errors.append(
                    f"resolve_partial_server:{role}:{type(error).__name__}:{error}"
                )
        server_by_role = {server["role"]: server for server in cleanup_servers}
        for endpoint in reversed(approval["endpoints"]):
            role = endpoint["model_role"]
            server = server_by_role.get(role)
            if server is None:
                continue
            try:
                final_unloads.append(
                    self.unload(approval, endpoint, server, "final_cleanup")
                )
            except Exception as error:
                errors.append(f"unload:{role}:{type(error).__name__}:{error}")
        for server in reversed(cleanup_servers):
            try:
                termination_commands.append(self._stop_server(approval, server))
            except Exception as error:
                errors.append(f"stop:{server['role']}:{type(error).__name__}:{error}")
        for role in unresolved_launchers:
            process = self._processes[role]
            if process.poll() is None:
                try:
                    process.terminate()
                except Exception as error:
                    errors.append(
                        f"terminate_launcher:{role}:{type(error).__name__}:{error}"
                    )
        for role, process in self._processes.items():
            try:
                process.wait(timeout=approval["cleanup_timeout_seconds"])
            except subprocess.TimeoutExpired:
                errors.append(f"launcher_still_running:{role}")
        for handle in self._logs.values():
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
        self._collect_warnings(attempt_dir)
        ports = [endpoint["port"] for endpoint in approval["endpoints"]]
        closed = [port for port in ports if not self._port_open(port)]
        absent = sorted(
            server["server_pid"]
            for server in cleanup_servers
            if not Path(f"/proc/{server['server_pid']}").exists()
        )
        gpu = self._gpu_observation()
        pids_by_uuid: Dict[str, list[int]] = {}
        for row in gpu["compute_rows"]:
            pids_by_uuid.setdefault(row["gpu_uuid"], []).append(row["pid"])
        gpu_idle = [
            {
                "uuid": row["uuid"],
                "memory_used_mib": row["memory_used_mib"],
                "utilization_gpu": row["utilization_gpu"],
                "compute_pids": sorted(pids_by_uuid.get(row["uuid"], [])),
            }
            for row in gpu["gpu_rows"]
        ]
        existing_status, _, existing_version = self._api_json(
            "GET", f"http://127.0.0.1:{approval['existing_ollama_port']}/api/version"
        )
        ps_status, _, existing_ps = self._api_json(
            "GET", f"http://127.0.0.1:{approval['existing_ollama_port']}/api/ps"
        )
        try:
            existing_start_ticks, existing_command = self._pid_state(
                approval["existing_ollama_pid_before"]
            )
            existing_pid = approval["existing_ollama_pid_before"]
        except (OSError, ValueError):
            existing_start_ticks = None
            existing_command = None
            existing_pid = None
        existing = {
            "port": approval["existing_ollama_port"],
            "pid": existing_pid,
            "start_time_ticks": existing_start_ticks,
            "command": existing_command,
            "version": existing_version.get("version") if existing_status == 200 else None,
            "ps_models": existing_ps.get("models") if ps_status == 200 else None,
        }
        passed = (
            not errors
            and closed == ports
            and len(absent) == len(cleanup_servers)
            and len(gpu_idle) == 8
            and all(
                row["memory_used_mib"] <= approval["idle_memory_threshold_mib"]
                and row["utilization_gpu"] == 0
                and row["compute_pids"] == []
                for row in gpu_idle
            )
            and existing["version"] == preflight.get("existing_service", {}).get("version")
            and existing["pid"] == preflight.get("existing_service", {}).get("pid")
            and existing["start_time_ticks"]
            == preflight.get("existing_service", {}).get("start_time_ticks")
            and existing["command"] == preflight.get("existing_service", {}).get("command")
            and existing["ps_models"] == []
        )
        return {
            "passed": passed,
            "errors": errors,
            "temporary_ports_closed": closed,
            "temporary_server_pids_absent": absent,
            "temporary_runner_pids_absent": not gpu["compute_rows"],
            "gpu_idle": gpu_idle,
            "existing_service": existing,
            "final_unloads": list(reversed(final_unloads)),
            "termination_commands": termination_commands,
            "prohibited_operations": [],
        }

    def _collect_warnings(self, attempt_dir: Path) -> None:
        for role in ROLE_ORDER:
            path = attempt_dir / "server-logs" / f"{role}.log"
            if not path.is_file():
                continue
            for line in path.read_text(errors="replace").splitlines():
                level = None
                if "level=WARN" in line or " WARN " in line:
                    level = "WARN"
                elif "level=ERROR" in line or " ERROR " in line:
                    level = "ERROR"
                elif any(
                    token in line.upper()
                    for token in (
                        "OOM",
                        "OUT OF MEMORY",
                        "PANIC",
                        "FATAL",
                        "CRASH",
                        "SEGFAULT",
                        "CUDA ERROR",
                        "XID",
                    )
                ):
                    level = "FATAL"
                if level:
                    self._warnings.append({"role": role, "level": level, "message": line})

    def warnings(self) -> list[Dict[str, Any]]:
        return copy.deepcopy(self._warnings)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise EndpointReuseInvocationError(message)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--approval-sha256", required=True)
    try:
        args = parser.parse_args(argv)
        receipt = run_approved_endpoint_reuse(
            args.approval,
            args.approval_sha256,
        )
        sys.stdout.buffer.write(
            canonical_json_bytes(
                {
                    "approval_id": receipt.approval_id,
                    "attempt_path": str(receipt.attempt_path),
                    "final_path": str(receipt.final_path) if receipt.final_path else None,
                    "receipt_path": str(receipt.receipt_path) if receipt.receipt_path else None,
                    "operational_backend_result": receipt.operational_backend_result,
                    "publication_verified": receipt.publication_verified,
                    "gate4_formal_pass": False,
                    "research_eligible": False,
                }
            )
        )
        return 0 if receipt.publication_verified else 1
    except EndpointReuseCollisionError as error:
        print(f"[COLLISION] {error}", file=sys.stderr)
        return 3
    except EndpointReuseInvocationError as error:
        print(f"[INVALID] {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("[ABORTED] interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"[FAILED] {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
