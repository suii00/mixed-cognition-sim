#!/usr/bin/env python3
"""Independent, read-only verification for a Gate 4 evidence bundle.

This module intentionally does not import the evidence publisher.  It
reimplements the closed publication contract so that publication receipts can
be checked by a separate code path.  Version 1 is deliberately limited to the
generic ``publication_structure_only`` profile: it does not validate a run's
operational outcome, resource use, or research eligibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Optional, Sequence


REPORT_SCHEMA_VERSION = "gate4-independent-verification-report-v1.1.0"
SUMMARY_SCHEMA_VERSION = "gate4-backend-evidence-summary-v1.0.0"
APPROVAL_SCHEMA_VERSION = "gate4-gpu-run-approval-v1.0.0"
CAPTURE_MANIFEST_SCHEMA_VERSION = "gate4-evidence-capture-manifest-v1.0.0"
PUBLISHER_VERSION = "gate4-evidence-publisher-v1.1.0"
PUBLICATION_SPEC_VERSION = "gate4-backend-evidence-publication-v1.1.0"
EXPECTED_PUBLICATION_SPEC_SHA256 = (
    "8201013f77d98cc0c63559fe31a7c3c8d4dc90b4d1eda0f245d0e56f77ba7b6c"
)

SUMMARY_FILENAME = "run-summary.json"
APPROVAL_FILENAME = "approval.json"
CAPTURE_MANIFEST_FILENAME = "capture-manifest.json"
INVENTORY_FILENAME = "files.sha256"
PUBLISHER_SNAPSHOT_PATH = "publication/gate4_evidence_publisher.py"
CONTRACT_SNAPSHOT_PATH = "publication/GATE4_EVIDENCE_PUBLICATION_SPEC.md"
ROOT_HASH_DOMAIN = b"MCS-EVIDENCE-BUNDLE-ROOT-V1\0"

SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
GPU_UUID_RE = re.compile(r"GPU-[0-9A-Fa-f-]{8,}\Z")
INVENTORY_LINE_RE = re.compile(r"([0-9a-f]{64})  \./([^\r\n]+)\Z")

EXECUTION_MODES = {
    "reference_ollama",
    "vllm_openai_compatible",
    "scripted_smoke",
}
STRUCTURE_ONLY_CLAIM_SCOPE = ["publication_structure_only"]
STRUCTURE_ONLY_UNVERIFIED_CLAIMS = sorted(
    [
        "run_id",
        "protocol_version",
        "metric_version",
        "execution_mode",
        "operational_backend_result",
        "resource_and_workload_limits",
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

SUMMARY_FIELDS = {
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
    "authorization",
    "claim_scope",
    "warnings",
    "unverified_claims",
    "correction",
    "source_capture",
    "publisher",
    "publication_contract",
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
PUBLISHER_OWNED_TOP_LEVEL = {
    SUMMARY_FILENAME,
    CAPTURE_MANIFEST_FILENAME,
    INVENTORY_FILENAME,
    "publication",
}
CONTRACT_DATA_PATHS = {
    SUMMARY_FILENAME,
    APPROVAL_FILENAME,
    CAPTURE_MANIFEST_FILENAME,
    INVENTORY_FILENAME,
}


class IndependentVerificationError(RuntimeError):
    """The bundle violates the independently implemented contract."""


@dataclass(frozen=True)
class FileRecord:
    sha256: str
    bytes: int
    lines: int

    def as_dict(self) -> Dict[str, Any]:
        return {"sha256": self.sha256, "bytes": self.bytes, "lines": self.lines}


@dataclass(frozen=True)
class DirectoryIdentity:
    device: int
    inode: int

    @classmethod
    def from_value(
        cls,
        value: Mapping[str, Any],
        context: str,
    ) -> "DirectoryIdentity":
        if not isinstance(value, Mapping) or set(value) != {"device", "inode"}:
            raise IndependentVerificationError(f"{context} fields differ")
        device = value["device"]
        inode = value["inode"]
        if type(device) is not int or device < 0:
            raise IndependentVerificationError(f"{context}.device is invalid")
        if type(inode) is not int or inode <= 0:
            raise IndependentVerificationError(f"{context}.inode is invalid")
        return cls(device, inode)

    def as_dict(self) -> Dict[str, int]:
        return {"device": self.device, "inode": self.inode}


@dataclass(frozen=True)
class TreeSnapshot:
    records: Mapping[str, FileRecord]
    contract_bytes: Mapping[str, bytes]
    root_identity: DirectoryIdentity


@dataclass(frozen=True)
class VerifiedCommitments:
    evidence_bundle_id: str
    operational_backend_result: str
    summary_sha256: str
    inventory_sha256: str
    bundle_root_sha256: str
    inventory_entries: int
    correction_kind: str
    capture_files: Mapping[str, Mapping[str, Any]]
    directory_identity: DirectoryIdentity


@dataclass(frozen=True)
class IndependentVerificationReport:
    path: Path
    publication_conforming: bool
    commitments_match: bool
    valid: bool
    evidence_bundle_id: Optional[str]
    operational_backend_result: Optional[str]
    summary_sha256: Optional[str]
    inventory_sha256: Optional[str]
    bundle_root_sha256: Optional[str]
    inventory_entries: int
    formal_gate4_pass: bool
    research_eligible: bool
    backend_freeze_status: Optional[str]
    directory_identity: Optional[DirectoryIdentity]
    errors: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "path": str(self.path),
            "publication_conforming": self.publication_conforming,
            "commitments_match": self.commitments_match,
            "valid": self.valid,
            "evidence_bundle_id": self.evidence_bundle_id,
            "operational_backend_result": self.operational_backend_result,
            "summary_sha256": self.summary_sha256,
            "inventory_sha256": self.inventory_sha256,
            "bundle_root_sha256": self.bundle_root_sha256,
            "inventory_entries": self.inventory_entries,
            "formal_gate4_pass": self.formal_gate4_pass,
            "research_eligible": self.research_eligible,
            "backend_freeze_status": self.backend_freeze_status,
            "directory_identity": (
                self.directory_identity.as_dict()
                if self.directory_identity is not None
                else None
            ),
            "errors": list(self.errors),
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bundle_root_hash(inventory_sha256: str) -> str:
    return _sha256(ROOT_HASH_DOMAIN + bytes.fromhex(inventory_sha256))


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
        raise IndependentVerificationError("contract JSON is not serializable") from error
    return rendered.encode("utf-8") + b"\n"


def _reject_floats(value: Any, context: str) -> None:
    if isinstance(value, float):
        raise IndependentVerificationError(f"{context} may not contain floats")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise IndependentVerificationError(
                    f"{context} object keys must be strings"
                )
            _reject_floats(item, f"{context}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{context}[{index}]")


def _decode_canonical_json(data: bytes, context: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IndependentVerificationError(f"{context} is not UTF-8") from error

    def object_pairs(pairs: Sequence[tuple[str, Any]]) -> Dict[str, Any]:
        value: Dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise IndependentVerificationError(
                    f"{context} contains duplicate object key {key!r}"
                )
            value[key] = item
        return value

    def invalid_constant(token: str) -> None:
        raise IndependentVerificationError(
            f"{context} contains invalid numeric constant {token}"
        )

    try:
        value = json.loads(
            text,
            object_pairs_hook=object_pairs,
            parse_constant=invalid_constant,
        )
    except IndependentVerificationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise IndependentVerificationError(f"{context} is not valid JSON") from error
    _reject_floats(value, context)
    if _canonical_json_bytes(value) != data:
        raise IndependentVerificationError(f"{context} is not canonical JSON")
    return value


def _require_exact_keys(
    value: Any, expected: set[str], context: str
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise IndependentVerificationError(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        raise IndependentVerificationError(
            f"{context} key set differs; "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )
    return value


def _require_nonempty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IndependentVerificationError(f"{context} must be a non-empty string")
    return value


def _require_sha256(value: Any, context: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise IndependentVerificationError(f"{context} must be a lowercase SHA-256")
    return value


def _require_positive_int(value: Any, context: str) -> int:
    if type(value) is not int or value <= 0:
        raise IndependentVerificationError(f"{context} must be a positive integer")
    return value


def _require_sorted_unique_strings(
    value: Any, context: str, *, nonempty: bool = False
) -> list[str]:
    if not isinstance(value, list):
        raise IndependentVerificationError(f"{context} must be an array")
    result = [_require_nonempty_string(item, f"{context}[]") for item in value]
    if nonempty and not result:
        raise IndependentVerificationError(f"{context} must not be empty")
    if result != sorted(set(result)):
        raise IndependentVerificationError(f"{context} must be sorted and unique")
    return result


def _validate_bundle_id(value: Any, context: str = "evidence_bundle_id") -> str:
    identifier = _require_nonempty_string(value, context)
    if SAFE_ID_RE.fullmatch(identifier) is None or ".." in identifier:
        raise IndependentVerificationError(f"{context} is not a safe canonical ID")
    return identifier


def _safe_relative_path(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\0" in value
        or "\n" in value
        or "\r" in value
    ):
        raise IndependentVerificationError(f"{context} is not a safe relative path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or value.startswith("./")
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise IndependentVerificationError(
            f"{context} is not a canonical relative path"
        )
    return value


_STABLE_STAT_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_nlink",
    "st_uid",
    "st_gid",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)
_IDENTITY_STAT_FIELDS = ("st_dev", "st_ino", "st_mode")


def _require_same_metadata(
    before: os.stat_result,
    after: os.stat_result,
    context: str,
) -> None:
    if any(
        getattr(before, field) != getattr(after, field)
        for field in _STABLE_STAT_FIELDS
    ):
        raise IndependentVerificationError(f"{context} changed during snapshot")


def _require_same_identity(
    before: os.stat_result,
    after: os.stat_result,
    context: str,
) -> None:
    if any(
        getattr(before, field) != getattr(after, field)
        for field in _IDENTITY_STAT_FIELDS
    ):
        raise IndependentVerificationError(f"{context} changed during snapshot")


def _read_regular_descriptor(
    descriptor: int,
    relative: str,
    *,
    keep_bytes: bool,
) -> tuple[FileRecord, bytes, os.stat_result]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise IndependentVerificationError(
            "evidence tree may contain only regular files"
        )
    if before.st_nlink != 1:
        raise IndependentVerificationError(
            "evidence tree may not contain hard-linked files"
        )
    digest = hashlib.sha256()
    byte_count = 0
    line_count = 0
    retained: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        byte_count += len(chunk)
        line_count += chunk.count(b"\n")
        if keep_bytes:
            retained.append(chunk)
    after = os.fstat(descriptor)
    _require_same_metadata(before, after, f"evidence file {relative!r}")
    if byte_count != after.st_size:
        raise IndependentVerificationError(
            f"evidence file size changed while being read: {relative}"
        )
    return (
        FileRecord(digest.hexdigest(), byte_count, line_count),
        b"".join(retained),
        after,
    )


def _snapshot_tree(root: Path) -> TreeSnapshot:
    """Pin and hash a tree using only descriptor-relative child lookups.

    Once the root descriptor is opened, no child path is resolved from the
    process working directory.  Every named lookup is paired with an
    ``O_NOFOLLOW`` descriptor and before/after metadata identity checks.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise IndependentVerificationError(
            "descriptor-relative nofollow tree verification is unsupported"
        )
    records: Dict[str, FileRecord] = {}
    contract_bytes: Dict[str, bytes] = {}
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW

    root = Path(os.path.abspath(os.fspath(root)))
    path_components = root.parts[1:]
    opened_descriptors: list[int] = []
    directory_chain: list[
        tuple[int, str, int, os.stat_result, str]
    ] = []
    try:
        root_of_filesystem = os.open(os.sep, directory_flags)
    except OSError as error:
        raise IndependentVerificationError(
            "cannot safely open filesystem root directory"
        ) from error
    opened_descriptors.append(root_of_filesystem)
    try:
        filesystem_root_opened = os.fstat(root_of_filesystem)
        current_descriptor = root_of_filesystem
        traversed: list[str] = []
        for component in path_components:
            traversed.append(component)
            display = os.sep + os.path.join(*traversed)
            try:
                named_before = os.stat(
                    component,
                    dir_fd=current_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise IndependentVerificationError(
                    f"cannot inspect absolute path component: {display}"
                ) from error
            if stat.S_ISLNK(named_before.st_mode):
                raise IndependentVerificationError(
                    f"absolute evidence path may not contain symlink components: {display}"
                )
            if not stat.S_ISDIR(named_before.st_mode):
                raise IndependentVerificationError(
                    f"absolute evidence path component is not a directory: {display}"
                )
            try:
                child_descriptor = os.open(
                    component,
                    directory_flags,
                    dir_fd=current_descriptor,
                )
            except OSError as error:
                raise IndependentVerificationError(
                    f"cannot safely open absolute path component: {display}"
                ) from error
            opened_descriptors.append(child_descriptor)
            child_opened = os.fstat(child_descriptor)
            if not stat.S_ISDIR(child_opened.st_mode):
                raise IndependentVerificationError(
                    f"absolute evidence path component became non-directory: {display}"
                )
            _require_same_identity(
                named_before,
                child_opened,
                f"absolute path component {display!r} between named lookup and descriptor open",
            )
            directory_chain.append(
                (
                    current_descriptor,
                    component,
                    child_descriptor,
                    child_opened,
                    display,
                )
            )
            current_descriptor = child_descriptor

        root_descriptor = current_descriptor
        root_opened = os.fstat(root_descriptor)
        root_identity = DirectoryIdentity(root_opened.st_dev, root_opened.st_ino)
        if not stat.S_ISDIR(root_opened.st_mode):
            raise IndependentVerificationError("evidence root is not a directory")

        def named_stat(parent_descriptor: int, name: str, relative: str) -> os.stat_result:
            try:
                return os.stat(
                    name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise IndependentVerificationError(
                    f"cannot inspect evidence entry: {relative}"
                ) from error

        def directory_names(descriptor: int, relative: str) -> list[str]:
            try:
                with os.scandir(descriptor) as iterator:
                    names = sorted(entry.name for entry in iterator)
            except OSError as error:
                raise IndependentVerificationError(
                    f"cannot enumerate evidence directory: {relative or '.'}"
                ) from error
            for name in names:
                candidate = f"{relative}/{name}" if relative else name
                _safe_relative_path(candidate, "evidence path")
            return names

        def visit(directory_descriptor: int, relative_directory: str) -> None:
            directory_before = os.fstat(directory_descriptor)
            if not stat.S_ISDIR(directory_before.st_mode):
                raise IndependentVerificationError(
                    "evidence traversal descriptor is not a directory"
                )
            names_before = directory_names(directory_descriptor, relative_directory)
            for name in names_before:
                relative = (
                    f"{relative_directory}/{name}" if relative_directory else name
                )
                metadata_before = named_stat(directory_descriptor, name, relative)
                if stat.S_ISLNK(metadata_before.st_mode):
                    raise IndependentVerificationError(
                        "evidence tree may not contain symlinks"
                    )
                if stat.S_ISDIR(metadata_before.st_mode):
                    try:
                        child_descriptor = os.open(
                            name,
                            directory_flags,
                            dir_fd=directory_descriptor,
                        )
                    except OSError as error:
                        raise IndependentVerificationError(
                            f"cannot safely open evidence directory entry: {relative}"
                        ) from error
                    try:
                        child_opened = os.fstat(child_descriptor)
                        if not stat.S_ISDIR(child_opened.st_mode):
                            raise IndependentVerificationError(
                                f"evidence directory entry became non-directory: {relative}"
                            )
                        _require_same_metadata(
                            metadata_before,
                            child_opened,
                            f"evidence directory {relative!r} between named lookup and descriptor open",
                        )
                        visit(child_descriptor, relative)
                        child_after = os.fstat(child_descriptor)
                        metadata_after = named_stat(
                            directory_descriptor, name, relative
                        )
                        _require_same_metadata(
                            child_opened,
                            child_after,
                            f"evidence directory descriptor {relative!r}",
                        )
                        _require_same_metadata(
                            child_after,
                            metadata_after,
                            f"named evidence directory {relative!r}",
                        )
                    finally:
                        os.close(child_descriptor)
                    continue
                if not stat.S_ISREG(metadata_before.st_mode):
                    raise IndependentVerificationError(
                        "evidence tree may contain only regular files and directories"
                    )
                if metadata_before.st_nlink != 1:
                    raise IndependentVerificationError(
                        "evidence tree may not contain hard-linked files"
                    )
                try:
                    file_descriptor = os.open(
                        name,
                        file_flags,
                        dir_fd=directory_descriptor,
                    )
                except OSError as error:
                    raise IndependentVerificationError(
                        f"cannot safely open evidence file entry: {relative}"
                    ) from error
                try:
                    file_opened = os.fstat(file_descriptor)
                    _require_same_metadata(
                        metadata_before,
                        file_opened,
                        f"evidence file {relative!r} between named lookup and descriptor open",
                    )
                    record, data, file_after = _read_regular_descriptor(
                        file_descriptor,
                        relative,
                        keep_bytes=relative in CONTRACT_DATA_PATHS,
                    )
                    metadata_after = named_stat(directory_descriptor, name, relative)
                    _require_same_metadata(
                        file_after,
                        metadata_after,
                        f"named evidence file {relative!r}",
                    )
                finally:
                    os.close(file_descriptor)
                if relative in records:
                    raise IndependentVerificationError(
                        f"duplicate evidence path: {relative}"
                    )
                records[relative] = record
                if relative in CONTRACT_DATA_PATHS:
                    contract_bytes[relative] = data

            names_after = directory_names(directory_descriptor, relative_directory)
            if names_after != names_before:
                raise IndependentVerificationError(
                    f"evidence directory entries changed during snapshot: {relative_directory or '.'}"
                )
            directory_after = os.fstat(directory_descriptor)
            _require_same_metadata(
                directory_before,
                directory_after,
                f"evidence directory {relative_directory or '.'!r}",
            )

        visit(root_descriptor, "")
        root_descriptor_after = os.fstat(root_descriptor)
        _require_same_metadata(
            root_opened,
            root_descriptor_after,
            "evidence root descriptor",
        )
        for (
            parent_descriptor,
            component,
            child_descriptor,
            child_opened,
            display,
        ) in reversed(directory_chain):
            child_after = os.fstat(child_descriptor)
            try:
                named_after = os.stat(
                    component,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise IndependentVerificationError(
                    f"absolute path component name changed during snapshot: {display}"
                ) from error
            _require_same_identity(
                child_opened,
                child_after,
                f"absolute path descriptor {display!r}",
            )
            _require_same_identity(
                child_after,
                named_after,
                f"named absolute path component {display!r}",
            )
        _require_same_identity(
            filesystem_root_opened,
            os.fstat(root_of_filesystem),
            "filesystem root descriptor",
        )
    finally:
        for descriptor in reversed(opened_descriptors):
            os.close(descriptor)
    return TreeSnapshot(
        records=records,
        contract_bytes=contract_bytes,
        root_identity=root_identity,
    )


def _parse_inventory(data: bytes) -> Dict[str, str]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise IndependentVerificationError("files.sha256 is not ASCII") from error
    if not text or not text.endswith("\n"):
        raise IndependentVerificationError(
            "files.sha256 must be non-empty and end with a newline"
        )
    result: Dict[str, str] = {}
    ordered: list[str] = []
    for line in text.splitlines():
        match = INVENTORY_LINE_RE.fullmatch(line)
        if match is None:
            raise IndependentVerificationError("files.sha256 line format is invalid")
        digest, relative = match.groups()
        _safe_relative_path(relative, "inventory path")
        if relative == INVENTORY_FILENAME:
            raise IndependentVerificationError("files.sha256 may not list itself")
        if relative in result:
            raise IndependentVerificationError(
                "files.sha256 contains a duplicate path"
            )
        result[relative] = digest
        ordered.append(relative)
    if ordered != sorted(ordered):
        raise IndependentVerificationError("files.sha256 paths are not sorted")
    return result


def _validate_file_record(value: Any, context: str) -> Dict[str, Any]:
    record = _require_exact_keys(value, {"sha256", "bytes", "lines"}, context)
    digest = _require_sha256(record["sha256"], f"{context}.sha256")
    for field in ("bytes", "lines"):
        if type(record[field]) is not int or record[field] < 0:
            raise IndependentVerificationError(
                f"{context}.{field} must be a nonnegative integer"
            )
    return {
        "sha256": digest,
        "bytes": record["bytes"],
        "lines": record["lines"],
    }


def _validate_capture_manifest(value: Any) -> Dict[str, Dict[str, Any]]:
    manifest = _require_exact_keys(
        value, {"schema_version", "files"}, "capture_manifest"
    )
    if manifest["schema_version"] != CAPTURE_MANIFEST_SCHEMA_VERSION:
        raise IndependentVerificationError("capture manifest schema_version differs")
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise IndependentVerificationError(
            "capture_manifest.files must be a non-empty object"
        )
    validated: Dict[str, Dict[str, Any]] = {}
    for relative, record in files.items():
        _safe_relative_path(relative, "capture manifest path")
        if PurePosixPath(relative).parts[0] in PUBLISHER_OWNED_TOP_LEVEL:
            raise IndependentVerificationError(
                f"capture manifest uses publisher-owned path {relative!r}"
            )
        validated[relative] = _validate_file_record(
            record, f"capture_manifest.files[{relative!r}]"
        )
    if APPROVAL_FILENAME not in validated or len(validated) < 2:
        raise IndependentVerificationError(
            "capture manifest requires approval.json and raw evidence"
        )
    return validated


def _validate_approval(
    value: Any, *, bundle_id: str, bundle_path: Path
) -> Mapping[str, Any]:
    approval = _require_exact_keys(value, APPROVAL_FIELDS, "approval")
    if approval["schema_version"] != APPROVAL_SCHEMA_VERSION:
        raise IndependentVerificationError("approval schema_version differs")
    if _validate_bundle_id(
        approval["evidence_bundle_id"], "approval.evidence_bundle_id"
    ) != bundle_id:
        raise IndependentVerificationError("approval evidence_bundle_id differs")
    approved_path = _require_nonempty_string(
        approval["approved_final_path"], "approval.approved_final_path"
    )
    candidate = Path(approved_path)
    if (
        not candidate.is_absolute()
        or candidate.resolve() != bundle_path.resolve()
    ):
        raise IndependentVerificationError("approval final path differs")
    _require_positive_int(
        approval["logical_generation_limit"], "approval.logical_generation_limit"
    )
    _require_positive_int(
        approval["wall_clock_limit_seconds"], "approval.wall_clock_limit_seconds"
    )
    gpu_uuids = _require_sorted_unique_strings(
        approval["gpu_uuids"], "approval.gpu_uuids", nonempty=True
    )
    if any(GPU_UUID_RE.fullmatch(item) is None for item in gpu_uuids):
        raise IndependentVerificationError("approval contains an invalid GPU UUID")
    _require_sorted_unique_strings(
        approval["stop_conditions"], "approval.stop_conditions", nonempty=True
    )
    if approval["approved"] is not True:
        raise IndependentVerificationError("approval.approved must be true")
    _require_nonempty_string(
        approval["approval_reference"], "approval.approval_reference"
    )
    return approval


def _validate_correction(value: Any) -> None:
    correction = _require_exact_keys(value, CORRECTION_FIELDS, "summary.correction")
    kind = correction["kind"]
    if kind not in {"original", "derived_correction"}:
        raise IndependentVerificationError("summary.correction.kind is invalid")
    if correction["raw_artifacts_changed"] is not False:
        raise IndependentVerificationError(
            "summary.correction.raw_artifacts_changed must be false"
        )
    repaired = _require_sorted_unique_strings(
        correction["repaired_properties"],
        "summary.correction.repaired_properties",
    )
    not_repaired = _require_sorted_unique_strings(
        correction["not_repaired"], "summary.correction.not_repaired"
    )
    if set(repaired).intersection(not_repaired):
        raise IndependentVerificationError(
            "summary correction repaired/not_repaired properties must be disjoint"
        )
    if HISTORICAL_NONREPAIRABLE.intersection(repaired):
        raise IndependentVerificationError(
            "historical publication properties cannot be repaired"
        )
    if not set(repaired).issubset(CORRECTION_REPAIRABLE):
        raise IndependentVerificationError(
            "summary correction names an unsupported repaired property"
        )
    if not set(not_repaired).issubset(HISTORICAL_NONREPAIRABLE):
        raise IndependentVerificationError(
            "summary correction names an unsupported unrepaired property"
        )
    if kind == "original":
        if correction["supersedes"] is not None:
            raise IndependentVerificationError(
                "original correction.supersedes must be null"
            )
        if correction["reason_code"] is not None or correction["reason"] is not None:
            raise IndependentVerificationError(
                "original correction reason fields must be null"
            )
        if repaired or not_repaired:
            raise IndependentVerificationError(
                "original correction property lists must be empty"
            )
        return
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
        raise IndependentVerificationError(
            "summary correction reason_code is unsupported"
        )
    _require_nonempty_string(correction["reason"], "summary.correction.reason")
    if not repaired:
        raise IndependentVerificationError(
            "corrected derivative must name a repaired property"
        )
    if repaired != [CORRECTION_REASON_PROPERTIES[reason_code]]:
        raise IndependentVerificationError(
            "summary correction reason_code and repaired property differ"
        )


def _validate_summary(value: Any, *, expected_bundle_id: str) -> Mapping[str, Any]:
    summary = _require_exact_keys(value, SUMMARY_FIELDS, "summary")
    if summary["schema_version"] != SUMMARY_SCHEMA_VERSION:
        raise IndependentVerificationError("summary schema_version differs")
    if _validate_bundle_id(summary["evidence_bundle_id"]) != expected_bundle_id:
        raise IndependentVerificationError("summary evidence_bundle_id differs")
    _require_nonempty_string(summary["run_id"], "summary.run_id")
    _require_nonempty_string(summary["protocol_version"], "summary.protocol_version")
    _require_nonempty_string(summary["metric_version"], "summary.metric_version")
    if summary["execution_mode"] not in EXECUTION_MODES:
        raise IndependentVerificationError("summary.execution_mode is invalid")

    # Generic publisher v1 validates only publication structure.  It may not
    # promote unverified run content into an operational outcome.
    if summary["operational_backend_result"] != "NOT_EVALUATED":
        raise IndependentVerificationError(
            "summary operational result must be NOT_EVALUATED for structure-only v1"
        )
    if summary["evidence_publication_conformance"] != "CONFORMING":
        raise IndependentVerificationError(
            "summary publication conformance must be CONFORMING"
        )
    if summary["gate4_formal_pass"] is not False:
        raise IndependentVerificationError("summary.gate4_formal_pass must be false")
    if summary["research_eligible"] is not False:
        raise IndependentVerificationError("summary.research_eligible must be false")
    backend = _require_exact_keys(
        summary["backend_freeze"], {"status"}, "summary.backend_freeze"
    )
    if backend["status"] != "not_frozen":
        raise IndependentVerificationError(
            "summary backend freeze must be not_frozen"
        )
    claim_scope = _require_sorted_unique_strings(
        summary["claim_scope"], "summary.claim_scope", nonempty=True
    )
    warnings = _require_sorted_unique_strings(summary["warnings"], "summary.warnings")
    unverified = _require_sorted_unique_strings(
        summary["unverified_claims"], "summary.unverified_claims"
    )
    if claim_scope != STRUCTURE_ONLY_CLAIM_SCOPE:
        raise IndependentVerificationError(
            "summary claim_scope must be publication_structure_only for v1"
        )
    if warnings:
        raise IndependentVerificationError(
            "summary warnings must be empty for structure-only NOT_EVALUATED v1"
        )
    if unverified != STRUCTURE_ONLY_UNVERIFIED_CLAIMS:
        raise IndependentVerificationError(
            "summary unverified_claims differs from the structure-only v1 set"
        )
    _validate_correction(summary["correction"])
    if (
        summary["correction"]["kind"] == "derived_correction"
        and summary["correction"]["supersedes"]["evidence_bundle_id"]
        == expected_bundle_id
    ):
        raise IndependentVerificationError(
            "corrected derivative must use a distinct evidence bundle ID"
        )

    authorization = _require_exact_keys(
        summary["authorization"], {"path", "sha256"}, "summary.authorization"
    )
    if authorization["path"] != APPROVAL_FILENAME:
        raise IndependentVerificationError("summary authorization path differs")
    _require_sha256(authorization["sha256"], "summary.authorization.sha256")

    capture = _require_exact_keys(
        summary["source_capture"],
        {"manifest_path", "manifest_sha256"},
        "summary.source_capture",
    )
    if capture["manifest_path"] != CAPTURE_MANIFEST_FILENAME:
        raise IndependentVerificationError("summary capture manifest path differs")
    _require_sha256(
        capture["manifest_sha256"], "summary.source_capture.manifest_sha256"
    )

    publisher = _require_exact_keys(
        summary["publisher"], {"path", "sha256", "version"}, "summary.publisher"
    )
    if publisher["path"] != PUBLISHER_SNAPSHOT_PATH:
        raise IndependentVerificationError("summary publisher path differs")
    if publisher["version"] != PUBLISHER_VERSION:
        raise IndependentVerificationError("summary publisher version differs")
    _require_sha256(publisher["sha256"], "summary.publisher.sha256")

    contract = _require_exact_keys(
        summary["publication_contract"],
        {"path", "sha256", "version"},
        "summary.publication_contract",
    )
    if contract["path"] != CONTRACT_SNAPSHOT_PATH:
        raise IndependentVerificationError("summary contract path differs")
    if contract["version"] != PUBLICATION_SPEC_VERSION:
        raise IndependentVerificationError("summary contract version differs")
    _require_sha256(contract["sha256"], "summary.publication_contract.sha256")
    return summary


def _resolve_bundle_directory(path: Path | str, context: str) -> Path:
    # Keep the lexical final component intact.  Calling resolve() here would
    # follow a symlink installed after lstat but before the descriptor-relative
    # snapshot's O_NOFOLLOW root open.
    candidate = Path(path).absolute()
    try:
        metadata = os.lstat(candidate)
    except OSError as error:
        raise IndependentVerificationError(f"{context} cannot be inspected") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise IndependentVerificationError(f"{context} is a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise IndependentVerificationError(f"{context} is not a directory")
    return candidate


def _require_same_tree_snapshot(
    expected: TreeSnapshot,
    observed: TreeSnapshot,
    context: str,
) -> None:
    if (
        observed.records != expected.records
        or observed.contract_bytes != expected.contract_bytes
        or observed.root_identity != expected.root_identity
    ):
        raise IndependentVerificationError(f"{context} changed during verification")


def _verify_or_raise(
    root: Path, *, predecessor_path: Optional[Path | str]
) -> VerifiedCommitments:
    snapshot = _snapshot_tree(root)
    for required in CONTRACT_DATA_PATHS | {
        PUBLISHER_SNAPSHOT_PATH,
        CONTRACT_SNAPSHOT_PATH,
    }:
        if required not in snapshot.records:
            raise IndependentVerificationError(f"required bundle file is missing: {required}")

    inventory_bytes = snapshot.contract_bytes[INVENTORY_FILENAME]
    inventory = _parse_inventory(inventory_bytes)
    actual_paths = set(snapshot.records) - {INVENTORY_FILENAME}
    if set(inventory) != actual_paths:
        missing = sorted(actual_paths - set(inventory))
        extra = sorted(set(inventory) - actual_paths)
        raise IndependentVerificationError(
            f"inventory path set differs; missing={missing}, extra={extra}"
        )
    for relative, expected_digest in inventory.items():
        if snapshot.records[relative].sha256 != expected_digest:
            raise IndependentVerificationError(f"inventory hash differs: {relative}")

    summary_bytes = snapshot.contract_bytes[SUMMARY_FILENAME]
    summary = _decode_canonical_json(summary_bytes, SUMMARY_FILENAME)
    summary = _validate_summary(summary, expected_bundle_id=root.name)
    bundle_id = summary["evidence_bundle_id"]
    if root.name.startswith(".") or root.name != bundle_id:
        raise IndependentVerificationError(
            "directory basename is not the published evidence_bundle_id"
        )

    approval_bytes = snapshot.contract_bytes[APPROVAL_FILENAME]
    approval = _decode_canonical_json(approval_bytes, APPROVAL_FILENAME)
    _validate_approval(approval, bundle_id=bundle_id, bundle_path=root)
    approval_sha = _sha256(approval_bytes)
    if summary["authorization"]["sha256"] != approval_sha:
        raise IndependentVerificationError("summary approval hash differs")

    capture_bytes = snapshot.contract_bytes[CAPTURE_MANIFEST_FILENAME]
    capture = _decode_canonical_json(capture_bytes, CAPTURE_MANIFEST_FILENAME)
    capture_files = _validate_capture_manifest(capture)
    capture_sha = _sha256(capture_bytes)
    if summary["source_capture"]["manifest_sha256"] != capture_sha:
        raise IndependentVerificationError("summary capture manifest hash differs")

    captured_actual = {
        relative: record.as_dict()
        for relative, record in snapshot.records.items()
        if PurePosixPath(relative).parts[0] not in PUBLISHER_OWNED_TOP_LEVEL
    }
    if captured_actual != capture_files:
        raise IndependentVerificationError(
            "capture manifest path/hash/size/line set differs from captured files"
        )

    publisher_sha = snapshot.records[PUBLISHER_SNAPSHOT_PATH].sha256
    contract_sha = snapshot.records[CONTRACT_SNAPSHOT_PATH].sha256
    if summary["publisher"]["sha256"] != publisher_sha:
        raise IndependentVerificationError("summary publisher snapshot hash differs")
    if summary["publication_contract"]["sha256"] != contract_sha:
        raise IndependentVerificationError("summary contract snapshot hash differs")
    if contract_sha != EXPECTED_PUBLICATION_SPEC_SHA256:
        raise IndependentVerificationError(
            "publication contract snapshot is not the guarded v1 contract"
        )

    # A second complete read prevents later field parsing from being combined
    # with a different tree state.  No bytes are written by either pass.
    second_snapshot = _snapshot_tree(root)
    _require_same_tree_snapshot(snapshot, second_snapshot, "evidence tree")

    summary_sha = _sha256(summary_bytes)
    inventory_sha = _sha256(inventory_bytes)
    commitments = VerifiedCommitments(
        evidence_bundle_id=bundle_id,
        operational_backend_result=summary["operational_backend_result"],
        summary_sha256=summary_sha,
        inventory_sha256=inventory_sha,
        bundle_root_sha256=_bundle_root_hash(inventory_sha),
        inventory_entries=len(inventory),
        correction_kind=summary["correction"]["kind"],
        capture_files=capture_files,
        directory_identity=snapshot.root_identity,
    )

    correction = summary["correction"]
    if correction["kind"] == "original":
        if predecessor_path is not None:
            raise IndependentVerificationError(
                "original bundle may not name a predecessor"
            )
        return commitments

    if predecessor_path is None:
        raise IndependentVerificationError(
            "derived correction requires a predecessor path"
        )
    predecessor_root = _resolve_bundle_directory(
        predecessor_path, "predecessor bundle path"
    )
    predecessor = _verify_or_raise(predecessor_root, predecessor_path=None)
    if predecessor.correction_kind != "original":
        raise IndependentVerificationError(
            "derived correction predecessor must be a conforming original"
        )
    supersedes = correction["supersedes"]
    expected_predecessor = {
        "evidence_bundle_id": predecessor.evidence_bundle_id,
        "summary_sha256": predecessor.summary_sha256,
        "inventory_sha256": predecessor.inventory_sha256,
        "bundle_root_sha256": predecessor.bundle_root_sha256,
    }
    for field, observed in expected_predecessor.items():
        if supersedes[field] != observed:
            raise IndependentVerificationError(f"predecessor {field} differs")
    if predecessor.evidence_bundle_id == bundle_id:
        raise IndependentVerificationError(
            "corrected derivative must use a distinct evidence bundle ID"
        )
    predecessor_raw = {
        relative: record
        for relative, record in predecessor.capture_files.items()
        if relative != APPROVAL_FILENAME
    }
    current_raw = {
        relative: record
        for relative, record in capture_files.items()
        if relative != APPROVAL_FILENAME
    }
    if current_raw != predecessor_raw:
        raise IndependentVerificationError(
            "corrected derivative changed captured raw artifacts"
        )
    current_after_predecessor = _snapshot_tree(root)
    _require_same_tree_snapshot(
        snapshot,
        current_after_predecessor,
        "current evidence tree after predecessor verification",
    )
    return commitments


def _expected_commitment_errors(
    commitments: VerifiedCommitments,
    *,
    expected_summary_sha256: Optional[str],
    expected_inventory_sha256: Optional[str],
    expected_bundle_root_sha256: Optional[str],
    expected_final_identity: Optional[Mapping[str, Any]],
) -> list[str]:
    pairs = (
        ("S", expected_summary_sha256, commitments.summary_sha256),
        ("I", expected_inventory_sha256, commitments.inventory_sha256),
        ("R", expected_bundle_root_sha256, commitments.bundle_root_sha256),
    )
    errors: list[str] = []
    for label, expected, actual in pairs:
        if expected is None:
            continue
        if SHA256_RE.fullmatch(expected) is None:
            errors.append(f"expected {label} is not a lowercase SHA-256")
        elif expected != actual:
            errors.append(f"expected {label} commitment differs")
    if expected_final_identity is not None:
        try:
            expected_identity = DirectoryIdentity.from_value(
                expected_final_identity,
                "expected final directory identity",
            )
        except IndependentVerificationError as error:
            errors.append(str(error))
        else:
            if expected_identity != commitments.directory_identity:
                errors.append("expected final directory identity differs")
    return errors


def verify_bundle(
    path: Path | str,
    *,
    expected_summary_sha256: Optional[str] = None,
    expected_inventory_sha256: Optional[str] = None,
    expected_bundle_root_sha256: Optional[str] = None,
    expected_final_identity: Optional[Mapping[str, Any]] = None,
    predecessor_path: Optional[Path | str] = None,
) -> IndependentVerificationReport:
    """Verify a published bundle without importing or invoking its publisher."""
    requested = Path(path)
    absolute = requested.absolute()
    try:
        root = _resolve_bundle_directory(requested, "published evidence path")
        commitments = _verify_or_raise(root, predecessor_path=predecessor_path)
    except Exception as error:
        return IndependentVerificationReport(
            path=absolute,
            publication_conforming=False,
            commitments_match=False,
            valid=False,
            evidence_bundle_id=None,
            operational_backend_result=None,
            summary_sha256=None,
            inventory_sha256=None,
            bundle_root_sha256=None,
            inventory_entries=0,
            formal_gate4_pass=False,
            research_eligible=False,
            backend_freeze_status=None,
            directory_identity=None,
            errors=(f"{type(error).__name__}: {error}",),
        )

    mismatch_errors = _expected_commitment_errors(
        commitments,
        expected_summary_sha256=expected_summary_sha256,
        expected_inventory_sha256=expected_inventory_sha256,
        expected_bundle_root_sha256=expected_bundle_root_sha256,
        expected_final_identity=expected_final_identity,
    )
    commitments_match = not mismatch_errors
    return IndependentVerificationReport(
        path=root,
        publication_conforming=True,
        commitments_match=commitments_match,
        valid=commitments_match,
        evidence_bundle_id=commitments.evidence_bundle_id,
        operational_backend_result=commitments.operational_backend_result,
        summary_sha256=commitments.summary_sha256,
        inventory_sha256=commitments.inventory_sha256,
        bundle_root_sha256=commitments.bundle_root_sha256,
        inventory_entries=commitments.inventory_entries,
        formal_gate4_pass=False,
        research_eligible=False,
        backend_freeze_status="not_frozen",
        directory_identity=commitments.directory_identity,
        errors=tuple(mismatch_errors),
    )


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independently verify a published Gate 4 evidence bundle"
    )
    parser.add_argument("bundle", type=Path)
    parser.add_argument(
        "--expected-summary-sha256",
        "--expected-s",
        dest="expected_summary_sha256",
    )
    parser.add_argument(
        "--expected-inventory-sha256",
        "--expected-i",
        dest="expected_inventory_sha256",
    )
    parser.add_argument(
        "--expected-bundle-root-sha256",
        "--expected-r",
        dest="expected_bundle_root_sha256",
    )
    parser.add_argument(
        "--predecessor",
        dest="predecessor_path",
        type=Path,
        help="required predecessor bundle for a derived correction",
    )
    parser.add_argument("--expected-final-device", type=int)
    parser.add_argument("--expected-final-inode", type=int)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = _build_argument_parser().parse_args(argv)
    expected_identity = None
    if (
        arguments.expected_final_device is not None
        or arguments.expected_final_inode is not None
    ):
        expected_identity = {
            "device": arguments.expected_final_device,
            "inode": arguments.expected_final_inode,
        }
    report = verify_bundle(
        arguments.bundle,
        expected_summary_sha256=arguments.expected_summary_sha256,
        expected_inventory_sha256=arguments.expected_inventory_sha256,
        expected_bundle_root_sha256=arguments.expected_bundle_root_sha256,
        expected_final_identity=expected_identity,
        predecessor_path=arguments.predecessor_path,
    )
    sys.stdout.write(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
