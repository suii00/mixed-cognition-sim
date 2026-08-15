import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.provenance import file_manifest
from engine.sim import Simulation
from tools.validate_run import main as validator_main
from tools.validate_run import validate_run


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "tools" / "validate_run.py"


def make_config(run_id: str) -> dict:
    return {
        "simulation": {
            "duration": 1,
            "half_space_size": 2,
            "seed": 7,
            "run_name": "validator_fixture",
            "run_id": run_id,
            "protocol_version": "test-protocol-v1",
            "metric_version": "test-metric-v1",
        },
        "blocs": [
            {
                "name": "alpha",
                "model": "mock-model",
                "base_url": "http://127.0.0.1:11434",
                "num_agents": 1,
            }
        ],
        "agents": {
            "communication_radius": 1,
            "memory_limit": 2,
            "memory_size": 1,
            "message_history_limit": 2,
            "message_context_size": 1,
        },
        "places": [],
        "llm_defaults": {
            "temperature": 0.0,
            "max_tokens": 32,
            "timeout_s": 1,
        },
    }


def offline_llm(**kwargs):
    telemetry = kwargs.get("telemetry")
    if telemetry is not None:
        telemetry("http_attempt", 1)
    parsed = {
        "message": "",
        "action": "stay",
        "direction": "",
        "memory": "",
        "reasoning": "",
    }
    return parsed, json.dumps(parsed)


def nonempty_message_llm(**kwargs):
    telemetry = kwargs.get("telemetry")
    if telemetry is not None:
        telemetry("http_attempt", 1)
    parsed = {
        "message": "shared-message",
        "action": "stay",
        "direction": "",
        "memory": "",
        "reasoning": "shared-reasoning",
    }
    return parsed, json.dumps(parsed)


def syntax_failure_llm(**kwargs):
    telemetry = kwargs.get("telemetry")
    if telemetry is not None:
        telemetry("http_attempt", 2)
        telemetry("generation_retry", 1)
        telemetry("syntax_parse_attempt_failure", 2)
    return None, "not-json"


class ValidateRunTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.output_root = Path(self.temp_directory.name)

        git_info = {
            "git_sha": "b" * 40,
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
        self.git_patch = mock.patch(
            "engine.provenance.collect_git_info", return_value=git_info
        )
        self.gpu_patch = mock.patch(
            "engine.provenance.collect_gpu_info", return_value=gpu_info
        )
        self.git_patch.start()
        self.gpu_patch.start()
        self.addCleanup(self.git_patch.stop)
        self.addCleanup(self.gpu_patch.stop)

    def create_fixture(
        self,
        run_id: str,
        config: dict | None = None,
        llm=offline_llm,
    ) -> Path:
        fixture_config = config or make_config(run_id)
        with mock.patch("engine.sim.call_ollama", side_effect=llm):
            with contextlib.redirect_stdout(io.StringIO()):
                simulation = Simulation(
                    fixture_config,
                    output_root=self.output_root,
                    repo_root=REPO_ROOT,
                )
                simulation.run()
        return Path(simulation.output_dir)

    def test_strict_fixture_passes_and_reports_unverifiable_limits(self):
        run_dir = self.create_fixture("validator-pass")

        report = validate_run(run_dir, strict=True)
        self.assertTrue(report.valid, report.errors)
        self.assertFalse(report.errors)
        self.assertTrue(report.unverifiable)
        self.assertTrue(
            any("event_id" in message for message in report.unverifiable),
            report.unverifiable,
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = validator_main([str(run_dir), "--strict"])
        rendered = output.getvalue()
        self.assertEqual(exit_code, 0, rendered)
        self.assertIn("PASS:", rendered)
        self.assertIn("UNVERIFIABLE:", rendered)

    def test_missing_required_raw_file_fails(self):
        run_dir = self.create_fixture("validator-missing")
        (run_dir / "messages.jsonl").unlink()

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any("required raw files are missing" in error for error in report.errors),
            report.errors,
        )

    def test_raw_modification_fails_manifest_validation(self):
        run_dir = self.create_fixture("validator-tampered")
        raw_path = run_dir / "phase1_raw.jsonl"
        with raw_path.open("a", encoding="utf-8") as handle:
            handle.write('{"tampered":true}\n')

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any("raw manifest mismatch" in error for error in report.errors),
            report.errors,
        )

    def test_manifest_counts_reject_boolean_values(self):
        run_dir = self.create_fixture("validator-manifest-types")
        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        empty_entry = meta["raw_manifest"]["files"]["messages.jsonl"]
        self.assertEqual(empty_entry["bytes"], 0)
        self.assertEqual(empty_entry["lines"], 0)
        empty_entry["bytes"] = False
        empty_entry["lines"] = False
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any(
                "must be a non-negative integer" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_duplicate_natural_key_fails_after_manifest_is_recomputed(self):
        run_dir = self.create_fixture("validator-duplicate")
        raw_path = run_dir / "phase1_raw.jsonl"
        first_line = raw_path.read_text(encoding="utf-8").splitlines()[0]
        with raw_path.open("a", encoding="utf-8") as handle:
            handle.write(first_line + "\n")

        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["raw_manifest"]["files"][raw_path.name] = file_manifest(raw_path)
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertFalse(
            any("raw manifest mismatch" in error for error in report.errors),
            report.errors,
        )
        self.assertTrue(
            any("duplicates natural key" in error for error in report.errors),
            report.errors,
        )

    def test_message_must_match_phase1_after_manifest_is_recomputed(self):
        config = make_config("validator-message-tamper")
        config["blocs"][0]["num_agents"] = 2
        config["agents"]["communication_radius"] = 100
        run_dir = self.create_fixture(
            "validator-message-tamper",
            config=config,
            llm=nonempty_message_llm,
        )
        message_path = run_dir / "messages.jsonl"
        records = [
            json.loads(line)
            for line in message_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(records)
        records[0]["message"] = "TAMPERED_NOT_IN_PHASE1"
        message_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["raw_manifest"]["files"][message_path.name] = file_manifest(
            message_path
        )
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any("differs from the matching Phase 1" in error for error in report.errors),
            report.errors,
        )

    def test_deleted_message_fails_after_manifest_is_recomputed(self):
        config = make_config("validator-message-deleted")
        config["blocs"][0]["num_agents"] = 2
        config["agents"]["communication_radius"] = 100
        run_dir = self.create_fixture(
            "validator-message-deleted",
            config=config,
            llm=nonempty_message_llm,
        )
        message_path = run_dir / "messages.jsonl"
        lines = message_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        message_path.write_text(lines[1] + "\n", encoding="utf-8")

        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["raw_manifest"]["files"][message_path.name] = file_manifest(
            message_path
        )
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertFalse(
            any("raw manifest mismatch" in error for error in report.errors),
            report.errors,
        )
        self.assertTrue(
            any(
                "expected message natural keys" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_receiver_subset_fails_after_manifest_is_recomputed(self):
        config = make_config("validator-receiver-subset")
        config["blocs"][0]["num_agents"] = 3
        config["agents"]["communication_radius"] = 100
        run_dir = self.create_fixture(
            "validator-receiver-subset",
            config=config,
            llm=nonempty_message_llm,
        )
        message_path = run_dir / "messages.jsonl"
        records = [
            json.loads(line)
            for line in message_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(records[0]["receiver_ids"], [1, 2])
        records[0]["receiver_ids"] = [1]
        message_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["raw_manifest"]["files"][message_path.name] = file_manifest(
            message_path
        )
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertFalse(
            any("raw manifest mismatch" in error for error in report.errors),
            report.errors,
        )
        self.assertTrue(
            any(
                "reconstructed communication boundary" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_unexpected_message_fails_after_manifest_is_recomputed(self):
        config = make_config("validator-message-unexpected")
        config["blocs"][0]["num_agents"] = 2
        config["agents"]["communication_radius"] = 0
        run_dir = self.create_fixture(
            "validator-message-unexpected",
            config=config,
            llm=nonempty_message_llm,
        )
        message_path = run_dir / "messages.jsonl"
        self.assertEqual(message_path.read_text(encoding="utf-8"), "")
        message_path.write_text(
            json.dumps({
                "step": 1,
                "sender_id": 0,
                "sender_bloc": "alpha",
                "sender_model": "mock-model",
                "receiver_ids": [1],
                "message": "shared-message",
                "reasoning": "shared-reasoning",
            }) + "\n",
            encoding="utf-8",
        )

        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["raw_manifest"]["files"][message_path.name] = file_manifest(
            message_path
        )
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any(
                "unexpected message natural keys" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_message_reconstruction_exception_fails_closed(self):
        run_dir = self.create_fixture("validator-message-reconstruct-error")
        with mock.patch(
            "tools.validate_run.World",
            side_effect=RuntimeError("must-not-be-reported"),
        ):
            report = validate_run(run_dir, strict=True)

        self.assertFalse(report.valid)
        self.assertTrue(
            any(
                error == "cannot reconstruct expected messages: RuntimeError"
                for error in report.errors
            ),
            report.errors,
        )
        self.assertNotIn("must-not-be-reported", "\n".join(report.errors))

    def test_parse_failure_threshold_boundary_passes(self):
        config = make_config("validator-parse-threshold-pass")
        config["simulation"]["failure_thresholds"] = {
            "transport_failures": 0,
            "syntax_parse_failures": 2,
            "schema_validation_failures": 0,
        }
        run_dir = self.create_fixture(
            "validator-parse-threshold-pass",
            config=config,
            llm=syntax_failure_llm,
        )

        report = validate_run(run_dir, strict=True)
        self.assertTrue(report.valid, report.errors)

    def test_parse_failure_above_threshold_fails(self):
        config = make_config("validator-parse-threshold-fail")
        config["simulation"]["failure_thresholds"] = {
            "transport_failures": 0,
            "syntax_parse_failures": 1,
            "schema_validation_failures": 0,
        }
        run_dir = self.create_fixture(
            "validator-parse-threshold-fail",
            config=config,
            llm=syntax_failure_llm,
        )

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any("syntax_parse_failures exceeds threshold" in error for error in report.errors),
            report.errors,
        )

    def test_unavailable_dependency_and_cuda_probes_are_explicit(self):
        run_dir = self.create_fixture("validator-partial-provenance")
        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        dependency_names = list(meta["dependencies"])
        meta["dependencies"] = {name: None for name in dependency_names}
        meta["dependencies_probe_status"] = "unavailable"
        meta["dependencies_probe_errors"] = [
            f"{name}:version_unavailable" for name in dependency_names
        ]
        meta["gpu_info"] = {
            "status": "available",
            "error": "cuda_version_not_reported",
            "driver_version": "999.0",
            "cuda_version": None,
            "cuda_probe_status": "unavailable",
            "cuda_probe_error": "cuda_version_not_reported",
            "malformed_device_rows": 0,
            "devices": [{
                "index": "0",
                "name": "mock-gpu",
                "uuid": "GPU-mock",
                "memory_total_mib": "1024",
            }],
        }
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertTrue(report.valid, report.errors)
        rendered = "\n".join(report.unverifiable)
        self.assertIn("dependency environment", rendered)
        self.assertIn("CUDA version", rendered)

    def test_partial_gpu_inventory_is_explicitly_unverifiable(self):
        run_dir = self.create_fixture("validator-partial-gpu")
        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["gpu_info"] = {
            "status": "partial",
            "error": "malformed_device_rows",
            "driver_version": "999.0",
            "cuda_version": "99.0",
            "cuda_probe_status": "available",
            "cuda_probe_error": None,
            "malformed_device_rows": 1,
            "devices": [{
                "index": "0",
                "name": "mock-gpu",
                "uuid": "GPU-mock",
                "memory_total_mib": "1024",
            }],
        }
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertTrue(report.valid, report.errors)
        self.assertTrue(
            any("complete GPU inventory" in item for item in report.unverifiable),
            report.unverifiable,
        )

    def test_available_gpu_cannot_silently_report_malformed_rows(self):
        run_dir = self.create_fixture("validator-silent-partial-gpu")
        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["gpu_info"] = {
            "status": "available",
            "error": None,
            "driver_version": "999.0",
            "cuda_version": "99.0",
            "cuda_probe_status": "available",
            "cuda_probe_error": None,
            "malformed_device_rows": 1,
            "devices": [{
                "index": "0",
                "name": "mock-gpu",
                "uuid": "GPU-mock",
                "memory_total_mib": "1024",
            }],
        }
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any("cannot contain malformed" in item for item in report.errors),
            report.errors,
        )

    def test_blank_dependency_version_fails(self):
        run_dir = self.create_fixture("validator-blank-dependency")
        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["dependencies"] = {
            name: "" for name in meta["dependencies"]
        }
        meta["dependencies_probe_status"] = "available"
        meta["dependencies_probe_errors"] = []
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        report = validate_run(run_dir, strict=True)
        self.assertFalse(report.valid)
        self.assertTrue(
            any(
                "non-empty version strings" in error
                for error in report.errors
            ),
            report.errors,
        )

    def test_real_validator_subprocess_returns_zero(self):
        run_dir = self.create_fixture("validator-subprocess")
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        completed = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                str(run_dir),
                "--strict",
            ],
            cwd=str(REPO_ROOT),
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("PASS:", completed.stdout)
        self.assertIn("UNVERIFIABLE:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
