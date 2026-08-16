import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from engine.provenance import build_raw_manifest, file_manifest
from tests.gate3_fixtures import (
    REPO_ROOT,
    patched_gate3_environment,
    tree_hashes,
    write_plan_fixture,
)
from tools.eight_cell_core import canonical_json_file_bytes, sha256_file
from tools.eight_cell_runner import run_smoke_batch
from tools.research_validator import (
    validate_batch_profile,
    validate_run_profile,
)


class ResearchValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared_temp = tempfile.TemporaryDirectory()
        cls.shared_root = Path(cls.shared_temp.name)
        _, _, _, cls.bundle = write_plan_fixture(
            cls.shared_root, matrix_id="gate3-validator"
        )
        with patched_gate3_environment():
            cls.batch_dir = run_smoke_batch(
                cls.bundle,
                cls.shared_root / "batches",
                repo_root=REPO_ROOT,
            )

    @classmethod
    def tearDownClass(cls):
        cls.shared_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def copy_batch(self, name: str) -> Path:
        target = self.root / name / self.batch_dir.name
        target.parent.mkdir(parents=True)
        shutil.copytree(self.batch_dir, target)
        return target

    @staticmethod
    def read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_bytes(canonical_json_file_bytes(value))

    @staticmethod
    def read_rows(batch: Path) -> list[dict]:
        return [
            json.loads(line)
            for line in (batch / "planned_runs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    @staticmethod
    def write_rows(batch: Path, rows: list[dict]) -> None:
        (batch / "planned_runs.jsonl").write_bytes(
            b"".join(canonical_json_file_bytes(row) for row in rows)
        )

    def first_run_paths(self, batch: Path) -> tuple[dict, Path, Path]:
        row = self.read_rows(batch)[0]
        config_path = batch / row["config_path"]
        run_dir = batch / "runs" / f"output_{row['run_id']}"
        return row, config_path, run_dir

    def test_smoke_pass_research_unverifiable_and_read_only(self):
        before = tree_hashes(self.batch_dir)
        smoke = validate_batch_profile(self.batch_dir, "smoke")
        after = tree_hashes(self.batch_dir)
        self.assertEqual(smoke.exit_code, 0, smoke.errors)
        self.assertTrue(smoke.to_dict()["smoke_valid"])
        self.assertFalse(smoke.to_dict()["research_eligible"])
        self.assertEqual(smoke.details["execution_mode"], "scripted_smoke")
        self.assertTrue(smoke.unverified_research_requirements)
        self.assertTrue(smoke.strict_unverifiable)
        self.assertEqual(before, after)

        research = validate_batch_profile(self.batch_dir, "research")
        self.assertEqual(research.exit_code, 2, research.errors)
        self.assertEqual(research.classification, "UNVERIFIABLE")
        self.assertFalse(research.to_dict()["research_eligible"])
        self.assertEqual(research.details["execution_mode"], "scripted_smoke")

    def test_single_run_profiles_bind_to_planned_evidence(self):
        row = self.bundle.rows[0]
        run_dir = self.batch_dir / "runs" / f"output_{row['run_id']}"
        smoke = validate_run_profile(
            run_dir, self.batch_dir, dict(row), "smoke"
        )
        research = validate_run_profile(
            run_dir, self.batch_dir, dict(row), "research"
        )
        self.assertEqual(smoke.exit_code, 0, smoke.errors)
        self.assertEqual(research.exit_code, 2, research.errors)
        self.assertEqual(smoke.details["execution_mode"], "scripted_smoke")
        self.assertEqual(research.details["execution_mode"], "scripted_smoke")

    def test_execution_mode_conflicts_fail_across_every_evidence_layer(self):
        for layer in ("batch", "row", "config", "run"):
            with self.subTest(layer=layer):
                batch = self.copy_batch(f"mode-{layer}")
                row, config_path, run_dir = self.first_run_paths(batch)
                if layer == "batch":
                    meta_path = batch / "batch_meta.json"
                    value = self.read_json(meta_path)
                    value["execution_mode"] = "reference_ollama"
                    self.write_json(meta_path, value)
                elif layer == "row":
                    rows = self.read_rows(batch)
                    rows[0]["execution_mode"] = "reference_ollama"
                    self.write_rows(batch, rows)
                elif layer == "config":
                    value = self.read_json(config_path)
                    value["simulation"]["execution_mode"] = "reference_ollama"
                    self.write_json(config_path, value)
                else:
                    meta_path = run_dir / "run_meta.json"
                    value = self.read_json(meta_path)
                    value["config"]["simulation"][
                        "execution_mode"
                    ] = "reference_ollama"
                    self.write_json(meta_path, value)

                before = tree_hashes(batch)
                report = validate_batch_profile(batch, "research")
                self.assertEqual(report.exit_code, 3, report.errors)
                self.assertFalse(report.to_dict()["research_eligible"])
                self.assertIsNone(report.details["execution_mode"])
                self.assertTrue(
                    any("execution_mode conflict" in error for error in report.errors),
                    report.errors,
                )
                self.assertEqual(before, tree_hashes(batch))

    def test_recomputed_manifest_cannot_conceal_batch_mode_conflict(self):
        batch = self.copy_batch("mode-recomputed")
        meta_path = batch / "batch_meta.json"
        manifest_path = batch / "batch_manifest.json"
        meta = self.read_json(meta_path)
        meta["execution_mode"] = "reference_ollama"
        manifest = self.read_json(manifest_path)
        self.write_json(manifest_path, manifest)
        meta["batch_manifest_sha256"] = sha256_file(manifest_path)
        self.write_json(meta_path, meta)

        row = self.read_rows(batch)[0]
        run_dir = batch / "runs" / f"output_{row['run_id']}"
        before = tree_hashes(batch)
        batch_result = validate_batch_profile(batch, "research")
        run_result = validate_run_profile(
            run_dir, batch, row, "research"
        )
        self.assertEqual(batch_result.exit_code, 3, batch_result.errors)
        self.assertEqual(run_result.exit_code, 3, run_result.errors)
        self.assertIsNone(batch_result.details["execution_mode"])
        self.assertIsNone(run_result.details["execution_mode"])
        self.assertTrue(
            any(
                "execution_mode conflict" in error
                for error in batch_result.errors + run_result.errors
            )
        )
        self.assertEqual(before, tree_hashes(batch))

        batch_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.research_validator",
                "batch",
                "--profile",
                "research",
                "--batch-dir",
                str(batch),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        run_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.research_validator",
                "run",
                "--profile",
                "research",
                "--batch-dir",
                str(batch),
                "--run-id",
                row["run_id"],
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(batch_cli.returncode, 3, batch_cli.stderr + batch_cli.stdout)
        self.assertEqual(run_cli.returncode, 3, run_cli.stderr + run_cli.stdout)
        self.assertEqual(
            json.loads(batch_cli.stdout)["classification"],
            json.loads(run_cli.stdout)["classification"],
        )
        self.assertEqual(before, tree_hashes(batch))

    def test_persisted_research_eligible_cannot_override_derived_result(self):
        for layer in ("batch", "row", "config", "run", "manifest"):
            with self.subTest(layer=layer):
                batch = self.copy_batch(f"eligible-{layer}")
                row, config_path, run_dir = self.first_run_paths(batch)
                if layer == "batch":
                    path = batch / "batch_meta.json"
                    value = self.read_json(path)
                    value["research_eligible"] = True
                    self.write_json(path, value)
                elif layer == "row":
                    rows = self.read_rows(batch)
                    rows[0]["research_eligible"] = True
                    self.write_rows(batch, rows)
                elif layer == "config":
                    value = self.read_json(config_path)
                    value["simulation"]["research_eligible"] = True
                    self.write_json(config_path, value)
                elif layer == "run":
                    path = run_dir / "run_meta.json"
                    value = self.read_json(path)
                    value["config"]["simulation"]["research_eligible"] = True
                    self.write_json(path, value)
                else:
                    path = batch / "batch_manifest.json"
                    value = self.read_json(path)
                    value["runs"][0]["research_eligible"] = True
                    self.write_json(path, value)

                before = tree_hashes(batch)
                report = validate_batch_profile(batch, "research")
                self.assertEqual(report.exit_code, 3, report.errors)
                self.assertFalse(report.to_dict()["research_eligible"])
                self.assertTrue(
                    any(
                        "research eligible" in error
                        or "research_eligible" in error
                        for error in report.errors
                    ),
                    report.errors,
                )
                self.assertEqual(before, tree_hashes(batch))

    def test_config_cell_policy_seed_and_planned_run_tampering_fail(self):
        mutations = (
            ("config-cell", "config", lambda value: value["simulation"].update({"cell_id": "qqq-full"})),
            ("config-policy", "config", lambda value: value["agents"].update({"edge_policy": "within_bloc_only"})),
            ("config-seed", "config", lambda value: value["simulation"].update({"seed": 9999})),
            ("planned-run", "planned", lambda value: value[0].update({"run_id": "tampered-run"})),
        )
        for name, target, mutate in mutations:
            with self.subTest(name=name):
                batch = self.copy_batch(name)
                if target == "config":
                    config_path = batch / self.bundle.rows[0]["config_path"]
                    value = json.loads(config_path.read_text(encoding="utf-8"))
                    mutate(value)
                    config_path.write_bytes(canonical_json_file_bytes(value))
                else:
                    rows_path = batch / "planned_runs.jsonl"
                    value = [
                        json.loads(line)
                        for line in rows_path.read_text(encoding="utf-8").splitlines()
                    ]
                    mutate(value)
                    rows_path.write_text(
                        "".join(
                            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                            for row in value
                        ),
                        encoding="utf-8",
                        newline="\n",
                    )
                report = validate_batch_profile(batch, "smoke")
                self.assertEqual(report.exit_code, 3, report.errors)

    def test_manifest_extra_and_missing_run_tampering_fail(self):
        manifest_batch = self.copy_batch("manifest")
        meta_path = manifest_batch / "batch_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["batch_manifest_sha256"] = "0" * 64
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")
        self.assertEqual(
            validate_batch_profile(manifest_batch, "smoke").exit_code, 3
        )

        extra_batch = self.copy_batch("extra")
        (extra_batch / "runs" / "output_extra-run").mkdir()
        self.assertEqual(validate_batch_profile(extra_batch, "smoke").exit_code, 3)

        missing_batch = self.copy_batch("missing")
        missing = missing_batch / "runs" / f"output_{self.bundle.rows[0]['run_id']}"
        shutil.rmtree(missing)
        self.assertEqual(validate_batch_profile(missing_batch, "smoke").exit_code, 3)

    def test_cross_bloc_delivery_tamper_fails_even_with_recomputed_manifests(self):
        batch = self.copy_batch("cross-edge")
        row = next(
            item for item in self.bundle.rows
            if item["edge_policy"] == "within_bloc_only"
        )
        run_dir = batch / "runs" / f"output_{row['run_id']}"
        messages_path = run_dir / "messages.jsonl"
        messages = [
            json.loads(line)
            for line in messages_path.read_text(encoding="utf-8").splitlines()
        ]
        messages[0]["receiver_ids"].append(4)
        messages[0]["receiver_ids"].sort()
        messages_path.write_text(
            "".join(json.dumps(item) + "\n" for item in messages),
            encoding="utf-8",
            newline="\n",
        )
        run_meta_path = run_dir / "run_meta.json"
        run_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
        run_meta["raw_manifest"] = build_raw_manifest(run_dir)
        run_meta_path.write_text(
            json.dumps(run_meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        batch_manifest_path = batch / "batch_manifest.json"
        batch_manifest = json.loads(
            batch_manifest_path.read_text(encoding="utf-8")
        )
        manifest_row = next(
            item for item in batch_manifest["runs"] if item["run_id"] == row["run_id"]
        )
        manifest_row["run_meta_manifest"] = file_manifest(run_meta_path)
        manifest_row["raw_manifest"] = run_meta["raw_manifest"]
        batch_manifest_path.write_bytes(canonical_json_file_bytes(batch_manifest))
        batch_meta_path = batch / "batch_meta.json"
        batch_meta = json.loads(batch_meta_path.read_text(encoding="utf-8"))
        batch_meta["batch_manifest_sha256"] = sha256_file(batch_manifest_path)
        batch_meta_path.write_text(
            json.dumps(batch_meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        report = validate_batch_profile(batch, "smoke")
        self.assertEqual(report.exit_code, 3, report.errors)
        self.assertTrue(
            any("communication boundary" in error for error in report.errors),
            report.errors,
        )

    def test_cli_process_exit_codes_zero_two_three_and_sixty_four(self):
        base = [sys.executable, "-m", "tools.research_validator", "batch"]
        smoke = subprocess.run(
            base + ["--profile", "smoke", "--batch-dir", str(self.batch_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        research = subprocess.run(
            base + ["--profile", "research", "--batch-dir", str(self.batch_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        run_id = self.bundle.rows[0]["run_id"]
        run_base = [
            sys.executable,
            "-m",
            "tools.research_validator",
            "run",
            "--batch-dir",
            str(self.batch_dir),
            "--run-id",
            run_id,
        ]
        run_smoke = subprocess.run(
            run_base + ["--profile", "smoke"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        run_research = subprocess.run(
            run_base + ["--profile", "research"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        tampered = self.copy_batch("cli-tampered")
        (tampered / "batch_manifest.json").write_text("{}\n", encoding="utf-8")
        failed = subprocess.run(
            base + ["--profile", "smoke", "--batch-dir", str(tampered)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        invocation = subprocess.run(
            [sys.executable, "-m", "tools.research_validator"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(smoke.returncode, 0, smoke.stderr + smoke.stdout)
        self.assertEqual(research.returncode, 2, research.stderr + research.stdout)
        self.assertEqual(run_smoke.returncode, 0, run_smoke.stderr + run_smoke.stdout)
        self.assertEqual(
            run_research.returncode,
            2,
            run_research.stderr + run_research.stdout,
        )
        self.assertEqual(
            json.loads(research.stdout)["classification"],
            json.loads(run_research.stdout)["classification"],
        )
        self.assertEqual(failed.returncode, 3, failed.stderr + failed.stdout)
        self.assertEqual(invocation.returncode, 64, invocation.stderr + invocation.stdout)


if __name__ == "__main__":
    unittest.main()
