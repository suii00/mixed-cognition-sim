import contextlib
import copy
import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from engine.llm_client import LLMTransportError
from tests.gate3_fixtures import (
    REPO_ROOT,
    base_config,
    matrix_plan,
    tree_hashes,
)
from tools.eight_cell_core import (
    CELL_DEFINITIONS,
    PlanValidationError,
    canonical_json_file_bytes,
    sha256_file,
)
from tools.ollama_reference_runner import (
    MANIFEST_SCHEMA_VERSION,
    ReferenceCollisionError,
    ReferenceExecutionError,
    prepare_reference,
    run_reference_stage,
    select_stage_rows,
)
from tools.research_validator import validate_batch_profile


class NativeResponseFixture:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.calls = []

    def __call__(
        self,
        prompt,
        model,
        base_url,
        temperature=0.2,
        max_tokens=1024,
        timeout_s=120,
        llm_overrides=None,
        telemetry=None,
        **kwargs,
    ):
        self.calls.append({
            "prompt": prompt,
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_s": timeout_s,
            "llm_overrides": copy.deepcopy(llm_overrides),
            "extra": copy.deepcopy(kwargs),
        })
        if telemetry is not None:
            telemetry("http_attempt", 1)
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            if telemetry is not None:
                telemetry("transport_failure", 1)
            raise LLMTransportError("injected Gate 4A transport failure")
        if "Decide what message" in prompt:
            parsed = {"message": "reference-message", "reasoning": ""}
        else:
            parsed = {
                "action": "stay",
                "direction": "",
                "memory": "",
                "reasoning": "",
            }
        return parsed, json.dumps(
            parsed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class OllamaReferenceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case_index = 0

    def write_reference_plan(
        self,
        *,
        matrix_id=None,
        base_mutator=None,
        plan_mutator=None,
    ):
        self.case_index += 1
        case_root = self.root / f"case-{self.case_index}"
        case_root.mkdir()
        base = base_config()
        base["llm_defaults"]["max_concurrency"] = 1
        if base_mutator is not None:
            base_mutator(base)
        base_path = case_root / "base_config.json"
        base_path.write_text(
            json.dumps(base, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        plan = matrix_plan(
            sha256_file(base_path),
            matrix_id=matrix_id or f"gate4a-reference-{self.case_index}",
            execution_mode="reference_ollama",
        )
        for profile in plan["model_catalog"].values():
            profile["llm_overrides"] = {"num_ctx": 4096}
            profile["model_digest"] = "5" * 64
            profile["quantization"] = "Q4_K_M"
            profile["chat_template"] = "{{ .Prompt }}"
        if plan_mutator is not None:
            plan_mutator(plan)
        plan_path = case_root / "matrix_plan.json"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return (
            plan_path,
            sha256_file(plan_path),
            sha256_file(REPO_ROOT / "docs" / "EIGHT_CELL_MATRIX_SPEC.md"),
        )

    def prepare(self, **kwargs):
        plan_path, plan_sha, spec_sha = self.write_reference_plan(**kwargs)
        return prepare_reference(
            plan_path,
            plan_sha,
            spec_sha,
            repo_root=REPO_ROOT,
        )

    @contextlib.contextmanager
    def patched_runtime(self, native):
        git_info = {
            "git_sha": "4" * 40,
            "git_dirty": False,
            "git_probe_status": "available",
            "git_probe_errors": [],
        }
        gpu_info = {
            "status": "unavailable",
            "error": "test_disabled",
            "driver_version": None,
            "cuda_version": None,
            "cuda_probe_status": "unavailable",
            "cuda_probe_error": "test_disabled",
            "malformed_device_rows": 0,
            "devices": [],
        }
        dependencies = {
            "requests": "test",
            "PyYAML": "test",
            "matplotlib": "test",
            "Pillow": "test",
        }
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch("engine.provenance.collect_git_info", return_value=git_info)
            )
            stack.enter_context(
                mock.patch("engine.provenance.collect_gpu_info", return_value=gpu_info)
            )
            stack.enter_context(
                mock.patch(
                    "engine.provenance.collect_dependency_versions",
                    return_value=dependencies,
                )
            )
            guarded_post = stack.enter_context(
                mock.patch(
                    "engine.llm_client.requests.post",
                    side_effect=AssertionError("unexpected real network call"),
                )
            )
            stack.enter_context(mock.patch("engine.sim.call_ollama", side_effect=native))
            with contextlib.redirect_stdout(io.StringIO()):
                yield guarded_post

    @staticmethod
    def read_manifest(execution_dir):
        return json.loads(
            (execution_dir / "reference_manifest.json").read_text(encoding="utf-8")
        )

    def test_stages_select_expected_cells_use_native_path_and_record_evidence(self):
        cases = (
            ("4A-2", ["qqq-full"], {"qwen-placeholder"}),
            ("4A-3", ["het-full"], {
                "qwen-placeholder", "gemma-placeholder", "llama-placeholder"
            }),
            ("4A-4", [cell_id for cell_id, _, _ in CELL_DEFINITIONS], {
                "qwen-placeholder", "gemma-placeholder", "llama-placeholder"
            }),
        )
        for stage, expected_cells, expected_models in cases:
            with self.subTest(stage=stage):
                prepared = self.prepare(matrix_id=f"reference-{stage.lower()}")
                self.assertEqual(
                    [row["cell_id"] for row in select_stage_rows(prepared, stage)],
                    expected_cells,
                )
                native = NativeResponseFixture()
                output_root = self.root / f"outputs-{stage.lower()}"
                with self.patched_runtime(native) as guarded_post:
                    execution_dir = run_reference_stage(
                        prepared,
                        stage,
                        output_root,
                        repo_root=REPO_ROOT,
                    )
                guarded_post.assert_not_called()

                expected_calls = len(expected_cells) * 24
                self.assertEqual(len(native.calls), expected_calls)
                self.assertEqual(
                    {call["model"] for call in native.calls}, expected_models
                )
                self.assertTrue(
                    all(
                        call["llm_overrides"] == {"num_ctx": 4096}
                        for call in native.calls
                    )
                )

                manifest = self.read_manifest(execution_dir)
                self.assertEqual(
                    manifest["schema_version"], MANIFEST_SCHEMA_VERSION
                )
                self.assertEqual(manifest["stage"], stage)
                self.assertEqual(manifest["status"], "completed")
                self.assertEqual(manifest["execution_mode"], "reference_ollama")
                self.assertEqual(manifest["transport"], "ollama_native")
                self.assertEqual(manifest["endpoint"], "/api/chat")
                self.assertFalse(manifest["research_eligible"])
                self.assertEqual(
                    manifest["gate3_research_validator_scope"],
                    "not_a_gate3_batch",
                )
                self.assertEqual(manifest["planned_runs"], len(expected_cells))
                self.assertEqual(manifest["started_runs"], len(expected_cells))
                self.assertEqual(manifest["completed_runs"], len(expected_cells))
                self.assertEqual(manifest["failed_runs"], 0)
                self.assertEqual(manifest["aborted_runs"], 0)
                self.assertEqual(manifest["not_started_runs"], 0)
                self.assertEqual(
                    manifest["expected_logical_llm_calls"], expected_calls
                )
                self.assertEqual(
                    manifest["aggregate_counters"]["logical_llm_calls"],
                    expected_calls,
                )
                self.assertEqual(
                    manifest["aggregate_counters"]["http_attempts"],
                    expected_calls,
                )
                for counter in (
                    "transport_failures",
                    "syntax_parse_failures",
                    "schema_validation_failures",
                ):
                    self.assertEqual(manifest["aggregate_counters"][counter], 0)
                self.assertEqual(
                    [row["cell_id"] for row in manifest["runs"]], expected_cells
                )
                self.assertTrue(
                    all(
                        row["status"] == "completed"
                        and row["lifecycle_status"] == "completed"
                        and row["strict_executed"] is True
                        and row["strict_valid"] is True
                        and row["reference_smoke_valid"] is True
                        and row["reference_smoke_errors"] == []
                        and row["research_eligible"] is False
                        and row["counters"]["logical_llm_calls"] == 24
                        for row in manifest["runs"]
                    )
                )
                manifest_path = execution_dir / "reference_manifest.json"
                self.assertEqual(
                    manifest_path.read_bytes(), canonical_json_file_bytes(manifest)
                )
                meta = json.loads(
                    (execution_dir / "reference_meta.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(meta["status"], "completed")
                self.assertEqual(meta["manifest_sha256"], sha256_file(manifest_path))

                if stage != "4A-4":
                    self.assertFalse((execution_dir / "batch_meta.json").exists())
                    self.assertFalse((execution_dir / "planned_runs.jsonl").exists())
                    self.assertFalse((execution_dir / "batch_manifest.json").exists())
                    report = validate_batch_profile(execution_dir, "smoke")
                    self.assertEqual(report.exit_code, 3)

    def test_transport_failure_preserves_completed_aborted_and_not_started_rows(self):
        prepared = self.prepare(matrix_id="reference-failure")
        native = NativeResponseFixture(fail_at=25)
        output_root = self.root / "failure-outputs"
        with self.patched_runtime(native):
            with self.assertRaises(ReferenceExecutionError) as raised:
                run_reference_stage(
                    prepared,
                    "4A-4",
                    output_root,
                    repo_root=REPO_ROOT,
                )
        execution_dir = raised.exception.execution_dir
        manifest = self.read_manifest(execution_dir)
        self.assertEqual(manifest["status"], "aborted")
        self.assertEqual(
            [row["status"] for row in manifest["runs"]],
            ["completed", "aborted"] + ["not_started"] * 6,
        )
        self.assertEqual(manifest["planned_runs"], 8)
        self.assertEqual(manifest["started_runs"], 2)
        self.assertEqual(manifest["completed_runs"], 1)
        self.assertEqual(manifest["aborted_runs"], 1)
        self.assertEqual(manifest["not_started_runs"], 6)
        self.assertEqual(
            manifest["aggregate_counters"]["logical_llm_calls"], 36
        )
        self.assertEqual(
            manifest["aggregate_counters"]["transport_failures"], 1
        )
        self.assertIsNotNone(manifest["runs"][1]["run_meta_manifest"])
        self.assertEqual(manifest["runs"][1]["lifecycle_status"], "aborted")
        self.assertFalse(manifest["research_eligible"])

    def test_recovered_parse_retry_is_not_an_accepted_reference_smoke(self):
        prepared = self.prepare(matrix_id="reference-retry")
        native = NativeResponseFixture()

        original = native.__call__

        def retrying(*args, **kwargs):
            result = original(*args, **kwargs)
            if len(native.calls) == 1:
                kwargs["telemetry"]("syntax_parse_attempt_failure", 1)
                kwargs["telemetry"]("generation_retry", 1)
                kwargs["telemetry"]("http_attempt", 1)
            return result

        output_root = self.root / "retry-outputs"
        with self.patched_runtime(retrying):
            with self.assertRaises(ReferenceExecutionError) as raised:
                run_reference_stage(
                    prepared,
                    "4A-2",
                    output_root,
                    repo_root=REPO_ROOT,
                )
        manifest = self.read_manifest(raised.exception.execution_dir)
        row = manifest["runs"][0]
        self.assertEqual(row["status"], "failed")
        self.assertTrue(row["strict_valid"])
        self.assertFalse(row["reference_smoke_valid"])
        self.assertTrue(
            any("generation_retries" in error for error in row["reference_smoke_errors"])
        )
        self.assertTrue(
            any("http_attempts mismatch" in error for error in row["reference_smoke_errors"])
        )

    def test_collision_is_fail_closed_and_does_not_call_native_transport(self):
        prepared = self.prepare(matrix_id="reference-collision")
        output_root = self.root / "collision-outputs"
        first_native = NativeResponseFixture()
        with self.patched_runtime(first_native):
            execution_dir = run_reference_stage(
                prepared,
                "4A-2",
                output_root,
                repo_root=REPO_ROOT,
            )
        before = tree_hashes(execution_dir)
        losing_native = NativeResponseFixture()
        with self.patched_runtime(losing_native):
            with self.assertRaises(ReferenceCollisionError):
                run_reference_stage(
                    prepared,
                    "4A-2",
                    output_root,
                    repo_root=REPO_ROOT,
                )
        self.assertEqual(losing_native.calls, [])
        self.assertEqual(tree_hashes(execution_dir), before)

    def test_preflight_rejects_out_of_envelope_plans_before_output_creation(self):
        cases = (
            (
                "duration",
                lambda base: base["simulation"].update({"duration": 2}),
                None,
                "duration",
            ),
            (
                "threshold",
                lambda base: base["simulation"]["failure_thresholds"].update(
                    {"syntax_parse_failures": 1}
                ),
                None,
                "thresholds",
            ),
            (
                "concurrency-missing",
                lambda base: base["llm_defaults"].pop("max_concurrency"),
                None,
                "max_concurrency",
            ),
            (
                "num-ctx",
                None,
                lambda plan: plan["model_catalog"]["qwen"]["llm_overrides"].update(
                    {"num_ctx": 8192}
                ),
                "num_ctx",
            ),
            (
                "replicates",
                None,
                lambda plan: plan["replicates"].append(
                    {"replicate_id": "r001", "world_seed": 1002}
                ),
                "one replicate",
            ),
            (
                "mode",
                None,
                lambda plan: plan.update({"execution_mode": "scripted_smoke"}),
                "reference_ollama",
            ),
        )
        for name, base_mutator, plan_mutator, pattern in cases:
            with self.subTest(name=name):
                plan_path, plan_sha, spec_sha = self.write_reference_plan(
                    base_mutator=base_mutator,
                    plan_mutator=plan_mutator,
                )
                with self.assertRaisesRegex(PlanValidationError, pattern):
                    prepare_reference(
                        plan_path,
                        plan_sha,
                        spec_sha,
                        repo_root=REPO_ROOT,
                    )

    def test_hash_mismatch_is_rejected(self):
        plan_path, _, spec_sha = self.write_reference_plan()
        with self.assertRaisesRegex(PlanValidationError, "plan SHA-256 mismatch"):
            prepare_reference(
                plan_path,
                "0" * 64,
                spec_sha,
                repo_root=REPO_ROOT,
            )


if __name__ == "__main__":
    unittest.main()
