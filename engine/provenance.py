"""Run identity, provenance capture, and atomic lifecycle metadata."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import platform as platform_module
import re
import socket
import subprocess
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import parse_qsl, unquote_plus, urlsplit, urlunsplit


LOG_SCHEMA_VERSION = "1.0.0"
DEFAULT_PROTOCOL_VERSION = "unversioned"
DEFAULT_METRIC_VERSION = "unversioned"
RAW_JSONL_FILES = (
    "phase1_raw.jsonl",
    "messages.jsonl",
    "memory_reasoning.jsonl",
    "parse_errors.jsonl",
)
DEPENDENCY_DISTRIBUTIONS = ("requests", "PyYAML", "matplotlib", "Pillow")

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9_-])?$")
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_SECRET_KEYS = {
    "token", "apikey", "accesstoken", "refreshtoken", "authtoken", "authorization",
    "password", "passwd", "pass", "passphrase", "pwd", "secret", "clientsecret", "credential",
    "credentials", "privatekey", "cookie", "setcookie", "headers",
    "httpheaders",
}
_URL_KEYS = {
    "url",
    "baseurl",
    "endpoint",
    "apiendpoint",
    "connectionstring",
    "odbcconnect",
}
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?:^|[?&#;,\s])"
    r"(?:api[-_]?key|access[-_]?token|auth(?:orization)?|bearer|"
    r"password|passwd|passphrase|pwd|pass|secret|token)\s*[:=]",
    re.IGNORECASE,
)
_JDBC_OPAQUE_CREDENTIAL_RE = re.compile(
    r"^jdbc:(?:[^:@/\s]+:)+[^:@/\s]+/[^@\s]+@",
    re.IGNORECASE,
)
_COUNTER_FIELDS = {
    "logical_llm_calls",
    "http_attempts",
    "generation_retries",
    "transport_failures",
    "syntax_parse_attempt_failures",
    "syntax_parse_failures",
    "schema_validation_failures",
}


class InvalidRunIdError(ValueError):
    """Raised before a run directory is created when a run ID is unsafe."""


class RunCollisionError(FileExistsError):
    """Raised when the exclusive run directory already exists."""


class RunLifecycleError(RuntimeError):
    """Raised when a run lifecycle invariant cannot be satisfied."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_run_id(value: str) -> str:
    """Validate a canonical, cross-platform-safe run ID without rewriting it."""
    if not isinstance(value, str):
        raise InvalidRunIdError("run ID must be a string")
    if not value or value != value.strip():
        raise InvalidRunIdError("run ID must be non-empty and have no edge whitespace")
    normalized = unicodedata.normalize("NFKC", value)
    if normalized != value:
        raise InvalidRunIdError("run ID must already be NFKC-normalized")
    if value in {".", ".."} or ".." in value:
        raise InvalidRunIdError("run ID may not contain '..'")
    if "/" in value or "\\" in value or "\x00" in value:
        raise InvalidRunIdError("run ID may not contain path separators or NUL")
    if os.path.isabs(value) or Path(value).is_absolute():
        raise InvalidRunIdError("run ID may not be an absolute path")
    if not _RUN_ID_RE.fullmatch(value):
        raise InvalidRunIdError(
            "run ID must be 1-128 ASCII characters using letters, digits, '.', '_', or '-'"
        )
    if value.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise InvalidRunIdError("run ID uses a reserved filename")
    return value


def generate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return normalize_run_id(f"{timestamp}-{uuid.uuid4().hex[:12]}")


def resolve_run_id(config: Dict[str, Any]) -> str:
    explicit = config.get("simulation", {}).get("run_id")
    return normalize_run_id(explicit) if explicit is not None else generate_run_id()


def _normalized_key(key: Any) -> str:
    text = unicodedata.normalize("NFKC", str(key)).casefold()
    return re.sub(r"[^a-z0-9]", "", text)


def sanitize_url(value: str) -> str:
    """Keep only scheme and host/port; drop credentials, path, query, fragment."""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if not hostname:
            return "<redacted-url>"
        display_host = f"[{hostname}]" if ":" in hostname else hostname
        try:
            port = parsed.port
        except ValueError:
            return "<redacted-url>"
        netloc = f"{display_host}:{port}" if port is not None else display_host
        return urlunsplit((parsed.scheme, netloc, "", "", ""))
    except (TypeError, ValueError):
        return "<redacted-url>"


