import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
import yaml

from engine.config import load_config
from engine.llm_client import LLMTransportError, call_ollama
from engine.provenance import (
    InvalidRunIdError,
    RunLifecycle,
    collect_bloc_models,
    collect_git_info,
    collect_gpu_info,
    compute_config_hash,
    compute_prompt_hash,
    generate_run_id,
    normalize_run_id,
    sanitize_config,
    validate_base_url,
)


class FakeResponse:
    def __init__(self, content, http_error=None):
        self.content = content
        self.http_error = http_error

    def raise_for_status(self):
        if self.http_error is not None:
            raise self.http_error

    def json(self):
        return {"message": {"content": self.content}}


class RunIdentityTests(unittest.TestCase):
    def test_generated_run_ids_are_unique_and_canonical(self):
        first = generate_run_id()
        second = generate_run_id()

        self.assertNotEqual(first, second)
        self.assertEqual(normalize_run_id(first), first)
        self.assertEqual(normalize_run_id(second), second)

    def test_unsafe_or_noncanonical_run_ids_are_rejected(self):
        invalid_ids = (
            "",
            " ",
            ".",
            "..",
            "a..b",
            "../escape",
            "/absolute",
            "a/b",
            r"a\b",
            "C:\\escape",
            "CON",
            "con.txt",
            " full-width-edge ",
            "ｆｕｌｌｗｉｄｔｈ",
            "a" * 129,
        )
        for run_id in invalid_ids:
            with self.subTest(run_id=run_id):
                with self.assertRaises(InvalidRunIdError):
                    normalize_run_id(run_id)

    def test_safe_boundary_run_ids_are_accepted_without_rewriting(self):
        for run_id in ("a", "Run-01.alpha_beta", "a" * 128):
            with self.subTest(run_id=run_id):
                self.assertEqual(normalize_run_id(run_id), run_id)


def minimal_config(run_id="provenance-test"):
    return {
        "simulation": {
            "duration": 1,
            "half_space_size": 2,
            "seed": 7,
            "run_name": "test",
            "run_id": run_id,
        },
        "blocs": [{
            "name": "alpha",
            "provider": "ollama",
            "model": "model-a",
            "base_url": "http://localhost:11434",
            "num_agents": 1,
        }],
        "agents": {},
        "places": [],
        "llm_defaults": {"max_tokens": 32},
    }


