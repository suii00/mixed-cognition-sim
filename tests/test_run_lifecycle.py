import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import main as cli_main
import yaml
from engine.llm_client import LLMTransportError
from engine.provenance import (
    RAW_JSONL_FILES,
    RunCollisionError,
    RunLifecycleError,
)
from engine.sim import Simulation, SimulationAbortedError


REPO_ROOT = Path(__file__).resolve().parents[1]


def make_config(run_id: str = "test-run") -> dict:
    return {
        "simulation": {
            "duration": 1,
            "half_space_size": 2,
            "seed": 42,
            "run_name": "test_run",
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


def successful_llm(**kwargs):
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


def load_meta(output_dir: Path) -> dict:
    with (output_dir / "run_meta.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def directory_hashes(output_dir: Path) -> dict:
    hashes = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(output_dir))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashes


class RunLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.output_root = Path(self.temp_directory.name)

        git_info = {
            "git_sha": "a" * 40,
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

    def new_simulation(self, run_id: str) -> Simulation:
        return Simulation(
            make_config(run_id),
            output_root=self.output_root,
            repo_root=REPO_ROOT,
        )

    def test_new_run_is_created_and_completed(self):
        with mock.patch("engine.sim.call_ollama", side_effect=successful_llm):
            simulation = self.new_simulation("new-completed-run")
            output_dir = self.output_root / "output_new-completed-run"
            running_meta = load_meta(output_dir)
            self.assertEqual(running_meta["status"], "running")
            self.assertIsNone(running_meta["end_time_utc"])
            for filename in RAW_JSONL_FILES:
                self.assertTrue((output_dir / filename).is_file())
            simulation.run()

        self.assertEqual(Path(simulation.output_dir), output_dir)
        self.assertTrue(output_dir.is_dir())
        meta = load_meta(output_dir)
        self.assertEqual(meta["run_id"], "new-completed-run")
        self.assertEqual(meta["status"], "completed")
        self.assertFalse(meta["aborted"])
        self.assertEqual(meta["expected_steps"], 1)
        self.assertEqual(meta["completed_steps"], 1)
        self.assertEqual(meta["expected_agents"], 1)
        self.assertEqual(meta["observed_agents"], 1)

    def test_missing_config_run_id_generates_and_persists_one(self):
        config = make_config()
        del config["simulation"]["run_id"]
        with mock.patch("engine.sim.call_ollama", side_effect=successful_llm):
            simulation = Simulation(
                config,
                output_root=self.output_root,
                repo_root=REPO_ROOT,
            )
            simulation.run()

        output_dir = Path(simulation.output_dir)
        meta = load_meta(output_dir)
        self.assertEqual(meta["run_id"], simulation.run_id)
        self.assertEqual(output_dir.name, f"output_{simulation.run_id}")
        self.assertNotIn("run_id", meta["config"]["simulation"])

    def test_failed_completed_meta_replace_never_reports_completed(self):
        simulation = self.new_simulation("atomic-finalize-failure")

        from engine import provenance

        real_atomic_write = provenance.atomic_write_json

        def fail_completed(path, value):
            if value.get("status") == "completed":
                raise OSError("synthetic atomic replace failure")
            return real_atomic_write(path, value)

        with (
            mock.patch("engine.sim.call_ollama", side_effect=successful_llm),
            mock.patch(
                "engine.provenance.atomic_write_json",
                side_effect=fail_completed,
            ),
        ):
            with self.assertRaisesRegex(OSError, "atomic replace"):
                simulation.run()

        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["aborted"])
        self.assertNotEqual(meta["status"], "completed")

    def test_missing_required_raw_file_cannot_complete(self):
        simulation = self.new_simulation("missing-raw-finalize")
        (Path(simulation.output_dir) / "messages.jsonl").unlink()

        with mock.patch("engine.sim.call_ollama", side_effect=successful_llm):
            with self.assertRaisesRegex(RunLifecycleError, "missing required raw"):
                simulation.run()

        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["aborted"])

    def test_manifest_hash_failure_still_persists_failed_meta(self):
        simulation = self.new_simulation("manifest-hash-failure")

        with (
            mock.patch("engine.sim.call_ollama", side_effect=successful_llm),
            mock.patch(
                "engine.provenance.build_raw_manifest",
                side_effect=OSError("synthetic hash failure"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "synthetic hash failure"):
                simulation.run()

        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["aborted"])
        self.assertIsNone(meta["raw_manifest"])
        self.assertEqual(meta["raw_manifest_status"], "unavailable")
        self.assertEqual(meta["raw_manifest_error"], "raw_manifest_hash_failed")

    def test_collision_happens_before_llm_and_preserves_first_run(self):
        config = make_config("fixed-collision-run")
        with mock.patch("engine.sim.call_ollama", side_effect=successful_llm):
            first = Simulation(
                config,
                output_root=self.output_root,
                repo_root=REPO_ROOT,
            )
            first.run()

        output_dir = self.output_root / "output_fixed-collision-run"
        before = directory_hashes(output_dir)

        with mock.patch("engine.sim.call_ollama") as llm_mock:
            with self.assertRaises(RunCollisionError):
                Simulation(
                    config,
                    output_root=self.output_root,
                    repo_root=REPO_ROOT,
                )
            llm_mock.assert_not_called()

        self.assertEqual(directory_hashes(output_dir), before)

    def test_transport_abort_leaves_aborted_meta(self):
        simulation = self.new_simulation("transport-abort-run")

        def transport_failure(**kwargs):
            telemetry = kwargs.get("telemetry")
            for _ in range(3):
                telemetry("http_attempt", 1)
                telemetry("transport_failure", 1)
            raise LLMTransportError("synthetic transport failure")

        with mock.patch(
            "engine.sim.call_ollama",
            side_effect=transport_failure,
        ):
            with self.assertRaises(SimulationAbortedError):
                simulation.run()

        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "aborted")
        self.assertTrue(meta["aborted"])
        self.assertEqual(meta["abort_reason"], "transport_failure")
        self.assertEqual(meta["failure_step"], 1)
        self.assertEqual(meta["failure_phase"], "phase1")
        self.assertEqual(meta["failure_agent_id"], 0)
        self.assertEqual(meta["completed_steps"], 0)
        self.assertEqual(meta["logical_llm_calls"], 1)
        self.assertEqual(meta["http_attempts"], 3)
        self.assertEqual(meta["transport_failures"], 3)

    def test_unhandled_exception_leaves_failed_meta_and_is_reraised(self):
        simulation = self.new_simulation("unexpected-failure-run")
        with mock.patch(
            "engine.sim.call_ollama", side_effect=RuntimeError("synthetic bug")
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic bug"):
                simulation.run()

        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["aborted"])
        self.assertEqual(meta["abort_reason"], "unhandled_exception")
        self.assertEqual(meta["failure_exception_type"], "RuntimeError")
        self.assertEqual(meta["failure_step"], 1)
        self.assertEqual(meta["failure_phase"], "phase1")
        self.assertEqual(meta["failure_agent_id"], 0)

    def test_startup_output_exception_leaves_failed_meta(self):
        simulation = self.new_simulation("stdout-failure-run")
        with mock.patch("builtins.print", side_effect=OSError("closed pipe")):
            with self.assertRaisesRegex(OSError, "closed pipe"):
                simulation.run()

        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["aborted"])
        self.assertEqual(meta["abort_reason"], "unhandled_exception")
        self.assertEqual(meta["failure_exception_type"], "OSError")

    def test_zero_bloc_run_is_rejected_before_output_creation(self):
        config = make_config("zero-bloc-run")
        config["blocs"] = []

        with self.assertRaises(ValueError):
            Simulation(
                config,
                output_root=self.output_root,
                repo_root=REPO_ROOT,
            )

        self.assertFalse((self.output_root / "output_zero-bloc-run").exists())

    def test_keyboard_interrupt_leaves_aborted_meta(self):
        simulation = self.new_simulation("keyboard-interrupt-run")
        with mock.patch("engine.sim.call_ollama", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                simulation.run()

        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "aborted")
        self.assertTrue(meta["aborted"])
        self.assertEqual(meta["abort_reason"], "keyboard_interrupt")
        self.assertEqual(meta["failure_exception_type"], "KeyboardInterrupt")
        self.assertEqual(meta["failure_step"], 1)
        self.assertEqual(meta["failure_phase"], "phase1")
        self.assertEqual(meta["failure_agent_id"], 0)

    def test_mkdir_interrupt_after_creation_leaves_aborted_meta(self):
        config = make_config("mkdir-interrupt-run")
        output_dir = self.output_root / "output_mkdir-interrupt-run"
        real_mkdir = Path.mkdir

        def create_then_interrupt(path, *args, **kwargs):
            real_mkdir(path, *args, **kwargs)
            raise KeyboardInterrupt

        with mock.patch.object(
            Path,
            "mkdir",
            autospec=True,
            side_effect=create_then_interrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                Simulation(
                    config,
                    output_root=self.output_root,
                    repo_root=REPO_ROOT,
                )

        meta = load_meta(output_dir)
        self.assertEqual(meta["status"], "aborted")
        self.assertTrue(meta["aborted"])
        self.assertEqual(meta["abort_reason"], "keyboard_interrupt")
        self.assertEqual(meta["failure_exception_type"], "KeyboardInterrupt")

    def test_mkdir_system_exit_after_creation_leaves_failed_meta(self):
        config = make_config("mkdir-system-exit-run")
        output_dir = self.output_root / "output_mkdir-system-exit-run"
        real_mkdir = Path.mkdir

        def create_then_exit(path, *args, **kwargs):
            real_mkdir(path, *args, **kwargs)
            raise SystemExit(0)

        with mock.patch.object(
            Path,
            "mkdir",
            autospec=True,
            side_effect=create_then_exit,
        ):
            with self.assertRaises(SystemExit) as raised:
                Simulation(
                    config,
                    output_root=self.output_root,
                    repo_root=REPO_ROOT,
                )

        self.assertEqual(raised.exception.code, 0)
        meta = load_meta(output_dir)
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["aborted"])
        self.assertEqual(
            meta["abort_reason"], "run_directory_creation_failure"
        )
        self.assertEqual(meta["failure_exception_type"], "SystemExit")

    def test_system_exit_zero_leaves_failed_meta(self):
        simulation = self.new_simulation("system-exit-zero-run")
        with mock.patch("engine.sim.call_ollama", side_effect=SystemExit(0)):
            with self.assertRaises(SystemExit) as raised:
                simulation.run()

        self.assertEqual(raised.exception.code, 0)
        meta = load_meta(Path(simulation.output_dir))
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["aborted"])
        self.assertEqual(meta["failure_exception_type"], "SystemExit")


