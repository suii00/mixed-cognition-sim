import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.llm_client import LLMTransportError
from tools import ollama_prompt6_runner as runner


REPO_ROOT = Path(__file__).resolve().parents[1]


def json_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


class FakeApi:
    def __init__(
        self,
        bindings,
        *,
        wrong_digest=False,
        wrong_post_context=False,
        preloaded_slot=None,
    ):
        self.bindings = tuple(bindings)
        self.wrong_digest = wrong_digest
        self.wrong_post_context = wrong_post_context
        self.preloaded_slot = preloaded_slot
        self.ps_counts = {binding.slot: 0 for binding in self.bindings}
        self.calls = []

    def binding_for_url(self, url):
        matches = [binding for binding in self.bindings if url.startswith(binding.base_url)]
        if len(matches) != 1:
            raise AssertionError(f"unmapped URL: {url}")
        return matches[0]

    def __call__(self, method, url, payload, timeout_s):
        self.calls.append((method, url, payload, timeout_s))
        binding = self.binding_for_url(url)
        if url.endswith("/api/version"):
            value = {"version": "test-ollama"}
        elif url.endswith("/api/tags"):
            digest = "f" * 64 if self.wrong_digest and binding.slot == "qwen" else binding.digest
            value = {
                "models": [{
                    "name": binding.model,
                    "digest": digest,
                    "details": {"quantization_level": binding.quantization},
                }]
            }
        elif url.endswith("/api/show"):
            value = {"template": f"template-{binding.slot}"}
        elif url.endswith("/api/ps"):
            count = self.ps_counts[binding.slot]
            self.ps_counts[binding.slot] += 1
            if count == 0:
                value = {
                    "models": (
                        [{
                            "name": binding.model,
                            "digest": binding.digest,
                            "context_length": runner.NUM_CTX,
                            "size": 1000,
                            "size_vram": 1000,
                        }]
                        if self.preloaded_slot == binding.slot else []
                    )
                }
            else:
                context = (
                    8192
                    if self.wrong_post_context and binding.slot == "gemma"
                    else runner.NUM_CTX
                )
                value = {
                    "models": [{
                        "name": binding.model,
                        "digest": binding.digest,
                        "context_length": context,
                        "size": 1000,
                        "size_vram": 1000,
                    }]
                }
        else:
            raise AssertionError(f"unexpected API URL: {url}")
        return runner.HttpJson(200, value, json_bytes(value))


class FakeNative:
    def __init__(
        self,
        *,
        retry_first=False,
        wrong_model_at=None,
        transport_at=None,
        wrong_http_status_at=None,
        schema_diagnostic_at=None,
    ):
        self.retry_first = retry_first
        self.wrong_model_at = wrong_model_at
        self.transport_at = transport_at
        self.wrong_http_status_at = wrong_http_status_at
        self.schema_diagnostic_at = schema_diagnostic_at
        self.calls = []

    @staticmethod
    def parsed_for_prompt(prompt, ordinal):
        if "Decide what message to send" in prompt:
            return {
                "message": f"message-{ordinal}",
                "reasoning": f"phase1-reasoning-{ordinal}",
            }
        if "Decide your next action" in prompt:
            return {
                "action": "stay",
                "direction": "",
                "memory": f"memory-{ordinal}",
                "reasoning": f"phase3-reasoning-{ordinal}",
            }
        raise AssertionError("prompt was not built by a known current prompt builder")

    @staticmethod
    def envelope(model, content):
        return {
            "model": model,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
            "total_duration": 100,
            "load_duration": 10,
            "prompt_eval_count": 20,
            "prompt_eval_duration": 30,
            "eval_count": 40,
            "eval_duration": 50,
        }

    def __call__(self, **kwargs):
        ordinal = len(self.calls) + 1
        self.calls.append(kwargs)
        telemetry = kwargs["telemetry"]
        observer = kwargs["response_observer"]
        http_observer = kwargs["http_response_observer"]
        if self.transport_at == ordinal:
            telemetry("http_attempt", 1)
            telemetry("transport_failure", 1)
            raise LLMTransportError("synthetic terminal failure")
        parsed = self.parsed_for_prompt(kwargs["prompt"], ordinal)
        if self.schema_diagnostic_at == ordinal:
            parsed = {}
        content = json.dumps(parsed, ensure_ascii=False)
        if self.retry_first and ordinal == 1:
            telemetry("http_attempt", 1)
            first_envelope = self.envelope(kwargs["model"], "not json")
            http_observer(200, json_bytes(first_envelope))
            observer(first_envelope)
            telemetry("syntax_parse_attempt_failure", 1)
            telemetry("generation_retry", 1)
        telemetry("http_attempt", 1)
        response_model = (
            "unexpected:model"
            if self.wrong_model_at == ordinal
            else kwargs["model"]
        )
        envelope = self.envelope(response_model, content)
        http_observer(
            201 if self.wrong_http_status_at == ordinal else 200,
            json_bytes(envelope),
        )
        observer(envelope)
        return parsed, content