class ProvenanceSanitizationTests(unittest.TestCase):
    def test_recursive_secret_keys_and_urls_are_not_retained(self):
        secrets = [
            "EXACT_TOKEN_SECRET",
            "API_TOKEN_SECRET",
            "API_KEY_SECRET",
            "AUTH_SECRET",
            "URL_PASSWORD_SECRET",
            "URL_QUERY_SECRET",
            "NESTED_URL_SECRET",
        ]
        config = {
            "token": secrets[0],
            "api_token": secrets[1],
            "service_secret": "SUFFIX_SECRET",
            "session_cookie": "COOKIE_SECRET",
            "aws_secret_access_key": "AWS_ACCESS_SECRET",
            "secretKey": "CAMEL_SECRET_KEY",
            "access-key": "ACCESS_KEY_SECRET",
            "secretkey": "COMPACT_SECRET_KEY",
            "accesskey": "COMPACT_ACCESS_KEY",
            "authkey": "COMPACT_AUTH_KEY",
            "key": "GENERIC_KEY_SECRET",
            "openai_key": "OPENAI_KEY_SECRET",
            "tls_key": "TLS_KEY_SECRET",
            "ａｐｉ＿ｋｅｙ": "FULLWIDTH_KEY_SECRET",
            "proxy_auth": "PROXY_AUTH_SECRET",
            "bearer": "BEARER_SECRET",
            "passphrase": "PASSPHRASE_SECRET",
            "pwd": "PWD_SECRET",
            "pass": "PASS_SECRET",
            "dbPass": "DB_PASS_SECRET",
            "dbpass": "COMPACT_DB_PASS_SECRET",
            "db_pwd": "DB_PWD_SECRET",
            "nested": [{
                "api-key": secrets[2],
                "headers": {"Authorization": secrets[3]},
                "max_tokens": 123,
                "tokenizer": "public-tokenizer-name",
            }],
            "base_url": (
                "https://user:URL_PASSWORD_SECRET@example.test:8443/"
                "private/URL_PASSWORD_SECRET?token=URL_QUERY_SECRET#fragment"
            ),
            "application_specific": (
                "https://user:NESTED_URL_SECRET@nested.example/path"
            ),
            "database_dsn": (
                "postgresql://user:POSTGRES_SECRET@db.example/private"
            ),
            "redis_uri": "redis://user:REDIS_SECRET@redis.example/0",
            "connection_string": (
                "jdbc:postgresql://user:JDBC_SECRET@db.example/private"
            ),
            "connectionstring": (
                "jdbc:mysql://user:MYSQL_SECRET@db.example/private"
            ),
            "odbc_connect": "Driver=DB;Server=db.example;Pwd=ODBC_SECRET",
            "jdbc_setting": (
                "jdbc:postgresql://user:JDBC_NESTED_SECRET@db.example/private"
            ),
            "oracle_connection": (
                "jdbc:oracle:thin:user/ORACLE_SECRET@db.example:1521:XE"
            ),
            "encoded_odbc": (
                "Driver%3DDB%3BServer%3Ddb.example%3BPwd%3DENCODED_ODBC_SECRET"
            ),
        }

        snapshot = sanitize_config(config)
        serialized = json.dumps(snapshot, sort_keys=True)

        for secret in secrets:
            self.assertNotIn(secret, serialized)
        self.assertNotIn("SUFFIX_SECRET", serialized)
        self.assertNotIn("COOKIE_SECRET", serialized)
        self.assertNotIn("AWS_ACCESS_SECRET", serialized)
        self.assertNotIn("CAMEL_SECRET_KEY", serialized)
        self.assertNotIn("ACCESS_KEY_SECRET", serialized)
        self.assertNotIn("COMPACT_SECRET_KEY", serialized)
        self.assertNotIn("COMPACT_ACCESS_KEY", serialized)
        self.assertNotIn("COMPACT_AUTH_KEY", serialized)
        self.assertNotIn("GENERIC_KEY_SECRET", serialized)
        self.assertNotIn("OPENAI_KEY_SECRET", serialized)
        self.assertNotIn("TLS_KEY_SECRET", serialized)
        self.assertNotIn("FULLWIDTH_KEY_SECRET", serialized)
        self.assertNotIn("POSTGRES_SECRET", serialized)
        self.assertNotIn("REDIS_SECRET", serialized)
        self.assertNotIn("PROXY_AUTH_SECRET", serialized)
        self.assertNotIn("BEARER_SECRET", serialized)
        self.assertNotIn("PASSPHRASE_SECRET", serialized)
        self.assertNotIn("PWD_SECRET", serialized)
        self.assertNotIn("PASS_SECRET", serialized)
        self.assertNotIn("DB_PASS_SECRET", serialized)
        self.assertNotIn("COMPACT_DB_PASS_SECRET", serialized)
        self.assertNotIn("DB_PWD_SECRET", serialized)
        self.assertNotIn("JDBC_SECRET", serialized)
        self.assertNotIn("MYSQL_SECRET", serialized)
        self.assertNotIn("ODBC_SECRET", serialized)
        self.assertNotIn("JDBC_NESTED_SECRET", serialized)
        self.assertNotIn("ORACLE_SECRET", serialized)
        self.assertNotIn("ENCODED_ODBC_SECRET", serialized)
        self.assertEqual(snapshot["token"], "<redacted>")
        self.assertEqual(snapshot["api_token"], "<redacted>")
        self.assertEqual(snapshot["nested"][0]["max_tokens"], 123)
        self.assertEqual(
            snapshot["nested"][0]["tokenizer"], "public-tokenizer-name"
        )
        self.assertEqual(snapshot["base_url"], "https://example.test:8443")
        self.assertEqual(
            snapshot["application_specific"], "https://nested.example"
        )

    def test_bloc_model_summary_never_contains_url_credentials_or_path(self):
        config = minimal_config()
        config["blocs"][0]["base_url"] = (
            "https://user:password@example.test:9443/private?api_key=secret"
        )

        models = collect_bloc_models(config)
        serialized = json.dumps(models)

        self.assertEqual(models[0]["base_url_host"], "example.test")
        self.assertEqual(models[0]["base_url_port"], 9443)
        for forbidden in ("user", "password", "private", "api_key", "secret"):
            self.assertNotIn(forbidden, serialized)

    def test_config_hash_is_stable_across_mapping_order(self):
        first = sanitize_config({
            "simulation": {"seed": 1, "duration": 2},
            "items": [{"b": 2, "a": 1}],
        })
        second = sanitize_config({
            "items": [{"a": 1, "b": 2}],
            "simulation": {"duration": 2, "seed": 1},
        })

        self.assertEqual(compute_config_hash(first), compute_config_hash(second))
        changed = sanitize_config({
            "simulation": {"seed": 1, "duration": 2},
            "items": [{"a": 1, "b": 3}],
        })
        self.assertNotEqual(compute_config_hash(first), compute_config_hash(changed))

    def test_noncredential_url_options_remain_hash_distinct(self):
        first = sanitize_config({
            "llm_overrides": {
                "stop": ["https://stop.example/a?mode=one#first"]
            }
        })
        second = sanitize_config({
            "llm_overrides": {
                "stop": ["https://stop.example/b?mode=two#second"]
            }
        })

        self.assertEqual(
            first["llm_overrides"]["stop"][0],
            "https://stop.example/a?mode=one#first",
        )
        self.assertNotEqual(compute_config_hash(first), compute_config_hash(second))

        first_endpoint = sanitize_config({
            "endpoint": "https://service.example/a?mode=one#first",
            "database_dsn": "postgresql://db.example/database_a",
        })
        second_endpoint = sanitize_config({
            "endpoint": "https://service.example/b?mode=two#second",
            "database_dsn": "postgresql://db.example/database_b",
        })
        self.assertEqual(
            first_endpoint["endpoint"],
            "https://service.example/a?mode=one#first",
        )
        self.assertEqual(
            first_endpoint["database_dsn"],
            "postgresql://db.example/database_a",
        )
        self.assertNotEqual(
            compute_config_hash(first_endpoint),
            compute_config_hash(second_endpoint),
        )

        credential = sanitize_config({
            "llm_overrides": {
                "stop": [
                    "https://user:STOP_SECRET@stop.example/a?mode=one",
                    "https://stop.example/b?api_key=QUERY_SECRET",
                ]
            }
        })
        serialized = json.dumps(credential, sort_keys=True)
        self.assertNotIn("STOP_SECRET", serialized)
        self.assertNotIn("QUERY_SECRET", serialized)

    def test_non_json_config_values_are_rejected_before_output_creation(self):
        invalid_values = (
            ("set-value", {"values": {"alpha", "beta"}}),
            ("tuple-value", {"values": ("alpha", "beta")}),
            ("non-string-key", {1: "alpha"}),
        )
        for run_id, invalid in invalid_values:
            with self.subTest(run_id=run_id), tempfile.TemporaryDirectory() as temp_dir:
                with self.assertRaisesRegex(ValueError, "config"):
                    sanitize_config({"unsupported": invalid})

                config = minimal_config(run_id)
                config["unsupported"] = invalid
                output = Path(temp_dir)

                with self.assertRaisesRegex(ValueError, "config"):
                    RunLifecycle.create(config, output_root=output)

                self.assertFalse((output / f"output_{run_id}").exists())

    def test_only_the_effective_ollama_provider_is_accepted(self):
        without_provider = minimal_config()
        del without_provider["blocs"][0]["provider"]
        self.assertEqual(
            collect_bloc_models(without_provider)[0]["provider"],
            "ollama",
        )

        for provider in ("vllm", "Ollama", ""):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp_dir:
                config = minimal_config(f"provider-{provider or 'empty'}")
                config["blocs"][0]["provider"] = provider
                output = Path(temp_dir)
                with (
                    mock.patch("engine.provenance.collect_git_info") as git_probe,
                    self.assertRaisesRegex(ValueError, "exactly 'ollama'"),
                ):
                    RunLifecycle.create(config, output_root=output)
                git_probe.assert_not_called()
                self.assertFalse(
                    (output / f"output_{config['simulation']['run_id']}").exists()
                )

    def test_config_loader_rejects_a_non_ollama_provider(self):
        config = minimal_config("loader-provider")
        config["blocs"][0]["provider"] = "vllm"
        with mock.patch(
            "builtins.open",
            mock.mock_open(read_data=yaml.safe_dump(config)),
        ):
            with self.assertRaisesRegex(ValueError, "exactly 'ollama'"):
                load_config("unused.yaml")

    def test_prompt_hash_is_file_byte_hash_and_cwd_independent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "engine").mkdir()
            prompt_bytes = b"PROMPT = 'stable'\n"
            (root / "engine" / "prompts.py").write_bytes(prompt_bytes)
            expected = hashlib.sha256(prompt_bytes).hexdigest()

            self.assertEqual(compute_prompt_hash(root), expected)
            with mock.patch("pathlib.Path.cwd", return_value=Path("/unrelated")):
                self.assertEqual(compute_prompt_hash(root), expected)

    def test_current_prompt_hash_is_a_guarded_golden_value(self):
        self.assertEqual(
            compute_prompt_hash(),
            "f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d",
        )

    def test_persisted_run_meta_contains_no_config_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            output = root / "runs"
            (repo / "engine").mkdir(parents=True)
            output.mkdir()
            (repo / "engine" / "prompts.py").write_text("PROMPT = 'x'\n")
            config = minimal_config("secret-meta-test")
            config["llm_defaults"]["api_token"] = "META_TOKEN_SECRET"
            config["llm_defaults"]["aws_secret_access_key"] = "META_AWS_SECRET"
            config["llm_defaults"]["bearer"] = "META_BEARER_SECRET"
            config["llm_defaults"]["passphrase"] = "META_PASSPHRASE_SECRET"
            config["llm_defaults"]["pwd"] = "META_PWD_SECRET"
            config["llm_defaults"]["dbPass"] = "META_DB_PASS_SECRET"
            config["llm_defaults"]["dbpass"] = "META_COMPACT_DB_PASS_SECRET"
            config["llm_defaults"]["db_pwd"] = "META_DB_PWD_SECRET"
            config["llm_defaults"]["connection_string"] = (
                "jdbc:postgresql://user:META_JDBC_SECRET@db.example/private"
            )
            config["llm_defaults"]["connectionstring"] = (
                "jdbc:mysql://user:META_MYSQL_SECRET@db.example/private"
            )
            config["llm_defaults"]["odbc_connect"] = (
                "Driver=DB;Server=db.example;Pwd=META_ODBC_SECRET"
            )
            config["blocs"][0]["base_url"] = "https://example.test:9443"
            with (
                mock.patch("engine.provenance.collect_git_info", return_value={
                    "git_sha": "c" * 40,
                    "git_dirty": True,
                    "git_probe_status": "available",
                    "git_probe_errors": [],
                }),
                mock.patch("engine.provenance.collect_gpu_info", return_value={
                    "status": "unavailable",
                    "error": "test_disabled",
                    "driver_version": None,
                    "cuda_version": None,
                    "devices": [],
                }),
            ):
                lifecycle = RunLifecycle.create(
                    config, output_root=output, repo_root=repo
                )

            serialized = (lifecycle.output_dir / "run_meta.json").read_text(
                encoding="utf-8"
            )
            for secret in (
                "META_TOKEN_SECRET",
                "META_AWS_SECRET",
                "META_BEARER_SECRET",
                "META_PASSPHRASE_SECRET",
                "META_PWD_SECRET",
                "META_DB_PASS_SECRET",
                "META_COMPACT_DB_PASS_SECRET",
                "META_DB_PWD_SECRET",
                "META_JDBC_SECRET",
                "META_MYSQL_SECRET",
                "META_ODBC_SECRET",
            ):
                self.assertNotIn(secret, serialized)
            self.assertEqual(
                lifecycle.meta["config"]["llm_defaults"]["api_token"],
                "<redacted>",
            )
            self.assertEqual(
                lifecycle.meta["models"][0]["base_url_host"],
                "example.test",
            )

    def test_noncanonical_or_credentialed_base_urls_are_rejected(self):
        invalid_urls = (
            "localhost:11434",
            "ftp://example.test",
            "http://user:password@example.test",
            "http://example.test/",
            "http://example.test/api",
            "http://example.test?token=secret",
            "http://example.test#fragment",
        )
        for value in invalid_urls:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_base_url(value)

    def test_invalid_base_url_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            config = minimal_config("unsafe-url-run")
            config["blocs"][0]["base_url"] = (
                "https://user:URL_SECRET@example.test/private?token=secret"
            )

            with self.assertRaises(ValueError):
                RunLifecycle.create(config, output_root=output)

            self.assertFalse((output / "output_unsafe-url-run").exists())


