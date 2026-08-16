import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import gate4_evidence_publisher as publisher
from tools import verify_gate4_evidence_bundle as verifier


GPU_UUIDS = sorted(
    [
        "GPU-720e6563-7e95-65c4-659e-189ba0c7bac5",
        "GPU-2964f342-8734-a701-a2c6-4344579b03ee",
    ]
)
STOP_CONDITIONS = sorted(
    [
        "HTTP status is not 200",
        "transport or parse failure occurs",
    ]
)


def canonical_json(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_record(path):
    data = path.read_bytes()
    return {
        "sha256": sha256(data),
        "bytes": len(data),
        "lines": data.count(b"\n"),
    }


class IndependentGate4EvidenceVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.bundle = self.make_bundle("bundle-independent")

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def original_correction():
        return {
            "kind": "original",
            "supersedes": None,
            "reason_code": None,
            "reason": None,
            "raw_artifacts_changed": False,
            "repaired_properties": [],
            "not_repaired": [],
        }

    def make_bundle(self, bundle_id):
        root = self.workspace / bundle_id
        (root / "raw").mkdir(parents=True)
        (root / "publication").mkdir()
        (root / "raw" / "events.jsonl").write_bytes(b'{"event":"fixture"}\n')

        approval = {
            "schema_version": verifier.APPROVAL_SCHEMA_VERSION,
            "evidence_bundle_id": bundle_id,
            "approved_final_path": str(root.resolve()),
            "logical_generation_limit": 6,
            "wall_clock_limit_seconds": 900,
            "gpu_uuids": GPU_UUIDS,
            "stop_conditions": STOP_CONDITIONS,
            "approved": True,
            "approval_reference": "synthetic CPU-only fixture",
        }
        (root / verifier.APPROVAL_FILENAME).write_bytes(canonical_json(approval))

        captured_paths = [verifier.APPROVAL_FILENAME, "raw/events.jsonl"]
        capture = {
            "schema_version": verifier.CAPTURE_MANIFEST_SCHEMA_VERSION,
            "files": {
                relative: file_record(root / relative) for relative in captured_paths
            },
        }
        capture_bytes = canonical_json(capture)
        (root / verifier.CAPTURE_MANIFEST_FILENAME).write_bytes(capture_bytes)

        publisher_bytes = b'# immutable publisher snapshot fixture\nVERSION = "v1"\n'
        contract_bytes = (
            Path(verifier.__file__).resolve().parents[1]
            / "docs"
            / "GATE4_EVIDENCE_PUBLICATION_SPEC.md"
        ).read_bytes()
        (root / verifier.PUBLISHER_SNAPSHOT_PATH).write_bytes(publisher_bytes)
        (root / verifier.CONTRACT_SNAPSHOT_PATH).write_bytes(contract_bytes)

        summary = {
            "schema_version": verifier.SUMMARY_SCHEMA_VERSION,
            "evidence_bundle_id": bundle_id,
            "run_id": f"run-{bundle_id}",
            "protocol_version": "gate4-test-protocol-v1.0.0",
            "metric_version": "metric-v2.0.0",
            "execution_mode": "reference_ollama",
            "operational_backend_result": "NOT_EVALUATED",
            "evidence_publication_conformance": "CONFORMING",
            "gate4_formal_pass": False,
            "research_eligible": False,
            "backend_freeze": {"status": "not_frozen"},
            "authorization": {
                "path": verifier.APPROVAL_FILENAME,
                "sha256": sha256((root / verifier.APPROVAL_FILENAME).read_bytes()),
            },
            "claim_scope": verifier.STRUCTURE_ONLY_CLAIM_SCOPE,
            "warnings": [],
            "unverified_claims": verifier.STRUCTURE_ONLY_UNVERIFIED_CLAIMS,
            "correction": self.original_correction(),
            "source_capture": {
                "manifest_path": verifier.CAPTURE_MANIFEST_FILENAME,
                "manifest_sha256": sha256(capture_bytes),
            },
            "publisher": {
                "path": verifier.PUBLISHER_SNAPSHOT_PATH,
                "sha256": sha256(publisher_bytes),
                "version": verifier.PUBLISHER_VERSION,
            },
            "publication_contract": {
                "path": verifier.CONTRACT_SNAPSHOT_PATH,
                "sha256": sha256(contract_bytes),
                "version": verifier.PUBLICATION_SPEC_VERSION,
            },
        }
        (root / verifier.SUMMARY_FILENAME).write_bytes(canonical_json(summary))
        self.rebuild_inventory(root)
        return root

    @staticmethod
    def rebuild_inventory(root):
        paths = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name != verifier.INVENTORY_FILENAME
        )
        inventory = b"".join(
            f"{sha256((root / relative).read_bytes())}  ./{relative}\n".encode(
                "ascii"
            )
            for relative in paths
        )
        (root / verifier.INVENTORY_FILENAME).write_bytes(inventory)

    @staticmethod
    def load_summary(root):
        return json.loads((root / verifier.SUMMARY_FILENAME).read_bytes())

    def write_summary(self, root, summary):
        (root / verifier.SUMMARY_FILENAME).write_bytes(canonical_json(summary))
        self.rebuild_inventory(root)

    def refresh_capture_manifest(self, root):
        capture = {
            "schema_version": verifier.CAPTURE_MANIFEST_SCHEMA_VERSION,
            "files": {
                relative: file_record(root / relative)
                for relative in [verifier.APPROVAL_FILENAME, "raw/events.jsonl"]
            },
        }
        capture_bytes = canonical_json(capture)
        (root / verifier.CAPTURE_MANIFEST_FILENAME).write_bytes(capture_bytes)
        summary = self.load_summary(root)
        summary["source_capture"]["manifest_sha256"] = sha256(capture_bytes)
        (root / verifier.SUMMARY_FILENAME).write_bytes(canonical_json(summary))
        self.rebuild_inventory(root)

    def make_corrected_bundle(self, bundle_id, predecessor):
        predecessor_report = verifier.verify_bundle(predecessor)
        self.assertTrue(predecessor_report.valid, predecessor_report.errors)
        root = self.make_bundle(bundle_id)
        summary = self.load_summary(root)
        summary["correction"] = {
            "kind": "derived_correction",
            "supersedes": {
                "evidence_bundle_id": predecessor_report.evidence_bundle_id,
                "summary_sha256": predecessor_report.summary_sha256,
                "inventory_sha256": predecessor_report.inventory_sha256,
                "bundle_root_sha256": predecessor_report.bundle_root_sha256,
            },
            "reason_code": "summary_schema_correction",
            "reason": "Correct derived summary schema without changing captured raw bytes.",
            "raw_artifacts_changed": False,
            "repaired_properties": ["summary_schema"],
            "not_repaired": sorted(verifier.HISTORICAL_NONREPAIRABLE),
        }
        self.write_summary(root, summary)
        return root

    def replace_contract_bytes(self, root, relative, data):
        (root / relative).write_bytes(data)
        if relative in {verifier.APPROVAL_FILENAME, verifier.CAPTURE_MANIFEST_FILENAME}:
            summary = self.load_summary(root)
            if relative == verifier.APPROVAL_FILENAME:
                summary["authorization"]["sha256"] = sha256(data)
            else:
                summary["source_capture"]["manifest_sha256"] = sha256(data)
            (root / verifier.SUMMARY_FILENAME).write_bytes(canonical_json(summary))
        self.rebuild_inventory(root)

    def assert_invalid(self, root=None, contains=None):
        report = verifier.verify_bundle(root or self.bundle)
        self.assertFalse(report.valid)
        self.assertFalse(report.publication_conforming)
        self.assertFalse(report.formal_gate4_pass)
        self.assertFalse(report.research_eligible)
        self.assertTrue(report.errors)
        if contains is not None:
            self.assertIn(contains, " ".join(report.errors))
        return report

    def test_valid_bundle_computes_independent_s_i_r_and_fixed_axes(self):
        report = verifier.verify_bundle(self.bundle)
        self.assertTrue(report.valid, report.errors)
        self.assertTrue(report.publication_conforming)
        self.assertTrue(report.commitments_match)
        self.assertEqual(report.evidence_bundle_id, self.bundle.name)
        self.assertEqual(report.operational_backend_result, "NOT_EVALUATED")
        self.assertFalse(report.formal_gate4_pass)
        self.assertFalse(report.research_eligible)
        self.assertEqual(report.backend_freeze_status, "not_frozen")

        summary_bytes = (self.bundle / verifier.SUMMARY_FILENAME).read_bytes()
        inventory_bytes = (self.bundle / verifier.INVENTORY_FILENAME).read_bytes()
        expected_s = sha256(summary_bytes)
        expected_i = sha256(inventory_bytes)
        expected_r = sha256(
            verifier.ROOT_HASH_DOMAIN + bytes.fromhex(expected_i)
        )
        self.assertEqual(report.summary_sha256, expected_s)
        self.assertEqual(report.inventory_sha256, expected_i)
        self.assertEqual(report.bundle_root_sha256, expected_r)

        pinned = verifier.verify_bundle(
            self.bundle,
            expected_summary_sha256=expected_s,
            expected_inventory_sha256=expected_i,
            expected_bundle_root_sha256=expected_r,
        )
        self.assertTrue(pinned.valid, pinned.errors)

    def test_publisher_output_interoperates_with_independent_s_i_r_verifier(self):
        bundle_id = "bundle-publisher-interoperability"
        publication_root = self.workspace / "publisher-output"
        publication_root.mkdir()
        source = self.workspace / "publisher-source"
        (source / "raw").mkdir(parents=True)
        (source / "raw" / "events.jsonl").write_bytes(
            b'{"event":"publisher-interoperability-fixture"}\n'
        )
        approval = {
            "schema_version": publisher.APPROVAL_SCHEMA_VERSION,
            "evidence_bundle_id": bundle_id,
            "approved_final_path": str((publication_root / bundle_id).resolve()),
            "logical_generation_limit": 6,
            "wall_clock_limit_seconds": 900,
            "gpu_uuids": GPU_UUIDS,
            "stop_conditions": STOP_CONDITIONS,
            "approved": True,
            "approval_reference": "synthetic CPU-only interoperability fixture",
        }
        (source / publisher.APPROVAL_FILENAME).write_bytes(canonical_json(approval))
        summary = {
            "schema_version": publisher.SUMMARY_SCHEMA_VERSION,
            "evidence_bundle_id": bundle_id,
            "run_id": f"run-{bundle_id}",
            "protocol_version": "gate4-test-protocol-v1.0.0",
            "metric_version": "metric-v2.0.0",
            "execution_mode": "reference_ollama",
            "operational_backend_result": "NOT_EVALUATED",
            "evidence_publication_conformance": "CONFORMING",
            "gate4_formal_pass": False,
            "research_eligible": False,
            "backend_freeze": {"status": "not_frozen"},
            "claim_scope": list(publisher.GENERIC_CLAIM_SCOPE),
            "warnings": [],
            "unverified_claims": list(publisher.GENERIC_UNVERIFIED_CLAIMS),
            "correction": self.original_correction(),
        }

        receipt = publisher.publish_evidence(source, publication_root, summary)
        report = verifier.verify_bundle(
            receipt.final_path,
            expected_summary_sha256=receipt.summary_sha256,
            expected_inventory_sha256=receipt.inventory_sha256,
            expected_bundle_root_sha256=receipt.bundle_root_sha256,
            expected_final_identity=receipt.final_directory_identity.as_dict(),
        )
        self.assertTrue(report.valid, report.errors)
        self.assertTrue(report.publication_conforming)
        self.assertTrue(report.commitments_match)
        self.assertEqual(report.summary_sha256, receipt.summary_sha256)
        self.assertEqual(report.inventory_sha256, receipt.inventory_sha256)
        self.assertEqual(report.bundle_root_sha256, receipt.bundle_root_sha256)
        self.assertEqual(
            report.directory_identity.as_dict(),
            receipt.final_directory_identity.as_dict(),
        )
        wrong_identity = verifier.verify_bundle(
            receipt.final_path,
            expected_summary_sha256=receipt.summary_sha256,
            expected_inventory_sha256=receipt.inventory_sha256,
            expected_bundle_root_sha256=receipt.bundle_root_sha256,
            expected_final_identity={"device": 0, "inode": 1},
        )
        self.assertFalse(wrong_identity.valid)
        self.assertIn(
            "expected final directory identity differs",
            wrong_identity.errors,
        )

    def test_expected_commitment_mismatch_is_nonzero_quality_without_reclassifying_structure(self):
        report = verifier.verify_bundle(
            self.bundle,
            expected_summary_sha256="0" * 64,
            expected_inventory_sha256="not-a-hash",
        )
        self.assertFalse(report.valid)
        self.assertTrue(report.publication_conforming)
        self.assertFalse(report.commitments_match)
        self.assertIn("expected S commitment differs", report.errors)
        self.assertIn("expected I is not a lowercase SHA-256", report.errors)

    def test_verifier_has_no_publisher_import(self):
        source_path = Path(verifier.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(
            any(name.endswith("gate4_evidence_publisher") for name in imported),
            imported,
        )

    def test_all_contract_json_files_reject_duplicate_nan_and_noncanonical_bytes(self):
        cases = []

        root = self.make_bundle("bundle-json-summary-duplicate")
        data = (root / verifier.SUMMARY_FILENAME).read_bytes()
        cases.append(
            (
                root,
                verifier.SUMMARY_FILENAME,
                data[:-2]
                + b',"schema_version":"gate4-backend-evidence-summary-v1.0.0"}\n',
                "duplicate object key",
            )
        )

        root = self.make_bundle("bundle-json-approval-nan")
        data = (root / verifier.APPROVAL_FILENAME).read_bytes().replace(
            b'"logical_generation_limit":6',
            b'"logical_generation_limit":NaN',
        )
        cases.append((root, verifier.APPROVAL_FILENAME, data, "invalid numeric constant"))

        root = self.make_bundle("bundle-json-capture-noncanonical")
        value = json.loads((root / verifier.CAPTURE_MANIFEST_FILENAME).read_bytes())
        data = (json.dumps(value, indent=2) + "\n").encode("utf-8")
        cases.append(
            (root, verifier.CAPTURE_MANIFEST_FILENAME, data, "not canonical JSON")
        )

        for root, relative, data, expected in cases:
            with self.subTest(relative=relative):
                self.replace_contract_bytes(root, relative, data)
                self.assert_invalid(root, expected)

    def test_exact_inventory_path_set_and_hash_are_required(self):
        extra = self.make_bundle("bundle-extra")
        (extra / "raw" / "unlisted.txt").write_text("extra", encoding="utf-8")
        self.assert_invalid(extra, "inventory path set differs")

        tampered = self.make_bundle("bundle-tampered")
        (tampered / "raw" / "events.jsonl").write_bytes(b"tampered\n")
        self.assert_invalid(tampered, "inventory hash differs")

        missing = self.make_bundle("bundle-inventory-missing")
        lines = (missing / verifier.INVENTORY_FILENAME).read_bytes().splitlines(True)
        (missing / verifier.INVENTORY_FILENAME).write_bytes(b"".join(lines[1:]))
        self.assert_invalid(missing, "inventory path set differs")

        self_listed = self.make_bundle("bundle-inventory-self")
        inventory = (self_listed / verifier.INVENTORY_FILENAME).read_bytes()
        inventory += f"{'0' * 64}  ./files.sha256\n".encode("ascii")
        (self_listed / verifier.INVENTORY_FILENAME).write_bytes(inventory)
        self.assert_invalid(self_listed, "may not list itself")

    def test_capture_manifest_must_exactly_bind_path_hash_size_and_lines(self):
        capture_path = self.bundle / verifier.CAPTURE_MANIFEST_FILENAME
        capture = json.loads(capture_path.read_bytes())
        capture["files"]["raw/events.jsonl"]["lines"] += 1
        capture_bytes = canonical_json(capture)
        capture_path.write_bytes(capture_bytes)
        summary = self.load_summary(self.bundle)
        summary["source_capture"]["manifest_sha256"] = sha256(capture_bytes)
        (self.bundle / verifier.SUMMARY_FILENAME).write_bytes(canonical_json(summary))
        self.rebuild_inventory(self.bundle)
        self.assert_invalid(self.bundle, "capture manifest path/hash/size/line set differs")

    def test_contract_snapshot_must_match_the_guarded_v1_hash(self):
        contract_path = self.bundle / verifier.CONTRACT_SNAPSHOT_PATH
        changed = contract_path.read_bytes() + b"\nunauthorized contract change\n"
        contract_path.write_bytes(changed)
        summary = self.load_summary(self.bundle)
        summary["publication_contract"]["sha256"] = sha256(changed)
        (self.bundle / verifier.SUMMARY_FILENAME).write_bytes(canonical_json(summary))
        self.rebuild_inventory(self.bundle)
        self.assert_invalid(self.bundle, "not the guarded v1 contract")

    def test_symlink_hardlink_fifo_and_symlink_root_are_rejected(self):
        symlinked = self.make_bundle("bundle-symlink")
        os.symlink("events.jsonl", symlinked / "raw" / "alias")
        self.assert_invalid(symlinked, "symlinks")

        hardlinked = self.make_bundle("bundle-hardlink")
        outside = self.workspace / "outside.bin"
        outside.write_bytes(b"shared")
        os.link(outside, hardlinked / "raw" / "hardlink.bin")
        self.assert_invalid(hardlinked, "hard-linked")

        fifo = self.make_bundle("bundle-fifo")
        os.mkfifo(fifo / "raw" / "pipe")
        self.assert_invalid(fifo, "regular files")

        alias = self.workspace / "bundle-root-alias"
        os.symlink(self.bundle, alias)
        self.assert_invalid(alias, "path is a symlink")

    def test_fixed_structure_only_and_noneligibility_values_fail_closed(self):
        mutations = {
            "operational": ("operational_backend_result", "PASS"),
            "formal": ("gate4_formal_pass", True),
            "research": ("research_eligible", True),
            "scope": ("claim_scope", ["operational_backend_result"]),
            "warnings": ("warnings", ["warning"]),
            "unverified": ("unverified_claims", ["run_id"]),
        }
        for label, (field, replacement) in mutations.items():
            root = self.make_bundle(f"bundle-fixed-{label}")
            summary = self.load_summary(root)
            summary[field] = replacement
            self.write_summary(root, summary)
            with self.subTest(field=field):
                self.assert_invalid(root)

        root = self.make_bundle("bundle-fixed-backend")
        summary = self.load_summary(root)
        summary["backend_freeze"] = {"status": "frozen"}
        self.write_summary(root, summary)
        self.assert_invalid(root, "not_frozen")

    def test_unknown_missing_wrong_types_and_bool_integer_are_rejected(self):
        root = self.make_bundle("bundle-unknown-summary")
        summary = self.load_summary(root)
        summary["unknown"] = True
        self.write_summary(root, summary)
        self.assert_invalid(root, "key set differs")

        root = self.make_bundle("bundle-missing-summary")
        summary = self.load_summary(root)
        summary.pop("protocol_version")
        self.write_summary(root, summary)
        self.assert_invalid(root, "missing")

        root = self.make_bundle("bundle-bool-limit")
        approval_path = root / verifier.APPROVAL_FILENAME
        approval = json.loads(approval_path.read_bytes())
        approval["logical_generation_limit"] = True
        self.replace_contract_bytes(root, verifier.APPROVAL_FILENAME, canonical_json(approval))
        self.assert_invalid(root, "positive integer")

    def test_derived_correction_requires_and_fully_binds_original_predecessor(self):
        original = self.make_bundle("bundle-correction-original")
        corrected = self.make_corrected_bundle(
            "bundle-correction-derived", original
        )

        self.assert_invalid(corrected, "requires a predecessor")
        report = verifier.verify_bundle(corrected, predecessor_path=original)
        self.assertTrue(report.valid, report.errors)

        original_with_predecessor = verifier.verify_bundle(
            original, predecessor_path=self.bundle
        )
        self.assertFalse(original_with_predecessor.valid)
        self.assertIn(
            "original bundle may not name a predecessor",
            " ".join(original_with_predecessor.errors),
        )

        cli = subprocess.run(
            [
                sys.executable,
                str(Path(verifier.__file__)),
                str(corrected),
                "--predecessor",
                str(original),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
        self.assertTrue(json.loads(cli.stdout)["valid"])

    def test_correction_rejects_wrong_commitment_raw_change_and_correction_chain(self):
        original = self.make_bundle("bundle-correction-base")

        wrong_hash = self.make_corrected_bundle(
            "bundle-correction-wrong-hash", original
        )
        summary = self.load_summary(wrong_hash)
        summary["correction"]["supersedes"]["summary_sha256"] = "0" * 64
        self.write_summary(wrong_hash, summary)
        report = verifier.verify_bundle(wrong_hash, predecessor_path=original)
        self.assertFalse(report.valid)
        self.assertIn("predecessor summary_sha256 differs", " ".join(report.errors))

        raw_changed = self.make_corrected_bundle(
            "bundle-correction-raw-changed", original
        )
        (raw_changed / "raw" / "events.jsonl").write_bytes(b"changed raw\n")
        self.refresh_capture_manifest(raw_changed)
        report = verifier.verify_bundle(raw_changed, predecessor_path=original)
        self.assertFalse(report.valid)
        self.assertIn("changed captured raw artifacts", " ".join(report.errors))

        first_correction = self.make_corrected_bundle(
            "bundle-correction-first", original
        )
        first_report = verifier.verify_bundle(
            first_correction, predecessor_path=original
        )
        self.assertTrue(first_report.valid, first_report.errors)
        chained = self.make_bundle("bundle-correction-chain")
        summary = self.load_summary(chained)
        summary["correction"] = {
            "kind": "derived_correction",
            "supersedes": {
                "evidence_bundle_id": first_report.evidence_bundle_id,
                "summary_sha256": first_report.summary_sha256,
                "inventory_sha256": first_report.inventory_sha256,
                "bundle_root_sha256": first_report.bundle_root_sha256,
            },
            "reason_code": "derived_metadata_correction",
            "reason": "A correction chain is intentionally unsupported by v1.",
            "raw_artifacts_changed": False,
            "repaired_properties": ["derived_metadata"],
            "not_repaired": [],
        }
        self.write_summary(chained, summary)
        report = verifier.verify_bundle(chained, predecessor_path=first_correction)
        self.assertFalse(report.valid)
        self.assertIn("requires a predecessor", " ".join(report.errors))

    def test_correction_uses_closed_reason_and_property_sets_and_distinct_id(self):
        original = self.make_bundle("bundle-correction-closed-base")
        mutations = {
            "unsupported_reason": ("reason_code", "fixture"),
            "mismatched_reason": (
                "reason_code",
                "derived_metadata_correction",
            ),
            "unsupported_repaired": ("repaired_properties", ["raw_evidence"]),
            "unsupported_unrepaired": ("not_repaired", ["summary_schema"]),
            "non_disjoint": (
                "both",
                ["summary_schema"],
            ),
            "same_id": ("same_id", None),
        }
        for label, (field, replacement) in mutations.items():
            root = self.make_corrected_bundle(
                f"bundle-correction-closed-{label}", original
            )
            summary = self.load_summary(root)
            correction = summary["correction"]
            if field == "both":
                correction["repaired_properties"] = replacement
                correction["not_repaired"] = replacement
            elif field == "same_id":
                correction["supersedes"]["evidence_bundle_id"] = root.name
            else:
                correction[field] = replacement
            self.write_summary(root, summary)
            with self.subTest(label=label):
                report = verifier.verify_bundle(root, predecessor_path=original)
                self.assertFalse(report.valid)

    def test_second_snapshot_compares_retained_contract_bytes_not_only_records(self):
        real_snapshot = verifier._snapshot_tree
        calls = 0

        def alter_second_snapshot(root):
            nonlocal calls
            calls += 1
            snapshot = real_snapshot(root)
            if calls == 2:
                retained = dict(snapshot.contract_bytes)
                retained[verifier.SUMMARY_FILENAME] += b"changed-after-records"
                return verifier.TreeSnapshot(
                    snapshot.records,
                    retained,
                    snapshot.root_identity,
                )
            return snapshot

        with mock.patch.object(verifier, "_snapshot_tree", alter_second_snapshot):
            report = verifier.verify_bundle(self.bundle)
        self.assertFalse(report.valid)
        self.assertIn("changed during verification", " ".join(report.errors))

    def test_descriptor_relative_walk_rejects_intermediate_directory_symlink_swap(self):
        real_open = verifier.os.open
        raw = self.bundle / "raw"
        parked = self.bundle / "raw-before-swap"
        swapped = False

        def swap_before_child_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if (
                not swapped
                and path == "raw"
                and kwargs.get("dir_fd") is not None
                and flags & os.O_DIRECTORY
            ):
                swapped = True
                os.rename(raw, parked)
                os.symlink(parked.name, raw, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(verifier.os, "open", swap_before_child_open):
            report = verifier.verify_bundle(self.bundle)
        self.assertTrue(swapped)
        self.assertFalse(report.valid)
        self.assertIn(
            "cannot safely open evidence directory entry: raw",
            " ".join(report.errors),
        )

    def test_descriptor_relative_walk_rejects_named_file_inode_swap(self):
        real_open = verifier.os.open
        event = self.bundle / "raw" / "events.jsonl"
        parked = self.bundle / "raw" / "events-before-swap.jsonl"
        swapped = False

        def swap_before_file_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if (
                not swapped
                and path == "events.jsonl"
                and kwargs.get("dir_fd") is not None
                and not flags & os.O_DIRECTORY
            ):
                swapped = True
                os.rename(event, parked)
                event.write_bytes(b"replacement inode with different bytes\n")
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(verifier.os, "open", swap_before_file_open):
            report = verifier.verify_bundle(self.bundle)
        self.assertTrue(swapped)
        self.assertFalse(report.valid)
        self.assertIn(
            "between named lookup and descriptor open changed during snapshot",
            " ".join(report.errors),
        )

    def test_root_component_walk_rejects_static_ancestor_symlink(self):
        bundle = self.make_bundle("bundle-static-ancestor-symlink")
        real_parent = self.workspace / "real-ancestor"
        real_parent.mkdir()
        relocated = real_parent / bundle.name
        os.rename(bundle, relocated)
        alias_parent = self.workspace / "alias-ancestor"
        os.symlink(real_parent.name, alias_parent, target_is_directory=True)

        report = verifier.verify_bundle(alias_parent / relocated.name)
        self.assertFalse(report.valid)
        self.assertIn(
            "absolute evidence path may not contain symlink components",
            " ".join(report.errors),
        )

    def test_root_component_walk_rejects_ancestor_lookup_open_swap(self):
        bundle = self.make_bundle("bundle-ancestor-swap")
        ancestor = self.workspace / "ancestor-before-swap"
        ancestor.mkdir()
        relocated = ancestor / bundle.name
        os.rename(bundle, relocated)
        parked = self.workspace / "ancestor-after-swap"
        real_open = verifier.os.open
        swapped = False

        def swap_ancestor_before_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if (
                not swapped
                and path == ancestor.name
                and kwargs.get("dir_fd") is not None
                and flags & os.O_DIRECTORY
            ):
                swapped = True
                os.rename(ancestor, parked)
                ancestor.mkdir()
            return real_open(path, flags, *args, **kwargs)

        try:
            with mock.patch.object(verifier.os, "open", swap_ancestor_before_open):
                report = verifier.verify_bundle(ancestor / relocated.name)
        finally:
            if parked.exists():
                ancestor.rmdir()
                os.rename(parked, ancestor)
        self.assertTrue(swapped)
        self.assertFalse(report.valid)
        self.assertIn(
            "between named lookup and descriptor open changed during snapshot",
            " ".join(report.errors),
        )

    def test_derived_current_tree_is_rechecked_after_predecessor_verification(self):
        original = self.make_bundle("bundle-post-predecessor-original")
        corrected = self.make_corrected_bundle(
            "bundle-post-predecessor-current", original
        )
        real_snapshot = verifier._snapshot_tree
        calls = 0

        def alter_current_final_snapshot(root):
            nonlocal calls
            calls += 1
            snapshot = real_snapshot(root)
            if calls == 5:
                self.assertEqual(root, corrected.resolve())
                retained = dict(snapshot.contract_bytes)
                retained[verifier.SUMMARY_FILENAME] += b"post-predecessor-swap"
                return verifier.TreeSnapshot(
                    snapshot.records,
                    retained,
                    snapshot.root_identity,
                )
            return snapshot

        with mock.patch.object(
            verifier, "_snapshot_tree", alter_current_final_snapshot
        ):
            report = verifier.verify_bundle(corrected, predecessor_path=original)
        self.assertEqual(calls, 5)
        self.assertFalse(report.valid)
        self.assertIn(
            "current evidence tree after predecessor verification changed",
            " ".join(report.errors),
        )

    def test_cli_always_emits_json_and_returns_zero_only_for_valid_matching_bundle(self):
        script = Path(verifier.__file__)
        baseline = verifier.verify_bundle(self.bundle)
        valid = subprocess.run(
            [
                sys.executable,
                str(script),
                str(self.bundle),
                "--expected-s",
                baseline.summary_sha256,
                "--expected-i",
                baseline.inventory_sha256,
                "--expected-r",
                baseline.bundle_root_sha256,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        valid_report = json.loads(valid.stdout)
        self.assertTrue(valid_report["valid"])
        self.assertEqual(valid_report["schema_version"], verifier.REPORT_SCHEMA_VERSION)

        mismatch = subprocess.run(
            [
                sys.executable,
                str(script),
                str(self.bundle),
                "--expected-r",
                "f" * 64,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(mismatch.returncode, 1)
        mismatch_report = json.loads(mismatch.stdout)
        self.assertFalse(mismatch_report["valid"])
        self.assertTrue(mismatch_report["publication_conforming"])
        self.assertFalse(mismatch_report["commitments_match"])

        missing = subprocess.run(
            [sys.executable, str(script), str(self.workspace / "not-present")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(missing.returncode, 1)
        missing_report = json.loads(missing.stdout)
        self.assertFalse(missing_report["publication_conforming"])


if __name__ == "__main__":
    unittest.main()
