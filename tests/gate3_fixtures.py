"""Shared temporary-only fixtures for Gate 3 regression tests."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
from unittest import mock

from tools.eight_cell_core import build_bundle, load_plan, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "EIGHT_CELL_MATRIX_SPEC.md"


def base_config() -> dict:
    return {
        "simulation": {
            "duration": 1,
            "half_space_size": 2,
            "seed": 0,
            "run_name": "gate3-base",
            "failure_thresholds": {
                "transport_failures": 0,
                "syntax_parse_failures": 0,
                "schema_validation_failures": 0,
            },
        },
        "blocs": [
            {
                "name": name,
                "model": "base-placeholder",
                "base_url": "http://127.0.0.1:11434",
                "num_agents": 4,
            }
            for name in ("alpha", "beta", "neutral")
        ],
        "agents": {
            "communication_radius": 100,
            "memory_limit": 4,
            "memory_size": 2,
            "message_history_limit": 20,
            "message_context_size": 20,
        },
        "places": [],
        "llm_defaults": {
            "temperature": 0.0,
            "max_tokens": 32,
            "timeout_s": 1,
            "max_concurrency": 3,
        },
    }


def matrix_plan(
    base_sha256: str,
    *,
    matrix_id: str = "gate3-smoke",
    replicates: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "eight-cell-matrix-plan-v1.0.0",
        "matrix_id": matrix_id,
        "protocol_version": "gate3-test-protocol-v1",
        "metric_version": "metric-v2.0.0",
        "base_config": {
            "path": "base_config.json",
            "sha256": base_sha256,
        },
        "model_catalog": {
            "qwen": {
                "provider": "ollama",
                "model": "qwen-placeholder",
                "base_url": "http://127.0.0.1:11434",
            },
            "gemma": {
                "provider": "ollama",
                "model": "gemma-placeholder",
                "base_url": "http://127.0.0.1:11435",
            },
            "llama": {
                "provider": "ollama",
                "model": "llama-placeholder",
                "base_url": "http://127.0.0.1:11436",
            },
        },
        "replicates": replicates or [
            {"replicate_id": "r000", "world_seed": 1001}
        ],
        "candidate_registry": {"status": "not_frozen", "sha256": None},
        "backend_freeze": {"status": "not_frozen", "evidence_id": None},
    }


def write_plan_fixture(
    root: Path,
    *,
    matrix_id: str = "gate3-smoke",
    replicates: list[dict] | None = None,
):
    base_path = root / "base_config.json"
    base_path.write_text(
        json.dumps(base_config(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    base_sha = sha256_file(base_path)
    plan = matrix_plan(base_sha, matrix_id=matrix_id, replicates=replicates)
    plan_path = root / "matrix_plan.json"
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    plan_sha = sha256_file(plan_path)
    spec_sha = sha256_file(SPEC_PATH)
    loaded = load_plan(plan_path, plan_sha)
    bundle = build_bundle(loaded, spec_sha, repo_root=REPO_ROOT)
    return plan_path, plan_sha, spec_sha, bundle


def gate3_patchers():
    git_info = {
        "git_sha": "3" * 40,
        "git_dirty": True,
        "git_probe_status": "available",
        "git_probe_errors": [],
    }
    gpu_info = {
        "status": "unavailable",
        "error": "test_disabled",
        "driver_version": None,
        "cuda_version": None,
        "devices": [],
    }
    dependencies = {
        "requests": "test",
        "PyYAML": "test",
        "matplotlib": "test",
        "Pillow": "test",
    }
    return (
        mock.patch("engine.provenance.collect_git_info", return_value=git_info),
        mock.patch("engine.provenance.collect_gpu_info", return_value=gpu_info),
        mock.patch(
            "engine.provenance.collect_dependency_versions",
            return_value=dependencies,
        ),
        mock.patch(
            "engine.llm_client.requests.post",
            side_effect=AssertionError("real network is forbidden in Gate 3 tests"),
        ),
    )


@contextlib.contextmanager
def patched_gate3_environment():
    patchers = gate3_patchers()
    for patcher in patchers:
        patcher.start()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        for patcher in reversed(patchers):
            patcher.stop()


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
