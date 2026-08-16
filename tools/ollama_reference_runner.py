"""Gate 4A runner for real Ollama-native reference smoke evidence.

This module deliberately does not extend or relax the frozen Gate 3 runner.  It
loads the same hash-pinned matrix plan and generated bundle, but publishes a
separate Gate 4A evidence package.  Standalone-cell stages are therefore not
canonical Gate 3 batches and cannot be promoted by the Gate 3 research
validator.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import yaml

from engine import provenance
from engine.provenance import atomic_write_json, file_manifest, utc_now_iso
from engine.sim import Simulation, SimulationAbortedError
from tools.eight_cell_core import (
    CELL_DEFINITIONS,
    MatrixBundle,
    LoadedPlan,
    PlanValidationError,
    build_bundle,
    canonical_json_file_bytes,
    load_plan,
    planned_rows_bytes,
    sha256_file,
    write_exclusive_bytes,
)
from tools.validate_run import validate_run


MANIFEST_SCHEMA_VERSION = "gate4a-ollama-reference-manifest-v1.0.0"
META_SCHEMA_VERSION = "gate4a-ollama-reference-meta-v1.0.0"
EXPECTED_EXECUTION_MODE = "reference_ollama"
EXPECTED_NUM_CTX = 4096
EXPECTED_DURATION = 1
EXPECTED_AGENTS = 12
FAILURE_COUNTERS = (
    "transport_failures",
    "syntax_parse_failures",
    "schema_validation_failures",
)
REFERENCE_ZERO_COUNTERS = (
    "generation_retries",
    "transport_failures",
    "syntax_parse_attempt_failures",
    "syntax_parse_failures",
    "schema_validation_failures",
)
TELEMETRY_COUNTERS = (
    "logical_llm_calls",
    "http_attempts",
    "generation_retries",
    "transport_failures",
    "syntax_parse_attempt_failures",
    "syntax_parse_failures",
    "schema_validation_failures",
)
STAGE_CELLS: Dict[str, Tuple[str, ...]] = {
    "4A-2": ("qqq-full",),
    "4A-3": ("het-full",),
    "4A-4": tuple(cell_id for cell_id, _, _ in CELL_DEFINITIONS),
}


class ReferenceCollisionError(FileExistsError):
    """A matrix ID already owns a Gate 4A output directory."""


class ReferenceExecutionError(RuntimeError):
    """A claimed Gate 4A execution did not complete successfully."""

    def __init__(self, message: str, execution_dir: Path):
        super().__init__(message)
        self.execution_dir = execution_dir


class InvocationError(ValueError):
    """CLI syntax is invalid rather than plan evidence being invalid."""


class ReferenceArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InvocationError(message)


@dataclass(frozen=True)
class PreparedReference:
    """A fully hash-checked Gate 3 bundle admitted to the Gate 4A envelope."""

    loaded_plan: LoadedPlan
    bundle: MatrixBundle
    max_concurrency: int


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _load_declared_base_config(loaded: LoadedPlan) -> Dict[str, Any]:
    try:
        value = yaml.safe_load(loaded.base_config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise PlanValidationError(
            f"cannot inspect declared base config: {type(error).__name__}"
        ) from error
    if not isinstance(value, dict):
        raise PlanValidationError("declared base config must be a mapping")
    return value


def _verify_matrix_spec_hash(expected: str, repo_root: Path) -> str:
    if not isinstance(expected, str):
        raise PlanValidationError("matrix spec SHA-256 is required")
    actual = sha256_file(repo_root / "docs" / "EIGHT_CELL_MATRIX_SPEC.md")
    if actual != expected:
        raise PlanValidationError(
            f"matrix spec SHA-256 mismatch: expected {expected}, got {actual}"
        )
    return actual


def _validate_reference_envelope(
    loaded: LoadedPlan,
    bundle: MatrixBundle,
) -> int:
    plan = loaded.data
    if plan.get("execution_mode") != EXPECTED_EXECUTION_MODE:
        raise PlanValidationError(
            "Gate 4A reference runner requires execution_mode reference_ollama"
        )
    replicates = plan.get("replicates")
    if not isinstance(replicates, list) or len(replicates) != 1:
        raise PlanValidationError("Gate 4A reference stages require exactly one replicate")

    declared = _load_declared_base_config(loaded)
    declared_simulation = declared.get("simulation")
    declared_llm = declared.get("llm_defaults")
    if not isinstance(declared_simulation, dict):
        raise PlanValidationError("declared simulation config must be a mapping")
    if declared_simulation.get("duration") != EXPECTED_DURATION:
        raise PlanValidationError("Gate 4A reference duration must be exactly 1")
    thresholds = declared_simulation.get("failure_thresholds")
    expected_thresholds = {counter: 0 for counter in FAILURE_COUNTERS}
    if thresholds != expected_thresholds:
        raise PlanValidationError(
            "Gate 4A failure thresholds must be explicitly declared as zero"
        )
    if not isinstance(declared_llm, dict) or "max_concurrency" not in declared_llm:
        raise PlanValidationError(
            "Gate 4A base config must explicitly declare llm_defaults.max_concurrency"
        )
    max_concurrency = declared_llm.get("max_concurrency")
    if not _is_positive_int(max_concurrency):
        raise PlanValidationError(
            "Gate 4A llm_defaults.max_concurrency must be a positive integer"
        )

    model_catalog = plan.get("model_catalog")
    if not isinstance(model_catalog, dict):
        raise PlanValidationError("Gate 4A model_catalog must be an object")
    for slot, profile in model_catalog.items():
        if not isinstance(profile, dict):
            raise PlanValidationError(f"model_catalog.{slot} must be an object")
        for artifact_field in ("model_digest", "quantization", "chat_template"):
            artifact = profile.get(artifact_field)
            if not isinstance(artifact, str) or not artifact:
                raise PlanValidationError(
                    f"model_catalog.{slot}.{artifact_field} must be fixed before "
                    "a Gate 4A simulation stage"
                )
        overrides = profile.get("llm_overrides") if isinstance(profile, dict) else None
        num_ctx = overrides.get("num_ctx") if isinstance(overrides, dict) else None
        if (
            not isinstance(num_ctx, int)
            or isinstance(num_ctx, bool)
            or num_ctx != EXPECTED_NUM_CTX
        ):
            raise PlanValidationError(
                f"model_catalog.{slot}.llm_overrides.num_ctx must be "
                f"exactly {EXPECTED_NUM_CTX}"
            )

    if len(bundle.rows) != len(CELL_DEFINITIONS):
        raise PlanValidationError("one-replicate Gate 4A bundle must contain eight cells")
    if tuple(row.get("cell_id") for row in bundle.rows) != STAGE_CELLS["4A-4"]:
        raise PlanValidationError("Gate 4A bundle cell order is not canonical")

    for row in bundle.rows:
        config = bundle.configs.get(row.get("run_id"))
        if not isinstance(config, dict):
            raise PlanValidationError("Gate 4A generated config is missing")
        simulation = config.get("simulation")
        llm_defaults = config.get("llm_defaults")
        blocs = config.get("blocs")
        if not isinstance(simulation, dict) or not isinstance(llm_defaults, dict):
            raise PlanValidationError("Gate 4A generated config sections are invalid")
        if simulation.get("duration") != EXPECTED_DURATION:
            raise PlanValidationError("Gate 4A generated duration differs from 1")
        if simulation.get("failure_thresholds") != expected_thresholds:
            raise PlanValidationError("Gate 4A generated failure thresholds are not zero")
        if simulation.get("execution_mode") != EXPECTED_EXECUTION_MODE:
            raise PlanValidationError("Gate 4A generated execution mode is invalid")
        if simulation.get("research_eligible") is not False:
            raise PlanValidationError(
                "Gate 4A generated config must declare research_eligible false"
            )
        if llm_defaults.get("max_concurrency") != max_concurrency:
            raise PlanValidationError(
                "Gate 4A generated max_concurrency differs from its declaration"
            )
        if not isinstance(blocs, list) or sum(
            bloc.get("num_agents", 0) for bloc in blocs if isinstance(bloc, dict)
        ) != EXPECTED_AGENTS:
            raise PlanValidationError("Gate 4A generated config must contain 12 agents")
        for bloc in blocs:
            overrides = bloc.get("llm_overrides") if isinstance(bloc, dict) else None
            if not isinstance(overrides, dict) or overrides.get("num_ctx") != EXPECTED_NUM_CTX:
                raise PlanValidationError(
                    "Gate 4A generated model profile lacks num_ctx 4096"
                )
    return max_concurrency


def prepare_reference(
    plan_path: Path | str,
    plan_sha256: str,
    matrix_spec_sha256: str,
    *,
    repo_root: Optional[Path] = None,
) -> PreparedReference:
    """Load all pinned inputs and enforce the narrow Gate 4A smoke envelope."""
    repository = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    spec_sha = _verify_matrix_spec_hash(matrix_spec_sha256, repository)
    loaded = load_plan(plan_path, plan_sha256)
    bundle = build_bundle(loaded, spec_sha, repo_root=repository)
    max_concurrency = _validate_reference_envelope(loaded, bundle)
    return PreparedReference(loaded, bundle, max_concurrency)


def select_stage_rows(
    prepared: PreparedReference,
    stage: str,
) -> Tuple[Dict[str, Any], ...]:
    """Select the declared smoke scope without changing Gate 3 planned rows."""
    if stage not in STAGE_CELLS:
        raise InvocationError(f"unknown Gate 4A stage: {stage!r}")
    wanted = STAGE_CELLS[stage]
    rows_by_cell = {row["cell_id"]: row for row in prepared.bundle.rows}
    try:
        selected = tuple(rows_by_cell[cell_id] for cell_id in wanted)
    except KeyError as error:
        raise PlanValidationError(f"Gate 4A bundle lacks cell {error.args[0]}") from error
    if tuple(row["cell_id"] for row in selected) != wanted:
        raise PlanValidationError("Gate 4A stage selection order is invalid")
    return selected


def _execution_directory(output_root: Path, matrix_id: str) -> Path:
    # A matrix ID may be used for only one Gate 4A stage in an output root.  A
    # later stage must use a new plan/matrix ID so run IDs remain unique.
    return output_root / f"output_gate4a-{matrix_id}"


def _initial_manifest_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "stage_ordinal": None,
        "plan_ordinal": row["ordinal"],
        "run_id": row["run_id"],
        "cell_id": row["cell_id"],
        "replicate_id": row["replicate_id"],
        "execution_mode": row["execution_mode"],
        "status": "not_started",
        "lifecycle_status": None,
        "config_path": row["config_path"],
        "config_sha256": row["config_sha256"],
        "run_directory": f"runs/output_{row['run_id']}",
        "run_meta_manifest": None,
        "raw_manifest": None,
        "strict_executed": False,
        "strict_valid": False,
        "strict_errors": [],
        "strict_unverifiable": [],
        "reference_smoke_valid": False,
        "reference_smoke_errors": [],
        "expected_logical_llm_calls": 2 * EXPECTED_DURATION * EXPECTED_AGENTS,
        "counters": None,
        "research_eligible": False,
    }


def _status_counts(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    statuses = [row.get("status") for row in rows]
    return {
        "planned_runs": len(rows),
        "started_runs": sum(status != "not_started" for status in statuses),
        "completed_runs": statuses.count("completed"),
        "failed_runs": statuses.count("failed"),
        "aborted_runs": statuses.count("aborted"),
        "not_started_runs": statuses.count("not_started"),
    }


def _aggregate_counters(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    totals = {field: 0 for field in TELEMETRY_COUNTERS}
    for row in rows:
        counters = row.get("counters")
        if not isinstance(counters, dict):
            continue
        for field in TELEMETRY_COUNTERS:
            value = counters.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                totals[field] += value
    return totals


def _capture_run_evidence(run_dir: Path, row: Dict[str, Any]) -> None:
    meta_path = run_dir / "run_meta.json"
    if not meta_path.is_file() or meta_path.is_symlink():
        return
    try:
        row["run_meta_manifest"] = file_manifest(meta_path)
        run_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(run_meta, dict):
        return
    row["lifecycle_status"] = run_meta.get("status")
    row["raw_manifest"] = copy.deepcopy(run_meta.get("raw_manifest"))
    row["counters"] = {
        field: run_meta.get(field) for field in TELEMETRY_COUNTERS
    }


def _validate_reference_run_counters(row: Dict[str, Any]) -> list[str]:
    errors = []
    counters = row.get("counters")
    if not isinstance(counters, dict):
        return ["run counters are unavailable"]
    expected_calls = row["expected_logical_llm_calls"]
    if counters.get("logical_llm_calls") != expected_calls:
        errors.append(
            "logical_llm_calls mismatch: "
            f"expected {expected_calls}, got {counters.get('logical_llm_calls')}"
        )
    if counters.get("http_attempts") != expected_calls:
        errors.append(
            "http_attempts mismatch under the zero-retry acceptance rule: "
            f"expected {expected_calls}, got {counters.get('http_attempts')}"
        )
    for counter in REFERENCE_ZERO_COUNTERS:
        if counters.get(counter) != 0:
            errors.append(
                f"{counter} must be zero, got {counters.get(counter)}"
            )
    return errors


def _write_static_evidence(
    execution_dir: Path,
    prepared: PreparedReference,
    selected_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    configs_dir = execution_dir / "configs"
    configs_dir.mkdir(mode=0o755, parents=False, exist_ok=False)
    write_exclusive_bytes(
        execution_dir / "plan.json",
        canonical_json_file_bytes(prepared.bundle.plan),
    )
    write_exclusive_bytes(
        execution_dir / "selected_runs.jsonl",
        planned_rows_bytes(selected_rows),
    )
    for row in selected_rows:
        write_exclusive_bytes(
            execution_dir / row["config_path"],
            canonical_json_file_bytes(prepared.bundle.configs[row["run_id"]]),
        )
    static_paths = ["plan.json", "selected_runs.jsonl"] + [
        row["config_path"] for row in selected_rows
    ]
    return {
        relative: file_manifest(execution_dir / relative)
        for relative in static_paths
    }


def _running_meta(
    prepared: PreparedReference,
    stage: str,
    rows: Sequence[Dict[str, Any]],
    git_info: Dict[str, Any],
) -> Dict[str, Any]:
    now = utc_now_iso()
    return {
        "schema_version": META_SCHEMA_VERSION,
        "stage": stage,
        "matrix_id": prepared.bundle.plan["matrix_id"],
        "status": "running",
        "start_time_utc": now,
        "end_time_utc": None,
        "execution_mode": EXPECTED_EXECUTION_MODE,
        "transport": "ollama_native",
        "endpoint": "/api/chat",
        "research_eligible": False,
        "gate3_research_validator_scope": "not_a_gate3_batch",
        "plan_sha256": prepared.bundle.plan_sha256,
        "matrix_spec_sha256": prepared.bundle.matrix_spec_sha256,
        "base_config_sha256": prepared.bundle.plan["base_config"]["sha256"],
        "prompt_sha256": prepared.bundle.prompt_sha256,
        "num_ctx": EXPECTED_NUM_CTX,
        "max_concurrency": prepared.max_concurrency,
        "source_git_sha": git_info.get("git_sha"),
        "source_git_dirty": git_info.get("git_dirty"),
        "source_git_probe_status": git_info.get("git_probe_status"),
        "source_git_probe_errors": copy.deepcopy(
            git_info.get("git_probe_errors", [])
        ),
        **_status_counts(rows),
        "aggregate_counters": _aggregate_counters(rows),
        "manifest_sha256": None,
        "failure_type": None,
    }


def _update_running_meta(
    execution_dir: Path,
    meta: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
) -> None:
    meta.update(_status_counts(rows))
    meta["aggregate_counters"] = _aggregate_counters(rows)
    atomic_write_json(execution_dir / "reference_meta.json", meta)


def run_reference_stage(
    prepared: PreparedReference,
    stage: str,
    output_root: Path | str,
    *,
    repo_root: Optional[Path] = None,
) -> Path:
    """Claim and run one Gate 4A stage with the native Simulation transport."""
    validated_concurrency = _validate_reference_envelope(
        prepared.loaded_plan, prepared.bundle
    )
    if prepared.max_concurrency != validated_concurrency:
        raise PlanValidationError(
            "prepared Gate 4A max_concurrency differs from validated evidence"
        )
    selected_rows = select_stage_rows(prepared, stage)
    repository = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    try:
        git_info = provenance.collect_git_info(repository)
    except Exception:
        git_info = {
            "git_sha": None,
            "git_dirty": None,
            "git_probe_status": "unavailable",
            "git_probe_errors": ["unexpected_probe_error"],
        }

    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    execution_dir = _execution_directory(root, prepared.bundle.plan["matrix_id"])
    try:
        execution_dir.mkdir(mode=0o755, parents=False, exist_ok=False)
    except FileExistsError as error:
        raise ReferenceCollisionError(
            f"Gate 4A output already exists for matrix ID "
            f"{prepared.bundle.plan['matrix_id']!r}"
        ) from error

    manifest_rows = [_initial_manifest_row(row) for row in selected_rows]
    for index, row in enumerate(manifest_rows):
        row["stage_ordinal"] = index
    meta = _running_meta(prepared, stage, manifest_rows, git_info)
    atomic_write_json(execution_dir / "reference_meta.json", meta)
    failure: Optional[BaseException] = None
    final_status = "failed"
    static_files: Dict[str, Any] = {}
    try:
        static_files = _write_static_evidence(
            execution_dir, prepared, selected_rows
        )
        runs_dir = execution_dir / "runs"
        runs_dir.mkdir(mode=0o755, parents=False, exist_ok=False)
        for planned, manifest_row in zip(selected_rows, manifest_rows):
            manifest_row["status"] = "running"
            _update_running_meta(execution_dir, meta, manifest_rows)
            run_dir = runs_dir / f"output_{planned['run_id']}"
            try:
                simulation = Simulation(
                    copy.deepcopy(prepared.bundle.configs[planned["run_id"]]),
                    output_root=runs_dir,
                    repo_root=repository,
                    transport=None,
                )
                simulation.run()
                strict = validate_run(run_dir, strict=True)
                manifest_row["strict_executed"] = True
                manifest_row["strict_valid"] = strict.valid
                manifest_row["strict_errors"] = list(strict.errors)
                manifest_row["strict_unverifiable"] = list(strict.unverifiable)
                _capture_run_evidence(run_dir, manifest_row)
                manifest_row["reference_smoke_errors"] = (
                    _validate_reference_run_counters(manifest_row)
                )
                manifest_row["reference_smoke_valid"] = (
                    strict.valid and not manifest_row["reference_smoke_errors"]
                )
                if not manifest_row["reference_smoke_valid"]:
                    manifest_row["status"] = "failed"
                    raise ReferenceExecutionError(
                        f"reference smoke validation failed for {planned['run_id']}",
                        execution_dir,
                    )
                manifest_row["status"] = "completed"
            except KeyboardInterrupt as error:
                _capture_run_evidence(run_dir, manifest_row)
                manifest_row["status"] = "aborted"
                failure = error
                final_status = "aborted"
                break
            except SimulationAbortedError as error:
                _capture_run_evidence(run_dir, manifest_row)
                manifest_row["status"] = "aborted"
                failure = error
                final_status = "aborted"
                break
            except BaseException as error:
                _capture_run_evidence(run_dir, manifest_row)
                if manifest_row.get("status") == "running":
                    manifest_row["status"] = (
                        "aborted"
                        if manifest_row.get("lifecycle_status") == "aborted"
                        else "failed"
                    )
                failure = error
                final_status = (
                    "aborted"
                    if manifest_row.get("status") == "aborted"
                    else "failed"
                )
                break
            _update_running_meta(execution_dir, meta, manifest_rows)
        else:
            final_status = "completed"
    except KeyboardInterrupt as error:
        failure = error
        final_status = "aborted"
    except BaseException as error:
        failure = error
        final_status = "failed"

    end_time = utc_now_iso()
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "stage": stage,
        "completion_scope": (
            "full_eight_cell" if stage == "4A-4" else "standalone_cell"
        ),
        "matrix_id": prepared.bundle.plan["matrix_id"],
        "status": final_status,
        "start_time_utc": meta["start_time_utc"],
        "end_time_utc": end_time,
        "execution_mode": EXPECTED_EXECUTION_MODE,
        "transport": "ollama_native",
        "endpoint": "/api/chat",
        "outer_run_parallelism": 1,
        "research_eligible": False,
        "gate3_research_validator_scope": "not_a_gate3_batch",
        "plan_sha256": prepared.bundle.plan_sha256,
        "matrix_spec_sha256": prepared.bundle.matrix_spec_sha256,
        "base_config_sha256": prepared.bundle.plan["base_config"]["sha256"],
        "prompt_sha256": prepared.bundle.prompt_sha256,
        "num_ctx": EXPECTED_NUM_CTX,
        "max_concurrency": prepared.max_concurrency,
        "source_git_sha": meta.get("source_git_sha"),
        "source_git_dirty": meta.get("source_git_dirty"),
        "source_git_probe_status": meta.get("source_git_probe_status"),
        **_status_counts(manifest_rows),
        "expected_logical_llm_calls": (
            len(manifest_rows) * 2 * EXPECTED_DURATION * EXPECTED_AGENTS
        ),
        "aggregate_counters": _aggregate_counters(manifest_rows),
        "static_files": static_files,
        "runs": manifest_rows,
        "failure_type": type(failure).__name__ if failure is not None else None,
    }
    manifest_path = execution_dir / "reference_manifest.json"
    try:
        write_exclusive_bytes(
            manifest_path,
            canonical_json_file_bytes(manifest),
        )
        meta.update(_status_counts(manifest_rows))
        meta["aggregate_counters"] = _aggregate_counters(manifest_rows)
        meta["status"] = final_status
        meta["end_time_utc"] = end_time
        meta["failure_type"] = manifest["failure_type"]
        meta["manifest_sha256"] = sha256_file(manifest_path)
        atomic_write_json(execution_dir / "reference_meta.json", meta)
    except BaseException as finalize_error:
        if failure is None:
            failure = finalize_error
        final_status = "failed"
        meta["status"] = "failed"
        meta["end_time_utc"] = utc_now_iso()
        meta["failure_type"] = type(failure).__name__
        try:
            atomic_write_json(execution_dir / "reference_meta.json", meta)
        except BaseException:
            pass

    if failure is not None or final_status != "completed":
        raise ReferenceExecutionError(
            f"Gate 4A stage {stage} ended as {final_status}",
            execution_dir,
        ) from failure
    return execution_dir


def build_parser() -> argparse.ArgumentParser:
    parser = ReferenceArgumentParser(
        prog="python -m tools.ollama_reference_runner",
        description="Run a hash-pinned Gate 4A Ollama-native reference smoke",
    )
    parser.add_argument("--stage", choices=tuple(STAGE_CELLS), required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--matrix-spec-sha256", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except InvocationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 64
    repository = Path(__file__).resolve().parents[1]
    try:
        prepared = prepare_reference(
            args.plan,
            args.plan_sha256,
            args.matrix_spec_sha256,
            repo_root=repository,
        )
        execution_dir = run_reference_stage(
            prepared,
            args.stage,
            args.output_root,
            repo_root=repository,
        )
    except ReferenceCollisionError as error:
        print(f"COLLISION: {error}", file=sys.stderr)
        return 3
    except PlanValidationError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"INVALID: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    except ReferenceExecutionError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ABORTED: interrupted", file=sys.stderr)
        return 1
    print(f"PASS: Gate 4A {args.stage} completed at {execution_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
