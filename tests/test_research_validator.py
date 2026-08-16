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

    def test_smoke_pass_research_unverifiable_and_read_only(self):
        before = tree_hashes(self.batch_dir)
        smoke = validate_batch_profile(self.batch_dir, "smoke")
        after = tree_hashes(self.batch_dir)
        self.assertEqual(smoke.exit_code, 0, smoke.errors)
        self.assertTrue(smoke.to_dict()["smoke_valid"])
        self.assertFalse(smoke.to_dict()["research_eligible"])
        self.assertTrue(smoke.unverified_research_requirements)
        self.assertTrue(smoke.strict_unverifiable)
        self.assertEqual(before, after)

        research = validate_batch_profile(self.batch_dir, "research")
        self.assertEqual(research.exit_code, 2, research.errors)
        self.assertEqual(research.classification, "UNVERIFIABLE")
        self.assertFalse(research.to_dict()["research_eligible"])

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
        self.assertEqual(failed.returncode, 3, failed.stderr + failed.stdout)
        self.assertEqual(invocation.returncode, 64, invocation.stderr + invocation.stdout)


if __name__ == "__main__":
    unittest.main()