class Prompt6RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        templates = {slot: f"template-{slot}" for slot in ("qwen", "gemma", "llama")}
        original_by_slot = {binding.slot: binding for binding in runner.MODEL_BINDINGS}
        self.bindings = tuple(
            runner.ModelBinding(
                slot=slot,
                bloc=original_by_slot[slot].bloc,
                model=original_by_slot[slot].model,
                base_url=original_by_slot[slot].base_url,
                digest=character * 64,
                quantization="F16",
                template_sha256=runner.sha256_bytes(templates[slot].encode("utf-8")),
                gpu_uuid=original_by_slot[slot].gpu_uuid,
            )
            for slot, character in (("qwen", "a"), ("gemma", "b"), ("llama", "c"))
        )

    @contextlib.contextmanager
    def patched_runtime(self, native):
        git_info = {
            "git_sha": "1" * 40,
            "git_dirty": True,
            "git_probe_status": "available",
            "git_probe_errors": [],
        }
        gpu_info = {
            "status": "available",
            "error": None,
            "driver_version": "test-driver",
            "cuda_version": "test-cuda",
            "cuda_probe_status": "available",
            "cuda_probe_error": None,
            "malformed_device_rows": 0,
            "devices": [{
                "index": "0",
                "name": "NVIDIA test GPU",
                "uuid": "GPU-test",
                "memory_total_mib": "24564",
            }],
        }
        with (
            mock.patch.object(runner, "MODEL_BINDINGS", self.bindings),
            mock.patch("engine.sim.call_ollama", side_effect=native) as native_mock,
            mock.patch(
                "tools.ollama_prompt6_runner.requests.request",
                side_effect=AssertionError("real network is forbidden in CPU tests"),
            ),
            mock.patch("engine.provenance.collect_git_info", return_value=git_info),
            mock.patch("engine.provenance.collect_gpu_info", return_value=gpu_info),
            mock.patch("tools.ollama_prompt6_runner.collect_git_info", return_value=git_info),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            yield native_mock

    @staticmethod
    def read_manifest(directory):
        return json.loads(
            (directory / "prompt6_manifest.json").read_text(encoding="utf-8")
        )

    def test_success_runs_exact_six_current_prompts_and_retains_evidence(self):
        output = self.root / "prompt6-success"
        api = FakeApi(self.bindings)
        native = FakeNative()
        with self.patched_runtime(native) as native_mock:
            result = runner.run_prompt6(
                output,
                "prompt6-success-run",
                repo_root=REPO_ROOT,
                api_client=api,
            )

        self.assertEqual(result, output.resolve())
        self.assertEqual(native_mock.call_count, 6)
        self.assertEqual(len(native.calls), 6)
        self.assertTrue(all(call["keep_alive"] == -1 for call in native.calls))
        self.assertTrue(all(call["temperature"] == 0.2 for call in native.calls))
        self.assertTrue(all(call["max_tokens"] == 256 for call in native.calls))
        self.assertTrue(
            all(call["llm_overrides"] == {"num_ctx": 4096} for call in native.calls)
        )
        self.assertEqual(
            [call["model"] for call in native.calls],
            [
                self.bindings[0].model,
                self.bindings[1].model,
                self.bindings[2].model,
                self.bindings[0].model,
                self.bindings[1].model,
                self.bindings[2].model,
            ],
        )
        self.assertTrue(
            all("Decide what message to send" in call["prompt"] for call in native.calls[:3])
        )
        self.assertTrue(
            all("Decide your next action" in call["prompt"] for call in native.calls[3:])
        )
        self.assertTrue(
            all("Recent messages received:" in call["prompt"] for call in native.calls[3:])
        )

        manifest = self.read_manifest(output)
        self.assertEqual(manifest["status"], "passed")
        self.assertFalse(manifest["research_eligible"])
        self.assertEqual(manifest["formal_gate4_status"], "not_a_formal_gate4a_stage")
        self.assertEqual(manifest["logical_transport_records"], 6)
        self.assertEqual(manifest["native_response_envelopes"], 6)
        self.assertEqual(manifest["http_response_observations"], 6)
        self.assertEqual(
            manifest["native_http_status_observation"],
            "client_callback_exact_status_and_raw_body",
        )
        self.assertEqual(manifest["status_scope"], "core_simulation_prompt_path_only")
        self.assertEqual(manifest["overall_backend_evidence_status"], "not_evaluated")
        self.assertIn(
            "exact runner source bytes bound to the recorded runner hash",
            manifest["external_evidence_required"],
        )
        self.assertEqual(
            manifest["guarded_documents"],
            {
                runner.AUXILIARY_SPEC_PATH:
                    runner.EXPECTED_AUXILIARY_SPEC_SHA256,
                runner.EVIDENCE_LEDGER_PATH:
                    runner.EXPECTED_EVIDENCE_LEDGER_SHA256,
            },
        )
        source_bytes = (REPO_ROOT / manifest["runner_source"]["path"]).read_bytes()
        self.assertEqual(manifest["runner_source"]["bytes"], len(source_bytes))
        self.assertEqual(
            manifest["runner_source"]["sha256"],
            runner.sha256_bytes(source_bytes),
        )
        self.assertIn(
            "external orchestration",
            manifest["runner_source"]["evidence_boundary"],
        )
        self.assertEqual(manifest["failures"], [])
        self.assertEqual(manifest["observed_request_ids"], list(runner.EXPECTED_REQUEST_IDS))
        self.assertTrue(manifest["strict_validation"]["valid"])
        self.assertEqual(manifest["run_counters"]["logical_llm_calls"], 6)
        self.assertEqual(manifest["run_counters"]["http_attempts"], 6)
        for counter in runner.ZERO_COUNTERS:
            self.assertEqual(manifest["run_counters"][counter], 0)
        self.assertEqual(len(manifest["request_transcript"]), 6)
        self.assertEqual(
            len(list((output / "prompts").glob("*.txt"))), 6
        )
        self.assertEqual(
            len(list((output / "requests").glob("*.json"))), 6
        )
        self.assertEqual(
            len(list((output / "native_responses").glob("*.json"))), 6
        )
        self.assertEqual(
            len(list((output / "telemetry").glob("*.json"))), 6
        )
        self.assertEqual(
            len(list((output / "http_responses").glob("*.body"))), 6
        )
        self.assertEqual(
            len(list((output / "http_responses").glob("*.http.json"))), 6
        )
        for item in manifest["request_transcript"]:
            self.assertEqual(item["http_response_count"], 1)
            http_meta = json.loads(
                (output / item["http_response_paths"][0]["meta_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(http_meta["status_code"], 200)
            self.assertGreaterEqual(item["timing"]["elapsed_ns"], 0)
        config = json.loads((output / "config.json").read_text(encoding="utf-8"))
        self.assertEqual([bloc["num_agents"] for bloc in config["blocs"]], [1, 1, 1])
        self.assertEqual(config["agents"]["edge_policy"], "full")
        self.assertEqual(config["agents"]["communication_radius"], 3)
        self.assertEqual(config["simulation"]["duration"], 1)
        run_dir = output / "runs" / "output_prompt6-success-run"
        phase1 = (run_dir / "phase1_raw.jsonl").read_text(encoding="utf-8").splitlines()
        phase3 = (run_dir / "memory_reasoning.jsonl").read_text(encoding="utf-8").splitlines()
        messages = (run_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(phase1), 3)
        self.assertEqual(len(phase3), 3)
        self.assertEqual(len(messages), 3)
        self.assertEqual(len(api.calls), 15)  # 4 preflight + 1 postflight per endpoint

    def test_manifest_inventory_recomputes_and_detects_sidecar_tamper(self):
        output = self.root / "prompt6-inventory"
        api = FakeApi(self.bindings)
        native = FakeNative()
        with self.patched_runtime(native):
            runner.run_prompt6(
                output,
                "prompt6-inventory-run",
                repo_root=REPO_ROOT,
                api_client=api,
            )

        manifest = self.read_manifest(output)
        self.assertNotIn("prompt6_manifest.json", manifest["files"])
        for relative, recorded in manifest["files"].items():
            self.assertEqual(runner.file_manifest(output / relative), recorded)

        target_relative = sorted(
            relative
            for relative in manifest["files"]
            if relative.startswith("prompts/")
        )[0]
        target = output / target_relative
        with target.open("ab") as handle:
            handle.write(b"synthetic-tamper\n")
        self.assertNotEqual(
            runner.file_manifest(target),
            manifest["files"][target_relative],
        )

    def test_recovered_parse_retry_is_retained_but_fails_acceptance(self):
        output = self.root / "prompt6-retry"
        api = FakeApi(self.bindings)
        native = FakeNative(retry_first=True)
        with self.patched_runtime(native):
            with self.assertRaises(runner.Prompt6ExecutionError) as raised:
                runner.run_prompt6(
                    output,
                    "prompt6-retry-run",
                    repo_root=REPO_ROOT,
                    api_client=api,
                )
        self.assertEqual(raised.exception.evidence_dir, output.resolve())
        manifest = self.read_manifest(output)
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["logical_transport_records"], 6)
        self.assertEqual(manifest["native_response_envelopes"], 7)
        self.assertEqual(manifest["http_response_observations"], 7)
        self.assertTrue(manifest["strict_validation"]["valid"])
        self.assertEqual(manifest["run_counters"]["generation_retries"], 1)
        self.assertEqual(manifest["run_counters"]["http_attempts"], 7)
        self.assertTrue(any("per_request_telemetry" in item for item in manifest["failures"]))
        self.assertTrue(any("native_response_count" in item for item in manifest["failures"]))
        self.assertEqual(
            len(list((output / "native_responses").glob("*.json"))), 7
        )

    def test_wrong_native_response_model_fails_after_complete_run(self):
        output = self.root / "prompt6-wrong-model"
        api = FakeApi(self.bindings)
        native = FakeNative(wrong_model_at=5)
        with self.patched_runtime(native):
            with self.assertRaises(runner.Prompt6ExecutionError):
                runner.run_prompt6(
                    output,
                    "prompt6-wrong-model-run",
                    repo_root=REPO_ROOT,
                    api_client=api,
                )
        manifest = self.read_manifest(output)
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(manifest["strict_validation"]["valid"])
        self.assertTrue(
            any("native_response_model_mismatch" in item for item in manifest["failures"])
        )

    def test_preflight_digest_mismatch_stops_before_native_call(self):
        output = self.root / "prompt6-wrong-digest"
        api = FakeApi(self.bindings, wrong_digest=True)
        native = FakeNative()
        with self.patched_runtime(native) as native_mock:
            with self.assertRaises(runner.Prompt6ExecutionError):
                runner.run_prompt6(
                    output,
                    "prompt6-wrong-digest-run",
                    repo_root=REPO_ROOT,
                    api_client=api,
                )
        native_mock.assert_not_called()
        manifest = self.read_manifest(output)
        self.assertEqual(manifest["status"], "failed")
        self.assertIn("qwen:model_digest_mismatch", manifest["failures"])
        self.assertEqual(manifest["logical_transport_records"], 0)
        self.assertTrue((output / "preflight" / "qwen-api-tags.json").is_file())

    def test_preflight_requires_all_three_endpoints_to_start_empty(self):
        output = self.root / "prompt6-preloaded"
        api = FakeApi(self.bindings, preloaded_slot="llama")
        native = FakeNative()
        with self.patched_runtime(native) as native_mock:
            with self.assertRaises(runner.Prompt6ExecutionError):
                runner.run_prompt6(
                    output,
                    "prompt6-preloaded-run",
                    repo_root=REPO_ROOT,
                    api_client=api,
                )
        native_mock.assert_not_called()
        manifest = self.read_manifest(output)
        self.assertIn("llama:ps_before_not_empty", manifest["failures"])

    def test_exact_native_http_status_is_fail_closed(self):
        output = self.root / "prompt6-http-status"
        api = FakeApi(self.bindings)
        native = FakeNative(wrong_http_status_at=4)
        with self.patched_runtime(native):
            with self.assertRaises(runner.Prompt6ExecutionError):
                runner.run_prompt6(
                    output,
                    "prompt6-http-status-run",
                    repo_root=REPO_ROOT,
                    api_client=api,
                )
        manifest = self.read_manifest(output)
        self.assertTrue(
            any("http_status_not_200" in item for item in manifest["failures"])
        )
        fourth = manifest["request_transcript"][3]
        http_meta = json.loads(
            (output / fourth["http_response_paths"][0]["meta_path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(http_meta["status_code"], 201)

    def test_shape_diagnostics_do_not_replace_approved_parsed_acceptance(self):
        output = self.root / "prompt6-schema-diagnostic"
        api = FakeApi(self.bindings)
        native = FakeNative(schema_diagnostic_at=1)
        with self.patched_runtime(native):
            runner.run_prompt6(
                output,
                "prompt6-schema-diagnostic-run",
                repo_root=REPO_ROOT,
                api_client=api,
            )
        manifest = self.read_manifest(output)
        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(manifest["failures"], [])
        self.assertFalse(manifest["schema_validation_supported_by_engine"])
        self.assertEqual(len(manifest["schema_diagnostics"]), 1)
        self.assertEqual(
            manifest["schema_diagnostics"][0]["acceptance_effect"],
            "diagnostic_only",
        )

    def test_collision_is_fail_closed_before_api_or_native(self):
        output = self.root / "prompt6-collision"
        first_api = FakeApi(self.bindings)
        first_native = FakeNative()
        with self.patched_runtime(first_native):
            runner.run_prompt6(
                output,
                "prompt6-collision-run",
                repo_root=REPO_ROOT,
                api_client=first_api,
            )
        before = {
            path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*")
            if path.is_file()
        }
        second_api = FakeApi(self.bindings)
        second_native = FakeNative()
        with self.patched_runtime(second_native) as native_mock:
            with self.assertRaises(runner.Prompt6CollisionError):
                runner.run_prompt6(
                    output,
                    "prompt6-collision-run",
                    repo_root=REPO_ROOT,
                    api_client=second_api,
                )
        native_mock.assert_not_called()
        self.assertEqual(second_api.calls, [])
        after = {
            path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_terminal_phase1_transport_failure_retains_aborted_run(self):
        output = self.root / "prompt6-transport"
        api = FakeApi(self.bindings)
        native = FakeNative(transport_at=2)
        with self.patched_runtime(native):
            with self.assertRaises(runner.Prompt6ExecutionError):
                runner.run_prompt6(
                    output,
                    "prompt6-transport-run",
                    repo_root=REPO_ROOT,
                    api_client=api,
                )
        manifest = self.read_manifest(output)
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["logical_transport_records"], 3)
        self.assertIn("run_lifecycle_not_completed", manifest["failures"])
        run_meta = json.loads(
            (
                output
                / "runs"
                / "output_prompt6-transport-run"
                / "run_meta.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(run_meta["status"], "aborted")
        self.assertTrue(run_meta["aborted"])
        self.assertEqual(run_meta["logical_llm_calls"], 3)


if __name__ == "__main__":
    unittest.main()