class CliExitCodeTests(unittest.TestCase):
    def test_invalid_config_returns_two(self):
        with mock.patch.object(
            cli_main, "load_config", side_effect=ValueError("invalid")
        ):
            self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 2)

    def test_invalid_yaml_returns_two(self):
        with mock.patch.object(
            cli_main, "load_config", side_effect=yaml.YAMLError("invalid yaml")
        ):
            self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 2)

    def test_invalid_run_id_returns_two_before_llm(self):
        with mock.patch.object(
            cli_main, "load_config", return_value=make_config("../escape")
        ):
            with mock.patch("engine.sim.call_ollama") as llm_mock:
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 2)
                llm_mock.assert_not_called()

    def test_collision_returns_two(self):
        with mock.patch.object(cli_main, "load_config", return_value=make_config()):
            with mock.patch.object(
                cli_main,
                "Simulation",
                side_effect=RunCollisionError("collision"),
            ):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 2)

    def test_controlled_transport_abort_returns_one(self):
        simulation = mock.Mock()
        simulation.run.side_effect = SimulationAbortedError("transport abort")
        with mock.patch.object(cli_main, "load_config", return_value=make_config()):
            with mock.patch.object(cli_main, "Simulation", return_value=simulation):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 1)

    def test_keyboard_interrupt_returns_130(self):
        simulation = mock.Mock()
        simulation.run.side_effect = KeyboardInterrupt
        with mock.patch.object(cli_main, "load_config", return_value=make_config()):
            with mock.patch.object(cli_main, "Simulation", return_value=simulation):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 130)

    def test_system_exit_zero_during_run_returns_nonzero(self):
        simulation = mock.Mock()
        simulation.run.side_effect = SystemExit(0)
        with mock.patch.object(cli_main, "load_config", return_value=make_config()):
            with mock.patch.object(cli_main, "Simulation", return_value=simulation):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 1)

    def test_system_exit_zero_during_start_returns_nonzero(self):
        with mock.patch.object(cli_main, "load_config", return_value=make_config()):
            with mock.patch.object(cli_main, "Simulation", side_effect=SystemExit(0)):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 1)

    def test_unhandled_exception_is_reraised(self):
        simulation = mock.Mock()
        simulation.run.side_effect = RuntimeError("unexpected")
        with mock.patch.object(cli_main, "load_config", return_value=make_config()):
            with mock.patch.object(cli_main, "Simulation", return_value=simulation):
                with self.assertRaisesRegex(RuntimeError, "unexpected"):
                    cli_main.main(["--config", "ignored.yaml"])

    def test_success_requires_completed_meta(self):
        completed = mock.Mock()
        completed.run_lifecycle = SimpleNamespace(
            meta={"status": "completed", "aborted": False}
        )
        incomplete = mock.Mock()
        incomplete.run_lifecycle = SimpleNamespace(
            meta={"status": "running", "aborted": False}
        )
        contradictory = mock.Mock()
        contradictory.run_lifecycle = SimpleNamespace(
            meta={"status": "completed", "aborted": True}
        )
        with mock.patch.object(cli_main, "load_config", return_value=make_config()):
            with mock.patch.object(cli_main, "Simulation", return_value=completed):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 0)
            with mock.patch.object(cli_main, "Simulation", return_value=incomplete):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 1)
            with mock.patch.object(
                cli_main, "Simulation", return_value=contradictory
            ):
                self.assertEqual(cli_main.main(["--config", "ignored.yaml"]), 1)


if __name__ == "__main__":
    unittest.main()