class ProvenanceProbeTests(unittest.TestCase):
    def test_lifecycle_constructor_interrupt_leaves_no_reserved_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            with (
                mock.patch("engine.provenance.collect_git_info", return_value={
                    "git_sha": "d" * 40,
                    "git_dirty": False,
                    "git_probe_status": "available",
                    "git_probe_errors": [],
                }),
                mock.patch("engine.provenance.collect_gpu_info", return_value={
                    "status": "unavailable",
                    "error": "test_disabled",
                    "driver_version": None,
                    "cuda_version": None,
                    "devices": [],
                }),
                mock.patch.object(
                    RunLifecycle,
                    "__init__",
                    side_effect=KeyboardInterrupt,
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    RunLifecycle.create(
                        minimal_config("constructor-interrupt"),
                        output_root=output,
                    )

            self.assertFalse(
                (output / "output_constructor-interrupt").exists()
            )

    def test_git_dirty_uses_porcelain_output_without_storing_it(self):
        responses = [
            (True, "abc123\n", ""),
            (True, " M tracked.py\n?? untracked-secret-name\n", ""),
        ]
        with mock.patch("engine.provenance._run_command", side_effect=responses):
            info = collect_git_info(Path("/repo"))

        self.assertEqual(info["git_sha"], "abc123")
        self.assertTrue(info["git_dirty"])
        self.assertNotIn("tracked.py", json.dumps(info))
        self.assertNotIn("untracked-secret-name", json.dumps(info))

    def test_unexpected_git_probe_error_is_nonfatal_and_sanitized(self):
        with mock.patch(
            "engine.provenance._run_command",
            side_effect=RuntimeError("SECRET_FROM_GIT"),
        ):
            info = collect_git_info(Path("/repo"))

        self.assertEqual(info["git_probe_status"], "unavailable")
        self.assertIsNone(info["git_sha"])
        self.assertIsNone(info["git_dirty"])
        self.assertNotIn("SECRET_FROM_GIT", json.dumps(info))

    def test_gpu_command_failure_is_explicit_and_nonfatal(self):
        with mock.patch(
            "engine.provenance._run_command",
            return_value=(False, "", "command_not_found"),
        ):
            info = collect_gpu_info()

        self.assertEqual(info["status"], "unavailable")
        self.assertEqual(info["error"], "command_not_found")
        self.assertEqual(info["devices"], [])

    def test_partially_malformed_gpu_output_is_explicit(self):
        responses = [
            (
                True,
                "0, GPU-A, UUID-A, 40960, 555.1\nmalformed-row\n",
                "",
            ),
            (
                True,
                "NVIDIA-SMI 555.1 Driver Version: 555.1 "
                "CUDA Version: 12.5 |\n",
                "",
            ),
        ]
        with mock.patch(
            "engine.provenance._run_command", side_effect=responses
        ):
            info = collect_gpu_info()

        self.assertEqual(info["status"], "partial")
        self.assertEqual(info["error"], "malformed_device_rows")
        self.assertEqual(info["malformed_device_rows"], 1)
        self.assertEqual(len(info["devices"]), 1)

    def test_unexpected_gpu_probe_error_is_nonfatal_and_sanitized(self):
        with mock.patch(
            "engine.provenance._run_command",
            side_effect=RuntimeError("SECRET_FROM_PROBE"),
        ):
            info = collect_gpu_info()

        self.assertEqual(info["status"], "unavailable")
        self.assertEqual(info["error"], "unexpected_probe_error")
        self.assertNotIn("SECRET_FROM_PROBE", json.dumps(info))

    def test_lifecycle_survives_an_injected_gpu_probe_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            output = root / "runs"
            (repo / "engine").mkdir(parents=True)
            output.mkdir()
            (repo / "engine" / "prompts.py").write_text("PROMPT = 'x'\n")
            with (
                mock.patch("engine.provenance.collect_gpu_info", side_effect=RuntimeError("secret")),
                mock.patch("engine.provenance.collect_git_info", return_value={
                    "git_sha": "abc",
                    "git_dirty": True,
                    "git_probe_status": "available",
                    "git_probe_errors": [],
                }),
                mock.patch("engine.provenance.collect_dependency_versions", return_value={}),
            ):
                lifecycle = RunLifecycle.create(
                    minimal_config(), output_root=output, repo_root=repo
                )

            self.assertEqual(lifecycle.meta["gpu_info"]["status"], "unavailable")
            self.assertEqual(
                lifecycle.meta["gpu_info"]["error"], "unexpected_probe_error"
            )
            self.assertNotIn("secret", json.dumps(lifecycle.meta))

    def test_initial_meta_finalize_failure_does_not_mask_original_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            output = root / "runs"
            (repo / "engine").mkdir(parents=True)
            output.mkdir()
            (repo / "engine" / "prompts.py").write_text("PROMPT = 'x'\n")
            primary = OSError("primary metadata write failure")
            secondary = OSError("secondary finalize failure")
            with (
                mock.patch("engine.provenance.atomic_write_json", side_effect=[primary, secondary]),
                mock.patch("engine.provenance.collect_git_info", return_value={
                    "git_sha": "abc",
                    "git_dirty": False,
                    "git_probe_status": "available",
                    "git_probe_errors": [],
                }),
                mock.patch("engine.provenance.collect_gpu_info", return_value={
                    "status": "unavailable",
                    "error": "command_not_found",
                    "driver_version": None,
                    "cuda_version": None,
                    "devices": [],
                }),
                mock.patch("engine.provenance.collect_dependency_versions", return_value={}),
            ):
                with self.assertRaisesRegex(OSError, "primary metadata") as raised:
                    RunLifecycle.create(
                        minimal_config(), output_root=output, repo_root=repo
                    )
            self.assertIs(raised.exception, primary)


class LlmTelemetryTests(unittest.TestCase):
    def _call(self, post_side_effect):
        events = []
        with (
            mock.patch("engine.llm_client.requests.post", side_effect=post_side_effect),
            mock.patch("engine.llm_client.time.sleep") as sleep,
        ):
            result = call_ollama(
                prompt="prompt",
                model="model",
                base_url="http://localhost:11434",
                telemetry=lambda event, amount: events.extend([event] * amount),
            )
        return result, events, sleep

    def test_success_counts_one_http_attempt(self):
        result, events, sleep = self._call([
            FakeResponse('{"message":"ok"}'),
        ])

        self.assertEqual(result[0], {"message": "ok"})
        self.assertEqual(events, ["http_attempt"])
        sleep.assert_not_called()

    def test_transport_retries_count_each_attempt_and_failure(self):
        result, events, sleep = self._call([
            requests.ConnectionError("secret-1"),
            requests.Timeout("secret-2"),
            FakeResponse('{"message":"ok"}'),
        ])

        self.assertEqual(result[0], {"message": "ok"})
        self.assertEqual(events.count("http_attempt"), 3)
        self.assertEqual(events.count("transport_failure"), 2)
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2)])

    def test_terminal_transport_failure_has_sanitized_error_and_counts(self):
        events = []
        with (
            mock.patch(
                "engine.llm_client.requests.post",
                side_effect=requests.ConnectionError("SECRET_URL_TOKEN"),
            ),
            mock.patch("engine.llm_client.time.sleep"),
        ):
            with self.assertRaises(LLMTransportError) as raised:
                call_ollama(
                    prompt="prompt",
                    model="model",
                    base_url="https://user:SECRET@example.test?token=SECRET",
                    telemetry=lambda event, amount: events.extend([event] * amount),
                )

        self.assertEqual(events.count("http_attempt"), 3)
        self.assertEqual(events.count("transport_failure"), 3)
        self.assertNotIn("SECRET", str(raised.exception))

    def test_generation_retry_and_syntax_attempts_are_distinct(self):
        result, events, sleep = self._call([
            FakeResponse("not json"),
            FakeResponse('{"message":"recovered"}'),
        ])

        self.assertEqual(result[0], {"message": "recovered"})
        self.assertEqual(events.count("http_attempt"), 2)
        self.assertEqual(events.count("generation_retry"), 1)
        self.assertEqual(events.count("syntax_parse_attempt_failure"), 1)
        sleep.assert_not_called()

    def test_final_syntax_failure_counts_both_invalid_generations(self):
        result, events, _ = self._call([
            FakeResponse("not json one"),
            FakeResponse("not json two"),
        ])

        self.assertIsNone(result[0])
        self.assertEqual(events.count("http_attempt"), 2)
        self.assertEqual(events.count("generation_retry"), 1)
        self.assertEqual(events.count("syntax_parse_attempt_failure"), 2)


if __name__ == "__main__":
    unittest.main()
