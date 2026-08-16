"""Atomic, closed-schema publication for Gate 4 evidence bundles.

Execution and resource capture happen in a separate, unpublished source tree.
This module copies that tree into a hidden sibling stage, adds publisher-owned
canonical metadata, verifies the complete inventory, and only then exposes the
bundle with a Linux no-replace atomic directory rename.

Operational outcome, publication conformance, and Gate/research eligibility are
deliberately independent.  This publisher never promotes a bundle to formal
Gate 4 or research evidence.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterator, Mapping, Optional, Sequence


PUBLICATION_VERSION = "gate4-evidence-publisher-v1.1.0"
PUBLICATION_SPEC_VERSION = "gate4-backend-evidence-publication-v1.1.0"
PUBLICATION_SPEC_PATH = "docs/GATE4_EVIDENCE_PUBLICATION_SPEC.md"
EXPECTED_PUBLICATION_SPEC_SHA256 = (
    "8201013f77d98cc0c63559fe31a7c3c8d4dc90b4d1eda0f245d0e56f77ba7b6c"
)
SUMMARY_SCHEMA_VERSION = "gate4-backend-evidence-summary-v1.0.0"
APPROVAL_SCHEMA_VERSION = "gate4-gpu-run-approval-v1.0.0"
CAPTURE_MANIFEST_SCHEMA_VERSION = "gate4-evidence-capture-manifest-v1.0.0"

SUMMARY_FILENAME = "run-summary.json"
INVENTORY_FILENAME = "files.sha256"
CAPTURE_MANIFEST_FILENAME = "capture-manifest.json"
APPROVAL_FILENAME = "approval.json"
PUBLISHER_SNAPSHOT_PATH = "publication/gate4_evidence_publisher.py"
CONTRACT_SNAPSHOT_PATH = "publication/GATE4_EVIDENCE_PUBLICATION_SPEC.md"
ROOT_HASH_DOMAIN = b"MCS-EVIDENCE-BUNDLE-ROOT-V1\0"

SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
GPU_UUID_RE = re.compile(r"GPU-[0-9A-Fa-f-]{8,}\Z")
INVENTORY_LINE_RE = re.compile(r"([0-9a-f]{64})  \./([^\r\n]+)\Z")

OPERATIONAL_RESULTS = {"NOT_EVALUATED"}
EXECUTION_MODES = {
    "reference_ollama",
    "vllm_openai_compatible",
    "scripted_smoke",
}
GENERIC_CLAIM_SCOPE = ["publication_structure_only"]
GENERIC_UNVERIFIED_CLAIMS = sorted(
    [
        "execution_mode",
        "metric_version",
        "operational_backend_result",
        "protocol_version",
        "resource_and_workload_limits",
        "run_id",
    ]
)
HISTORICAL_NONREPAIRABLE = {
    "original_publication_order",
    "original_atomic_publication",
    "original_approval_completeness",
}
CORRECTION_REPAIRABLE = {
    "derived_metadata",
    "inventory_metadata",
    "summary_schema",
}
CORRECTION_REASON_PROPERTIES = {
    "derived_metadata_correction": "derived_metadata",
    "inventory_metadata_correction": "inventory_metadata",
    "summary_schema_correction": "summary_schema",
}
RESERVED_SOURCE_TOP_LEVEL = {
    SUMMARY_FILENAME,
    INVENTORY_FILENAME,
    CAPTURE_MANIFEST_FILENAME,
    "publication",
}

DRAFT_SUMMARY_FIELDS = {
    "schema_version",
    "evidence_bundle_id",
    "run_id",
    "protocol_version",
    "metric_version",
    "execution_mode",
    "operational_backend_result",
    "evidence_publication_conformance",
    "gate4_formal_pass",
    "research_eligible",
    "backend_freeze",
    "claim_scope",
    "warnings",
    "unverified_claims",
    "correction",
}
FINAL_SUMMARY_FIELDS = DRAFT_SUMMARY_FIELDS | {
    "authorization",
    "source_capture",
    "publisher",
    "publication_contract",
}
CORRECTION_FIELDS = {
    "kind",
    "supersedes",
    "reason_code",
    "reason",
    "raw_artifacts_changed",
    "repaired_properties",
    "not_repaired",
}
SUPERSEDES_FIELDS = {
    "evidence_bundle_id",
    "summary_sha256",
    "inventory_sha256",
    "bundle_root_sha256",
}
APPROVAL_FIELDS = {
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

CheckpointHook = Callable[[str, Path, Path], None]


class EvidencePublicationError(RuntimeError):
    """The evidence could not be safely published."""


class EvidenceCollisionError(EvidencePublicationError):
    """The final evidence ID is already owned or being published."""


class EvidenceValidationError(EvidencePublicationError):
    """A capture, summary, inventory, or publication contract is invalid."""


@dataclass(frozen=True)
class PublicationValidationReport:
    path: Path
    evidence_bundle_id: Optional[str]
    schema_version: Optional[str]
    operational_backend_result: Optional[str]
    summary_sha256: Optional[str]
    inventory_sha256: Optional[str]
    bundle_root_sha256: Optional[str]
    inventory_entries: int
    publication_conforming: bool
    formal_gate4_pass: bool
    research_eligible: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class PublicationReceipt:
    final_path: Path
    evidence_bundle_id: str
    schema_version: str
    operational_backend_result: str
    summary_sha256: str
    inventory_sha256: str
    bundle_root_sha256: str
    inventory_entries: int
    source_directory_identity: Optional["DirectoryIdentity"]
    final_directory_identity: "DirectoryIdentity"


@dataclass(frozen=True)
class DirectoryIdentity:
    device: int
    inode: int

    @classmethod
    def from_descriptor(cls, descriptor: int) -> "DirectoryIdentity":
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise EvidenceValidationError("directory identity descriptor is invalid")
        return cls(metadata.st_dev, metadata.st_ino)

    @classmethod
    def from_value(
        cls,
        value: Mapping[str, Any],
        context: str,
    ) -> "DirectoryIdentity":
        if not isinstance(value, Mapping) or set(value) != {"device", "inode"}:
            raise EvidenceValidationError(f"{context} fields differ")
        device = value["device"]
        inode = value["inode"]
        if type(device) is not int or device < 0:
            raise EvidenceValidationError(f"{context}.device is invalid")
        if type(inode) is not int or inode <= 0:
            raise EvidenceValidationError(f"{context}.inode is invalid")
        return cls(device, inode)

    def as_dict(self) -> Dict[str, int]:
        return {"device": self.device, "inode": self.inode}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _absolute_lexical_path(path: Path | str, context: str) -> Path:
    raw = os.fspath(path)
    if not raw or "\0" in raw:
        raise EvidenceValidationError(f"{context} is not a valid path")
    absolute = os.path.abspath(raw)
    if absolute.startswith("//"):
        raise EvidenceValidationError(f"{context} has an unsupported root")
    return Path(absolute)


@dataclass
class _PinnedDirectory:
    """A directory plus every no-follow descriptor in its absolute path."""

    path: Path
    descriptors: list[int]
    components: tuple[str, ...]

    @property
    def fd(self) -> int:
        return self.descriptors[-1]

    def assert_path_identity(self) -> None:
        root_opened = os.fstat(self.descriptors[0])
        root_named = os.stat("/", follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or (root_opened.st_dev, root_opened.st_ino)
            != (root_named.st_dev, root_named.st_ino)
        ):
            raise EvidenceValidationError("filesystem root identity changed")
        for index, component in enumerate(self.components, start=1):
            opened = os.fstat(self.descriptors[index])
            try:
                named = os.stat(
                    component,
                    dir_fd=self.descriptors[index - 1],
                    follow_symlinks=False,
                )
            except OSError as error:
                raise EvidenceValidationError(
                    f"pinned directory path changed: {self.path}"
                ) from error
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or (opened.st_dev, opened.st_ino)
                != (named.st_dev, named.st_ino)
            ):
                raise EvidenceValidationError(
                    f"pinned directory path changed: {self.path}"
                )

    def close(self) -> None:
        while self.descriptors:
            os.close(self.descriptors.pop())


@contextlib.contextmanager
def _pin_directory(path: Path | str, context: str) -> Iterator[_PinnedDirectory]:
    absolute = _absolute_lexical_path(path, context)
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise EvidencePublicationError(
            "O_NOFOLLOW and O_DIRECTORY are required for evidence directories"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptors: list[int] = []
    components = tuple(part for part in absolute.parts if part != "/")
    try:
        descriptors.append(os.open("/", flags))
        for component in components:
            parent_fd = descriptors[-1]
            descriptor = os.open(component, flags, dir_fd=parent_fd)
            try:
                opened = os.fstat(descriptor)
                named = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not stat.S_ISDIR(named.st_mode)
                    or (opened.st_dev, opened.st_ino)
                    != (named.st_dev, named.st_ino)
                ):
                    raise EvidenceValidationError(
                        f"{context} contains an unsafe component"
                    )
            except Exception:
                os.close(descriptor)
                raise
            descriptors.append(descriptor)
        pinned = _PinnedDirectory(absolute, descriptors, components)
        pinned.assert_path_identity()
        try:
            yield pinned
        finally:
            pinned.close()
    except EvidencePublicationError:
        for descriptor in reversed(descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)
        raise
    except OSError as error:
        for descriptor in reversed(descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)
        raise EvidenceValidationError(f"{context} cannot be opened safely") from error


def _stable_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    """Fields that must remain unchanged across one authoritative file read."""
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_open_regular_file(
    path: Path | str,
    *,
    context: str,
    dir_fd: Optional[int] = None,
) -> bytes:
    """Read one named file without following its final symlink.

    The open descriptor and the still-named directory entry must identify the
    same single-link regular file, and its metadata must remain stable for the
    whole read.  This makes a path swap or concurrent write fail closed.
    """
    if not hasattr(os, "O_NOFOLLOW"):
        raise EvidencePublicationError("O_NOFOLLOW is required for evidence reads")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(os.fspath(path), flags, dir_fd=dir_fd)
    except OSError as error:
        raise EvidenceValidationError(f"{context} cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise EvidenceValidationError(f"{context} must be a regular file")
        if before.st_nlink != 1:
            raise EvidenceValidationError(f"{context} must have exactly one link")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if _stable_file_identity(before) != _stable_file_identity(after):
            raise EvidenceValidationError(f"{context} changed while being read")
        try:
            named = os.stat(os.fspath(path), dir_fd=dir_fd, follow_symlinks=False)
        except OSError as error:
            raise EvidenceValidationError(f"{context} changed while being read") from error
        if _stable_file_identity(after) != _stable_file_identity(named):
            raise EvidenceValidationError(f"{context} path changed while being read")
        data = b"".join(chunks)
        if len(data) != after.st_size:
            raise EvidenceValidationError(f"{context} size changed while being read")
        return data
    finally:
        os.close(descriptor)


def _open_directory_nofollow(path: Path, context: str) -> int:
    with _pin_directory(path, context) as pinned:
        return os.dup(pinned.fd)


def _read_relative_regular_file_nofollow(
    root: Path,
    relative: str,
    context: str,
    *,
    root_fd: Optional[int] = None,
) -> bytes:
    """Open every path component relative to a pinned, no-follow root."""
    relative_path = _safe_relative_path(relative, context)
    descriptors: list[int] = [
        os.dup(root_fd)
        if root_fd is not None
        else _open_directory_nofollow(root, "evidence root")
    ]
    try:
        for component in relative_path.parts[:-1]:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            try:
                descriptor = os.open(component, flags, dir_fd=descriptors[-1])
            except OSError as error:
                raise EvidenceValidationError(
                    f"{context} contains an unsafe directory component"
                ) from error
            try:
                opened = os.fstat(descriptor)
                named = os.stat(
                    component,
                    dir_fd=descriptors[-1],
                    follow_symlinks=False,
                )
                if not stat.S_ISDIR(opened.st_mode) or (
                    opened.st_dev,
                    opened.st_ino,
                ) != (named.st_dev, named.st_ino):
                    raise EvidenceValidationError(
                        f"{context} contains an unsafe directory component"
                    )
            except Exception:
                os.close(descriptor)
                raise
            descriptors.append(descriptor)
        return _read_open_regular_file(
            relative_path.parts[-1],
            context=context,
            dir_fd=descriptors[-1],
        )
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_regular_file_nofollow(path: Path, context: str) -> bytes:
    absolute = _absolute_lexical_path(path, context)
    if absolute == Path("/"):
        raise EvidenceValidationError(f"{context} must be a regular file")
    with _pin_directory(absolute.parent, f"{context} parent") as parent:
        parent.assert_path_identity()
        data = _read_open_regular_file(
            absolute.name,
            context=context,
            dir_fd=parent.fd,
        )
        parent.assert_path_identity()
        return data


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(_read_regular_file_nofollow(path, str(path)))


def _file_record(path: Path) -> Dict[str, Any]:
    data = _read_regular_file_nofollow(path, str(path))
    return _bytes_record(data)


def _bytes_record(data: bytes) -> Dict[str, Any]:
    return {
        "sha256": _sha256_bytes(data),
        "bytes": len(data),
        "lines": data.count(b"\n"),
    }


def _canonical_json_bytes(value: Any) -> bytes:
    _reject_floats(value, "JSON")
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise EvidenceValidationError("contract JSON is not serializable") from error
    return rendered.encode("utf-8") + b"\n"


def _reject_floats(value: Any, context: str) -> None:
    if isinstance(value, float):
        raise EvidenceValidationError(f"{context} may not contain floats")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceValidationError(f"{context} object keys must be strings")
            _reject_floats(item, f"{context}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{context}[{index}]")


def _decode_contract_json(data: bytes, context: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvidenceValidationError(f"{context} is not UTF-8") from error

    def object_pairs(pairs: Sequence[tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceValidationError(
                    f"{context} contains duplicate object key {key!r}"
                )
            result[key] = value
        return result

    def invalid_constant(token: str) -> None:
        raise EvidenceValidationError(
            f"{context} contains invalid numeric constant {token}"
        )

    try:
        value = json.loads(
            text,
            object_pairs_hook=object_pairs,
            parse_constant=invalid_constant,
        )
    except EvidenceValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise EvidenceValidationError(f"{context} is not valid JSON") from error
    _reject_floats(value, context)
    if _canonical_json_bytes(value) != data:
        raise EvidenceValidationError(f"{context} is not canonical JSON")
    return value


def _require_exact_keys(value: Any, keys: set[str], context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceValidationError(f"{context} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        unknown = sorted(actual - keys)
        raise EvidenceValidationError(
            f"{context} key set differs; missing={missing}, unknown={unknown}"
        )
    return value


def _require_nonempty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{context} must be a non-empty string")
    return value


def _require_sha256(value: Any, context: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise EvidenceValidationError(f"{context} must be a lowercase SHA-256")
    return value


def _require_positive_int(value: Any, context: str) -> int:
    if type(value) is not int or value <= 0:
        raise EvidenceValidationError(f"{context} must be a positive integer")
    return value


def _require_sorted_unique_strings(
    value: Any,
    context: str,
    *,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise EvidenceValidationError(f"{context} must be an array")
    strings = [_require_nonempty_string(item, f"{context}[]") for item in value]
    if nonempty and not strings:
        raise EvidenceValidationError(f"{context} must not be empty")
    if strings != sorted(set(strings)):
        raise EvidenceValidationError(f"{context} must be sorted and unique")
    return strings


def _validate_bundle_id(value: Any, context: str = "evidence_bundle_id") -> str:
    identifier = _require_nonempty_string(value, context)
    if SAFE_ID_RE.fullmatch(identifier) is None or ".." in identifier:
        raise EvidenceValidationError(f"{context} is not a safe canonical ID")
    return identifier


def _safe_relative_path(value: str, context: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\0" in value or "\n" in value:
        raise EvidenceValidationError(f"{context} is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("./") or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise EvidenceValidationError(f"{context} is not a canonical relative path")
    return path


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _canonical_declared_absolute_path(value: Any, context: str) -> Path:
    declared = _require_nonempty_string(value, context)
    if "\0" in declared or not os.path.isabs(declared) or declared.startswith("//"):
        raise EvidenceValidationError(f"{context} must be a canonical absolute path")
    normalized = os.path.normpath(declared)
    if normalized != declared:
        raise EvidenceValidationError(f"{context} must be a canonical absolute path")
    return Path(declared)


def _validate_approval(
    approval: Any,
    *,
    expected_bundle_id: str,
    expected_final_path: Path,
) -> Mapping[str, Any]:
    value = _require_exact_keys(approval, APPROVAL_FIELDS, "approval")
    if value["schema_version"] != APPROVAL_SCHEMA_VERSION:
        raise EvidenceValidationError("approval schema_version differs")
    if _validate_bundle_id(value["evidence_bundle_id"], "approval.evidence_bundle_id") != expected_bundle_id:
        raise EvidenceValidationError("approval evidence_bundle_id differs")
    approved = _canonical_declared_absolute_path(
        value["approved_final_path"],
        "approval.approved_final_path",
    )
    expected = _absolute_lexical_path(expected_final_path, "expected final path")
    if approved != expected:
        raise EvidenceValidationError("approval final path differs")
    _require_positive_int(
        value["logical_generation_limit"], "approval.logical_generation_limit"
    )
    _require_positive_int(
        value["wall_clock_limit_seconds"], "approval.wall_clock_limit_seconds"
    )
    gpu_uuids = _require_sorted_unique_strings(
        value["gpu_uuids"], "approval.gpu_uuids", nonempty=True
    )
    if any(GPU_UUID_RE.fullmatch(item) is None for item in gpu_uuids):
        raise EvidenceValidationError("approval contains an invalid GPU UUID")
    _require_sorted_unique_strings(
        value["stop_conditions"], "approval.stop_conditions", nonempty=True
    )
    if value["approved"] is not True:
        raise EvidenceValidationError("approval.approved must be true")
    _require_nonempty_string(value["approval_reference"], "approval.approval_reference")
    return value


def validate_approval_file(
    approval_path: Path | str,
    *,
    expected_bundle_id: str,
    expected_final_path: Path | str,
) -> Mapping[str, Any]:
    """Read-only preflight validation for a canonical GPU approval record."""
    path = Path(approval_path)
    value = _decode_contract_json(
        _read_regular_file_nofollow(path, "approval.json"),
        "approval.json",
    )
    return _validate_approval(
        value,
        expected_bundle_id=_validate_bundle_id(expected_bundle_id),
        expected_final_path=_absolute_lexical_path(
            expected_final_path,
            "expected final path",
        ),
    )


def _validate_correction(value: Any) -> Mapping[str, Any]:
    correction = _require_exact_keys(value, CORRECTION_FIELDS, "summary.correction")
    kind = correction["kind"]
    if kind not in {"original", "derived_correction"}:
        raise EvidenceValidationError("summary.correction.kind is invalid")
    if correction["raw_artifacts_changed"] is not False:
        raise EvidenceValidationError("summary.correction.raw_artifacts_changed must be false")
    repaired = _require_sorted_unique_strings(
        correction["repaired_properties"], "summary.correction.repaired_properties"
    )
    not_repaired = _require_sorted_unique_strings(
        correction["not_repaired"], "summary.correction.not_repaired"
    )
    if set(repaired).intersection(not_repaired):
        raise EvidenceValidationError(
            "summary correction repaired/not_repaired properties must be disjoint"
        )
    if HISTORICAL_NONREPAIRABLE.intersection(repaired):
        raise EvidenceValidationError("historical publication properties cannot be repaired")
    if not set(repaired).issubset(CORRECTION_REPAIRABLE):
        raise EvidenceValidationError("summary correction names an unsupported repaired property")
    if not set(not_repaired).issubset(HISTORICAL_NONREPAIRABLE):
        raise EvidenceValidationError("summary correction names an unsupported unrepaired property")
    if kind == "original":
        if correction["supersedes"] is not None:
            raise EvidenceValidationError("original correction.supersedes must be null")
        if correction["reason_code"] is not None or correction["reason"] is not None:
            raise EvidenceValidationError("original correction reason fields must be null")
        if repaired or not_repaired:
            raise EvidenceValidationError("original correction property lists must be empty")
    else:
        supersedes = _require_exact_keys(
            correction["supersedes"], SUPERSEDES_FIELDS, "summary.correction.supersedes"
        )
        _validate_bundle_id(
            supersedes["evidence_bundle_id"],
            "summary.correction.supersedes.evidence_bundle_id",
        )
        for field in ("summary_sha256", "inventory_sha256", "bundle_root_sha256"):
            _require_sha256(
                supersedes[field], f"summary.correction.supersedes.{field}"
            )
        reason_code = _require_nonempty_string(
            correction["reason_code"], "summary.correction.reason_code"
        )
        if reason_code not in CORRECTION_REASON_PROPERTIES:
            raise EvidenceValidationError("summary correction reason_code is unsupported")
        _require_nonempty_string(correction["reason"], "summary.correction.reason")
        if not repaired:
            raise EvidenceValidationError("corrected derivative must name a repaired property")
        if repaired != [CORRECTION_REASON_PROPERTIES[reason_code]]:
            raise EvidenceValidationError(
                "summary correction reason_code and repaired property differ"
            )
    return correction


def _validate_summary(
    summary: Any,
    *,
    draft: bool,
    expected_bundle_id: Optional[str] = None,
) -> Mapping[str, Any]:
    fields = DRAFT_SUMMARY_FIELDS if draft else FINAL_SUMMARY_FIELDS
    value = _require_exact_keys(summary, fields, "summary")
    if value["schema_version"] != SUMMARY_SCHEMA_VERSION:
        raise EvidenceValidationError("summary schema_version differs")
    bundle_id = _validate_bundle_id(value["evidence_bundle_id"])
    if expected_bundle_id is not None and bundle_id != expected_bundle_id:
        raise EvidenceValidationError("summary evidence_bundle_id differs")
    _require_nonempty_string(value["run_id"], "summary.run_id")
    _require_nonempty_string(value["protocol_version"], "summary.protocol_version")
    _require_nonempty_string(value["metric_version"], "summary.metric_version")
    if value["execution_mode"] not in EXECUTION_MODES:
        raise EvidenceValidationError("summary.execution_mode is invalid")
    if value["operational_backend_result"] not in OPERATIONAL_RESULTS:
        raise EvidenceValidationError(
            "generic publisher may only record operational result NOT_EVALUATED"
        )
    if value["evidence_publication_conformance"] != "CONFORMING":
        raise EvidenceValidationError("summary publication conformance must be CONFORMING")
    if value["gate4_formal_pass"] is not False:
        raise EvidenceValidationError("summary.gate4_formal_pass must be false")
    if value["research_eligible"] is not False:
        raise EvidenceValidationError("summary.research_eligible must be false")
    backend = _require_exact_keys(
        value["backend_freeze"], {"status"}, "summary.backend_freeze"
    )
    if backend["status"] != "not_frozen":
        raise EvidenceValidationError("summary backend freeze must be not_frozen")
    claim_scope = _require_sorted_unique_strings(
        value["claim_scope"], "summary.claim_scope", nonempty=True
    )
    warnings = _require_sorted_unique_strings(value["warnings"], "summary.warnings")
    unverified_claims = _require_sorted_unique_strings(
        value["unverified_claims"], "summary.unverified_claims"
    )
    if claim_scope != GENERIC_CLAIM_SCOPE:
        raise EvidenceValidationError(
            "generic publisher claim_scope must be publication_structure_only"
        )
    if warnings:
        raise EvidenceValidationError(
            "generic publisher cannot classify content-derived warnings"
        )
    if unverified_claims != GENERIC_UNVERIFIED_CLAIMS:
        raise EvidenceValidationError(
            "generic publisher must retain every unverified operational field"
        )
    correction = _validate_correction(value["correction"])
    if (
        correction["kind"] == "derived_correction"
        and correction["supersedes"]["evidence_bundle_id"] == bundle_id
    ):
        raise EvidenceValidationError(
            "corrected derivative must use a distinct evidence bundle ID"
        )
    if not draft:
        authorization = _require_exact_keys(
            value["authorization"], {"path", "sha256"}, "summary.authorization"
        )
        if authorization["path"] != APPROVAL_FILENAME:
            raise EvidenceValidationError("summary authorization path differs")
        _require_sha256(authorization["sha256"], "summary.authorization.sha256")
        source_capture = _require_exact_keys(
            value["source_capture"],
            {"manifest_path", "manifest_sha256"},
            "summary.source_capture",
        )
        if source_capture["manifest_path"] != CAPTURE_MANIFEST_FILENAME:
            raise EvidenceValidationError("summary capture manifest path differs")
        _require_sha256(
            source_capture["manifest_sha256"],
            "summary.source_capture.manifest_sha256",
        )
        publisher = _require_exact_keys(
            value["publisher"], {"path", "sha256", "version"}, "summary.publisher"
        )
        if publisher["path"] != PUBLISHER_SNAPSHOT_PATH:
            raise EvidenceValidationError("summary publisher path differs")
        if publisher["version"] != PUBLICATION_VERSION:
            raise EvidenceValidationError("summary publisher version differs")
        _require_sha256(publisher["sha256"], "summary.publisher.sha256")
        contract = _require_exact_keys(
            value["publication_contract"],
            {"path", "sha256", "version"},
            "summary.publication_contract",
        )
        if contract["path"] != CONTRACT_SNAPSHOT_PATH:
            raise EvidenceValidationError("summary contract path differs")
        if contract["version"] != PUBLICATION_SPEC_VERSION:
            raise EvidenceValidationError("summary contract version differs")
        _require_sha256(contract["sha256"], "summary.publication_contract.sha256")
    return value


def _validate_file_record(value: Any, context: str) -> Mapping[str, Any]:
    record = _require_exact_keys(value, {"sha256", "bytes", "lines"}, context)
    _require_sha256(record["sha256"], f"{context}.sha256")
    for field in ("bytes", "lines"):
        if type(record[field]) is not int or record[field] < 0:
            raise EvidenceValidationError(f"{context}.{field} must be a nonnegative integer")
    return record


def _validate_capture_manifest(value: Any) -> Mapping[str, Any]:
    manifest = _require_exact_keys(
        value, {"schema_version", "files"}, "capture_manifest"
    )
    if manifest["schema_version"] != CAPTURE_MANIFEST_SCHEMA_VERSION:
        raise EvidenceValidationError("capture manifest schema_version differs")
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise EvidenceValidationError("capture manifest files must be a non-empty object")
    for relative, record in files.items():
        _safe_relative_path(relative, "capture manifest path")
        _validate_file_record(record, f"capture_manifest.files[{relative!r}]")
    return manifest


def _enumerate_regular_files(
    root: Path,
    *,
    source: bool,
    root_fd: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    root_descriptor = (
        os.dup(root_fd)
        if root_fd is not None
        else _open_directory_nofollow(root, "evidence root")
    )
    records: Dict[str, Dict[str, Any]] = {}
    visited: set[tuple[int, int]] = set()

    def walk(directory_fd: int, prefix: PurePosixPath) -> None:
        directory_stat = os.fstat(directory_fd)
        identity = (directory_stat.st_dev, directory_stat.st_ino)
        if identity in visited:
            raise EvidenceValidationError("evidence tree contains a directory cycle")
        visited.add(identity)
        try:
            with os.scandir(directory_fd) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
            for entry in entries:
                name = entry.name
                relative_path = prefix / name if prefix.parts else PurePosixPath(name)
                relative = relative_path.as_posix()
                _safe_relative_path(relative, "evidence path")
                try:
                    metadata = os.stat(
                        name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except OSError as error:
                    raise EvidenceValidationError(
                        "evidence file cannot be inspected"
                    ) from error
                if stat.S_ISLNK(metadata.st_mode):
                    raise EvidenceValidationError(
                        "evidence tree may not contain symlinks"
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                    if hasattr(os, "O_CLOEXEC"):
                        flags |= os.O_CLOEXEC
                    child_fd = os.open(name, flags, dir_fd=directory_fd)
                    try:
                        opened = os.fstat(child_fd)
                        if (opened.st_dev, opened.st_ino) != (
                            metadata.st_dev,
                            metadata.st_ino,
                        ):
                            raise EvidenceValidationError(
                                "evidence directory changed during enumeration"
                            )
                        walk(child_fd, relative_path)
                    finally:
                        os.close(child_fd)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise EvidenceValidationError(
                        "evidence tree may contain only regular files"
                    )
                if metadata.st_nlink != 1:
                    raise EvidenceValidationError(
                        "evidence tree may not contain hard-linked files"
                    )
                if source and relative_path.parts[0] in RESERVED_SOURCE_TOP_LEVEL:
                    raise EvidenceValidationError(
                        f"source capture uses reserved path {relative!r}"
                    )
                data = _read_open_regular_file(
                    name,
                    context=f"evidence file {relative!r}",
                    dir_fd=directory_fd,
                )
                records[relative] = _bytes_record(data)
        finally:
            visited.remove(identity)

    try:
        walk(root_descriptor, PurePosixPath())
    except EvidencePublicationError:
        raise
    except OSError as error:
        raise EvidenceValidationError("evidence tree changed during enumeration") from error
    finally:
        os.close(root_descriptor)
    if source and (APPROVAL_FILENAME not in records or len(records) < 2):
        raise EvidenceValidationError("source capture requires approval.json and raw evidence")
    return records


def _write_fsynced(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _open_or_create_parent_at(root_fd: int, relative: PurePosixPath) -> list[int]:
    descriptors = [os.dup(root_fd)]
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        for component in relative.parts[:-1]:
            try:
                os.mkdir(component, 0o700, dir_fd=descriptors[-1])
            except FileExistsError:
                pass
            descriptor = os.open(component, flags, dir_fd=descriptors[-1])
            try:
                opened = os.fstat(descriptor)
                named = os.stat(
                    component,
                    dir_fd=descriptors[-1],
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or (opened.st_dev, opened.st_ino)
                    != (named.st_dev, named.st_ino)
                ):
                    raise EvidenceValidationError(
                        "staging parent changed while being created"
                    )
            except Exception:
                os.close(descriptor)
                raise
            descriptors.append(descriptor)
        return descriptors
    except Exception:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _open_exclusive_regular_at(root_fd: int, relative: str) -> tuple[int, list[int]]:
    relative_path = _safe_relative_path(relative, "staging output path")
    directories = _open_or_create_parent_at(root_fd, relative_path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(
            relative_path.parts[-1],
            flags,
            0o600,
            dir_fd=directories[-1],
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            os.close(descriptor)
            raise EvidenceValidationError("staging output is not a regular file")
        return descriptor, directories
    except Exception:
        for directory in reversed(directories):
            os.close(directory)
        raise


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise EvidencePublicationError("evidence write made no progress")
        offset += written


def _write_fsynced_at(root_fd: int, relative: str, data: bytes) -> None:
    descriptor, directories = _open_exclusive_regular_at(root_fd, relative)
    try:
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
        for directory in reversed(directories):
            os.close(directory)


def _write_inventory_with_checkpoint(
    path: Path,
    data: bytes,
    *,
    hook: Optional[CheckpointHook],
    staging: Path,
    final: Path,
) -> None:
    midpoint = max(1, len(data) // 2)
    with path.open("xb") as handle:
        handle.write(data[:midpoint])
        handle.flush()
        os.fsync(handle.fileno())
        if hook is not None:
            hook("during_inventory_write", staging, final)
        handle.write(data[midpoint:])
        handle.flush()
        os.fsync(handle.fileno())


def _write_inventory_with_checkpoint_at(
    root_fd: int,
    data: bytes,
    *,
    hook: Optional[CheckpointHook],
    staging: Path,
    final: Path,
) -> None:
    descriptor, directories = _open_exclusive_regular_at(
        root_fd,
        INVENTORY_FILENAME,
    )
    try:
        midpoint = max(1, len(data) // 2)
        _write_all(descriptor, data[:midpoint])
        os.fsync(descriptor)
        if hook is not None:
            hook("during_inventory_write", staging, final)
        _write_all(descriptor, data[midpoint:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
        for directory in reversed(directories):
            os.close(directory)


def _fsync_directory(path: Path) -> None:
    descriptor = _open_directory_nofollow(path, f"directory {path}")
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory_fd(descriptor: int) -> None:
    os.fsync(descriptor)


def _open_relative_regular_nofollow_for_fsync(
    root: Path,
    relative: str,
    *,
    root_fd: Optional[int] = None,
) -> int:
    relative_path = _safe_relative_path(relative, "fsync evidence path")
    directories: list[int] = [
        os.dup(root_fd)
        if root_fd is not None
        else _open_directory_nofollow(root, "fsync root")
    ]
    file_descriptor: Optional[int] = None
    try:
        for component in relative_path.parts[:-1]:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            descriptor = os.open(component, flags, dir_fd=directories[-1])
            opened = os.fstat(descriptor)
            named = os.stat(
                component,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
            ) != (named.st_dev, named.st_ino):
                os.close(descriptor)
                raise EvidenceValidationError(
                    "staging directory changed during fsync"
                )
            directories.append(descriptor)
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        file_descriptor = os.open(
            relative_path.parts[-1],
            flags,
            dir_fd=directories[-1],
        )
        opened = os.fstat(file_descriptor)
        named = os.stat(
            relative_path.parts[-1],
            dir_fd=directories[-1],
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _stable_file_identity(opened) != _stable_file_identity(named)
        ):
            os.close(file_descriptor)
            file_descriptor = None
            raise EvidenceValidationError("staging file changed during fsync")
        return file_descriptor
    except OSError as error:
        if file_descriptor is not None:
            os.close(file_descriptor)
        raise EvidenceValidationError("staging tree cannot be opened safely for fsync") from error
    finally:
        for directory in reversed(directories):
            os.close(directory)


def _fsync_regular_files(root: Path, *, root_fd: Optional[int] = None) -> None:
    records = _enumerate_regular_files(root, source=False, root_fd=root_fd)
    for relative in sorted(records):
        descriptor = _open_relative_regular_nofollow_for_fsync(
            root,
            relative,
            root_fd=root_fd,
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _fsync_tree_directories_at(root_fd: int) -> None:
    def visit(directory_fd: int) -> None:
        with os.scandir(directory_fd) as iterator:
            names = sorted(entry.name for entry in iterator)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        for name in names:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                continue
            child_fd = os.open(name, flags, dir_fd=directory_fd)
            try:
                opened = os.fstat(child_fd)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise EvidenceValidationError(
                        "staging directory changed during fsync"
                    )
                visit(child_fd)
                os.fsync(child_fd)
            finally:
                os.close(child_fd)

    visit(root_fd)


def _inventory_bytes(root: Path, *, root_fd: Optional[int] = None) -> bytes:
    records = _enumerate_regular_files(root, source=False, root_fd=root_fd)
    records.pop(INVENTORY_FILENAME, None)
    return b"".join(
        f"{record['sha256']}  ./{relative}\n".encode("ascii")
        for relative, record in sorted(records.items())
    )


def _parse_inventory(data: bytes) -> Dict[str, str]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise EvidenceValidationError("inventory is not ASCII") from error
    if text and not text.endswith("\n"):
        raise EvidenceValidationError("inventory must end with a newline")
    entries: Dict[str, str] = {}
    ordered_paths: list[str] = []
    for line in text.splitlines():
        match = INVENTORY_LINE_RE.fullmatch(line)
        if match is None:
            raise EvidenceValidationError("inventory line format is invalid")
        digest, relative = match.groups()
        _safe_relative_path(relative, "inventory path")
        if relative == INVENTORY_FILENAME:
            raise EvidenceValidationError("inventory may not list itself")
        if relative in entries:
            raise EvidenceValidationError("inventory contains a duplicate path")
        entries[relative] = digest
        ordered_paths.append(relative)
    if not entries:
        raise EvidenceValidationError("inventory must not be empty")
    if ordered_paths != sorted(ordered_paths):
        raise EvidenceValidationError("inventory paths are not sorted")
    return entries


def _bundle_root_hash(inventory_sha256: str) -> str:
    _require_sha256(inventory_sha256, "inventory_sha256")
    return _sha256_bytes(ROOT_HASH_DOMAIN + bytes.fromhex(inventory_sha256))


def _validate_predecessor(
    correction: Mapping[str, Any],
    predecessor: Optional[Path],
    current_capture_files: Mapping[str, Any],
) -> None:
    if correction["kind"] == "original":
        if predecessor is not None:
            raise EvidenceValidationError("original bundle may not name a predecessor")
        return
    if predecessor is None:
        raise EvidenceValidationError("corrected derivative requires a predecessor path")
    with _pin_directory(predecessor, "predecessor") as pinned:
        path = pinned.path
        supersedes = correction["supersedes"]
        if path.name != supersedes["evidence_bundle_id"]:
            raise EvidenceValidationError("predecessor bundle ID differs")

        # A correction may derive only from a bundle that independently validates
        # as an original publication. Passing no predecessor deliberately makes a
        # correction chain fail closed.
        verified = _verify_bundle_or_raise(
            path,
            expected_final_path=path,
            require_final_name=True,
            predecessor_path=None,
            root_fd=pinned.fd,
        )
        expected = {
            "summary_sha256": verified.summary_sha256,
            "inventory_sha256": verified.inventory_sha256,
            "bundle_root_sha256": verified.bundle_root_sha256,
        }
        for field, observed in expected.items():
            if supersedes[field] != observed:
                raise EvidenceValidationError(f"predecessor {field} differs")
        predecessor_summary = _validate_summary(
            _decode_contract_json(
                _read_relative_regular_file_nofollow(
                    path,
                    SUMMARY_FILENAME,
                    "predecessor run-summary.json",
                    root_fd=pinned.fd,
                ),
                "predecessor run-summary.json",
            ),
            draft=False,
        )
        if predecessor_summary["correction"]["kind"] != "original":
            raise EvidenceValidationError("predecessor must be an original bundle")

        predecessor_capture = _decode_contract_json(
            _read_relative_regular_file_nofollow(
                path,
                CAPTURE_MANIFEST_FILENAME,
                "predecessor capture-manifest.json",
                root_fd=pinned.fd,
            ),
            "predecessor capture-manifest.json",
        )
        predecessor_capture = _validate_capture_manifest(predecessor_capture)
        predecessor_actual = _enumerate_regular_files(
            path,
            source=False,
            root_fd=pinned.fd,
        )
        owned_top_level = {
            CAPTURE_MANIFEST_FILENAME,
            SUMMARY_FILENAME,
            INVENTORY_FILENAME,
            "publication",
        }
        actual_capture = {
            relative: record
            for relative, record in predecessor_actual.items()
            if PurePosixPath(relative).parts[0] not in owned_top_level
        }
        if actual_capture != predecessor_capture["files"]:
            raise EvidenceValidationError(
                "predecessor actual capture differs from its manifest"
            )
        previous_raw = {
            relative: record
            for relative, record in actual_capture.items()
            if relative != APPROVAL_FILENAME
        }
        current_raw = {
            relative: record
            for relative, record in current_capture_files.items()
            if relative != APPROVAL_FILENAME
        }
        if current_raw != previous_raw:
            raise EvidenceValidationError(
                "corrected derivative changed captured raw artifacts"
            )

        verified_after = _verify_bundle_or_raise(
            path,
            expected_final_path=path,
            require_final_name=True,
            predecessor_path=None,
            root_fd=pinned.fd,
        )
        pinned.assert_path_identity()
        if verified_after != verified:
            raise EvidenceValidationError(
                "predecessor changed during correction validation"
            )


def _verify_bundle_or_raise(
    path: Path,
    *,
    expected_final_path: Path,
    require_final_name: bool,
    predecessor_path: Optional[Path],
    root_fd: Optional[int] = None,
) -> PublicationReceipt:
    if root_fd is None:
        with _pin_directory(path, "published evidence path") as pinned:
            return _verify_bundle_or_raise(
                pinned.path,
                expected_final_path=expected_final_path,
                require_final_name=require_final_name,
                predecessor_path=predecessor_path,
                root_fd=pinned.fd,
            )
    root = _absolute_lexical_path(path, "published evidence path")
    inventory_path = root / INVENTORY_FILENAME
    inventory_bytes = _read_relative_regular_file_nofollow(
        root,
        INVENTORY_FILENAME,
        "published inventory",
        root_fd=root_fd,
    )
    inventory = _parse_inventory(inventory_bytes)
    actual = _enumerate_regular_files(root, source=False, root_fd=root_fd)
    actual_without_inventory = {
        relative: record
        for relative, record in actual.items()
        if relative != INVENTORY_FILENAME
    }
    if set(actual_without_inventory) != set(inventory):
        raise EvidenceValidationError("inventory path set differs from actual files")
    for relative, digest in inventory.items():
        if actual_without_inventory[relative]["sha256"] != digest:
            raise EvidenceValidationError(f"inventory hash differs: {relative}")

    summary_path = root / SUMMARY_FILENAME
    summary_bytes = _read_relative_regular_file_nofollow(
        root,
        SUMMARY_FILENAME,
        "published summary",
        root_fd=root_fd,
    )
    if _sha256_bytes(summary_bytes) != inventory[SUMMARY_FILENAME]:
        raise EvidenceValidationError("summary bytes differ from inventory")
    summary = _decode_contract_json(summary_bytes, SUMMARY_FILENAME)
    summary = _validate_summary(summary, draft=False)
    bundle_id = summary["evidence_bundle_id"]
    if require_final_name and (root.name != bundle_id or root.name.startswith(".")):
        raise EvidenceValidationError("directory basename is not the published bundle ID")
    expected_final = _absolute_lexical_path(
        expected_final_path,
        "expected final path",
    )
    if expected_final.name != bundle_id:
        raise EvidenceValidationError("expected final path does not match bundle ID")

    approval_path = root / APPROVAL_FILENAME
    approval_bytes = _read_relative_regular_file_nofollow(
        root,
        APPROVAL_FILENAME,
        "published approval",
        root_fd=root_fd,
    )
    if _sha256_bytes(approval_bytes) != inventory[APPROVAL_FILENAME]:
        raise EvidenceValidationError("approval bytes differ from inventory")
    if _sha256_bytes(approval_bytes) != summary["authorization"]["sha256"]:
        raise EvidenceValidationError("summary approval hash differs")
    approval = _decode_contract_json(approval_bytes, APPROVAL_FILENAME)
    _validate_approval(
        approval,
        expected_bundle_id=bundle_id,
        expected_final_path=expected_final,
    )

    capture_path = root / CAPTURE_MANIFEST_FILENAME
    capture_bytes = _read_relative_regular_file_nofollow(
        root,
        CAPTURE_MANIFEST_FILENAME,
        "published capture manifest",
        root_fd=root_fd,
    )
    if _sha256_bytes(capture_bytes) != inventory[CAPTURE_MANIFEST_FILENAME]:
        raise EvidenceValidationError("capture manifest bytes differ from inventory")
    if _sha256_bytes(capture_bytes) != summary["source_capture"]["manifest_sha256"]:
        raise EvidenceValidationError("summary capture manifest hash differs")
    capture = _decode_contract_json(capture_bytes, CAPTURE_MANIFEST_FILENAME)
    capture = _validate_capture_manifest(capture)
    owned_top_level = {
        CAPTURE_MANIFEST_FILENAME,
        SUMMARY_FILENAME,
        INVENTORY_FILENAME,
        "publication",
    }
    captured_actual = {
        relative: record
        for relative, record in actual.items()
        if PurePosixPath(relative).parts[0] not in owned_top_level
    }
    if captured_actual != capture["files"]:
        raise EvidenceValidationError("capture manifest path/hash set differs")
    for relative, record in capture["files"].items():
        observed_record = _bytes_record(
            _read_relative_regular_file_nofollow(
                root,
                relative,
                f"captured source {relative!r}",
                root_fd=root_fd,
            )
        )
        if (
            observed_record != record
            or observed_record["sha256"] != inventory[relative]
        ):
            raise EvidenceValidationError(f"captured source differs: {relative}")

    publisher_path = root / PUBLISHER_SNAPSHOT_PATH
    contract_path = root / CONTRACT_SNAPSHOT_PATH
    publisher_sha = _sha256_bytes(
        _read_relative_regular_file_nofollow(
            root,
            PUBLISHER_SNAPSHOT_PATH,
            "publisher source snapshot",
            root_fd=root_fd,
        )
    )
    contract_sha = _sha256_bytes(
        _read_relative_regular_file_nofollow(
            root,
            CONTRACT_SNAPSHOT_PATH,
            "publication contract snapshot",
            root_fd=root_fd,
        )
    )
    if publisher_sha != inventory[PUBLISHER_SNAPSHOT_PATH]:
        raise EvidenceValidationError("publisher source differs from inventory")
    if contract_sha != inventory[CONTRACT_SNAPSHOT_PATH]:
        raise EvidenceValidationError("publication contract differs from inventory")
    if publisher_sha != summary["publisher"]["sha256"]:
        raise EvidenceValidationError("publisher source snapshot hash differs")
    if contract_sha != summary["publication_contract"]["sha256"]:
        raise EvidenceValidationError("publication contract snapshot hash differs")
    if summary["publication_contract"]["sha256"] != EXPECTED_PUBLICATION_SPEC_SHA256:
        raise EvidenceValidationError("publication contract hash is not the guarded version")

    _validate_predecessor(
        summary["correction"], predecessor_path, capture["files"]
    )
    actual_after = _enumerate_regular_files(
        root,
        source=False,
        root_fd=root_fd,
    )
    if actual_after != actual:
        raise EvidenceValidationError("evidence bundle changed during verification")
    inventory_bytes_after = _read_relative_regular_file_nofollow(
        root,
        INVENTORY_FILENAME,
        "published inventory final check",
        root_fd=root_fd,
    )
    if inventory_bytes_after != inventory_bytes:
        raise EvidenceValidationError("inventory changed during verification")
    summary_sha = _sha256_bytes(summary_bytes)
    inventory_sha = _sha256_bytes(inventory_bytes_after)
    return PublicationReceipt(
        final_path=expected_final,
        evidence_bundle_id=bundle_id,
        schema_version=summary["schema_version"],
        operational_backend_result=summary["operational_backend_result"],
        summary_sha256=summary_sha,
        inventory_sha256=inventory_sha,
        bundle_root_sha256=_bundle_root_hash(inventory_sha),
        inventory_entries=len(inventory),
        source_directory_identity=None,
        final_directory_identity=DirectoryIdentity.from_descriptor(root_fd),
    )


def validate_published_bundle(
    path: Path | str,
    *,
    predecessor_path: Optional[Path | str] = None,
) -> PublicationValidationReport:
    """Read-only validation; invalid/partial trees return explicit errors."""
    requested = Path(path)
    if requested.is_symlink():
        return PublicationValidationReport(
            path=requested.absolute(),
            evidence_bundle_id=None,
            schema_version=None,
            operational_backend_result=None,
            summary_sha256=None,
            inventory_sha256=None,
            bundle_root_sha256=None,
            inventory_entries=0,
            publication_conforming=False,
            formal_gate4_pass=False,
            research_eligible=False,
            errors=("EvidenceValidationError: published evidence path is a symlink",),
        )
    root = _absolute_lexical_path(requested, "published evidence path")
    predecessor = Path(predecessor_path) if predecessor_path is not None else None
    try:
        receipt = _verify_bundle_or_raise(
            root,
            expected_final_path=root,
            require_final_name=True,
            predecessor_path=predecessor,
        )
    except Exception as error:
        return PublicationValidationReport(
            path=root,
            evidence_bundle_id=None,
            schema_version=None,
            operational_backend_result=None,
            summary_sha256=None,
            inventory_sha256=None,
            bundle_root_sha256=None,
            inventory_entries=0,
            publication_conforming=False,
            formal_gate4_pass=False,
            research_eligible=False,
            errors=(f"{type(error).__name__}: {error}",),
        )
    return PublicationValidationReport(
        path=root,
        evidence_bundle_id=receipt.evidence_bundle_id,
        schema_version=receipt.schema_version,
        operational_backend_result=receipt.operational_backend_result,
        summary_sha256=receipt.summary_sha256,
        inventory_sha256=receipt.inventory_sha256,
        bundle_root_sha256=receipt.bundle_root_sha256,
        inventory_entries=receipt.inventory_entries,
        publication_conforming=True,
        formal_gate4_pass=False,
        research_eligible=False,
        errors=(),
    )


@contextlib.contextmanager
def _publication_lock(
    root: Path,
    bundle_id: str,
    *,
    root_fd: Optional[int] = None,
) -> Iterator[None]:
    lock_path = root / f".{bundle_id}.publish.lock"
    lock_name = lock_path.name
    if not hasattr(os, "O_NOFOLLOW"):
        raise EvidencePublicationError("O_NOFOLLOW is required for publication locks")
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(
            lock_name if root_fd is not None else lock_path,
            flags,
            0o600,
            dir_fd=root_fd,
        )
    except OSError as error:
        raise EvidencePublicationError("publication lock cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        named = os.stat(
            lock_name if root_fd is not None else lock_path,
            dir_fd=root_fd,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise EvidencePublicationError(
                "publication lock must be a single-link regular file"
            )
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise EvidencePublicationError("publication lock path changed while opening")
        handle = os.fdopen(descriptor, "a+b", closefd=True)
    except Exception:
        os.close(descriptor)
        raise
    locked = False
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError) as error:
            if isinstance(error, OSError) and error.errno in {
                errno.EACCES,
                errno.EAGAIN,
                errno.EDEADLK,
            }:
                raise EvidenceCollisionError(
                    f"publication is already in progress for {bundle_id!r}"
                ) from error
            raise EvidencePublicationError("exclusive publication lock is unavailable") from error
        locked = True
        yield
    finally:
        if locked:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
        handle.close()


def _entry_lexists_at(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _assert_directory_entry_identity(
    parent_fd: int,
    name: str,
    directory_fd: int,
    context: str,
) -> None:
    opened = os.fstat(directory_fd)
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as error:
        raise EvidenceValidationError(f"{context} path changed") from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(named.st_mode)
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise EvidenceValidationError(f"{context} path changed")


def _create_staging_directory(
    root: _PinnedDirectory,
    bundle_id: str,
) -> tuple[str, Path, int]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    for _ in range(128):
        name = f".{bundle_id}.staging.{secrets.token_hex(8)}"
        try:
            os.mkdir(name, 0o700, dir_fd=root.fd)
        except FileExistsError:
            continue
        descriptor = os.open(name, flags, dir_fd=root.fd)
        try:
            _assert_directory_entry_identity(root.fd, name, descriptor, "staging")
            if os.fstat(descriptor).st_dev != os.fstat(root.fd).st_dev:
                raise EvidencePublicationError(
                    "staging and final paths use different filesystems"
                )
        except Exception:
            os.close(descriptor)
            raise
        return name, root.path / name, descriptor
    raise EvidenceCollisionError("could not allocate a unique staging directory")


def _rename_noreplace(
    source: Path | str,
    destination: Path | str,
    *,
    source_dir_fd: int = -100,
    destination_dir_fd: int = -100,
) -> None:
    """Linux renameat2(RENAME_NOREPLACE), with no unsafe fallback."""
    if os.name != "posix":
        raise EvidencePublicationError("atomic no-replace publication is unsupported")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise EvidencePublicationError("renameat2 is unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        source_dir_fd,
        os.fsencode(source),
        destination_dir_fd,
        os.fsencode(destination),
        1,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise EvidenceCollisionError(
            f"published evidence already exists: {destination}"
        )
    if error_number in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV}:
        raise EvidencePublicationError(
            f"safe atomic publication is unsupported: errno={error_number}"
        )
    raise EvidencePublicationError(
        f"atomic publication failed: errno={error_number}"
    )


def publish_evidence(
    source_dir: Path | str,
    publication_root: Path | str,
    summary_draft: Mapping[str, Any],
    *,
    predecessor_path: Optional[Path | str] = None,
    checkpoint_hook: Optional[CheckpointHook] = None,
    expected_source_identity: Optional[Mapping[str, Any]] = None,
    expected_publication_root_identity: Optional[Mapping[str, Any]] = None,
) -> PublicationReceipt:
    """Publish a complete capture once, leaving failures only in hidden staging."""
    draft = dict(summary_draft)
    _validate_summary(draft, draft=True)
    predecessor = Path(predecessor_path) if predecessor_path is not None else None
    expected_source = (
        DirectoryIdentity.from_value(
            expected_source_identity,
            "expected source directory identity",
        )
        if expected_source_identity is not None
        else None
    )
    expected_publication_root = (
        DirectoryIdentity.from_value(
            expected_publication_root_identity,
            "expected publication root directory identity",
        )
        if expected_publication_root_identity is not None
        else None
    )
    publisher_source = _absolute_lexical_path(Path(__file__), "publisher source")
    repository = publisher_source.parents[1]
    with _pin_directory(source_dir, "source capture") as source_pin:
        with _pin_directory(publication_root, "publication_root") as root_pin:
            with _pin_directory(repository, "publisher repository") as repository_pin:
                return _publish_evidence_pinned(
                    source_pin,
                    root_pin,
                    repository_pin,
                    publisher_source,
                    draft,
                    predecessor=predecessor,
                    checkpoint_hook=checkpoint_hook,
                    expected_source_identity=expected_source,
                    expected_publication_root_identity=expected_publication_root,
                )


def _publish_evidence_pinned(
    source_pin: _PinnedDirectory,
    root_pin: _PinnedDirectory,
    repository_pin: _PinnedDirectory,
    publisher_source: Path,
    draft: Mapping[str, Any],
    *,
    predecessor: Optional[Path],
    checkpoint_hook: Optional[CheckpointHook],
    expected_source_identity: Optional[DirectoryIdentity],
    expected_publication_root_identity: Optional[DirectoryIdentity],
) -> PublicationReceipt:
    bundle_id = draft["evidence_bundle_id"]
    source = source_pin.path
    root = root_pin.path
    final = root / bundle_id
    source_directory_identity = DirectoryIdentity.from_descriptor(source_pin.fd)
    if (
        expected_source_identity is not None
        and source_directory_identity != expected_source_identity
    ):
        raise EvidenceValidationError(
            "source capture identity differs from expected handoff"
        )
    source_identity = (
        source_directory_identity.device,
        source_directory_identity.inode,
    )
    root_identity = (os.fstat(root_pin.fd).st_dev, os.fstat(root_pin.fd).st_ino)
    if (
        expected_publication_root_identity is not None
        and DirectoryIdentity(*root_identity) != expected_publication_root_identity
    ):
        raise EvidenceValidationError(
            "publication root identity differs from expected handoff"
        )
    source_chain = {
        (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
        for descriptor in source_pin.descriptors
    }
    root_chain = {
        (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
        for descriptor in root_pin.descriptors
    }
    if (
        source == root
        or source in root.parents
        or root in source.parents
        or source_identity == root_identity
        or source_identity in root_chain
        or root_identity in source_chain
    ):
        raise EvidenceValidationError("source and publication root must not overlap")
    source_pin.assert_path_identity()
    root_pin.assert_path_identity()
    if _entry_lexists_at(root_pin.fd, bundle_id):
        raise EvidenceCollisionError(f"published evidence already exists: {final}")

    approval_bytes = _read_relative_regular_file_nofollow(
        source,
        APPROVAL_FILENAME,
        "source approval.json",
        root_fd=source_pin.fd,
    )
    approval = _decode_contract_json(approval_bytes, APPROVAL_FILENAME)
    _validate_approval(
        approval,
        expected_bundle_id=bundle_id,
        expected_final_path=final,
    )
    source_before = _enumerate_regular_files(
        source,
        source=True,
        root_fd=source_pin.fd,
    )
    if source_before[APPROVAL_FILENAME] != _bytes_record(approval_bytes):
        raise EvidenceValidationError("source approval changed during preflight")

    publisher_relative = publisher_source.relative_to(repository_pin.path).as_posix()
    contract_bytes = _read_relative_regular_file_nofollow(
        repository_pin.path,
        PUBLICATION_SPEC_PATH,
        "publication specification source",
        root_fd=repository_pin.fd,
    )
    contract_sha = _sha256_bytes(contract_bytes)
    if contract_sha != EXPECTED_PUBLICATION_SPEC_SHA256:
        raise EvidenceValidationError("publication specification hash differs")
    publisher_bytes = _read_relative_regular_file_nofollow(
        repository_pin.path,
        publisher_relative,
        "publisher source",
        root_fd=repository_pin.fd,
    )
    source_pin.assert_path_identity()
    root_pin.assert_path_identity()
    repository_pin.assert_path_identity()

    with _publication_lock(root, bundle_id, root_fd=root_pin.fd):
        source_pin.assert_path_identity()
        root_pin.assert_path_identity()
        repository_pin.assert_path_identity()
        if _entry_lexists_at(root_pin.fd, bundle_id):
            raise EvidenceCollisionError(f"published evidence already exists: {final}")
        staging_name, staging, staging_fd = _create_staging_directory(
            root_pin,
            bundle_id,
        )
        try:
            for relative, expected in sorted(source_before.items()):
                source_bytes = _read_relative_regular_file_nofollow(
                    source,
                    relative,
                    f"source capture {relative!r}",
                    root_fd=source_pin.fd,
                )
                if _bytes_record(source_bytes) != expected:
                    raise EvidenceValidationError(
                        f"source changed before copy: {relative}"
                    )
                _write_fsynced_at(staging_fd, relative, source_bytes)
                copied = _read_relative_regular_file_nofollow(
                    staging,
                    relative,
                    f"staged copy {relative!r}",
                    root_fd=staging_fd,
                )
                if _bytes_record(copied) != expected:
                    raise EvidenceValidationError(f"source copy differs: {relative}")
            source_after = _enumerate_regular_files(
                source,
                source=True,
                root_fd=source_pin.fd,
            )
            if source_after != source_before:
                raise EvidenceValidationError("source capture changed during publication")
            if checkpoint_hook is not None:
                checkpoint_hook("after_raw_copy", staging, final)
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                staging_name,
                staging_fd,
                "staging",
            )

            _write_fsynced_at(
                staging_fd,
                PUBLISHER_SNAPSHOT_PATH,
                publisher_bytes,
            )
            _write_fsynced_at(
                staging_fd,
                CONTRACT_SNAPSHOT_PATH,
                contract_bytes,
            )
            capture_manifest = {
                "schema_version": CAPTURE_MANIFEST_SCHEMA_VERSION,
                "files": source_before,
            }
            capture_bytes = _canonical_json_bytes(capture_manifest)
            _validate_capture_manifest(
                _decode_contract_json(capture_bytes, CAPTURE_MANIFEST_FILENAME)
            )
            _write_fsynced_at(
                staging_fd,
                CAPTURE_MANIFEST_FILENAME,
                capture_bytes,
            )
            if checkpoint_hook is not None:
                checkpoint_hook("after_capture_manifest", staging, final)
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                staging_name,
                staging_fd,
                "staging",
            )

            summary = {
                **draft,
                "authorization": {
                    "path": APPROVAL_FILENAME,
                    "sha256": _sha256_bytes(approval_bytes),
                },
                "source_capture": {
                    "manifest_path": CAPTURE_MANIFEST_FILENAME,
                    "manifest_sha256": _sha256_bytes(capture_bytes),
                },
                "publisher": {
                    "path": PUBLISHER_SNAPSHOT_PATH,
                    "sha256": _sha256_bytes(publisher_bytes),
                    "version": PUBLICATION_VERSION,
                },
                "publication_contract": {
                    "path": CONTRACT_SNAPSHOT_PATH,
                    "sha256": contract_sha,
                    "version": PUBLICATION_SPEC_VERSION,
                },
            }
            _validate_summary(summary, draft=False, expected_bundle_id=bundle_id)
            summary_bytes = _canonical_json_bytes(summary)
            _write_fsynced_at(staging_fd, SUMMARY_FILENAME, summary_bytes)
            if checkpoint_hook is not None:
                checkpoint_hook("after_summary", staging, final)
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                staging_name,
                staging_fd,
                "staging",
            )

            inventory_bytes = _inventory_bytes(staging, root_fd=staging_fd)
            _write_inventory_with_checkpoint_at(
                staging_fd,
                inventory_bytes,
                hook=checkpoint_hook,
                staging=staging,
                final=final,
            )
            if checkpoint_hook is not None:
                checkpoint_hook("after_inventory_write", staging, final)
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                staging_name,
                staging_fd,
                "staging",
            )

            _verify_bundle_or_raise(
                staging,
                expected_final_path=final,
                require_final_name=False,
                predecessor_path=predecessor,
                root_fd=staging_fd,
            )
            if checkpoint_hook is not None:
                checkpoint_hook(
                    "after_inventory_verification_before_publish",
                    staging,
                    final,
                )
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                staging_name,
                staging_fd,
                "staging",
            )
            if (
                _enumerate_regular_files(
                    source,
                    source=True,
                    root_fd=source_pin.fd,
                )
                != source_before
            ):
                raise EvidenceValidationError("source capture changed before publication")
            if (
                _read_relative_regular_file_nofollow(
                    repository_pin.path,
                    publisher_relative,
                    "publisher source",
                    root_fd=repository_pin.fd,
                )
                != publisher_bytes
            ):
                raise EvidenceValidationError(
                    "publisher source changed during publication"
                )
            if (
                _read_relative_regular_file_nofollow(
                    repository_pin.path,
                    PUBLICATION_SPEC_PATH,
                    "publication specification source",
                    root_fd=repository_pin.fd,
                )
                != contract_bytes
            ):
                raise EvidenceValidationError(
                    "publication specification changed during publication"
                )
            staged_capture = _decode_contract_json(
                _read_relative_regular_file_nofollow(
                    staging,
                    CAPTURE_MANIFEST_FILENAME,
                    "staged capture manifest",
                    root_fd=staging_fd,
                ),
                CAPTURE_MANIFEST_FILENAME,
            )
            staged_capture = _validate_capture_manifest(staged_capture)
            if staged_capture["files"] != source_before:
                raise EvidenceValidationError(
                    "staged capture no longer matches the source"
                )

            _fsync_regular_files(staging, root_fd=staging_fd)
            _fsync_tree_directories_at(staging_fd)
            _fsync_directory_fd(staging_fd)
            _fsync_directory_fd(root_pin.fd)
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                staging_name,
                staging_fd,
                "staging",
            )
            staged_receipt = _verify_bundle_or_raise(
                staging,
                expected_final_path=final,
                require_final_name=False,
                predecessor_path=predecessor,
                root_fd=staging_fd,
            )
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                staging_name,
                staging_fd,
                "staging",
            )
            if _entry_lexists_at(root_pin.fd, bundle_id):
                raise EvidenceCollisionError(
                    f"published evidence already exists: {final}"
                )
            _rename_noreplace(
                staging_name,
                bundle_id,
                source_dir_fd=root_pin.fd,
                destination_dir_fd=root_pin.fd,
            )
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                bundle_id,
                staging_fd,
                "published evidence",
            )
            if _entry_lexists_at(root_pin.fd, staging_name):
                raise EvidencePublicationError(
                    "staging name remained after atomic publication"
                )
            _fsync_directory_fd(root_pin.fd)

            final_receipt = _verify_bundle_or_raise(
                final,
                expected_final_path=final,
                require_final_name=True,
                predecessor_path=predecessor,
                root_fd=staging_fd,
            )
            source_pin.assert_path_identity()
            root_pin.assert_path_identity()
            repository_pin.assert_path_identity()
            _assert_directory_entry_identity(
                root_pin.fd,
                bundle_id,
                staging_fd,
                "published evidence",
            )
            if (
                final_receipt.summary_sha256 != staged_receipt.summary_sha256
                or final_receipt.inventory_sha256 != staged_receipt.inventory_sha256
                or final_receipt.bundle_root_sha256
                != staged_receipt.bundle_root_sha256
                or final_receipt.inventory_entries != staged_receipt.inventory_entries
            ):
                raise EvidencePublicationError(
                    "published leaf commitments differ from verified staging"
                )
            return replace(
                final_receipt,
                source_directory_identity=source_directory_identity,
                final_directory_identity=DirectoryIdentity.from_descriptor(
                    staging_fd
                ),
            )
        finally:
            os.close(staging_fd)
