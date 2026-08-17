import contextlib
import io
import json
import shutil
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools import gate4_endpoint_reuse_orchestrator as orchestrator
from tools import gate4_evidence_publisher as publisher
from tools import validate_gate4_ollama_endpoint_reuse as validator
from tools import verify_gate4_evidence_bundle as independent


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "a" * 40
DIGESTS = {
    "qwen": "59805ce4a4046be2d8f63231a78daacd2e66f5dccf1a64d0d138ebeeb26ff16c",
    "llama": "4aacac4194543ff7f70dab3f2ebc169c132d5319bb36f7a7e99c4ff525ebcc09",
    "gemma": "28e6684b085085f78551db7c96a9daa546161b1da9d055ea01b84cb1163013cf",
}
GPU_UUIDS = {
    "qwen": "GPU-720e6563-7e95-65c4-659e-189ba0c7bac5",
    "llama": "GPU-2964f342-8734-a701-a2c6-4344579b03ee",
    "gemma": "GPU-af1ef9b0-329f-ff38-d4dd-062e2beca9e0",
}


class FakeBackend:
    def __init__(self, scenario="success"):
        self.scenario = scenario
        self.generation_count = 0
        self.unload_count = 0
        self.cleanup_called = False
        self.generation_sequence = []
        self._warning_events = []

    @staticmethod
    def _log_line(level, source_line, message, **attributes):
        suffix = "".join(f" {key}={value}" for key, value in attributes.items())
        return (
            "time=2026-08-17T12:00:00+00:00 "
            f"level={level} source=runner.go:{source_line} "
            f"msg={json.dumps(message)}{suffix}\n"
        )

    def _logs_for_scenario(self, approval):
        logs = {role: b"" for role in validator.ROLE_ORDER}
        if self.scenario in {
            "known_warning",
            "error_with_approved_warning",
            "fatal_with_approved_warning",
        }:
            for endpoint in approval["endpoints"]:
                role = endpoint["model_role"]
                text = self._log_line(
                    "WARN",
                    722,
                    "user overrode visible devices",
                    CUDA_VISIBLE_DEVICES=endpoint["gpu_uuid"],
                )
                text += self._log_line(
                    "WARN",
                    726,
                    "if GPUs are not correctly discovered, unset and try again",
                )
                logs[role] = text.encode("utf-8")
        if self.scenario == "unknown_warning":
            logs["qwen"] = self._log_line("WARN", 999, "new warning").encode()
        elif self.scenario == "error_with_approved_warning":
            logs["qwen"] = (
                self._log_line("ERROR", 900, "request failure").encode()
                + logs["qwen"]
            )
        elif self.scenario == "fatal_with_approved_warning":
            logs["qwen"] = (
                self._log_line("FATAL", 901, "synthetic fatal event").encode()
                + logs["qwen"]
            )
        return logs

    @staticmethod
    def _server_pid(role):
        return {"qwen": 2101, "llama": 2102, "gemma": 2103}[role]

    @staticmethod
    def _command(command, stdout=""):
        return {
            "command": list(command),
            "exit_code": 0,
            "stdout": stdout,
            "stderr": "",
        }

    @classmethod
    def _gpu_observation(cls, approval, loaded_roles=()):
        selected = {
            endpoint["model_role"]: endpoint["gpu_uuid"]
            for endpoint in approval["endpoints"]
        }
        all_uuids = [selected["qwen"]]
        all_uuids.extend(f"GPU-00000000-0000-0000-0000-{index:012d}" for index in range(1, 6))
        all_uuids.extend([selected["llama"], selected["gemma"]])
        compute_rows = [
            {
                "gpu_uuid": selected[role],
                "pid": cls._server_pid(role) + 1000,
                "used_memory_mib": 10000,
            }
            for role in loaded_roles
        ]
        return {
            "gpu_rows": [
                {
                    "uuid": uuid,
                    "memory_used_mib": 1 if uuid not in {row["gpu_uuid"] for row in compute_rows} else 10001,
                    "utilization_gpu": 0,
                }
                for uuid in all_uuids
            ],
            "compute_rows": compute_rows,
            "commands": [cls._command(["nvidia-smi", "synthetic"])],
        }

    def preflight(self, approval, attempt_dir):
        if self.scenario == "keyboard_interrupt":
            raise KeyboardInterrupt
        artifacts = []
        for endpoint in approval["endpoints"]:
            artifacts.append(
                {
                    "role": endpoint["model_role"],
                    "model_tag": endpoint["model_tag"],
                    "model_digest": endpoint["model_digest"],
                    "quantization": "F16",
                    "template": f"template-{endpoint['model_role']}",
                }
            )
        selected = [endpoint["gpu_uuid"] for endpoint in approval["endpoints"]]
        if self.scenario == "preflight_gpu_mismatch":
            selected[-1] = "GPU-wrong-preflight"
        if self.scenario == "preflight_digest_mismatch":
            artifacts[-1]["model_digest"] = "0" * 64
        return {
            "passed": True,
            "selected_gpu_uuids": selected,
            "ports_free": [11440, 11441, 11442],
            "model_artifacts": artifacts,
            "existing_service": {
                "port": 11434,
                "pid": approval["existing_ollama_pid_before"],
                "start_time_ticks": 100,
                "command": "/usr/local/bin/ollama serve",
                "version": "0.32.13",
                "ps_models": [],
            },
            "nvidia_smi_L": self._command(
                ["nvidia-smi", "-L"],
                "\n".join(selected),
            ),
            "gpu_observation": self._gpu_observation(approval),
            "sudo_check": self._command(["sudo", "-n", "/usr/bin/true"]),
            "ollama_cli_version": self._command(
                [approval["ollama_binary"], "--version"],
                "ollama version is 0.32.13\n",
            ),
        }

    def start_servers(self, approval, attempt_dir, preflight):
        log_root = attempt_dir / "server-logs"
        log_root.mkdir(parents=True, exist_ok=True)
        logs = self._logs_for_scenario(approval)
        for role in validator.ROLE_ORDER:
            (log_root / f"{role}.log").write_bytes(logs[role])
        self._warning_events = []
        for role in validator.ROLE_ORDER:
            self._warning_events.extend(
                validator.parse_ollama_diagnostic_stream(role, logs[role])
            )
        servers = []
        for index, endpoint in enumerate(approval["endpoints"]):
            role = endpoint["model_role"]
            command = validator._expected_launch_command(approval, endpoint)
            artifact = next(
                item for item in preflight["model_artifacts"] if item["role"] == role
            )
            servers.append({
                "role": endpoint["model_role"],
                "port": endpoint["port"],
                "gpu_uuid": endpoint["gpu_uuid"],
                "launcher_pid": self._server_pid(endpoint["model_role"]) - 100,
                "server_pid": self._server_pid(endpoint["model_role"]),
                "start_time_ticks": 200 + index,
                "server_command": "/usr/local/bin/ollama serve",
                "version": "0.32.13",
                "launch_command": command,
                "initial_ps_models": [],
                "model_artifact": artifact,
            })
        return servers

    def generate(self, approval, endpoint, server, request_payload):
        self.generation_count += 1
        ordinal = self.generation_count
        phase = (
            "phase1"
            if "Decide what message to send" in request_payload["messages"][0]["content"]
            else "phase3"
        )
        self.generation_sequence.append((phase, endpoint["model_role"]))
        if self.scenario == "timeout_first" and ordinal == 1:
            raise TimeoutError("synthetic approved request timeout")
        if self.scenario == "slow":
            time.sleep(0.21)
        phase1 = phase == "phase1"
        parsed = (
            {"message": f"message-{ordinal}", "reasoning": "synthetic"}
            if phase1
            else {
                "action": "stay",
                "direction": "",
                "memory": f"memory-{ordinal}",
                "reasoning": "synthetic",
            }
        )
        if self.scenario == "parse_failure" and ordinal == 1:
            parsed = None
            raw_output = "not json"
        else:
            raw_output = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        envelope = {
            "model": endpoint["model_tag"],
            "message": {"role": "assistant", "content": raw_output},
            "done": True,
            "done_reason": "stop",
            "total_duration": 10,
            "load_duration": 2,
            "prompt_eval_count": 3,
            "prompt_eval_duration": 4,
            "eval_count": 5,
            "eval_duration": 6,
        }
        status = 503 if self.scenario == "initial_http_failure" and ordinal == 1 else 200
        telemetry = {
            "http_attempts": 1,
            "generation_retries": 0,
            "transport_failures": 0,
            "syntax_parse_failures": 0 if parsed is not None else 1,
        }
        if self.scenario == "retry" and ordinal == 1:
            telemetry["http_attempts"] = 2
            telemetry["generation_retries"] = 1
        return {
            "status_code": status,
            "raw_body": json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(),
            "envelope": envelope,
            "parsed": parsed,
            "raw_output": raw_output,
            "telemetry": telemetry,
        }

    def snapshot(self, approval, endpoint, server, stage):
        role = endpoint["model_role"]
        size = 10_000 + self.generation_count
        model = {
            "name": endpoint["model_tag"],
            "digest": endpoint["model_digest"],
            "context_length": 4096,
            "size": size,
            "size_vram": size,
        }
        runner_pid = server["server_pid"] + 1000
        gpu = self._gpu_observation(approval, validator.ROLE_ORDER)
        value = {
            "role": role,
            "port": endpoint["port"],
            "server_pid": server["server_pid"],
            "runner_pid": runner_pid,
            "gpu_uuid": endpoint["gpu_uuid"],
            "model_tag": endpoint["model_tag"],
            "model_digest": endpoint["model_digest"],
            "quantization": "F16",
            "context_length": 4096,
            "size": size,
            "size_vram": size,
            "processor": "100% GPU",
            "loaded_models": 1,
            "runner_gpu_uuids": [endpoint["gpu_uuid"]],
            "api_ps": {"models": [model]},
            "api_show": {
                "details": {"quantization_level": "F16"},
                "template": f"template-{role}",
            },
            "ollama_ps": self._command(
                ["ollama", "ps"],
                f"{endpoint['model_tag']} 100% GPU\n",
            ),
            "gpu_observation": gpu,
            "runner_process": {
                "pid": runner_pid,
                "ppid": server["server_pid"],
                "user": "ollama",
                "args": "/usr/local/lib/ollama/llama-server --synthetic",
            },
        }
        if stage == "phase3" and role == "gemma":
            if self.scenario == "server_pid_change":
                value["server_pid"] += 99
            elif self.scenario == "reload_gpu_change":
                value["gpu_uuid"] = "GPU-wrong-reload"
                value["runner_gpu_uuids"] = ["GPU-wrong-reload"]
            elif self.scenario == "reload_digest_change":
                value["model_digest"] = "f" * 64
            elif self.scenario == "reload_context_change":
                value["context_length"] = 8192
            elif self.scenario == "reload_offload":
                value["size_vram"] = value["size"] - 1
                value["processor"] = "90% GPU"
            elif self.scenario == "unexpected_eviction":
                value["loaded_models"] = 0
        if stage == "stability" and role == "gemma" and self.scenario == "stability_pid_change":
            value["runner_pid"] += 77
            value["runner_process"]["pid"] = value["runner_pid"]
        return value

    def unload(self, approval, endpoint, server, stage):
        self.unload_count += 1
        models = []
        if self.scenario == "unload_incomplete" and stage == "between_phases" and self.unload_count == 1:
            models = [{"name": endpoint["model_tag"]}]
        return {
            "role": endpoint["model_role"],
            "port": endpoint["port"],
            "model_tag": endpoint["model_tag"],
            "status_code": 200,
            "done": True,
            "done_reason": "unload",
            "ps_models_after": models,
        }

    def cleanup(self, approval, attempt_dir, preflight, servers):
        self.cleanup_called = True
        final_unloads = [
            {
                "role": endpoint["model_role"],
                "port": endpoint["port"],
                "model_tag": endpoint["model_tag"],
                "status_code": 200,
                "done": True,
                "done_reason": "unload",
                "ps_models_after": [],
            }
            for endpoint in approval["endpoints"]
        ]
        if self.scenario == "final_unload_done_false":
            final_unloads[0]["done"] = False
        gpu_idle = [
            {
                "uuid": f"GPU-synthetic-{index}",
                "memory_used_mib": 1,
                "utilization_gpu": 0,
                "compute_pids": [],
            }
            for index in range(8)
        ]
        existing_pid = approval["existing_ollama_pid_before"]
        if self.scenario == "existing_service_changed":
            existing_pid += 1
        passed = self.scenario != "cleanup_failure"
        value = {
            "passed": passed,
            "errors": [] if passed else ["synthetic cleanup failure"],
            "temporary_ports_closed": [11440, 11441, 11442],
            "temporary_server_pids_absent": sorted(
                server["server_pid"] for server in servers
            ),
            "temporary_runner_pids_absent": True,
            "gpu_idle": gpu_idle,
            "existing_service": {
                "port": 11434,
                "pid": existing_pid,
                "start_time_ticks": 100,
                "command": "/usr/local/bin/ollama serve",
                "version": "0.32.13",
                "ps_models": [],
            },
            "final_unloads": final_unloads,
            "termination_commands": [],
            "prohibited_operations": [],
        }
        if self.scenario == "cleanup_missing_port":
            value["temporary_ports_closed"] = [11440, 11441]
        elif self.scenario == "cleanup_server_present":
            value["temporary_server_pids_absent"] = value[
                "temporary_server_pids_absent"
            ][:-1]
        elif self.scenario == "cleanup_runner_present":
            value["temporary_runner_pids_absent"] = False
        elif self.scenario == "cleanup_gpu_busy":
            value["gpu_idle"][0]["memory_used_mib"] = 2048
        elif self.scenario == "cleanup_compute_present":
            value["gpu_idle"][0]["compute_pids"] = [9999]
        return value

    def warning_events(self):
        return list(self._warning_events)


class EndpointReuseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def approval_value(self, approval_id="reuse-synthetic", **overrides):
        evidence_root = self.root / f"evidence-{approval_id}"
        hashes = orchestrator._artifact_hashes(REPO_ROOT)
        endpoints = []
        models = {
            "qwen": (11440, "qwen2.5:7b-instruct-fp16"),
            "llama": (11441, "llama3.1:8b-instruct-fp16"),
            "gemma": (11442, "gemma2:9b-instruct-fp16"),
        }
        for role in validator.ROLE_ORDER:
            port, model = models[role]
            endpoints.append(
                {
                    "port": port,
                    "gpu_uuid": GPU_UUIDS[role],
                    "model_role": role,
                    "model_tag": model,
                    "model_digest": DIGESTS[role],
                }
            )
        value = {
            "schema_version": validator.APPROVAL_SCHEMA_VERSION,
            "approval_id": approval_id,
            "approval_reference": "synthetic CPU approval",
            "approved": True,
            "evidence_bundle_id": approval_id,
            "approved_final_path": str(evidence_root / "published" / approval_id),
            "source_commit_sha": SOURCE_SHA,
            "source_dirty": False,
            **hashes,
            "evidence_root": str(evidence_root),
            "endpoints": endpoints,
            "num_ctx": 4096,
            "num_predict": 256,
            "temperature": 0.2,
            "parallel_per_endpoint": 1,
            "maximum_generation_calls": 6,
            "maximum_wall_seconds": 60,
            "request_timeout_seconds": 10,
            "cleanup_timeout_seconds": 10,
            "stability_wait_seconds": 1,
            "idle_memory_threshold_mib": 16,
            "required_cleanup": True,
            "existing_ollama_port": 11434,
            "existing_ollama_pid_before": 373012,
            "ollama_binary": "/usr/local/bin/ollama",
            "server_user": "ollama",
            "allowed_warning_events": validator.expected_allowed_warning_events(
                {"endpoints": endpoints}
            ),
            "stop_conditions": list(validator.REQUIRED_STOP_CONDITIONS),
        }
        value.update(overrides)
        return value

    def write_approval(self, value):
        path = self.root / f"{value['approval_id']}-approval.json"
        data = validator.canonical_json_bytes(value)
        path.write_bytes(data)
        return path, orchestrator._sha256(data)

    @contextlib.contextmanager
    def cpu_only_runtime(self):
        git_info = {
            "git_sha": SOURCE_SHA,
            "git_dirty": False,
            "git_probe_status": "available",
            "git_probe_errors": [],
        }
        gpu_info = {
            "status": "available",
            "error": None,
            "driver_version": "synthetic",
            "cuda_version": "synthetic",
            "cuda_probe_status": "available",
            "cuda_probe_error": None,
            "malformed_device_rows": 0,
            "devices": [
                {
                    "index": "0",
                    "name": "Synthetic GPU",
                    "uuid": GPU_UUIDS["qwen"],
                    "memory_total_mib": "24564",
                }
            ],
        }
        with (
            mock.patch("engine.provenance.collect_git_info", return_value=git_info),
            mock.patch("engine.provenance.collect_gpu_info", return_value=gpu_info),
            mock.patch("engine.provenance.socket.gethostname", return_value="synthetic-host"),
            mock.patch("engine.provenance.platform_module.system", return_value="SyntheticOS"),
            mock.patch(
                "engine.provenance.platform_module.platform",
                return_value="SyntheticOS-1",
            ),
            mock.patch(
                "tools.gate4_endpoint_reuse_orchestrator.requests.request",
                side_effect=AssertionError("real network forbidden"),
            ),
            mock.patch(
                "tools.gate4_endpoint_reuse_orchestrator.requests.post",
                side_effect=AssertionError("real network forbidden"),
            ),
            mock.patch(
                "tools.gate4_endpoint_reuse_orchestrator.subprocess.Popen",
                side_effect=AssertionError("real process forbidden"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            yield

    @staticmethod
    def source_probe(_repository):
        return orchestrator.SourceState(SOURCE_SHA, False)

    def run_fixture(self, scenario="success", approval=None, backend=None, **run_kwargs):
        value = approval or self.approval_value(
            approval_id=f"reuse-{scenario.replace('_', '-')}"
        )
        path, digest = self.write_approval(value)
        active_backend = backend or FakeBackend(scenario)
        with self.cpu_only_runtime():
            receipt = orchestrator.run_approved_endpoint_reuse(
                path,
                digest,
                repository=REPO_ROOT,
                backend=active_backend,
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
                **run_kwargs,
            )
        return value, path, digest, receipt

    def make_request(self, approval, phase, role, ordinal):
        endpoint = next(
            endpoint
            for endpoint in approval["endpoints"]
            if endpoint["model_role"] == role
        )
        prompt = (
            "Decide what message to send"
            if phase == "phase1"
            else "Decide how to move"
        )
        return SimpleNamespace(
            model=endpoint["model_tag"],
            phase=phase,
            request_id=f"direct-{phase}-{role}-{ordinal}",
            prompt=prompt,
            temperature=approval["temperature"],
            max_tokens=approval["num_predict"],
            llm_overrides={"num_ctx": approval["num_ctx"]},
        )

    def make_transport(self, approval, backend, name="direct", monotonic_fn=lambda: 0.0):
        preflight = backend.preflight(approval, self.root / name)
        servers = backend.start_servers(approval, self.root / name, preflight)
        transcript = orchestrator.Transcript(self.root / f"{name}.jsonl")
        transcript.enter("preflight_passed", {})
        transcript.enter(
            "servers_started",
            {"server_pids": [server["server_pid"] for server in servers]},
        )
        transport = orchestrator.ReuseTransport(
            approval,
            backend,
            servers,
            transcript,
            approval["maximum_wall_seconds"],
            monotonic_fn=monotonic_fn,
        )
        return transport, transcript

    @staticmethod
    def rewrite_persisted_validation(root, *, result, eligible):
        validation_path = Path(root) / validator.VALIDATION_FILENAME
        value = json.loads(validation_path.read_text())
        value["operational_backend_result"] = result
        value["evidence_publication_eligible"] = eligible
        value["errors"] = ["synthetic_persisted_validation_mutation"]
        validation_bytes = validator.canonical_json_bytes(value)
        validation_path.write_bytes(validation_bytes)
        commitment_path = Path(root) / validator.VALIDATION_COMMITMENT_FILENAME
        commitment = json.loads(commitment_path.read_text())
        commitment["workload_validation_sha256"] = orchestrator._sha256(
            validation_bytes
        )
        commitment["operational_backend_result"] = result
        commitment["evidence_publication_eligible"] = eligible
        commitment_path.write_bytes(validator.canonical_json_bytes(commitment))

    def test_successful_six_call_fixture_publishes_and_independently_verifies(self):
        backend = FakeBackend()
        approval, _, digest, receipt = self.run_fixture("success", backend=backend)
        self.assertTrue(receipt.publication_verified)
        self.assertEqual(receipt.operational_backend_result, "PASS")
        self.assertIsNotNone(receipt.final_path)
        validation = json.loads(
            (receipt.attempt_path / validator.VALIDATION_FILENAME).read_text()
        )
        self.assertEqual(validation["operational_backend_result"], "PASS")
        self.assertTrue(validation["evidence_publication_eligible"])
        observations = json.loads(
            (receipt.attempt_path / validator.OBSERVATIONS_FILENAME).read_text()
        )
        self.assertEqual(len(observations["generations"]), 6)
        self.assertEqual(
            observations["execution_gate"],
            {
                "maximum_generation_calls": 6,
                "started_generation_calls": 6,
                "completed_generation_calls": 6,
                "terminal_stop_reason": None,
                "next_expected_phase_role": None,
                "completed_phase_roles": [
                    {"phase": phase, "role": role}
                    for phase, role in orchestrator.EXPECTED_PHASE_ROLE_ORDER
                ],
                "suppressed_requests": [],
            },
        )
        self.assertEqual(
            [(item["phase"], item["role"]) for item in observations["generations"]],
            list(orchestrator.EXPECTED_PHASE_ROLE_ORDER),
        )
        result = json.loads(
            (receipt.attempt_path / validator.RESULT_FILENAME).read_text()
        )
        self.assertEqual(result["state_history"], validator.EXPECTED_STATES)
        published_summary = json.loads(
            (receipt.final_path / publisher.SUMMARY_FILENAME).read_text()
        )
        self.assertEqual(published_summary["operational_backend_result"], "NOT_EVALUATED")
        self.assertFalse(published_summary["gate4_formal_pass"])
        verified = independent.verify_bundle(receipt.final_path)
        self.assertTrue(verified.valid, verified.errors)
        external = json.loads(receipt.receipt_path.read_text())
        self.assertEqual(
            external["state_history"],
            validator.EXPECTED_STATES + ["evidence_published", "evidence_verified"],
        )
        self.assertEqual(external["approval_sha256"], digest)
        self.assertFalse(external["gate4_formal_pass"])
        self.assertFalse(external["research_eligible"])
        self.assertTrue(external["workload_revalidated"])
        self.assertEqual(
            external["workload_validation_sha256"],
            orchestrator._sha256(
                (receipt.final_path / validator.VALIDATION_FILENAME).read_bytes()
            ),
        )
        self.assertEqual(external["workload_operational_backend_result"], "PASS")
        self.assertTrue(external["workload_publication_eligible"])
        self.assertEqual(
            external["source_directory_identity"],
            receipt.source_directory_identity.as_dict(),
        )
        self.assertEqual(
            external["final_directory_identity"],
            receipt.final_directory_identity.as_dict(),
        )
        self.assertEqual(
            backend.generation_sequence,
            list(orchestrator.EXPECTED_PHASE_ROLE_ORDER),
        )
        self.assertEqual(backend.unload_count, 3)
        self.assertEqual(len(observations["cleanup"]["final_unloads"]), 3)

    def test_timeout_latches_terminal_and_suppresses_queued_generation(self):
        backend = FakeBackend("timeout_first")
        _, _, _, receipt = self.run_fixture("timeout_first", backend=backend)
        self.assertEqual(backend.generation_count, 1)
        self.assertEqual(backend.generation_sequence, [("phase1", "qwen")])
        self.assertTrue(backend.cleanup_called)
        self.assertFalse(receipt.publication_verified)
        self.assertIsNone(receipt.final_path)
        observations = json.loads(
            (receipt.attempt_path / validator.OBSERVATIONS_FILENAME).read_text()
        )
        gate = observations["execution_gate"]
        self.assertEqual(gate["started_generation_calls"], 1)
        self.assertEqual(gate["completed_generation_calls"], 0)
        self.assertEqual(gate["terminal_stop_reason"], "generation_timeout:TimeoutError")
        self.assertEqual(
            [(item["phase"], item["role"]) for item in gate["suppressed_requests"]],
            [("phase1", "llama"), ("phase1", "gemma")],
        )
        events = [
            json.loads(line)
            for line in (receipt.attempt_path / validator.TRANSCRIPT_FILENAME)
            .read_text()
            .splitlines()
        ]
        self.assertEqual(
            len([event for event in events if event["event"] == "generation_suppressed"]),
            2,
        )

    def test_deadline_before_second_reservation_suppresses_remaining_calls(self):
        class MutableClock:
            value = 0.0

            def __call__(self):
                return self.value

        clock = MutableClock()
        backend = FakeBackend()
        original_snapshot = backend.snapshot

        def snapshot_and_expire(*args, **kwargs):
            value = original_snapshot(*args, **kwargs)
            if backend.generation_count == 1:
                clock.value = 61.0
            return value

        backend.snapshot = snapshot_and_expire
        approval = self.approval_value("reuse-deadline-before-second")
        _, _, _, receipt = self.run_fixture(
            approval=approval,
            backend=backend,
            monotonic_fn=clock,
        )
        self.assertEqual(backend.generation_count, 1)
        self.assertTrue(backend.cleanup_called)
        self.assertFalse(receipt.publication_verified)
        observations = json.loads(
            (receipt.attempt_path / validator.OBSERVATIONS_FILENAME).read_text()
        )
        gate = observations["execution_gate"]
        self.assertEqual(gate["completed_generation_calls"], 1)
        self.assertEqual(gate["terminal_stop_reason"], "approved_wall_time_expired")
        self.assertEqual(len(gate["suppressed_requests"]), 2)

    def test_direct_transport_rejects_seventh_call_before_backend(self):
        approval = self.approval_value("reuse-direct-budget")
        backend = FakeBackend()
        transport, transcript = self.make_transport(approval, backend, "budget")
        telemetry = lambda _event, _amount=1: None
        ordinal = 0
        for phase in ("phase1", "phase3"):
            for role in validator.ROLE_ORDER:
                ordinal += 1
                transport(self.make_request(approval, phase, role, ordinal), telemetry)
        with self.assertRaises(orchestrator.EndpointReuseExecutionError):
            transport(
                self.make_request(approval, "phase3", "gemma", 7),
                telemetry,
            )
        transcript.close()
        self.assertEqual(backend.generation_count, 6)
        self.assertEqual(
            backend.generation_sequence,
            list(orchestrator.EXPECTED_PHASE_ROLE_ORDER),
        )
        gate = transport.execution_gate.snapshot()
        self.assertEqual(gate["started_generation_calls"], 6)
        self.assertEqual(gate["completed_generation_calls"], 6)
        self.assertEqual(len(gate["suppressed_requests"]), 1)

    def test_early_phase3_fails_before_unload_or_generation(self):
        approval = self.approval_value("reuse-direct-early-phase3")
        backend = FakeBackend()
        transport, transcript = self.make_transport(approval, backend, "early-phase3")
        with self.assertRaises(orchestrator.EndpointReuseExecutionError):
            transport(
                self.make_request(approval, "phase3", "qwen", 1),
                lambda _event, _amount=1: None,
            )
        transcript.close()
        self.assertEqual(backend.unload_count, 0)
        self.assertEqual(backend.generation_count, 0)
        gate = transport.execution_gate.snapshot()
        self.assertEqual(gate["started_generation_calls"], 0)
        self.assertEqual(gate["terminal_stop_reason"], "phase1_state_not_complete")
        self.assertEqual(len(gate["suppressed_requests"]), 1)

    def warning_result(self, logs_by_role):
        approval = self.approval_value("reuse-warning-parser")
        events = []
        for role in validator.ROLE_ORDER:
            events.extend(
                validator.parse_ollama_diagnostic_stream(
                    role,
                    logs_by_role.get(role, b""),
                )
            )
        errors = []
        accepted, unknown = validator._warning_result(
            events,
            approval["allowed_warning_events"],
            errors,
        )
        operational = (
            "FAIL"
            if errors
            else "MANUAL_REVIEW_REQUIRED"
            if unknown
            else "PASS_WITH_WARNINGS"
            if accepted
            else "PASS"
        )
        return events, accepted, unknown, errors, operational

    def exact_warning_logs(self):
        approval = self.approval_value("reuse-exact-warning-lines")
        return FakeBackend("known_warning")._logs_for_scenario(approval)

    def test_structured_warning_exact_six_and_no_warning_results(self):
        events, accepted, unknown, errors, operational = self.warning_result(
            self.exact_warning_logs()
        )
        self.assertEqual(len(events), 6)
        self.assertEqual(len(accepted), 6)
        self.assertEqual(unknown, [])
        self.assertEqual(errors, [])
        self.assertEqual(operational, "PASS_WITH_WARNINGS")
        for event in events:
            self.assertEqual(set(event), validator.WARNING_EVENT_FIELDS)
            self.assertEqual(event["parse_status"], "parsed")
            self.assertEqual(event["level"], "WARN")
            self.assertEqual(len(event["raw_line_sha256"]), 64)
        _, accepted, unknown, errors, operational = self.warning_result({})
        self.assertEqual((accepted, unknown, errors, operational), ([], [], [], "PASS"))

    def test_mixed_severity_and_two_physical_lines_fail_closed(self):
        approved = self.exact_warning_logs()["qwen"].splitlines()[0]
        error = FakeBackend._log_line("ERROR", 900, "request failure").encode().strip()
        fatal = FakeBackend._log_line("FATAL", 901, "fatal event").encode().strip()
        cases = {
            "error_then_approved_same_line": error + b" " + approved,
            "fatal_then_approved_same_line": fatal + b" " + approved,
            "approved_then_error_same_line": approved + b" " + error,
            "two_physical_lines": error + b"\n" + approved + b"\n",
            "duplicate_level": (
                b'time=2026-08-17T12:00:00+00:00 level=WARN level=ERROR '
                b'source=runner.go:722 msg="user overrode visible devices"'
            ),
        }
        for name, raw in cases.items():
            with self.subTest(name=name):
                events, accepted, _, errors, operational = self.warning_result(
                    {"qwen": raw}
                )
                self.assertTrue(events)
                if name == "two_physical_lines":
                    self.assertEqual(len(accepted), 1)
                else:
                    self.assertEqual(accepted, [])
                self.assertTrue(errors)
                self.assertEqual(operational, "FAIL")

    def test_unknown_request_watchdog_and_stale_memory_warn_are_nonpublishable(self):
        messages = (
            "new warning",
            "request failure",
            "llama-server GPU discovery watchdog timed out",
            "unable to refresh free memory, using old values",
        )
        for message in messages:
            with self.subTest(message=message):
                raw = FakeBackend._log_line("WARN", 999, message).encode()
                _, accepted, unknown, errors, operational = self.warning_result(
                    {"qwen": raw}
                )
                self.assertEqual(accepted, [])
                self.assertEqual(errors, [])
                self.assertEqual(len(unknown), 1)
                self.assertEqual(operational, "MANUAL_REVIEW_REQUIRED")

    def test_oom_and_crash_warn_remain_fatal(self):
        for message in ("OOM while loading", "runner crash observed"):
            with self.subTest(message=message):
                raw = FakeBackend._log_line("WARN", 999, message).encode()
                _, accepted, _, errors, operational = self.warning_result(
                    {"qwen": raw}
                )
                self.assertEqual(accepted, [])
                self.assertTrue(errors)
                self.assertEqual(operational, "FAIL")

    def test_warning_identity_role_gpu_source_message_and_attributes_are_exact(self):
        approval = self.approval_value("reuse-warning-identity")
        qwen_uuid = approval["endpoints"][0]["gpu_uuid"]
        base = FakeBackend._log_line(
            "WARN",
            722,
            "user overrode visible devices",
            CUDA_VISIBLE_DEVICES=qwen_uuid,
        ).encode()
        cases = {
            "wrong_role": {"llama": base},
            "wrong_gpu": {
                "qwen": FakeBackend._log_line(
                    "WARN",
                    722,
                    "user overrode visible devices",
                    CUDA_VISIBLE_DEVICES="GPU-wrong",
                ).encode()
            },
            "wrong_source": {
                "qwen": FakeBackend._log_line(
                    "WARN",
                    723,
                    "user overrode visible devices",
                    CUDA_VISIBLE_DEVICES=qwen_uuid,
                ).encode()
            },
            "wrong_message": {
                "qwen": FakeBackend._log_line(
                    "WARN",
                    722,
                    "different message",
                    CUDA_VISIBLE_DEVICES=qwen_uuid,
                ).encode()
            },
            "extra_attribute": {
                "qwen": FakeBackend._log_line(
                    "WARN",
                    722,
                    "user overrode visible devices",
                    CUDA_VISIBLE_DEVICES=qwen_uuid,
                    unexpected="value",
                ).encode()
            },
        }
        for name, logs in cases.items():
            with self.subTest(name=name):
                _, accepted, unknown, errors, operational = self.warning_result(logs)
                self.assertEqual(accepted, [])
                self.assertEqual(errors, [])
                self.assertEqual(len(unknown), 1)
                self.assertEqual(operational, "MANUAL_REVIEW_REQUIRED")

    def test_warning_duplicate_occurrence_malformed_quote_and_duplicate_key_reject(self):
        approved = self.exact_warning_logs()["qwen"].splitlines()[0] + b"\n"
        _, accepted, unknown, errors, operational = self.warning_result(
            {"qwen": approved + approved}
        )
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(unknown), 1)
        self.assertEqual(errors, [])
        self.assertEqual(operational, "MANUAL_REVIEW_REQUIRED")
        malformed_cases = (
            b'time=2026-08-17T12:00:00+00:00 level=WARN source=runner.go:722 msg="unterminated',
            b'time=2026-08-17T12:00:00+00:00 level=WARN source=runner.go:722 source=runner.go:726 msg="duplicate"',
        )
        for raw in malformed_cases:
            with self.subTest(raw=raw):
                events, accepted, unknown, errors, operational = self.warning_result(
                    {"qwen": raw}
                )
                self.assertEqual(events[0]["parse_status"], "malformed")
                self.assertEqual(accepted, [])
                self.assertEqual(errors, [])
                self.assertEqual(len(unknown), 1)
                self.assertEqual(operational, "MANUAL_REVIEW_REQUIRED")

    def test_warning_parser_rejects_embedded_newline_and_has_no_glob_matcher(self):
        event = validator.parse_ollama_log_line(
            "qwen",
            validator.WARNING_STREAM,
            1,
            b'level=ERROR msg="failure"\nlevel=WARN msg="approved"',
        )
        self.assertEqual(event["parse_status"], "malformed")
        self.assertEqual(event["malformation_reason"], "embedded_line_break")
        source = (REPO_ROOT / "tools/validate_gate4_ollama_endpoint_reuse.py").read_text()
        self.assertNotIn("fnmatch", source)
        self.assertNotIn("allowed_warning_patterns", source)

    def test_warning_raw_hash_and_server_log_trace_are_verified(self):
        root = self.root / "warning-trace"
        log_root = root / "server-logs"
        log_root.mkdir(parents=True)
        logs = self.exact_warning_logs()
        events = []
        for role in validator.ROLE_ORDER:
            (log_root / f"{role}.log").write_bytes(logs[role])
            events.extend(validator.parse_ollama_diagnostic_stream(role, logs[role]))
        errors = []
        validator._validate_warning_event_trace(root, events, errors, root_fd=None)
        self.assertEqual(errors, [])

        tampered = json.loads(json.dumps(events))
        tampered[0]["line_sequence"] += 1
        errors = []
        validator._validate_warning_event_trace(root, tampered, errors, root_fd=None)
        self.assertIn("warning_event_raw_log_trace_mismatch", errors)

        tampered = json.loads(json.dumps(events))
        tampered[0]["raw_line_sha256"] = "0" * 64
        approval = self.approval_value("reuse-warning-hash")
        errors = []
        accepted, unknown = validator._warning_result(
            [tampered[0]],
            approval["allowed_warning_events"],
            errors,
        )
        self.assertEqual((accepted, unknown), ([], []))
        self.assertIn("warning_event[0]:raw_line_hash_mismatch", errors)

    def test_known_warning_is_retained_without_formal_promotion(self):
        _, _, _, receipt = self.run_fixture("known_warning")
        self.assertTrue(receipt.publication_verified)
        self.assertEqual(receipt.operational_backend_result, "PASS_WITH_WARNINGS")
        validation = json.loads(
            (receipt.attempt_path / validator.VALIDATION_FILENAME).read_text()
        )
        self.assertEqual(len(validation["accepted_warnings"]), 6)
        self.assertEqual(validation["unknown_warnings"], [])
        self.assertEqual(validation["errors"], [])
        self.assertEqual(
            [event["role"] for event in validation["accepted_warnings"]],
            ["qwen", "qwen", "llama", "llama", "gemma", "gemma"],
        )
        self.assertFalse(validation["gate4_formal_pass"])

    def test_unknown_warning_requires_manual_review_and_is_not_published(self):
        _, _, _, receipt = self.run_fixture("unknown_warning")
        self.assertFalse(receipt.publication_verified)
        self.assertEqual(receipt.operational_backend_result, "MANUAL_REVIEW_REQUIRED")
        self.assertIsNone(receipt.final_path)

    def test_error_or_fatal_with_approved_warnings_fails_without_publication(self):
        for scenario in ("error_with_approved_warning", "fatal_with_approved_warning"):
            with self.subTest(scenario=scenario):
                _, _, _, receipt = self.run_fixture(scenario)
                self.assertFalse(receipt.publication_verified)
                self.assertEqual(receipt.operational_backend_result, "FAIL")
                self.assertIsNone(receipt.final_path)

    def test_stability_wait_and_abort_classification_are_mechanical(self):
        value = self.approval_value("reuse-stability")
        path, digest = self.write_approval(value)
        waits = []
        with self.cpu_only_runtime():
            receipt = orchestrator.run_approved_endpoint_reuse(
                path,
                digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=waits.append,
            )
        self.assertTrue(receipt.publication_verified)
        self.assertEqual(waits, [value["stability_wait_seconds"]])
        observations = json.loads(
            (receipt.attempt_path / validator.OBSERVATIONS_FILENAME).read_text()
        )
        self.assertEqual(len(observations["stability_snapshots"]), 3)

        _, _, _, aborted = self.run_fixture("keyboard_interrupt")
        self.assertEqual(aborted.operational_backend_result, "ABORTED")
        self.assertFalse(aborted.publication_verified)

    def test_publication_and_verification_failures_get_terminal_receipts(self):
        publication_value = self.approval_value("reuse-publication-failure")
        publication_path, publication_digest = self.write_approval(publication_value)
        with self.cpu_only_runtime(), mock.patch(
            "tools.gate4_endpoint_reuse_orchestrator.publisher.publish_evidence",
            side_effect=RuntimeError("synthetic publication failure"),
        ):
            publication_receipt = orchestrator.run_approved_endpoint_reuse(
                publication_path,
                publication_digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
            )
        self.assertFalse(publication_receipt.publication_verified)
        self.assertIsNone(publication_receipt.final_path)
        publication_failure = json.loads(publication_receipt.receipt_path.read_text())
        self.assertEqual(publication_failure["status"], "publication_failed")

        verification_value = self.approval_value("reuse-verification-failure")
        verification_path, verification_digest = self.write_approval(verification_value)
        with self.cpu_only_runtime(), mock.patch(
            "tools.gate4_endpoint_reuse_orchestrator.independent_verifier.verify_bundle",
            return_value=SimpleNamespace(valid=False, errors=["synthetic mismatch"]),
        ):
            verification_receipt = orchestrator.run_approved_endpoint_reuse(
                verification_path,
                verification_digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
            )
        self.assertFalse(verification_receipt.publication_verified)
        self.assertIsNotNone(verification_receipt.final_path)
        verification_failure = json.loads(verification_receipt.receipt_path.read_text())
        self.assertEqual(verification_failure["status"], "verification_failed")

    def test_persisted_validation_mutation_before_publication_is_rejected(self):
        value = self.approval_value("reuse-persisted-source-mutation")
        path, digest = self.write_approval(value)
        real_publish = publisher.publish_evidence

        def mutate_source(source, *args, **kwargs):
            self.rewrite_persisted_validation(
                source,
                result="FAIL",
                eligible=False,
            )
            return real_publish(source, *args, **kwargs)

        with self.cpu_only_runtime(), mock.patch.object(
            publisher,
            "publish_evidence",
            side_effect=mutate_source,
        ):
            receipt = orchestrator.run_approved_endpoint_reuse(
                path,
                digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
            )
        self.assertFalse(receipt.publication_verified)
        self.assertIsNone(receipt.final_path)
        external = json.loads(receipt.receipt_path.read_text())
        self.assertEqual(external["status"], "publication_failed")
        self.assertEqual(external["operational_backend_result"], "FAIL")
        self.assertEqual(external["workload_operational_backend_result"], "NOT_VERIFIED")
        self.assertFalse(external["workload_publication_eligible"])

    def test_persisted_validation_mutation_in_staging_is_rejected(self):
        value = self.approval_value("reuse-persisted-staging-mutation")
        path, digest = self.write_approval(value)
        real_publish = publisher.publish_evidence

        def mutate_staging(source, publication_root, summary, **kwargs):
            workload_hook = kwargs["checkpoint_hook"]

            def combined_hook(checkpoint, staging, final):
                if checkpoint == "after_inventory_verification_before_publish":
                    self.rewrite_persisted_validation(
                        staging,
                        result="FAIL",
                        eligible=False,
                    )
                workload_hook(checkpoint, staging, final)

            kwargs["checkpoint_hook"] = combined_hook
            return real_publish(source, publication_root, summary, **kwargs)

        with self.cpu_only_runtime(), mock.patch.object(
            publisher,
            "publish_evidence",
            side_effect=mutate_staging,
        ):
            receipt = orchestrator.run_approved_endpoint_reuse(
                path,
                digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
            )
        self.assertFalse(receipt.publication_verified)
        self.assertIsNone(receipt.final_path)
        external = json.loads(receipt.receipt_path.read_text())
        self.assertEqual(external["status"], "publication_failed")

    def test_published_validation_and_final_inode_swap_are_rejected(self):
        value = self.approval_value("reuse-final-inode-mutation")
        path, digest = self.write_approval(value)
        real_verify = independent.verify_bundle
        swapped = []

        def swap_then_verify(bundle, **kwargs):
            bundle = Path(bundle)
            parked = bundle.with_name(bundle.name + "-original-inode")
            bundle.rename(parked)
            shutil.copytree(parked, bundle)
            self.rewrite_persisted_validation(
                bundle,
                result="FAIL",
                eligible=False,
            )
            swapped.append((parked, bundle))
            return real_verify(bundle, **kwargs)

        with self.cpu_only_runtime(), mock.patch.object(
            independent,
            "verify_bundle",
            side_effect=swap_then_verify,
        ):
            receipt = orchestrator.run_approved_endpoint_reuse(
                path,
                digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
            )
        self.assertEqual(len(swapped), 1)
        self.assertFalse(receipt.publication_verified)
        external = json.loads(receipt.receipt_path.read_text())
        self.assertEqual(external["status"], "verification_failed")
        self.assertFalse(external["workload_publication_eligible"])

    def test_persisted_validation_mutation_after_publication_is_rejected(self):
        value = self.approval_value("reuse-final-validation-mutation")
        path, digest = self.write_approval(value)
        real_verify = independent.verify_bundle

        def mutate_then_verify(bundle, **kwargs):
            self.rewrite_persisted_validation(
                bundle,
                result="FAIL",
                eligible=False,
            )
            return real_verify(bundle, **kwargs)

        with self.cpu_only_runtime(), mock.patch.object(
            independent,
            "verify_bundle",
            side_effect=mutate_then_verify,
        ):
            receipt = orchestrator.run_approved_endpoint_reuse(
                path,
                digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
            )
        self.assertFalse(receipt.publication_verified)
        external = json.loads(receipt.receipt_path.read_text())
        self.assertEqual(external["status"], "verification_failed")
        self.assertEqual(external["workload_operational_backend_result"], "NOT_VERIFIED")
        self.assertFalse(external["workload_publication_eligible"])

    def test_source_inode_swap_is_rejected_even_with_identical_bytes(self):
        value = self.approval_value("reuse-source-inode-swap")
        path, digest = self.write_approval(value)
        real_publish = publisher.publish_evidence

        def swap_source(source, publication_root, summary, **kwargs):
            source = Path(source)
            parked = source.with_name(source.name + "-original-inode")
            source.rename(parked)
            shutil.copytree(parked, source)
            return real_publish(source, publication_root, summary, **kwargs)

        with self.cpu_only_runtime(), mock.patch.object(
            publisher,
            "publish_evidence",
            side_effect=swap_source,
        ):
            receipt = orchestrator.run_approved_endpoint_reuse(
                path,
                digest,
                repository=REPO_ROOT,
                backend=FakeBackend(),
                source_probe=self.source_probe,
                sleep_fn=lambda _seconds: None,
            )
        self.assertFalse(receipt.publication_verified)
        self.assertIsNone(receipt.final_path)
        external = json.loads(receipt.receipt_path.read_text())
        self.assertEqual(external["status"], "publication_failed")

    def test_reverse_persisted_pass_against_recomputed_fail_is_rejected(self):
        _, _, digest, receipt = self.run_fixture("success")
        observations_path = receipt.attempt_path / validator.OBSERVATIONS_FILENAME
        observations = json.loads(observations_path.read_text())
        observations["generations"][0]["status_code"] = 503
        observations_path.write_bytes(validator.canonical_json_bytes(observations))
        with self.assertRaises(validator.EndpointReuseValidationError):
            validator.validate_persisted_validation(
                receipt.attempt_path,
                expected_approval_sha256=digest,
                expected_directory_identity=(
                    receipt.source_directory_identity.as_dict()
                ),
                source_directory_identity=(
                    receipt.source_directory_identity.as_dict()
                ),
            )

    def test_symlink_root_is_rejected_consistently(self):
        _, _, digest, receipt = self.run_fixture("success")
        attempt_link = self.root / "attempt-link"
        attempt_link.symlink_to(receipt.attempt_path, target_is_directory=True)
        workload = validator.validate_attempt(
            attempt_link,
            expected_approval_sha256=digest,
        )
        self.assertFalse(workload.publication_eligible)
        self.assertIsNone(workload.directory_identity)

        final_link = self.root / "final-link"
        final_link.symlink_to(receipt.final_path, target_is_directory=True)
        generic = independent.verify_bundle(final_link)
        self.assertFalse(generic.valid)
        with self.assertRaises(publisher.EvidencePublicationError):
            publisher.publish_evidence(
                attempt_link,
                self.root / "unused-publication-root",
                orchestrator._summary_draft(
                    self.approval_value("reuse-symlink-publisher")
                ),
            )

    def test_cleanup_done_false_exposes_failed_subcheck(self):
        _, _, _, receipt = self.run_fixture("final_unload_done_false")
        self.assertFalse(receipt.publication_verified)
        validation = json.loads(
            (receipt.attempt_path / validator.VALIDATION_FILENAME).read_text()
        )
        self.assertEqual(validation["checks"]["cleanup"], "FAIL")
        self.assertFalse(
            validation["checks"]["cleanup_subchecks"]["final_unloads_complete"]
        )
        self.assertFalse(validation["evidence_publication_eligible"])

    def test_each_cleanup_subcheck_is_reported_explicitly(self):
        scenarios = {
            "cleanup_failure": "backend_cleanup_passed",
            "final_unload_done_false": "final_unloads_complete",
            "cleanup_missing_port": "temporary_ports_closed",
            "cleanup_server_present": "temporary_server_pids_absent",
            "cleanup_runner_present": "temporary_runner_pids_absent",
            "cleanup_gpu_busy": "all_gpus_idle",
            "cleanup_compute_present": "no_compute_processes",
            "existing_service_changed": "existing_service_unchanged",
        }
        for scenario, failed_check in scenarios.items():
            with self.subTest(scenario=scenario):
                _, _, _, receipt = self.run_fixture(scenario)
                validation = json.loads(
                    (receipt.attempt_path / validator.VALIDATION_FILENAME).read_text()
                )
                checks = validation["checks"]
                self.assertEqual(checks["cleanup"], "FAIL")
                self.assertFalse(checks["cleanup_subchecks"][failed_check])
                self.assertFalse(validation["evidence_publication_eligible"])

    def test_concurrent_claim_has_one_owner_and_controlled_collision(self):
        value = self.approval_value("reuse-concurrent-claim")
        path, digest = self.write_approval(value)

        def invoke():
            try:
                return orchestrator.run_approved_endpoint_reuse(
                    path,
                    digest,
                    repository=REPO_ROOT,
                    backend=FakeBackend(),
                    source_probe=self.source_probe,
                    sleep_fn=lambda _seconds: None,
                )
            except Exception as error:
                return error

        with self.cpu_only_runtime(), ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: invoke(), range(2)))
        owners = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, orchestrator.OrchestrationReceipt)
        ]
        collisions = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, orchestrator.EndpointReuseCollisionError)
        ]
        self.assertEqual(len(owners), 1, outcomes)
        self.assertEqual(len(collisions), 1, outcomes)
        self.assertFalse(any(isinstance(outcome, FileExistsError) for outcome in outcomes))

    def test_late_publisher_final_collision_is_normalized(self):
        value = self.approval_value("reuse-late-final-collision")
        path, digest = self.write_approval(value)
        with self.cpu_only_runtime(), mock.patch.object(
            publisher,
            "publish_evidence",
            side_effect=publisher.EvidenceCollisionError(
                "synthetic final bundle claim race"
            ),
        ):
            with self.assertRaises(orchestrator.EndpointReuseCollisionError):
                orchestrator.run_approved_endpoint_reuse(
                    path,
                    digest,
                    repository=REPO_ROOT,
                    backend=FakeBackend(),
                    source_probe=self.source_probe,
                    sleep_fn=lambda _seconds: None,
                )
        receipt_path = Path(value["evidence_root"]) / "receipts" / (
            value["approval_id"] + ".json"
        )
        self.assertFalse(receipt_path.exists())

    def test_runtime_failures_are_retained_and_never_published(self):
        scenarios = [
            "initial_http_failure",
            "retry",
            "parse_failure",
            "unload_incomplete",
            "server_pid_change",
            "reload_gpu_change",
            "reload_digest_change",
            "reload_context_change",
            "reload_offload",
            "unexpected_eviction",
            "cleanup_failure",
            "existing_service_changed",
            "preflight_gpu_mismatch",
            "preflight_digest_mismatch",
            "stability_pid_change",
        ]
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                _, _, _, receipt = self.run_fixture(scenario)
                self.assertFalse(receipt.publication_verified)
                self.assertIsNone(receipt.final_path)
                self.assertTrue(receipt.attempt_path.is_dir())
                self.assertFalse(
                    (receipt.attempt_path.parent.parent / "published" / receipt.approval_id).exists()
                )

    def test_approval_hash_source_and_artifact_preflight_fail_before_attempt(self):
        value = self.approval_value("reuse-static-reject")
        path, digest = self.write_approval(value)
        with self.assertRaises(orchestrator.EndpointReuseInvocationError):
            orchestrator.load_approval(path, "0" * 64)

        with self.cpu_only_runtime():
            with self.assertRaises(orchestrator.EndpointReuseInvocationError):
                orchestrator.run_approved_endpoint_reuse(
                    path,
                    digest,
                    repository=REPO_ROOT,
                    backend=FakeBackend(),
                    source_probe=lambda _: orchestrator.SourceState(SOURCE_SHA, True),
                )
        self.assertFalse((Path(value["evidence_root"]) / "attempts").exists())

        with self.cpu_only_runtime():
            with self.assertRaises(orchestrator.EndpointReuseInvocationError):
                orchestrator.run_approved_endpoint_reuse(
                    path,
                    digest,
                    repository=REPO_ROOT,
                    backend=FakeBackend(),
                    source_probe=lambda _: orchestrator.SourceState("b" * 40, False),
                )

        wrong = self.approval_value("reuse-artifact-reject")
        wrong["publisher_sha256"] = "0" * 64
        wrong_path, wrong_digest = self.write_approval(wrong)
        with self.cpu_only_runtime():
            with self.assertRaises(orchestrator.EndpointReuseInvocationError):
                orchestrator.run_approved_endpoint_reuse(
                    wrong_path,
                    wrong_digest,
                    repository=REPO_ROOT,
                    backend=FakeBackend(),
                    source_probe=self.source_probe,
                    sleep_fn=lambda _seconds: None,
                )

    def test_closed_approval_rejects_endpoint_budget_path_and_model_mutations(self):
        mutations = {}
        wrong_port = self.approval_value("reuse-wrong-port")
        wrong_port["endpoints"][0]["port"] = 11540
        mutations["port"] = wrong_port
        wrong_uuid = self.approval_value("reuse-wrong-uuid")
        wrong_uuid["endpoints"][0]["gpu_uuid"] = "bad"
        mutations["uuid"] = wrong_uuid
        wrong_digest = self.approval_value("reuse-wrong-digest")
        wrong_digest["endpoints"][0]["model_digest"] = "short"
        mutations["digest"] = wrong_digest
        wrong_budget = self.approval_value("reuse-wrong-budget")
        wrong_budget["maximum_generation_calls"] = 7
        mutations["budget"] = wrong_budget
        unbounded = self.approval_value("reuse-unbounded")
        unbounded["maximum_wall_seconds"] = 3601
        mutations["unbounded"] = unbounded
        wrong_path = self.approval_value("reuse-wrong-path")
        wrong_path["approved_final_path"] = str(self.root / "elsewhere")
        mutations["path"] = wrong_path
        unknown = self.approval_value("reuse-unknown-field")
        unknown["cli_override"] = True
        mutations["unknown"] = unknown
        for label, value in mutations.items():
            with self.subTest(label=label):
                path, digest = self.write_approval(value)
                with self.assertRaises(orchestrator.EndpointReuseInvocationError):
                    orchestrator.load_approval(path, digest)

    def test_old_glob_approval_and_malformed_structured_allowlists_are_rejected(self):
        old = self.approval_value("reuse-old-glob-approval")
        old["schema_version"] = "gate4-ollama-endpoint-reuse-approval-v1.0.0"
        old.pop("allowed_warning_events")
        old["allowed_warning_patterns"] = ["time=* level=WARN *"]
        mutations = {"old_glob_schema": old}

        missing = self.approval_value("reuse-warning-missing")
        missing["allowed_warning_events"] = missing["allowed_warning_events"][:-1]
        mutations["missing_event"] = missing

        duplicate = self.approval_value("reuse-warning-duplicate")
        duplicate["allowed_warning_events"][-1] = dict(
            duplicate["allowed_warning_events"][0]
        )
        mutations["duplicate_identity"] = duplicate

        wildcard = self.approval_value("reuse-warning-wildcard")
        wildcard["allowed_warning_events"][0]["message"] = "user overrode *"
        mutations["wildcard"] = wildcard

        excess = self.approval_value("reuse-warning-excess-bound")
        excess["allowed_warning_events"][0]["maximum_occurrences"] = 2
        mutations["excess_bound"] = excess

        extra = self.approval_value("reuse-warning-extra-field")
        extra["allowed_warning_events"][0]["unexpected"] = True
        mutations["unknown_event_field"] = extra

        for label, value in mutations.items():
            with self.subTest(label=label):
                path, digest = self.write_approval(value)
                with self.assertRaises(orchestrator.EndpointReuseInvocationError):
                    orchestrator.load_approval(path, digest)

    def test_wall_time_ceiling_is_derived_from_observed_elapsed_time(self):
        value = self.approval_value("reuse-wall-time", maximum_wall_seconds=1)
        _, _, _, receipt = self.run_fixture("slow", approval=value)
        self.assertFalse(receipt.publication_verified)
        validation = json.loads(
            (receipt.attempt_path / validator.VALIDATION_FILENAME).read_text()
        )
        self.assertIn("wall_time_ceiling_exceeded", validation["errors"])

    def test_same_approval_id_collision_preserves_first_bundle(self):
        value, path, digest, first = self.run_fixture("success")
        before = {
            item.relative_to(first.final_path).as_posix(): item.read_bytes()
            for item in first.final_path.rglob("*")
            if item.is_file()
        }
        with self.cpu_only_runtime():
            with self.assertRaises(orchestrator.EndpointReuseCollisionError):
                orchestrator.run_approved_endpoint_reuse(
                    path,
                    digest,
                    repository=REPO_ROOT,
                    backend=FakeBackend(),
                    source_probe=self.source_probe,
                )
        after = {
            item.relative_to(first.final_path).as_posix(): item.read_bytes()
            for item in first.final_path.rglob("*")
            if item.is_file()
        }
        self.assertEqual(before, after)

    def test_validator_detects_tamper_without_reclassifying_formal_scope(self):
        _, _, digest, receipt = self.run_fixture("success")
        observations_path = receipt.attempt_path / validator.OBSERVATIONS_FILENAME
        observations = json.loads(observations_path.read_text())
        observations["generations"][5]["snapshot"]["model_digest"] = "0" * 64
        observations_path.write_bytes(validator.canonical_json_bytes(observations))
        report = validator.validate_attempt(
            receipt.attempt_path,
            expected_approval_sha256=digest,
        )
        self.assertFalse(report.publication_eligible)
        self.assertEqual(report.operational_backend_result, "FAIL")
        self.assertFalse(report.value["gate4_formal_pass"])
        self.assertFalse(report.value["research_eligible"])

    def test_real_backend_administrative_calls_are_bounded_and_exact_pid_only(self):
        approval = self.approval_value("reuse-local-admin")
        endpoint = approval["endpoints"][0]
        server = {
            "role": "qwen",
            "port": 11440,
            "server_pid": 3210,
            "start_time_ticks": 456,
        }
        backend = orchestrator.LocalOllamaBackend()
        with mock.patch.object(
            backend,
            "_api_json",
            side_effect=[
                (200, b"{}", {"done": True, "done_reason": "unload"}),
                (200, b"{}", {"models": []}),
            ],
        ) as api:
            unload = backend.unload(
                approval,
                endpoint,
                server,
                "between_phases",
            )
        self.assertEqual(unload["ps_models_after"], [])
        self.assertEqual(
            api.call_args_list[0].kwargs["payload"],
            {
                "model": endpoint["model_tag"],
                "keep_alive": 0,
                "stream": False,
            },
        )

        command_receipt = {
            "command": [],
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
        }
        with (
            mock.patch.object(
                backend,
                "_pid_state",
                return_value=(456, "/usr/local/bin/ollama serve"),
            ),
            mock.patch.object(backend, "_port_open", return_value=True),
            mock.patch.object(backend, "_run", return_value=command_receipt) as run,
            mock.patch(
                "tools.gate4_endpoint_reuse_orchestrator.pwd.getpwnam",
                return_value=SimpleNamespace(pw_uid=999),
            ),
            mock.patch.object(Path, "stat", return_value=SimpleNamespace(st_uid=999)),
            mock.patch.object(Path, "exists", return_value=False),
        ):
            backend._stop_server(approval, server)
        kill_command = run.call_args.args[0]
        self.assertEqual(
            kill_command,
            ["sudo", "-n", "-u", "ollama", "/bin/kill", "-TERM", "--", "3210"],
        )
        source = (REPO_ROOT / orchestrator.ORCHESTRATOR_PATH).read_text()
        for forbidden in ('"systemctl"', '"service"', '"shutdown"', '"reboot"', '"killall"', '"pkill"'):
            self.assertNotIn(forbidden, source)

    def test_cli_has_no_workload_override_arguments(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            code = orchestrator.main(
                [
                    "--approval",
                    "unused.json",
                    "--approval-sha256",
                    "0" * 64,
                    "--num-ctx",
                    "8192",
                ]
            )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
