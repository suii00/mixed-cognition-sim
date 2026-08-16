import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ollama_reference_probe import (
    ProbeCollisionError,
    ProbeFailure,
    run_probe,
)


GPU_UUID = "GPU-720e6563-7e95-65c4-659e-189ba0c7bac5"
DIGEST = "3" * 64
MODEL = "qwen2.5:3b"
TEMPLATE = "{{ .Prompt }}"
TEMPLATE_SHA256 = "b507b9c2f6ca642bffcd06665ea7c91f235fd32daeefdf875a0f938db05fb315"


class FakeResponse:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.content = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return copy.deepcopy(self.value)


def server_log(*, vulkan=False):
    compute = (
        f'time=x level=INFO msg="inference compute" filter_id={GPU_UUID} '
        "library=CUDA name=CUDA0\n"
    )
    if vulkan:
        compute += (
            'time=x level=INFO msg="inference compute" filter_id=1 '
            "library=Vulkan name=Vulkan1\n"
        )
    return (
        "time=x level=INFO msg=\"server config\" "
        f"env=\"map[CUDA_VISIBLE_DEVICES:{GPU_UUID} "
        "OLLAMA_CONTEXT_LENGTH:4096 OLLAMA_MAX_LOADED_MODELS:1 "
        "OLLAMA_NO_CLOUD:true OLLAMA_NUM_PARALLEL:1 "
        f"OLLAMA_VULKAN:{str(vulkan).lower()}]\"\n"
        "time=x level=INFO msg=\"Listening on 127.0.0.1:11440\"\n"
        + compute
        + "time=x level=INFO msg=\"selecting GPU backend\" library=CUDA\n"
    )


class OllamaReferenceProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.log = self.root / "server.log"
        self.log.write_text(server_log(), encoding="utf-8")
        self.context_length = 4096

    def tearDown(self):
        self.temp.cleanup()

    def fake_api(self, method, url, json=None, timeout=None):
        if url.endswith("/api/version"):
            return FakeResponse({"version": "0.32.13"})
        if url.endswith("/api/tags"):
            return FakeResponse({
                "models": [{
                    "name": MODEL,
                    "model": MODEL,
                    "digest": DIGEST,
                    "details": {
                        "format": "gguf",
                        "parameter_size": "3.1B",
                        "quantization_level": "Q4_K_M",
                    },
                }]
            })
        if url.endswith("/api/show"):
            self.assertEqual(method, "POST")
            self.assertEqual(json, {"model": MODEL})
            return FakeResponse({
                "template": TEMPLATE,
                "details": {"quantization_level": "Q4_K_M"},
            })
        if url.endswith("/api/ps"):
            return FakeResponse({
                "models": [{
                    "name": MODEL,
                    "model": MODEL,
                    "digest": DIGEST,
                    "size": 2_000_000_000,
                    "size_vram": 2_000_000_000,
                    "context_length": self.context_length,
                }]
            })
        raise AssertionError(url)

    @staticmethod
    def fake_command(args, *, timeout_s=30.0, env_overrides=None):
        command = " ".join(args)
        if args[:2] == ["ollama", "ps"]:
            stdout = (
                "NAME ID SIZE PROCESSOR CONTEXT UNTIL\n"
                f"{MODEL} {DIGEST[:12]} 2.0 GB 100% GPU 4096 Forever\n"
            ).encode()
        elif "--query-compute-apps=" in command:
            stdout = (
                f"{GPU_UUID}, 123, /usr/local/lib/ollama/ollama_llama_server, 2100\n"
            ).encode()
        elif args[:2] == ["ollama", "--version"]:
            stdout = b"ollama version is 0.32.13\n"
        else:
            stdout = b"read-only probe output\n"
        return {
            "argv": list(args),
            "exit_code": 0,
            "stdout": stdout,
            "stderr": b"",
            "error": None,
        }

    @staticmethod
    def fake_call_ollama(**kwargs):
        self_payload = kwargs
        self_payload["telemetry"]("http_attempt", 1)
        content = '{"message":"smoke"}'
        envelope = {
            "model": MODEL,
            "created_at": "2026-08-16T00:00:00Z",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
            "total_duration": 100,
            "load_duration": 10,
            "prompt_eval_count": 20,
            "prompt_eval_duration": 30,
            "eval_count": 5,
            "eval_duration": 40,
        }
        self_payload["response_observer"](envelope)
        return {"message": "smoke"}, content

    def invoke(self, output, **patches):
        call = patches.pop("call", self.fake_call_ollama)
        api = patches.pop("api", self.fake_api)
        command = patches.pop("command", self.fake_command)
        self.assertFalse(patches)
        with (
            mock.patch("tools.ollama_reference_probe.call_ollama", side_effect=call) as llm,
            mock.patch("tools.ollama_reference_probe.requests.request", side_effect=api),
            mock.patch("tools.ollama_reference_probe._run_command", side_effect=command),
            mock.patch(
                "tools.ollama_reference_probe.collect_git_info",
                return_value={
                    "git_sha": "a" * 40,
                    "git_dirty": False,
                    "git_probe_status": "available",
                    "git_probe_errors": [],
                },
            ),
            mock.patch(
                "tools.ollama_reference_probe.compute_prompt_hash",
                return_value="b" * 64,
            ),
        ):
            result = run_probe(
                output,
                server_log=self.log,
                base_url="http://127.0.0.1:11440",
                model=MODEL,
                expected_digest=DIGEST,
                expected_quantization="Q4_K_M",
                expected_template_sha256=TEMPLATE_SHA256,
                expected_gpu_uuid=GPU_UUID,
                temperature=0.2,
                max_tokens=256,
            )
        return result, llm

    def test_pass_captures_full_envelope_payload_and_manifest(self):
        output = self.root / "probe-pass"
        result, llm = self.invoke(output)
        self.assertEqual(result, output)
        manifest = json.loads(
            (output / "backend_evidence_manifest.json").read_text()
        )
        self.assertEqual(manifest["status"], "passed")
        self.assertFalse(manifest["research_eligible"])
        self.assertTrue(manifest["evidence_id"].startswith("gate4a1-"))
        self.assertEqual(manifest["native_response_count"], 1)
        self.assertFalse(manifest["failures"])
        self.assertTrue(all(check["passed"] for check in manifest["checks"]))
        request = json.loads((output / "request.json").read_text())
        self.assertEqual(request["options"]["num_ctx"], 4096)
        self.assertEqual(request["keep_alive"], -1)
        response = json.loads((output / "native-response-01.json").read_text())
        self.assertEqual(response["total_duration"], 100)
        kwargs = llm.call_args.kwargs
        self.assertEqual(kwargs["llm_overrides"], {"num_ctx": 4096})
        self.assertEqual(kwargs["keep_alive"], -1)
        self.assertIn("server-log-after.txt", manifest["files"])

    def test_wrong_allocated_context_fails_and_retains_evidence(self):
        output = self.root / "probe-context-fail"
        self.context_length = 8192
        with self.assertRaises(ProbeFailure):
            self.invoke(output)
        manifest = json.loads(
            (output / "backend_evidence_manifest.json").read_text()
        )
        self.assertEqual(manifest["status"], "failed")
        self.assertFalse(manifest["research_eligible"])
        self.assertIn("allocated_context_matches", manifest["failures"])
        self.assertTrue((output / "api-ps-after.json").is_file())

    def test_vulkan_visibility_stops_before_model_request(self):
        output = self.root / "probe-vulkan-fail"
        self.log.write_text(server_log(vulkan=True), encoding="utf-8")
        call = mock.Mock(side_effect=AssertionError("model request must not run"))
        with self.assertRaises(ProbeFailure):
            self.invoke(output, call=call)
        call.assert_not_called()
        manifest = json.loads(
            (output / "backend_evidence_manifest.json").read_text()
        )
        self.assertIn("server_vulkan_disabled", manifest["failures"])
        self.assertEqual(manifest["native_response_count"], 0)

    def test_existing_evidence_directory_is_not_modified(self):
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "sentinel.txt"
        sentinel.write_text("owned", encoding="utf-8")
        with self.assertRaises(ProbeCollisionError):
            run_probe(
                output,
                server_log=self.log,
                base_url="http://127.0.0.1:11440",
                model=MODEL,
                expected_digest=DIGEST,
                expected_quantization="Q4_K_M",
                expected_template_sha256=TEMPLATE_SHA256,
                expected_gpu_uuid=GPU_UUID,
                temperature=0.2,
                max_tokens=256,
            )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "owned")
        self.assertEqual([path.name for path in output.iterdir()], ["sentinel.txt"])


if __name__ == "__main__":
    unittest.main()
