"""Fail-closed Gate 3 smoke and research eligibility validator."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.provenance import (
    canonical_json_bytes,
    compute_config_hash,
    file_manifest,
    sanitize_config,
)
from tools.eight_cell_core import (
    BATCH_MANIFEST_VERSION,
    CANONICAL_BLOCS,
    CELL_DEFINITIONS,
    HEX64_RE,
    MATRIX_SPEC_VERSION,
    MODEL_PROFILE_FIELDS,
    PLANNED_ROW_FIELDS,
    PLAN_MANIFEST_VERSION,
    PlanValidationError,
    expected_model_slots,
    initial_state_input_hash,
    load_json_unique,
    paired_control_hash,
    planned_rows_bytes,
    read_jsonl_objects,
    sha256_file,
    validate_plan_data,
)
from tools.validate_run import validate_run


class InvocationError(ValueError):
    """CLI usage is invalid rather than research evidence being invalid."""


class ResearchArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InvocationError(message)


MANIFEST_ROW_FIELDS = frozenset({
    "ordinal",
    "run_id",
    "cell_id",
    "replicate_id",
    "status",
    "config_path",
    "config_sha256",
    "run_directory",
    "run_meta_manifest",
    "raw_manifest",
    "strict_valid",
    "strict_errors",
    "strict_unverifiable",
    "smoke_valid",
    "smoke_errors",
    "smoke_unverified_research_requirements",
    "research_eligible",
})


@dataclass
class ValidationResult:
    target: str
    profile: str
    errors: List[str] = field(default_factory=list)
    unverified_research_requirements: List[str] = field(default_factory=list)
    strict_unverifiable: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 3
        if self.profile == "research" and self.unverified_research_requirements:
            return 2
        return 0

    @property
    def classification(self) -> str:
        return {0: "PASS", 2: "UNVERIFIABLE", 3: "FAIL"}[self.exit_code]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification,
            "exit_code": self.exit_code,
            "target": self.target,
            "profile": self.profile,
            "smoke_valid": not self.errors,
            "research_eligible": (
                self.profile == "research"
                and not self.errors
                and not self.unverified_research_requirements
            ),
            "errors": self.errors,
            "unverified_research_requirements": (
                self.unverified_research_requirements
            ),
            "strict_unverifiable": self.strict_unverifiable,
            "details": self.details,
        }


def _error(result: ValidationResult, message: str) -> None:
    if message not in result.errors:
        result.errors.append(message)


def _unverified(result: ValidationResult, message: str) -> None:
    if message not in result.unverified_research_requirements:
        result.unverified_research_requirements.append(message)


def _read_object(path: Path, result: ValidationResult) -> Optional[Dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        _error(result, f"missing or non-regular file: {path.name}")
        return None
    try:
        return load_json_unique(path)
    except (OSError, PlanValidationError) as error:
        _error(result, f"invalid {path.name}: {error}")
        return None


def _manifest_equal(path: Path, expected: Any) -> bool:
    try:
        return file_manifest(path) == expected
    except OSError:
        return False


def _validate_plan_manifest(
    batch_dir: Path,
    plan: Dict[str, Any],
    meta: Dict[str, Any],
    manifest: Dict[str, Any],
    result: ValidationResult,
) -> None:
    expected_fields = {
        "schema_version",
        "matrix_spec_version",
        "matrix_spec_sha256",
        "matrix_id",
        "source_plan_sha256",
        "base_config_sha256",
        "prompt_sha256",
        "files",
    }
    if set(manifest) != expected_fields:
        _error(result, "plan_manifest.json fields are not canonical")
    if manifest.get("schema_version") != PLAN_MANIFEST_VERSION:
        _error(result, "plan manifest schema version mismatch")
    comparisons = {
        "matrix_spec_version": MATRIX_SPEC_VERSION,
        "matrix_spec_sha256": meta.get("matrix_spec_sha256"),
        "matrix_id": plan.get("matrix_id"),
        "source_plan_sha256": meta.get("plan_sha256"),
        "base_config_sha256": plan.get("base_config", {}).get("sha256"),
        "prompt_sha256": meta.get("prompt_sha256"),
    }
    for key, expected in comparisons.items():
        if manifest.get(key) != expected:
            _error(result, f"plan manifest {key} mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict):
        _error(result, "plan manifest files must be an object")
        return
    for relative, expected in files.items():
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            _error(result, "plan manifest contains an unsafe path")
            continue
        if not _manifest_equal(batch_dir / relative, expected):
            _error(result, f"plan manifest file mismatch: {relative}")


def _validate_row_and_config(
    row: Dict[str, Any],
    config: Dict[str, Any],
    plan: Dict[str, Any],
    prompt_sha256: Any,
    expected_replicate_index: int,
    expected_cell_index: int,
    result: ValidationResult,
) -> None:
    cell_id, condition, edge_policy = CELL_DEFINITIONS[expected_cell_index]
    replicate = plan["replicates"][expected_replicate_index]
    expected_run_id = (
        f"{plan['matrix_id']}-{replicate['replicate_id']}-{cell_id}"
    )
    expected_values = {
        "ordinal": expected_replicate_index * len(CELL_DEFINITIONS)
        + expected_cell_index,
        "matrix_id": plan["matrix_id"],
        "replicate_id": replicate["replicate_id"],
        "replicate_index": expected_replicate_index,
        "world_seed": replicate["world_seed"],
        "cell_index": expected_cell_index,
        "cell_id": cell_id,
        "model_condition": condition,
        "edge_policy": edge_policy,
        "rotation_index": expected_replicate_index % 3,
        "execution_mode": "scripted_smoke",
        "research_eligible": False,
        "run_id": expected_run_id,
        "config_path": f"configs/{expected_run_id}.json",
        "prompt_sha256": prompt_sha256,
        "model_slots_by_bloc": expected_model_slots(
            condition, expected_replicate_index
        ),
    }
    for key, expected in expected_values.items():
        if row.get(key) != expected:
            _error(result, f"planned row {expected_run_id} has invalid {key}")

    if row.get("config_sha256") != compute_config_hash(config):
        _error(result, f"planned config hash mismatch for {expected_run_id}")
    try:
        paired = paired_control_hash(config, prompt_sha256)
        initial = initial_state_input_hash(config)
    except (KeyError, TypeError, ValueError) as error:
        _error(result, f"cannot hash generated config {expected_run_id}: {error}")
        return
    if row.get("paired_control_hash") != paired:
        _error(result, f"paired control hash mismatch for {expected_run_id}")
    if row.get("initial_state_input_hash") != initial:
        _error(result, f"initial-state input hash mismatch for {expected_run_id}")

    simulation = config.get("simulation")
    agents = config.get("agents")
    blocs = config.get("blocs")
    if not isinstance(simulation, dict) or not isinstance(agents, dict):
        _error(result, f"generated config sections invalid for {expected_run_id}")
        return
    config_expected = {
        "matrix_id": plan["matrix_id"],
        "cell_id": cell_id,
        "model_condition": condition,
        "replicate_id": replicate["replicate_id"],
        "replicate_index": expected_replicate_index,
        "rotation_index": expected_replicate_index % 3,
        "execution_mode": "scripted_smoke",
        "research_eligible": False,
        "run_id": expected_run_id,
        "run_name": expected_run_id,
        "seed": replicate["world_seed"],
        "protocol_version": plan["protocol_version"],
        "metric_version": plan["metric_version"],
    }
    for key, expected in config_expected.items():
        if simulation.get(key) != expected:
            _error(result, f"config {expected_run_id} has invalid simulation.{key}")
    if agents.get("edge_policy") != edge_policy:
        _error(result, f"config {expected_run_id} has invalid edge policy")
    if not isinstance(blocs, list) or [
        (bloc.get("name"), bloc.get("num_agents"))
        for bloc in blocs
        if isinstance(bloc, dict)
    ] != [(name, 4) for name in CANONICAL_BLOCS]:
        _error(result, f"config {expected_run_id} has invalid bloc structure")
        return
    slots = expected_model_slots(condition, expected_replicate_index)
    for bloc in blocs:
        slot = slots[bloc["name"]]
        profile = plan["model_catalog"][slot]
        for field in MODEL_PROFILE_FIELDS:
            expected = profile.get(field)
            actual = bloc.get(field)
            if actual != expected:
                _error(
                    result,
                    f"config {expected_run_id} model assignment mismatch: "
                    f"{bloc['name']}.{field}",
                )


def _research_requirements(
    meta: Dict[str, Any],
    configs: List[Dict[str, Any]],
    run_metas: List[Dict[str, Any]],
    complete: bool,
    result: ValidationResult,
) -> None:
    if meta.get("source_git_probe_status") != "available":
        _unverified(result, "source git probe is not available")
    if meta.get("source_git_dirty") is not False:
        _unverified(result, "source worktree is not recorded clean")
    source_sha = meta.get("source_git_sha")
    if not isinstance(source_sha, str) or not source_sha:
        _unverified(result, "exact source SHA is unavailable")
    if any(run_meta.get("git_sha") != source_sha for run_meta in run_metas):
        _error(result, "run source SHA contradicts the batch source SHA")
    if any(
        run_meta.get("git_dirty") != meta.get("source_git_dirty")
        for run_meta in run_metas
    ):
        _error(result, "run source cleanliness contradicts batch provenance")
    if any(
        run_meta.get("git_probe_status") != meta.get("source_git_probe_status")
        for run_meta in run_metas
    ):
        _error(result, "run git probe status contradicts batch provenance")
    if meta.get("execution_mode") == "scripted_smoke":
        _unverified(result, "execution mode is scripted_smoke")
    backend = meta.get("backend_freeze")
    if not isinstance(backend, dict) or backend.get("status") != "frozen":
        _unverified(result, "backend artifacts are not frozen")
    elif not isinstance(backend.get("evidence_id"), str) or not backend[
        "evidence_id"
    ].strip():
        _error(result, "frozen backend has no evidence ID")
    registry = meta.get("candidate_registry")
    if not isinstance(registry, dict) or registry.get("status") != "frozen":
        _unverified(result, "production candidate registry is not frozen")
    elif (
        not isinstance(registry.get("sha256"), str)
        or HEX64_RE.fullmatch(registry["sha256"]) is None
    ):
        _error(result, "frozen registry has no valid SHA-256")
    for config in configs:
        for bloc in config.get("blocs", []):
            label = f"model artifact for bloc {bloc.get('name')}"
            for field in ("model_digest", "quantization", "chat_template"):
                if not isinstance(bloc.get(field), str) or not bloc[field]:
                    _unverified(result, f"{label} lacks {field}")
    for run_meta in run_metas:
        for model in run_meta.get("models", []):
            label = f"recorded model artifact for bloc {model.get('bloc')}"
            for field in ("model_digest", "quantization", "chat_template_hash"):
                if not isinstance(model.get(field), str) or not model[field]:
                    _unverified(result, f"{label} lacks {field}")
    if meta.get("protocol_frozen") is not True:
        _unverified(result, "protocol version is not frozen")
    if meta.get("matrix_plan_frozen") is not True:
        _unverified(result, "matrix plan is not frozen")
    if not complete:
        _unverified(result, "batch is not complete")
    approval = meta.get("run_start_approval_reference")
    if not isinstance(approval, str) or not approval.strip():
        _unverified(result, "run-start approval reference is absent")


def _validate_run_common(
    run_dir: Path,
    batch_meta: Dict[str, Any],
    plan: Dict[str, Any],
    row: Dict[str, Any],
    config: Dict[str, Any],
    result: ValidationResult,
) -> Optional[Dict[str, Any]]:
    before = {
        path.name: file_manifest(path)
        for path in run_dir.iterdir()
        if path.is_file() and not path.is_symlink()
    } if run_dir.is_dir() else {}
    strict = validate_run(run_dir, strict=True)
    result.strict_unverifiable.extend(strict.unverifiable)
    if not strict.valid:
        for message in strict.errors:
            _error(result, f"strict run validation: {message}")
    after = {
        path.name: file_manifest(path)
        for path in run_dir.iterdir()
        if path.is_file() and not path.is_symlink()
    } if run_dir.is_dir() else {}
    if before != after:
        _error(result, "run validation mutated run artifacts")
    run_meta = _read_object(run_dir / "run_meta.json", result)
    if run_meta is None:
        return None
    run_id = row.get("run_id")
    expected = {
        "run_id": run_id,
        "status": "completed",
        "aborted": False,
        "protocol_version": plan.get("protocol_version"),
        "metric_version": "metric-v2.0.0",
        "prompt_hash": batch_meta.get("prompt_sha256"),
        "seed": row.get("world_seed"),
    }
    for key, expected_value in expected.items():
        if run_meta.get(key) != expected_value:
            _error(result, f"run {run_id} has invalid {key}")
    if run_dir.name != f"output_{run_id}":
        _error(result, f"run directory name disagrees with run ID {run_id}")
    if run_meta.get("raw_manifest_status") != "available":
        _error(result, f"run {run_id} raw manifest is not available")
    if run_meta.get("completed_steps") != run_meta.get("expected_steps"):
        _error(result, f"run {run_id} has incomplete steps")
    if run_meta.get("observed_agents") != run_meta.get("expected_agents"):
        _error(result, f"run {run_id} has incomplete agent coverage")
    sanitized = sanitize_config(copy.deepcopy(config))
    if run_meta.get("config") != sanitized:
        _error(result, f"run {run_id} config snapshot mismatch")
    if run_meta.get("config_hash") != compute_config_hash(sanitized):
        _error(result, f"run {run_id} config hash mismatch")
    simulation = config.get("simulation", {})
    for key in (
        "matrix_id",
        "cell_id",
        "model_condition",
        "replicate_id",
        "replicate_index",
        "rotation_index",
        "execution_mode",
        "run_id",
        "seed",
        "protocol_version",
        "metric_version",
    ):
        if run_meta.get("config", {}).get("simulation", {}).get(key) != simulation.get(key):
            _error(result, f"run {run_id} saved simulation.{key} mismatch")
    if run_meta.get("git_sha") != batch_meta.get("source_git_sha"):
        _error(result, f"run {run_id} source SHA differs from batch")
    if not isinstance(run_meta.get("git_sha"), str) or not run_meta["git_sha"]:
        _error(result, f"run {run_id} has no source SHA")
    return run_meta


def _check_scripted_smoke_communication(
    run_dir: Path,
    row: Dict[str, Any],
    config: Dict[str, Any],
    result: ValidationResult,
) -> None:
    if row.get("execution_mode") != "scripted_smoke":
        return
    try:
        records = read_jsonl_objects(run_dir / "messages.jsonl")
    except (OSError, PlanValidationError) as error:
        _error(result, f"cannot inspect scripted smoke messages: {error}")
        return
    labels: Dict[int, Any] = {}
    agent_id = 0
    for bloc in config.get("blocs", []):
        if (
            not isinstance(bloc, dict)
            or not isinstance(bloc.get("num_agents"), int)
            or isinstance(bloc.get("num_agents"), bool)
        ):
            _error(result, "cannot derive scripted smoke bloc labels")
            return
        for _ in range(bloc["num_agents"]):
            labels[agent_id] = bloc.get("name")
            agent_id += 1
    same_bloc = 0
    cross_bloc = 0
    for record in records:
        receivers = record.get("receiver_ids")
        sender = record.get("sender_id")
        if not isinstance(receivers, list):
            continue
        if receivers != sorted(receivers):
            _error(result, "scripted smoke receiver IDs are not canonical")
        for receiver in receivers:
            if labels.get(sender) == labels.get(receiver):
                same_bloc += 1
            else:
                cross_bloc += 1
    policy = row.get("edge_policy")
    if policy == "full" and cross_bloc == 0:
        _error(result, "scripted full cell has no cross-bloc delivery")
    if policy == "within_bloc_only":
        if cross_bloc:
            _error(result, "scripted within-bloc cell has cross-bloc delivery")
        if not records or same_bloc == 0:
            _error(result, "scripted within-bloc cell has no same-bloc delivery")


def validate_run_profile(
    run_dir: Path | str,
    batch_dir: Path | str,
    row: Dict[str, Any],
    profile: str,
) -> ValidationResult:
    if profile not in {"smoke", "research"}:
        raise InvocationError("profile must be smoke or research")
    run_path = Path(run_dir).resolve()
    batch_path = Path(batch_dir).resolve()
    result = ValidationResult(str(run_path), profile)
    meta = _read_object(batch_path / "batch_meta.json", result)
    plan = _read_object(batch_path / "plan.json", result)
    config_path = batch_path / str(row.get("config_path", ""))
    config = _read_object(config_path, result)
    if meta is None or plan is None or config is None:
        return result
    try:
        validate_plan_data(plan)
        replicate_index = row.get("replicate_index")
        cell_index = row.get("cell_index")
        if (
            not isinstance(replicate_index, int)
            or isinstance(replicate_index, bool)
            or not isinstance(cell_index, int)
            or isinstance(cell_index, bool)
        ):
            raise PlanValidationError("planned row indices are invalid")
        _validate_row_and_config(
            row,
            config,
            plan,
            meta.get("prompt_sha256"),
            replicate_index,
            cell_index,
            result,
        )
    except (IndexError, PlanValidationError) as error:
        _error(result, f"run planning evidence is invalid: {error}")
    run_meta = _validate_run_common(
        run_path, meta, plan, row, config, result
    )
    _check_scripted_smoke_communication(run_path, row, config, result)
    complete = run_meta is not None and run_meta.get("status") == "completed"
    _research_requirements(
        meta,
        [config],
        [run_meta] if run_meta is not None else [],
        complete,
        result,
    )
    result.details.update({
        "run_id": row.get("run_id"),
        "edge_policy": row.get("edge_policy"),
        "execution_mode": row.get("execution_mode"),
    })
    return result


def validate_batch_profile(
    batch_dir: Path | str,
    profile: str,
) -> ValidationResult:
    if profile not in {"smoke", "research"}:
        raise InvocationError("profile must be smoke or research")
    batch_path = Path(batch_dir).resolve()
    result = ValidationResult(str(batch_path), profile)
    if not batch_path.is_dir() or batch_path.is_symlink():
        _error(result, "batch directory is missing or is a symlink")
        return result
    meta = _read_object(batch_path / "batch_meta.json", result)
    plan = _read_object(batch_path / "plan.json", result)
    plan_manifest = _read_object(batch_path / "plan_manifest.json", result)
    batch_manifest = _read_object(batch_path / "batch_manifest.json", result)
    try:
        rows = read_jsonl_objects(batch_path / "planned_runs.jsonl")
    except (OSError, PlanValidationError) as error:
        _error(result, f"invalid planned_runs.jsonl: {error}")
        rows = []
    if any(value is None for value in (meta, plan, plan_manifest, batch_manifest)):
        return result
    assert meta is not None and plan is not None
    assert plan_manifest is not None and batch_manifest is not None
    try:
        validate_plan_data(plan)
    except PlanValidationError as error:
        _error(result, f"copied plan is invalid: {error}")
    if meta.get("matrix_id") != plan.get("matrix_id"):
        _error(result, "batch matrix ID differs from plan")
    for key in ("protocol_version", "metric_version"):
        if meta.get(key) != plan.get(key):
            _error(result, f"batch {key} differs from plan")
    for key in ("candidate_registry", "backend_freeze"):
        if meta.get(key) != plan.get(key):
            _error(result, f"batch {key} differs from plan")
    if batch_path.name != f"batch_{plan.get('matrix_id')}":
        _error(result, "batch directory name differs from matrix ID")
    if meta.get("matrix_spec_version") != MATRIX_SPEC_VERSION:
        _error(result, "batch matrix spec version mismatch")
    spec_path = Path(__file__).resolve().parents[1] / "docs" / "EIGHT_CELL_MATRIX_SPEC.md"
    if meta.get("matrix_spec_sha256") != sha256_file(spec_path):
        _error(result, "batch matrix spec hash differs from the current specification")
    if meta.get("base_config_sha256") != plan.get("base_config", {}).get("sha256"):
        _error(result, "batch base config hash mismatch")
    _validate_plan_manifest(batch_path, plan, meta, plan_manifest, result)
    if meta.get("plan_manifest_sha256") != sha256_file(
        batch_path / "plan_manifest.json"
    ):
        _error(result, "plan manifest file hash mismatch")

    expected_count = len(plan.get("replicates", [])) * len(CELL_DEFINITIONS)
    if len(rows) != expected_count:
        _error(result, f"planned row count mismatch: expected {expected_count}")
    seen_run_ids = set()
    seen_cells = set()
    configs: List[Dict[str, Any]] = []
    config_by_run: Dict[str, Dict[str, Any]] = {}
    for ordinal, row in enumerate(rows):
        if set(row) != PLANNED_ROW_FIELDS:
            _error(result, f"planned row {ordinal} fields are not canonical")
        replicate_index, cell_index = divmod(ordinal, len(CELL_DEFINITIONS))
        if replicate_index >= len(plan.get("replicates", [])):
            _error(result, "planned rows exceed plan replicates")
            break
        config_path = batch_path / str(row.get("config_path", ""))
        config = _read_object(config_path, result)
        if config is None:
            continue
        _validate_row_and_config(
            row,
            config,
            plan,
            meta.get("prompt_sha256"),
            replicate_index,
            cell_index,
            result,
        )
        run_id = row.get("run_id")
        cell_key = (row.get("replicate_id"), row.get("cell_id"))
        if run_id in seen_run_ids:
            _error(result, f"duplicate planned run ID: {run_id}")
        if cell_key in seen_cells:
            _error(result, f"duplicate planned cell: {cell_key!r}")
        seen_run_ids.add(run_id)
        seen_cells.add(cell_key)
        if isinstance(run_id, str):
            config_by_run[run_id] = config
        configs.append(config)
        if config_path.read_bytes() != canonical_json_bytes(config) + b"\n":
            _error(result, f"generated config is not canonical: {run_id}")
    if (batch_path / "plan.json").read_bytes() != canonical_json_bytes(plan) + b"\n":
        _error(result, "plan.json is not canonical")
    if (batch_path / "planned_runs.jsonl").read_bytes() != planned_rows_bytes(rows):
        _error(result, "planned_runs.jsonl is not canonical")
    expected_static_files = {"plan.json", "planned_runs.jsonl"} | {
        str(row.get("config_path")) for row in rows
    }
    if set(plan_manifest.get("files", {})) != expected_static_files:
        _error(result, "plan manifest static file set mismatch")
    config_dir = batch_path / "configs"
    actual_config_files = {
        path.relative_to(batch_path).as_posix()
        for path in config_dir.iterdir()
        if path.is_file() and not path.is_symlink()
    } if config_dir.is_dir() else set()
    if actual_config_files != expected_static_files - {"plan.json", "planned_runs.jsonl"}:
        _error(result, "generated config file set mismatch")
    for replicate in plan.get("replicates", []):
        grouped = [
            row for row in rows
            if row.get("replicate_id") == replicate.get("replicate_id")
        ]
        if len(grouped) != len(CELL_DEFINITIONS):
            _error(result, f"replicate {replicate.get('replicate_id')} lacks eight cells")
        if len({row.get("world_seed") for row in grouped}) != 1:
            _error(result, "paired world seeds differ")
        if len({row.get("paired_control_hash") for row in grouped}) != 1:
            _error(result, "paired control hashes differ")
        if len({row.get("initial_state_input_hash") for row in grouped}) != 1:
            _error(result, "initial-state input hashes differ")

    expected_batch_manifest_fields = {
        "schema_version",
        "matrix_spec_version",
        "matrix_id",
        "status",
        "plan_sha256",
        "matrix_spec_sha256",
        "base_config_sha256",
        "prompt_sha256",
        "plan_manifest_sha256",
        "planned_runs",
        "started_runs",
        "completed_runs",
        "failed_runs",
        "aborted_runs",
        "not_started_runs",
        "runs",
    }
    if set(batch_manifest) != expected_batch_manifest_fields:
        _error(result, "batch manifest fields are not canonical")
    if (
        (batch_path / "batch_manifest.json").read_bytes()
        != canonical_json_bytes(batch_manifest) + b"\n"
    ):
        _error(result, "batch_manifest.json is not canonical")
    manifest_rows = batch_manifest.get("runs")
    if not isinstance(manifest_rows, list) or len(manifest_rows) != len(rows):
        _error(result, "batch manifest does not represent every planned row")
        manifest_rows = []
    manifest_by_run = {
        row.get("run_id"): row
        for row in manifest_rows
        if isinstance(row, dict) and isinstance(row.get("run_id"), str)
    }
    if len(manifest_by_run) != len(manifest_rows):
        _error(result, "batch manifest contains duplicate or invalid run rows")
    for ordinal, manifest_row in enumerate(manifest_rows):
        if not isinstance(manifest_row, dict) or set(manifest_row) != MANIFEST_ROW_FIELDS:
            _error(result, f"batch manifest run row {ordinal} fields are not canonical")

    runs_dir = batch_path / "runs"
    actual_run_dirs = {
        path.name
        for path in runs_dir.iterdir()
        if path.is_dir() and not path.is_symlink()
    } if runs_dir.is_dir() else set()
    expected_run_dirs = {
        f"output_{run_id}"
        for run_id, manifest_row in manifest_by_run.items()
        if manifest_row.get("status") != "not_started"
    }
    extra = actual_run_dirs - expected_run_dirs
    missing = expected_run_dirs - actual_run_dirs
    if extra:
        _error(result, f"extra run directories: {sorted(extra)!r}")
    if missing:
        _error(result, f"missing run directories: {sorted(missing)!r}")

    if batch_manifest.get("schema_version") != BATCH_MANIFEST_VERSION:
        _error(result, "batch manifest schema version mismatch")
    for key in (
        "matrix_id",
        "plan_sha256",
        "matrix_spec_sha256",
        "base_config_sha256",
        "prompt_sha256",
        "plan_manifest_sha256",
    ):
        if batch_manifest.get(key) != meta.get(key):
            _error(result, f"batch manifest {key} mismatch")
    if meta.get("batch_manifest_sha256") != sha256_file(
        batch_path / "batch_manifest.json"
    ):
        _error(result, "batch manifest file hash mismatch")
    run_metas: List[Dict[str, Any]] = []
    for row in rows:
        run_id = row.get("run_id")
        manifest_row = manifest_by_run.get(run_id)
        if not isinstance(manifest_row, dict):
            _error(result, f"batch manifest lacks run {run_id}")
            continue
        for key in ("ordinal", "run_id", "cell_id", "replicate_id", "config_path", "config_sha256"):
            if manifest_row.get(key) != row.get(key):
                _error(result, f"batch manifest row {run_id} has invalid {key}")
        status = manifest_row.get("status")
        if status not in {"completed", "failed", "aborted", "not_started"}:
            _error(result, f"batch manifest row {run_id} has invalid status")
            continue
        run_dir = runs_dir / f"output_{run_id}"
        if status == "completed":
            config = config_by_run.get(run_id)
            if config is None:
                continue
            run_result = ValidationResult(str(run_dir), profile)
            run_meta = _validate_run_common(
                run_dir, meta, plan, row, config, run_result
            )
            result.strict_unverifiable.extend(run_result.strict_unverifiable)
            for message in run_result.errors:
                _error(result, message)
            if run_meta is not None:
                run_metas.append(run_meta)
                if not _manifest_equal(
                    run_dir / "run_meta.json",
                    manifest_row.get("run_meta_manifest"),
                ):
                    _error(result, f"run-meta manifest mismatch for {run_id}")
                if manifest_row.get("raw_manifest") != run_meta.get("raw_manifest"):
                    _error(result, f"raw manifest copy mismatch for {run_id}")
            if manifest_row.get("strict_valid") is not True:
                _error(result, f"completed run {run_id} lacks strict PASS")
            if manifest_row.get("strict_errors") != []:
                _error(result, f"completed run {run_id} records strict errors")
            if manifest_row.get("strict_unverifiable") != run_result.strict_unverifiable:
                _error(result, f"stored strict validator evidence mismatch for {run_id}")
            if manifest_row.get("smoke_valid") is not True:
                _error(result, f"completed run {run_id} lacks smoke PASS")
            smoke_result = validate_run_profile(
                run_dir, batch_path, row, "smoke"
            )
            for message in smoke_result.errors:
                _error(result, f"smoke run validation: {message}")
            if manifest_row.get("smoke_errors") != smoke_result.errors:
                _error(result, f"stored smoke validator errors mismatch for {run_id}")
            if (
                manifest_row.get("smoke_unverified_research_requirements")
                != smoke_result.unverified_research_requirements
            ):
                _error(result, f"stored smoke eligibility evidence mismatch for {run_id}")
            if manifest_row.get("research_eligible") is not False:
                _error(result, f"smoke run {run_id} is incorrectly research eligible")
        elif status == "not_started" and run_dir.exists():
            _error(result, f"not-started run directory exists for {run_id}")

    statuses = [
        row.get("status") for row in manifest_rows if isinstance(row, dict)
    ]
    counts = {
        "planned_runs": len(rows),
        "started_runs": sum(status != "not_started" for status in statuses),
        "completed_runs": statuses.count("completed"),
        "failed_runs": statuses.count("failed"),
        "aborted_runs": statuses.count("aborted"),
        "not_started_runs": statuses.count("not_started"),
    }
    for key, expected in counts.items():
        if meta.get(key) != expected or batch_manifest.get(key) != expected:
            _error(result, f"batch {key} count mismatch")
    if batch_manifest.get("status") != meta.get("status"):
        _error(result, "batch status differs between metadata and manifest")
    complete = (
        meta.get("status") == "completed"
        and batch_manifest.get("status") == "completed"
        and counts["completed_runs"] == len(rows)
        and counts["failed_runs"] == 0
        and counts["aborted_runs"] == 0
        and counts["not_started_runs"] == 0
    )
    if not complete:
        _error(result, "selected batch is not a completed smoke batch")
    _research_requirements(meta, configs, run_metas, complete, result)
    result.strict_unverifiable = list(dict.fromkeys(result.strict_unverifiable))
    result.details.update({
        "matrix_id": plan.get("matrix_id"),
        "planned_runs": len(rows),
        "completed_runs": counts["completed_runs"],
        "execution_mode": meta.get("execution_mode"),
    })
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = ResearchArgumentParser(
        prog="python -m tools.research_validator",
        description="Validate Gate 3 run or batch research eligibility",
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, parser_class=ResearchArgumentParser
    )
    batch = subparsers.add_parser("batch")
    batch.add_argument("--profile", choices=("smoke", "research"), required=True)
    batch.add_argument("--batch-dir", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--profile", choices=("smoke", "research"), required=True)
    run.add_argument("--batch-dir", required=True)
    run.add_argument("--run-id")
    run.add_argument("--run-dir")
    return parser


def _find_run_row(
    batch_dir: Path,
    run_id: Optional[str],
    run_dir: Optional[str],
) -> Tuple[Path, Dict[str, Any]]:
    if (run_id is None) == (run_dir is None):
        raise InvocationError("run requires exactly one of --run-id or --run-dir")
    if run_dir is not None:
        path = Path(run_dir).resolve()
        name = path.name
        if not name.startswith("output_"):
            raise InvocationError("run directory name must start with output_")
        selected = name[len("output_"):]
    else:
        selected = run_id
        path = batch_dir / "runs" / f"output_{selected}"
    try:
        rows = read_jsonl_objects(batch_dir / "planned_runs.jsonl")
    except (OSError, PlanValidationError) as error:
        raise InvocationError(f"cannot read planned rows: {error}") from error
    matches = [row for row in rows if row.get("run_id") == selected]
    if len(matches) != 1:
        raise InvocationError("run ID does not map to exactly one planned row")
    return path, matches[0]


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "batch":
            result = validate_batch_profile(args.batch_dir, args.profile)
        else:
            batch_dir = Path(args.batch_dir).resolve()
            run_dir, row = _find_run_row(
                batch_dir, args.run_id, args.run_dir
            )
            result = validate_run_profile(
                run_dir, batch_dir, row, args.profile
            )
    except InvocationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 64
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        print(
            f"ERROR: validator configuration failure: {type(error).__name__}",
            file=sys.stderr,
        )
        return 64
    print(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