def validate_base_url(value: Any) -> str:
    """Require an origin-only HTTP(S) URL for the current Ollama client."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("bloc base_url must be a non-empty canonical URL")
    if any(character.isspace() for character in value):
        raise ValueError("bloc base_url may not contain whitespace")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise ValueError("bloc base_url is not a valid URL") from error
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("bloc base_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("bloc base_url may not contain credentials")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError(
            "bloc base_url must contain only scheme, host, and optional port"
        )
    # Accessing parsed.port above validates its syntax. Keep this assignment so
    # static readers can see that an optional port is intentionally accepted.
    del port
    return value


def validate_provider(value: Any) -> str:
    """Accept only the provider implemented by the current execution path."""
    if value != "ollama":
        raise ValueError("bloc provider must be exactly 'ollama'")
    return value


def _key_components(key: Any) -> set[str]:
    text = unicodedata.normalize("NFKC", str(key))
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return {
        component.lower()
        for component in re.split(r"[^A-Za-z0-9]+", text)
        if component
    }


def _is_secret_key(key: Any) -> bool:
    """Match credential keys without treating max_tokens/tokenizer as secrets."""
    normalized = _normalized_key(key)
    if normalized in _SECRET_KEYS:
        return True
    components = _key_components(key)
    if components & {
        "auth",
        "authentication",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "pass",
        "passphrase",
        "pwd",
        "secret",
        "token",
    }:
        return True
    if "key" in components:
        return True
    if "key" in components and components & {
        "access",
        "api",
        "aws",
        "encryption",
        "private",
        "secret",
        "signing",
        "ssh",
    }:
        return True
    return normalized.endswith((
        "token",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "authtoken",
        "password",
        "passwd",
        "pass",
        "passphrase",
        "pwd",
        "secret",
        "credential",
        "credentials",
        "clientsecret",
        "privatekey",
        "secretkey",
        "accesskey",
        "authkey",
        "authenticationkey",
        "authorizationkey",
        "bearerkey",
        "signingkey",
        "encryptionkey",
        "sshkey",
        "awskey",
        "licensekey",
        "subscriptionkey",
        "cookie",
        "headers",
        "bearer",
        "authentication",
    ))


def _is_url_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    components = _key_components(key)
    return (
        normalized in _URL_KEYS
        or bool(components & {"url", "uri", "dsn", "endpoint"})
        or normalized.endswith(("url", "uri", "dsn", "endpoint"))
    )


def _uri_has_sensitive_components(value: str) -> bool:
    """Detect URL/DSN credentials while preserving non-secret URL syntax."""
    normalized = unicodedata.normalize("NFKC", value)
    decoded = unquote_plus(normalized)
    if (
        _SENSITIVE_ASSIGNMENT_RE.search(normalized)
        or _SENSITIVE_ASSIGNMENT_RE.search(decoded)
        or _JDBC_OPAQUE_CREDENTIAL_RE.search(normalized)
        or _JDBC_OPAQUE_CREDENTIAL_RE.search(decoded)
    ):
        return True

    candidates = [normalized, decoded]
    if normalized.casefold().startswith("jdbc:"):
        candidates.append(normalized[5:])
        candidates.append(decoded[5:])
    for candidate in candidates:
        try:
            parsed = urlsplit(candidate)
        except (TypeError, ValueError):
            continue
        if not parsed.scheme:
            continue
        if parsed.username is not None or parsed.password is not None:
            return True
        for component in (parsed.query, parsed.fragment):
            try:
                pairs = parse_qsl(component, keep_blank_values=True)
            except ValueError:
                pairs = []
            if any(_is_secret_key(key) for key, _ in pairs):
                return True
    return False


def _validate_json_config_value(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("config mapping keys must be strings")
            _validate_json_config_value(child)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_config_value(item)
        return
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("config contains a non-finite float")
        return
    raise ValueError(
        f"config contains unsupported JSON value type: {type(value).__name__}"
    )


def sanitize_config(value: Any, parent_key: Optional[str] = None) -> Any:
    """Return a JSON-safe deep copy with credential-bearing fields redacted."""
    if parent_key is None:
        _validate_json_config_value(value)
    if parent_key is not None and _is_secret_key(parent_key):
        return "<redacted>"
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("config mapping keys must be strings")
            key_text = key
            if _is_secret_key(key_text):
                sanitized[key_text] = "<redacted>"
            elif _is_url_key(key_text) and isinstance(child, str):
                sanitized[key_text] = (
                    sanitize_url(child)
                    if _uri_has_sensitive_components(child)
                    else child
                )
            else:
                sanitized[key_text] = sanitize_config(child, key_text)
        return sanitized
    if isinstance(value, list):
        return [sanitize_config(item, parent_key) for item in value]
    if isinstance(value, str):
        # Preserve benign strings byte-for-byte for config hash fidelity. If a
        # URI hides credentials under an unrelated key, retain only its origin
        # to prevent credential persistence.
        return sanitize_url(value) if _uri_has_sensitive_components(value) else value
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("config contains a non-finite float")
        return value
    raise ValueError(
        f"config contains unsupported JSON value type: {type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_config_hash(config_snapshot: Dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(config_snapshot))


def compute_prompt_hash(repo_root: Optional[Path] = None) -> str:
    root = repo_root or Path(__file__).resolve().parent.parent
    return sha256_bytes((root / "engine" / "prompts.py").read_bytes())


def _run_command(args: Iterable[str], cwd: Path, timeout_s: float = 5.0) -> Tuple[bool, str, str]:
    try:
        completed = subprocess.run(
            list(args),
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return False, "", "command_not_found"
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except OSError:
        return False, "", "os_error"
    if completed.returncode != 0:
        return False, completed.stdout, f"exit_{completed.returncode}"
    return True, completed.stdout, ""


def collect_git_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    try:
        root = repo_root or Path(__file__).resolve().parent.parent
        sha_ok, sha_output, sha_error = _run_command(
            ["git", "rev-parse", "HEAD"], root
        )
        status_ok, status_output, status_error = _run_command(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], root
        )
        errors = [error for error in (sha_error, status_error) if error]
        return {
            "git_sha": sha_output.strip() if sha_ok else None,
            "git_dirty": bool(status_output) if status_ok else None,
            "git_probe_status": "available" if not errors else "unavailable",
            "git_probe_errors": errors,
        }
    except Exception:
        return {
            "git_sha": None,
            "git_dirty": None,
            "git_probe_status": "unavailable",
            "git_probe_errors": ["unexpected_probe_error"],
        }


def collect_dependency_versions() -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for distribution in DEPENDENCY_DISTRIBUTIONS:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
        except Exception:
            versions[distribution] = None
    return versions


def collect_gpu_info() -> Dict[str, Any]:
    try:
        query = [
            "nvidia-smi",
            "--query-gpu=index,name,uuid,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
        ok, output, error = _run_command(query, Path.cwd(), timeout_s=5.0)
        if not ok:
            return {
                "status": "unavailable",
                "error": error,
                "driver_version": None,
                "cuda_version": None,
                "cuda_probe_status": "unavailable",
                "cuda_probe_error": "gpu_query_unavailable",
                "malformed_device_rows": 0,
                "devices": [],
            }

        devices = []
        malformed_device_rows = 0
        driver_versions = set()
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 5 or any(not part for part in parts):
                malformed_device_rows += 1
                continue
            index, name, gpu_uuid, memory_total_mib, driver_version = parts
            driver_versions.add(driver_version)
            devices.append({
                "index": index,
                "name": name,
                "uuid": gpu_uuid,
                "memory_total_mib": memory_total_mib,
            })

        basic_ok, basic_output, basic_error = _run_command(
            ["nvidia-smi"], Path.cwd(), timeout_s=5.0
        )
        cuda_match = (
            re.search(r"CUDA Version:\s*([^|\s]+)", basic_output)
            if basic_ok else None
        )
        if not devices:
            error = "malformed_output"
            gpu_status = "unavailable"
        elif malformed_device_rows:
            error = "malformed_device_rows"
            gpu_status = "partial"
        elif not basic_ok:
            error = basic_error
            gpu_status = "available"
        else:
            error = None
            gpu_status = "available"
        cuda_version = cuda_match.group(1) if cuda_match else None
        if cuda_version is not None:
            cuda_probe_status = "available"
            cuda_probe_error = None
        elif not basic_ok:
            cuda_probe_status = "unavailable"
            cuda_probe_error = basic_error
        else:
            cuda_probe_status = "unavailable"
            cuda_probe_error = "cuda_version_not_reported"
        return {
            "status": gpu_status,
            "error": error,
            "driver_version": sorted(driver_versions)[0] if driver_versions else None,
            "cuda_version": cuda_version,
            "cuda_probe_status": cuda_probe_status,
            "cuda_probe_error": cuda_probe_error,
            "malformed_device_rows": malformed_device_rows,
            "devices": devices,
        }
    except Exception:
        # Provenance probing must never make a scientifically valid run fail.
        # Keep this diagnostic deliberately coarse so probe exceptions cannot
        # copy paths, command output, or credentials into run metadata.
        return {
            "status": "unavailable",
            "error": "unexpected_probe_error",
            "driver_version": None,
            "cuda_version": None,
            "cuda_probe_status": "unavailable",
            "cuda_probe_error": "unexpected_probe_error",
            "malformed_device_rows": 0,
            "devices": [],
        }


def collect_bloc_models(config: Dict[str, Any]) -> list[Dict[str, Any]]:
    result = []
    for bloc in config.get("blocs", []):
        try:
            parsed = urlsplit(str(bloc.get("base_url", "")))
            hostname = parsed.hostname
            port = parsed.port
        except (TypeError, ValueError):
            hostname = None
            port = None
        chat_template = bloc.get("chat_template")
        detail_values = (
            bloc.get("model_digest"),
            bloc.get("quantization"),
            chat_template,
        )
        result.append({
            "bloc": str(bloc.get("name", "")),
            "provider": validate_provider(bloc.get("provider", "ollama")),
            "model": str(bloc.get("model", "")),
            "base_url_host": hostname,
            "base_url_port": port,
            "model_digest": bloc.get("model_digest"),
            "quantization": bloc.get("quantization"),
            "chat_template_hash": (
                sha256_bytes(chat_template.encode("utf-8"))
                if isinstance(chat_template, str) else None
            ),
            "detail_source": (
                "config"
                if all(value is not None for value in detail_values)
                else (
                    "partial"
                    if any(value is not None for value in detail_values)
                    else "unavailable"
                )
            ),
        })
    return result


def file_manifest(path: Path) -> Dict[str, Any]:
    digest = hashlib.sha256()
    line_count = 0
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
            line_count += chunk.count(b"\n")
    return {"sha256": digest.hexdigest(), "bytes": size, "lines": line_count}


def build_raw_manifest(output_dir: Path) -> Dict[str, Any]:
    files = {}
    for filename in RAW_JSONL_FILES:
        path = output_dir / filename
        if path.is_file():
            files[filename] = file_manifest(path)
    return {"algorithm": "sha256", "files": files}


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    temp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _failure_thresholds(config: Dict[str, Any]) -> Dict[str, int]:
    configured = config.get("simulation", {}).get("failure_thresholds", {})
    if not isinstance(configured, dict):
        raise ValueError("simulation.failure_thresholds must be a mapping")
    defaults = {
        "transport_failures": 0,
        "syntax_parse_failures": 0,
        "schema_validation_failures": 0,
    }
    unknown = set(configured) - set(defaults)
    if unknown:
        raise ValueError(
            "unknown simulation.failure_thresholds keys: "
            + ", ".join(sorted(str(key) for key in unknown))
        )
    result = {}
    for key, default in defaults.items():
        value = configured.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"simulation.failure_thresholds.{key} must be a non-negative integer")
        result[key] = value
    return result


class RunLifecycle:
    """Own one exclusively-created run directory and its lifecycle metadata."""

    def __init__(self, output_dir: Path, run_id: str, meta: Dict[str, Any]):
        self.output_dir = output_dir
        self.run_id = run_id
        self.meta = meta
        self.current_step: Optional[int] = None
        self.current_phase: Optional[str] = None
        self.current_agent_id: Optional[int] = None
        self._observed_agent_ids: set[int] = set()
        self._terminal = False

    @classmethod
    def create(
        cls,
        config: Dict[str, Any],
        output_root: Optional[Path] = None,
        repo_root: Optional[Path] = None,
    ) -> "RunLifecycle":
        run_id = resolve_run_id(config)
        root = (output_root or Path.cwd()).resolve()
        output_dir = root / f"output_{run_id}"
        if output_dir.parent.resolve() != root:
            raise InvalidRunIdError("run output escapes the configured output root")
        if output_dir.exists() or output_dir.is_symlink():
            raise RunCollisionError(
                f"run directory already exists for run ID '{run_id}'"
            )

        config_snapshot = sanitize_config(copy.deepcopy(config))
        config_hash = compute_config_hash(config_snapshot)
        prompt_hash = compute_prompt_hash(repo_root)
        thresholds = _failure_thresholds(config)
        simulation = config.get("simulation", {})
        expected_steps = int(simulation["duration"])
        blocs = config.get("blocs", [])
        if not isinstance(blocs, list) or not blocs:
            raise ValueError("config.blocs must contain at least one bloc")
        for bloc in blocs:
            if not isinstance(bloc, dict):
                raise ValueError("each config bloc must be a mapping")
            validate_provider(bloc.get("provider", "ollama"))
            validate_base_url(bloc.get("base_url"))
        expected_agents = sum(
            int(bloc["num_agents"]) for bloc in blocs
        )
        if expected_steps <= 0:
            raise ValueError("simulation.duration must be positive")
        if expected_agents <= 0:
            raise ValueError("a run must contain at least one agent")

        # Capture source state before the run directory itself exists, so an
        # untracked output path cannot make a clean checkout appear dirty.
        try:
            git_info = collect_git_info(repo_root)
        except Exception:
            git_info = {
                "git_sha": None,
                "git_dirty": None,
                "git_probe_status": "unavailable",
                "git_probe_errors": ["unexpected_probe_error"],
            }

        start_time = utc_now_iso()
        # Keep the run usable even if a probe implementation or platform API
        # fails in an unforeseen way. collect_gpu_info itself is defensive,
        # and this boundary protects callers that inject/replace the probe.
        try:
            gpu_info = collect_gpu_info()
        except Exception:
            gpu_info = {
                "status": "unavailable",
                "error": "unexpected_probe_error",
                "driver_version": None,
                "cuda_version": None,
                "cuda_probe_status": "unavailable",
                "cuda_probe_error": "unexpected_probe_error",
                "malformed_device_rows": 0,
                "devices": [],
            }
        if not isinstance(gpu_info, dict):
            gpu_info = {
                "status": "unavailable",
                "error": "unexpected_probe_error",
                "driver_version": None,
                "cuda_version": None,
                "malformed_device_rows": 0,
                "devices": [],
            }
        else:
            gpu_info = dict(gpu_info)
        gpu_info.setdefault("malformed_device_rows", 0)
        gpu_info.setdefault(
            "cuda_probe_status",
            "available" if gpu_info.get("cuda_version") else "unavailable",
        )
        gpu_info.setdefault(
            "cuda_probe_error",
            None
            if gpu_info["cuda_probe_status"] == "available"
            else gpu_info.get("error") or "cuda_version_unavailable",
        )
        try:
            collected_dependencies = collect_dependency_versions()
        except Exception:
            collected_dependencies = {}
        if not isinstance(collected_dependencies, dict):
            collected_dependencies = {}
        dependencies = {
            name: (
                collected_dependencies.get(name)
                if isinstance(collected_dependencies.get(name), str)
                else None
            )
            for name in DEPENDENCY_DISTRIBUTIONS
        }
        available_dependency_count = sum(
            version is not None for version in dependencies.values()
        )
        if available_dependency_count == len(dependencies):
            dependencies_probe_status = "available"
        elif available_dependency_count == 0:
            dependencies_probe_status = "unavailable"
        else:
            dependencies_probe_status = "partial"
        dependencies_probe_errors = [
            f"{name}:version_unavailable"
            for name, version in dependencies.items()
            if version is None
        ]
        runtime_probe_errors = []
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = None
            runtime_probe_errors.append("hostname_unavailable")
        try:
            os_name = platform_module.system()
            platform_name = platform_module.platform()
        except Exception:
            os_name = None
            platform_name = None
            runtime_probe_errors.append("platform_unavailable")
        meta: Dict[str, Any] = {
            "run_id": run_id,
            "run_name": simulation.get("run_name"),
            "protocol_version": simulation.get("protocol_version", DEFAULT_PROTOCOL_VERSION),
            "log_schema_version": LOG_SCHEMA_VERSION,
            "metric_version": simulation.get("metric_version", DEFAULT_METRIC_VERSION),
            "start_time_utc": start_time,
            "end_time_utc": None,
            "start_time": start_time,
            "end_time": None,
            "status": "running",
            "aborted": False,
            "abort_reason": None,
            "failure_step": None,
            "failure_phase": None,
            "failure_agent_id": None,
            "failure_exception_type": None,
            "expected_steps": expected_steps,
            "completed_steps": 0,
            "expected_agents": expected_agents,
            "observed_agents": 0,
            "logical_llm_calls": 0,
            "http_attempts": 0,
            "generation_retries": 0,
            "transport_failures": 0,
            "syntax_parse_attempt_failures": 0,
            "syntax_parse_failures": 0,
            "schema_validation_failures": 0,
            "schema_validation_supported": False,
            "failure_thresholds": thresholds,
            "git_sha": git_info["git_sha"],
            "git_dirty": git_info["git_dirty"],
            "git_probe_status": git_info["git_probe_status"],
            "git_probe_errors": git_info["git_probe_errors"],
            "config": config_snapshot,
            "config_hash": config_hash,
            "config_hash_algorithm": "sha256-canonical-json-redacted-v1",
            "prompt_hash": prompt_hash,
            "prompt_hash_algorithm": "sha256-file-bytes",
            "hostname": hostname,
            "os": os_name,
            "platform": platform_name,
            "runtime_probe_errors": runtime_probe_errors,
            "python_version": sys.version,
            "dependencies": dependencies,
            "dependencies_probe_status": dependencies_probe_status,
            "dependencies_probe_errors": dependencies_probe_errors,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "gpu_info": gpu_info,
            "models": collect_bloc_models(config_snapshot),
            "raw_manifest": None,
            "raw_manifest_status": "pending",
            "raw_manifest_error": None,
            "output_directory": output_dir.name,
            # Backward-compatible aliases used by existing consumers.
            "seed": simulation.get("seed"),
            "total_llm_calls": 0,
            "parse_errors": 0,
            "parse_error_rate": 0.0,
        }

        lifecycle = cls(output_dir=output_dir, run_id=run_id, meta=meta)
        try:
            output_dir.mkdir(mode=0o755, parents=False, exist_ok=False)
        except FileExistsError as error:
            raise RunCollisionError(
                f"run directory already exists for run ID '{run_id}'"
            ) from error
        except BaseException as error:
            # A BaseException may be delivered after mkdir(2) created the
            # directory but before Path.mkdir returns. Recover only an empty,
            # ordinary directory after this exclusive-create attempt; never
            # touch an existing non-empty directory or a symlink. FileExistsError
            # is handled above and can never enter this recovery path.
            try:
                recoverable = (
                    output_dir.is_dir()
                    and not output_dir.is_symlink()
                    and not any(output_dir.iterdir())
                )
            except OSError:
                recoverable = False
            if recoverable:
                try:
                    interrupted = isinstance(error, KeyboardInterrupt)
                    lifecycle.finalize_failure(
                        "aborted" if interrupted else "failed",
                        (
                            "keyboard_interrupt"
                            if interrupted
                            else "run_directory_creation_failure"
                        ),
                        type(error).__name__,
                    )
                except BaseException:
                    pass
            raise

        try:
            lifecycle._write_meta()
            for filename in RAW_JSONL_FILES:
                (output_dir / filename).open("x", encoding="utf-8").close()
        except KeyboardInterrupt as error:
            try:
                lifecycle.finalize_failure(
                    "aborted", "keyboard_interrupt", type(error).__name__
                )
            except BaseException:
                pass
            raise
        except BaseException as error:
            try:
                lifecycle.finalize_failure(
                    "failed", "run_initialization_failure", type(error).__name__
                )
            except BaseException:
                # Preserve the initialization error even when the best-effort
                # terminal meta write fails as well. The last atomic meta, if
                # any, remains valid.
                pass
            raise
        return lifecycle

    def _sync_compatibility_fields(self) -> None:
        self.meta["observed_agents"] = len(self._observed_agent_ids)
        self.meta["total_llm_calls"] = self.meta["logical_llm_calls"]
        self.meta["parse_errors"] = self.meta["syntax_parse_failures"]
        calls = self.meta["logical_llm_calls"]
        self.meta["parse_error_rate"] = (
            self.meta["syntax_parse_failures"] / calls if calls else 0.0
        )

    def _write_meta(self) -> None:
        if self.meta.get("run_id") != self.run_id:
            raise RunLifecycleError("run ID changed during lifecycle")
        self._sync_compatibility_fields()
        atomic_write_json(self.output_dir / "run_meta.json", self.meta)

    def set_context(
        self,
        step: Optional[int],
        phase: Optional[str],
        agent_id: Optional[int] = None,
    ) -> None:
        self.current_step = step
        self.current_phase = phase
        self.current_agent_id = agent_id

    def observe_agent(self, agent_id: int) -> None:
        self._observed_agent_ids.add(agent_id)

    def increment(self, field: str, amount: int = 1) -> None:
        if field not in _COUNTER_FIELDS:
            raise RunLifecycleError(f"unknown lifecycle counter: {field}")
        self.meta[field] += amount

    def record_llm_telemetry(self, event: str, amount: int = 1) -> None:
        mapping = {
            "http_attempt": "http_attempts",
            "generation_retry": "generation_retries",
            "transport_failure": "transport_failures",
            "syntax_parse_attempt_failure": "syntax_parse_attempt_failures",
        }
        field = mapping.get(event)
        if field is None:
            raise RunLifecycleError(f"unknown LLM telemetry event: {event}")
        self.increment(field, amount)

    def mark_step_completed(self, step: int) -> None:
        expected_next = self.meta["completed_steps"] + 1
        if step != expected_next:
            raise RunLifecycleError(
                f"completed step sequence mismatch: expected {expected_next}, got {step}"
            )
        self.meta["completed_steps"] = step
        self._write_meta()

    def finalize_completed(self) -> None:
        if self._terminal:
            raise RunLifecycleError("run lifecycle is already terminal")
        if self.meta["completed_steps"] != self.meta["expected_steps"]:
            raise RunLifecycleError("cannot complete a run with missing steps")
        if len(self._observed_agent_ids) != self.meta["expected_agents"]:
            raise RunLifecycleError("cannot complete a run with missing observed agents")
        raw_manifest = build_raw_manifest(self.output_dir)
        if set(raw_manifest["files"]) != set(RAW_JSONL_FILES):
            raise RunLifecycleError(
                "cannot complete a run with missing required raw files"
            )
        self.meta.update({
            "status": "completed",
            "aborted": False,
            "abort_reason": None,
            "end_time_utc": utc_now_iso(),
            "raw_manifest": raw_manifest,
            "raw_manifest_status": "available",
            "raw_manifest_error": None,
        })
        self.meta["end_time"] = self.meta["end_time_utc"]
        self._write_meta()
        self._terminal = True

    def finalize_failure(
        self,
        status: str,
        reason: str,
        exception_type: Optional[str] = None,
    ) -> None:
        if self._terminal:
            return
        if status not in {"aborted", "failed"}:
            raise RunLifecycleError(f"invalid terminal failure status: {status}")
        try:
            raw_manifest = build_raw_manifest(self.output_dir)
            if set(raw_manifest["files"]) == set(RAW_JSONL_FILES):
                raw_manifest_status = "available"
                raw_manifest_error = None
            else:
                raw_manifest_status = "partial"
                raw_manifest_error = "required_raw_files_missing"
        except BaseException:
            raw_manifest = None
            raw_manifest_status = "unavailable"
            raw_manifest_error = "raw_manifest_hash_failed"
        self.meta.update({
            "status": status,
            "aborted": True,
            "abort_reason": reason,
            "failure_step": self.current_step,
            "failure_phase": self.current_phase,
            "failure_agent_id": self.current_agent_id,
            "failure_exception_type": exception_type,
            "end_time_utc": utc_now_iso(),
            "raw_manifest": raw_manifest,
            "raw_manifest_status": raw_manifest_status,
            "raw_manifest_error": raw_manifest_error,
        })
        self.meta["end_time"] = self.meta["end_time_utc"]
        self._write_meta()
        self._terminal = True
