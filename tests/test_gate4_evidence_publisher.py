import copy
import json
import multiprocessing
import os
import shutil
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools import gate4_evidence_publisher as publisher


GPU_UUIDS = sorted([
    "GPU-720e6563-7e95-65c4-659e-189ba0c7bac5",
    "GPU-2964f342-8734-a701-a2c6-4344579b03ee",
    "GPU-af1ef9b0-329f-ff38-d4dd-062e2beca9e0",
])
STOP_CONDITIONS = sorted([
    "HTTP status is not 200",
    "model digest differs",
    "transport or parse failure occurs",
])


class InjectedPublicationFailure(RuntimeError):
    pass


def crash_publish(source, publication_root, summary, checkpoint):
    def crash(actual, _staging, _final):
        if actual == checkpoint:
            os._exit(73)

    publisher.publish_evidence(
        Path(source),
        Path(publication_root),
        summary,
        checkpoint_hook=crash,
    )


def crash_immediately_after_rename(source, publication_root, summary):
    original = publisher._rename_noreplace

    def publish_then_crash(staging, final, **kwargs):
        original(staging, final, **kwargs)
        os._exit(74)

    publisher._rename_noreplace = publish_then_crash
    publisher.publish_evidence(
        Path(source),
        Path(publication_root),
        summary,
    )


def competing_publish(source, publication_root, summary, barrier, outcomes):
    barrier.wait(timeout=10)
    try:
        publisher.publish_evidence(
            Path(source),
            Path(publication_root),
            summary,
        )
        outcome = "published"
    except publisher.EvidenceCollisionError:
        outcome = "collision"
    outcomes.put(outcome)


class Gate4EvidencePublisherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.publication_root = self.root / "published"
        self.publication_root.mkdir()

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

    def summary(self, bundle_id, *, result="NOT_EVALUATED", correction=None):
        return {
            "schema_version": publisher.SUMMARY_SCHEMA_VERSION,
            "evidence_bundle_id": bundle_id,
            "run_id": f"run-{bundle_id}",
            "protocol_version": "gate4-test-protocol-v1.0.0",
            "metric_version": "metric-v2.0.0",
            "execution_mode": "reference_ollama",
            "operational_backend_result": result,
            "evidence_publication_conformance": "CONFORMING",
            "gate4_formal_pass": False,
            "research_eligible": False,
            "backend_freeze": {"status": "not_frozen"},
            "claim_scope": list(publisher.GENERIC_CLAIM_SCOPE),
            "warnings": [],
            "unverified_claims": list(publisher.GENERIC_UNVERIFIED_CLAIMS),
            "correction": correction or self.original_correction(),
        }

    def make_source(self, bundle_id, *, raw=b'{"event":"fixture"}\n'):
        source = self.root / f"source-{bundle_id}"
        (source / "raw").mkdir(parents=True)
        (source / "raw" / "events.jsonl").write_bytes(raw)
        approval = {
            "schema_version": publisher.APPROVAL_SCHEMA_VERSION,
            "evidence_bundle_id": bundle_id,
            "approved_final_path": str(
                (self.publication_root / bundle_id).resolve()
            ),
            "logical_generation_limit": 6,
            "wall_clock_limit_seconds": 900,
            "gpu_uuids": GPU_UUIDS,
            "stop_conditions": STOP_CONDITIONS,
            "approved": True,
            "approval_reference": "synthetic CPU fixture approval",
        }
        (source / publisher.APPROVAL_FILENAME).write_bytes(
            publisher._canonical_json_bytes(approval)
        )
        return source

    @staticmethod
    def file_bytes(root):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def publish(self, bundle_id="bundle-valid", **kwargs):
        source = kwargs.pop("source", None) or self.make_source(bundle_id)
        draft = kwargs.pop("draft", None) or self.summary(bundle_id)
        return publisher.publish_evidence(
            source,
            self.publication_root,
            draft,
            **kwargs,
        )

    def test_valid_publish_is_atomic_canonical_and_independently_reproducible(self):
        bundle_id = "bundle-valid"
        source = self.make_source(bundle_id)
        source_before = self.file_bytes(source)
        checkpoints = []

        def observe(name, staging, final):
            checkpoints.append(name)
            self.assertFalse(os.path.lexists(final))
            if name == "after_raw_copy":
                self.assertTrue((staging / "raw" / "events.jsonl").is_file())
                self.assertFalse((staging / publisher.SUMMARY_FILENAME).exists())
                self.assertFalse((staging / publisher.INVENTORY_FILENAME).exists())
            elif name == "after_summary":
                self.assertTrue((staging / "raw" / "events.jsonl").is_file())
                self.assertTrue((staging / publisher.SUMMARY_FILENAME).is_file())
                self.assertFalse((staging / publisher.INVENTORY_FILENAME).exists())
            elif name == "after_inventory_verification_before_publish":
                self.assertTrue((staging / publisher.INVENTORY_FILENAME).is_file())
                self.assertFalse(
                    publisher.validate_published_bundle(staging).publication_conforming
                )

        receipt = self.publish(
            bundle_id,
            source=source,
            checkpoint_hook=observe,
        )
        self.assertEqual(self.file_bytes(source), source_before)
        self.assertEqual(
            checkpoints,
            [
                "after_raw_copy",
                "after_capture_manifest",
                "after_summary",
                "during_inventory_write",
                "after_inventory_write",
                "after_inventory_verification_before_publish",
            ],
        )
        final = self.publication_root / bundle_id
        self.assertEqual(receipt.final_path, final)
        report = publisher.validate_published_bundle(final)
        self.assertTrue(report.publication_conforming, report.errors)
        self.assertFalse(report.formal_gate4_pass)
        self.assertFalse(report.research_eligible)
        self.assertEqual(report.summary_sha256, receipt.summary_sha256)
        self.assertEqual(report.inventory_sha256, receipt.inventory_sha256)
        self.assertEqual(report.bundle_root_sha256, receipt.bundle_root_sha256)
        expected_root = publisher._sha256_bytes(
            publisher.ROOT_HASH_DOMAIN + bytes.fromhex(receipt.inventory_sha256)
        )
        self.assertEqual(receipt.bundle_root_sha256, expected_root)

        summary_bytes = (final / publisher.SUMMARY_FILENAME).read_bytes()
        summary = json.loads(summary_bytes)
        self.assertEqual(summary_bytes, publisher._canonical_json_bytes(summary))
        self.assertEqual(set(summary), publisher.FINAL_SUMMARY_FIELDS)
        self.assertEqual(summary["evidence_bundle_id"], bundle_id)
        self.assertEqual(summary["run_id"], f"run-{bundle_id}")
        self.assertEqual(summary["backend_freeze"], {"status": "not_frozen"})

        inventory_lines = (
            final / publisher.INVENTORY_FILENAME
        ).read_text(encoding="ascii").splitlines()
        inventory_paths = [line.split("  ./", 1)[1] for line in inventory_lines]
        actual_paths = sorted(
            path.relative_to(final).as_posix()
            for path in final.rglob("*")
            if path.is_file() and path.name != publisher.INVENTORY_FILENAME
        )
        self.assertEqual(inventory_paths, actual_paths)
        self.assertNotIn(publisher.INVENTORY_FILENAME, inventory_paths)

    def test_summary_schema_rejects_missing_unknown_wrong_and_nested_unknown(self):
        base = self.summary("bundle-schema")
        for field in sorted(publisher.DRAFT_SUMMARY_FIELDS):
            with self.subTest(missing=field):
                candidate = copy.deepcopy(base)
                candidate.pop(field)
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._validate_summary(candidate, draft=True)

        unknown = copy.deepcopy(base)
        unknown["unexpected"] = True
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_summary(unknown, draft=True)

        nested = copy.deepcopy(base)
        nested["backend_freeze"]["unexpected"] = True
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_summary(nested, draft=True)

        wrong_schema = copy.deepcopy(base)
        wrong_schema["schema_version"] = (
            "ollama-fp16-three-endpoint-prompt6-summary-v1.0.0"
        )
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_summary(wrong_schema, draft=True)

        nested_objects = (
            ("backend_freeze", {"status": "not_frozen"}),
            ("correction", self.original_correction()),
        )
        for field, baseline in nested_objects:
            for nested_field in sorted(baseline):
                with self.subTest(object=field, missing=nested_field):
                    candidate = copy.deepcopy(base)
                    candidate[field].pop(nested_field)
                    with self.assertRaises(publisher.EvidenceValidationError):
                        publisher._validate_summary(candidate, draft=True)

    def test_every_nested_contract_object_rejects_missing_and_unknown_fields(self):
        bundle_id = "bundle-nested-schema"
        source = self.make_source(bundle_id)
        approval = json.loads((source / publisher.APPROVAL_FILENAME).read_bytes())
        for field in sorted(publisher.APPROVAL_FIELDS):
            candidate = copy.deepcopy(approval)
            candidate.pop(field)
            with self.subTest(object="approval", missing=field):
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._validate_approval(
                        candidate,
                        expected_bundle_id=bundle_id,
                        expected_final_path=self.publication_root / bundle_id,
                    )
        approval_unknown = copy.deepcopy(approval)
        approval_unknown["unexpected"] = True
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_approval(
                approval_unknown,
                expected_bundle_id=bundle_id,
                expected_final_path=self.publication_root / bundle_id,
            )

        record = publisher._file_record(source / "raw" / "events.jsonl")
        capture = {
            "schema_version": publisher.CAPTURE_MANIFEST_SCHEMA_VERSION,
            "files": {"raw/events.jsonl": record},
        }
        for field in ("schema_version", "files"):
            candidate = copy.deepcopy(capture)
            candidate.pop(field)
            with self.subTest(object="capture", missing=field):
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._validate_capture_manifest(candidate)
        capture_unknown = copy.deepcopy(capture)
        capture_unknown["unexpected"] = True
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_capture_manifest(capture_unknown)
        for field in ("sha256", "bytes", "lines"):
            candidate = copy.deepcopy(record)
            candidate.pop(field)
            with self.subTest(object="file_record", missing=field):
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._validate_file_record(candidate, "record")
        record_unknown = copy.deepcopy(record)
        record_unknown["unexpected"] = True
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_file_record(record_unknown, "record")

        receipt = self.publish(bundle_id, source=source)
        final_summary = json.loads(
            (receipt.final_path / publisher.SUMMARY_FILENAME).read_bytes()
        )
        for object_name in (
            "authorization",
            "source_capture",
            "publisher",
            "publication_contract",
        ):
            for field in sorted(final_summary[object_name]):
                candidate = copy.deepcopy(final_summary)
                candidate[object_name].pop(field)
                with self.subTest(object=object_name, missing=field):
                    with self.assertRaises(publisher.EvidenceValidationError):
                        publisher._validate_summary(candidate, draft=False)
            candidate = copy.deepcopy(final_summary)
            candidate[object_name]["unexpected"] = True
            with self.subTest(object=object_name, unknown=True):
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._validate_summary(candidate, draft=False)

        supersedes = {
            "evidence_bundle_id": "predecessor",
            "summary_sha256": "0" * 64,
            "inventory_sha256": "1" * 64,
            "bundle_root_sha256": "2" * 64,
        }
        correction = {
            "kind": "derived_correction",
            "supersedes": supersedes,
            "reason_code": "summary_schema_correction",
            "reason": "fixture",
            "raw_artifacts_changed": False,
            "repaired_properties": ["summary_schema"],
            "not_repaired": sorted(publisher.HISTORICAL_NONREPAIRABLE),
        }
        for field in sorted(publisher.SUPERSEDES_FIELDS):
            candidate = copy.deepcopy(correction)
            candidate["supersedes"].pop(field)
            with self.subTest(object="supersedes", missing=field):
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._validate_correction(candidate)
        candidate = copy.deepcopy(correction)
        candidate["supersedes"]["unexpected"] = True
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_correction(candidate)

    def test_contract_json_rejects_noncanonical_duplicate_nan_float_and_bool_int(self):
        value = {"a": 1, "b": ["x"]}
        canonical = publisher._canonical_json_bytes(value)
        self.assertEqual(publisher._decode_contract_json(canonical, "test"), value)
        for invalid in (
            b'{"b":["x"],"a":1}\n',
            b'{"a":1,"a":2}\n',
            b'{"a":NaN}\n',
            b'{"a":Infinity}\n',
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._decode_contract_json(invalid, "test")
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._canonical_json_bytes({"duration": 1.5})

        bundle_id = "bundle-bool-int"
        source = self.make_source(bundle_id)
        approval = json.loads((source / publisher.APPROVAL_FILENAME).read_bytes())
        approval["logical_generation_limit"] = True
        (source / publisher.APPROVAL_FILENAME).write_bytes(
            publisher._canonical_json_bytes(approval)
        )
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher.validate_approval_file(
                source / publisher.APPROVAL_FILENAME,
                expected_bundle_id=bundle_id,
                expected_final_path=self.publication_root / bundle_id,
            )

    def test_generic_publisher_cannot_assert_operational_results_or_hide_scope(self):
        bundle_id = "bundle-generic-boundary"
        for field, value in (
            ("operational_backend_result", "PASS"),
            ("claim_scope", ["GPU residency passed"]),
            ("warnings", ["observed warning"]),
            ("unverified_claims", ["real GPU behavior"]),
        ):
            with self.subTest(field=field):
                candidate = self.summary(bundle_id)
                candidate[field] = value
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher._validate_summary(candidate, draft=True)

        receipt = self.publish(bundle_id)
        self.assertEqual(receipt.operational_backend_result, "NOT_EVALUATED")
        persisted = json.loads(
            (receipt.final_path / publisher.SUMMARY_FILENAME).read_bytes()
        )
        self.assertEqual(
            persisted["claim_scope"], publisher.GENERIC_CLAIM_SCOPE
        )
        self.assertEqual(
            persisted["unverified_claims"],
            publisher.GENERIC_UNVERIFIED_CLAIMS,
        )

    def test_approval_requires_exact_path_uuid_limit_and_stop_contract(self):
        bundle_id = "bundle-approval"
        source = self.make_source(bundle_id)
        approval_path = source / publisher.APPROVAL_FILENAME
        baseline = json.loads(approval_path.read_bytes())
        mutations = {
            "wrong_path": ("approved_final_path", str(self.root / "wrong")),
            "empty_gpu": ("gpu_uuids", []),
            "zero_calls": ("logical_generation_limit", 0),
            "empty_stops": ("stop_conditions", []),
            "not_approved": ("approved", False),
        }
        for label, (field, replacement) in mutations.items():
            with self.subTest(label=label):
                candidate = copy.deepcopy(baseline)
                candidate[field] = replacement
                approval_path.write_bytes(publisher._canonical_json_bytes(candidate))
                with self.assertRaises(publisher.EvidenceValidationError):
                    publisher.validate_approval_file(
                        approval_path,
                        expected_bundle_id=bundle_id,
                        expected_final_path=self.publication_root / bundle_id,
                    )
        approval_path.write_bytes(publisher._canonical_json_bytes(baseline))
        validated = publisher.validate_approval_file(
            approval_path,
            expected_bundle_id=bundle_id,
            expected_final_path=self.publication_root / bundle_id,
        )
        self.assertTrue(validated["approved"])

    def test_approval_preflight_rejects_symlink_and_hardlink(self):
        bundle_id = "bundle-approval-link"
        source = self.make_source(bundle_id)
        approval = source / publisher.APPROVAL_FILENAME

        symlink = self.root / "approval-symlink.json"
        symlink.symlink_to(approval)
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher.validate_approval_file(
                symlink,
                expected_bundle_id=bundle_id,
                expected_final_path=self.publication_root / bundle_id,
            )
        hardlink = self.root / "approval-hardlink.json"
        os.link(approval, hardlink)
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher.validate_approval_file(
                hardlink,
                expected_bundle_id=bundle_id,
                expected_final_path=self.publication_root / bundle_id,
            )

    def test_approval_read_rejects_static_or_swapped_ancestor(self):
        bundle_id = "bundle-approval-ancestor"
        source = self.make_source(bundle_id)
        container = self.root / "approval-container"
        container.mkdir()
        capture = container / "capture"
        source.rename(capture)
        approval = capture / publisher.APPROVAL_FILENAME

        symlink_parent = self.root / "approval-container-link"
        symlink_parent.symlink_to(container, target_is_directory=True)
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher.validate_approval_file(
                symlink_parent / "capture" / publisher.APPROVAL_FILENAME,
                expected_bundle_id=bundle_id,
                expected_final_path=self.publication_root / bundle_id,
            )

        moved = self.root / "approval-container-moved"
        original_read = publisher.os.read
        swapped = False

        def swap_after_descriptor_read(descriptor, count):
            nonlocal swapped
            data = original_read(descriptor, count)
            if data and not swapped:
                container.rename(moved)
                shutil.copytree(moved, container)
                swapped = True
            return data

        with mock.patch.object(
            publisher.os,
            "read",
            side_effect=swap_after_descriptor_read,
        ):
            with self.assertRaises(publisher.EvidenceValidationError):
                publisher.validate_approval_file(
                    approval,
                    expected_bundle_id=bundle_id,
                    expected_final_path=self.publication_root / bundle_id,
                )
        self.assertTrue(swapped)

    def test_publication_lock_rejects_symlink_and_hardlink(self):
        symlink_id = "bundle-lock-symlink"
        target = self.root / "external-lock-target"
        target.write_bytes(b"external")
        (self.publication_root / f".{symlink_id}.publish.lock").symlink_to(target)
        with self.assertRaises(publisher.EvidencePublicationError):
            self.publish(symlink_id)
        self.assertFalse((self.publication_root / symlink_id).exists())

        hardlink_id = "bundle-lock-hardlink"
        hardlink = self.publication_root / f".{hardlink_id}.publish.lock"
        os.link(target, hardlink)
        with self.assertRaises(publisher.EvidencePublicationError):
            self.publish(hardlink_id)
        self.assertFalse((self.publication_root / hardlink_id).exists())

    def test_faults_never_publish_partial_final_leaf(self):
        checkpoints = (
            "after_raw_copy",
            "after_summary",
            "during_inventory_write",
            "after_inventory_verification_before_publish",
        )
        for index, target in enumerate(checkpoints):
            bundle_id = f"bundle-fault-{index}"
            source = self.make_source(bundle_id)

            def fail(name, staging, final, *, expected=target):
                if name == expected:
                    raise InjectedPublicationFailure(expected)

            with self.subTest(checkpoint=target):
                with self.assertRaises(InjectedPublicationFailure):
                    self.publish(
                        bundle_id,
                        source=source,
                        checkpoint_hook=fail,
                    )
                final = self.publication_root / bundle_id
                self.assertFalse(os.path.lexists(final))
                stages = list(
                    self.publication_root.glob(f".{bundle_id}.staging.*")
                )
                self.assertEqual(len(stages), 1)
                self.assertFalse(
                    publisher.validate_published_bundle(stages[0]).publication_conforming
                )

    def test_post_verification_source_or_stage_mutation_fails_closed(self):
        source_id = "bundle-late-source-mutation"
        source = self.make_source(source_id)

        def mutate_source(name, _staging, _final):
            if name == "after_inventory_verification_before_publish":
                (source / "raw" / "events.jsonl").write_bytes(b"changed\n")

        with self.assertRaises(publisher.EvidenceValidationError):
            self.publish(
                source_id,
                source=source,
                checkpoint_hook=mutate_source,
            )
        self.assertFalse((self.publication_root / source_id).exists())

        stage_id = "bundle-late-stage-mutation"
        stage_source = self.make_source(stage_id)

        def mutate_stage_consistently(name, staging, _final):
            if name != "after_inventory_verification_before_publish":
                return
            raw_path = staging / "raw" / "events.jsonl"
            raw_path.write_bytes(b"internally-consistent-substitution\n")
            capture_path = staging / publisher.CAPTURE_MANIFEST_FILENAME
            capture = json.loads(capture_path.read_bytes())
            capture["files"]["raw/events.jsonl"] = publisher._file_record(raw_path)
            capture_bytes = publisher._canonical_json_bytes(capture)
            capture_path.write_bytes(capture_bytes)
            summary_path = staging / publisher.SUMMARY_FILENAME
            summary = json.loads(summary_path.read_bytes())
            summary["source_capture"]["manifest_sha256"] = publisher._sha256_bytes(
                capture_bytes
            )
            summary_path.write_bytes(publisher._canonical_json_bytes(summary))
            (staging / publisher.INVENTORY_FILENAME).write_bytes(
                publisher._inventory_bytes(staging)
            )

        with self.assertRaises(publisher.EvidenceValidationError):
            self.publish(
                stage_id,
                source=stage_source,
                checkpoint_hook=mutate_stage_consistently,
            )
        self.assertFalse((self.publication_root / stage_id).exists())

    def test_mutation_during_fsync_is_reverified_before_atomic_rename(self):
        bundle_id = "bundle-fsync-mutation"
        source = self.make_source(bundle_id)
        original_fsync = publisher._fsync_regular_files

        def mutate_after_fsync(staging, **kwargs):
            original_fsync(staging, **kwargs)
            (staging / "raw" / "events.jsonl").write_bytes(b"changed after fsync\n")

        with mock.patch.object(
            publisher,
            "_fsync_regular_files",
            side_effect=mutate_after_fsync,
        ):
            with self.assertRaises(publisher.EvidenceValidationError):
                self.publish(bundle_id, source=source)
        self.assertFalse(os.path.lexists(self.publication_root / bundle_id))

    def test_source_ancestor_and_publication_root_swaps_fail_closed(self):
        source_id = "bundle-source-ancestor-swap"
        source_container = self.root / "source-container"
        source_container.mkdir()
        source = source_container / "capture"
        self.make_source(source_id).rename(source)
        moved_container = self.root / "source-container-moved"
        source_swapped = False

        def swap_source_ancestor(name, _staging, _final):
            nonlocal source_swapped
            if name == "after_raw_copy" and not source_swapped:
                source_container.rename(moved_container)
                source_container.mkdir()
                shutil.copytree(moved_container / "capture", source)
                source_swapped = True

        with self.assertRaises(publisher.EvidenceValidationError):
            self.publish(
                source_id,
                source=source,
                checkpoint_hook=swap_source_ancestor,
            )
        self.assertTrue(source_swapped)
        self.assertFalse(os.path.lexists(self.publication_root / source_id))

        root_id = "bundle-publication-root-swap"
        root_source = self.make_source(root_id)
        original_root = self.publication_root
        moved_root = self.root / "published-moved"
        root_swapped = False

        def swap_publication_root(name, _staging, _final):
            nonlocal root_swapped
            if name == "after_raw_copy" and not root_swapped:
                original_root.rename(moved_root)
                original_root.mkdir()
                root_swapped = True

        with self.assertRaises(publisher.EvidenceValidationError):
            self.publish(
                root_id,
                source=root_source,
                checkpoint_hook=swap_publication_root,
            )
        self.assertTrue(root_swapped)
        self.assertFalse(os.path.lexists(original_root / root_id))
        self.assertFalse(os.path.lexists(moved_root / root_id))

    def test_pinned_repository_and_final_child_inode_swaps_are_rejected(self):
        repository_container = self.root / "repository-container"
        repository = repository_container / "repo"
        (repository / "tools").mkdir(parents=True)
        (repository / "docs").mkdir()
        (repository / "tools" / "publisher.py").write_bytes(b"publisher\n")
        (repository / "docs" / "contract.md").write_bytes(b"contract\n")
        moved_container = self.root / "repository-container-moved"

        with publisher._pin_directory(repository, "test repository") as pinned:
            publisher._read_relative_regular_file_nofollow(
                pinned.path,
                "tools/publisher.py",
                "test publisher",
                root_fd=pinned.fd,
            )
            publisher._read_relative_regular_file_nofollow(
                pinned.path,
                "docs/contract.md",
                "test contract",
                root_fd=pinned.fd,
            )
            repository_container.rename(moved_container)
            shutil.copytree(moved_container, repository_container)
            with self.assertRaises(publisher.EvidenceValidationError):
                pinned.assert_path_identity()

        bundle_id = "bundle-final-child-swap"
        source = self.make_source(bundle_id)
        final = self.publication_root / bundle_id
        parked = self.publication_root / f"{bundle_id}.parked"
        original_verify = publisher._verify_bundle_or_raise
        final_swapped = False

        def swap_after_final_verify(path, **kwargs):
            nonlocal final_swapped
            receipt = original_verify(path, **kwargs)
            if kwargs.get("require_final_name") is True and not final_swapped:
                final.rename(parked)
                shutil.copytree(parked, final)
                final_swapped = True
            return receipt

        with mock.patch.object(
            publisher,
            "_verify_bundle_or_raise",
            side_effect=swap_after_final_verify,
        ):
            with self.assertRaises(publisher.EvidenceValidationError):
                self.publish(bundle_id, source=source)
        self.assertTrue(final_swapped)
        self.assertTrue(final.is_dir())
        self.assertTrue(parked.is_dir())
        self.assertNotEqual(final.stat().st_ino, parked.stat().st_ino)

    def test_abrupt_process_death_never_exposes_partial_final_leaf(self):
        context = multiprocessing.get_context("spawn")
        checkpoints = (
            "after_raw_copy",
            "after_summary",
            "during_inventory_write",
            "after_inventory_verification_before_publish",
        )
        for index, checkpoint in enumerate(checkpoints):
            bundle_id = f"bundle-crash-{index}"
            source = self.make_source(bundle_id)
            process = context.Process(
                target=crash_publish,
                args=(
                    str(source),
                    str(self.publication_root),
                    self.summary(bundle_id),
                    checkpoint,
                ),
            )
            process.start()
            process.join(timeout=10)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 73)
            final = self.publication_root / bundle_id
            self.assertFalse(os.path.lexists(final))
            stages = list(
                self.publication_root.glob(f".{bundle_id}.staging.*")
            )
            self.assertEqual(len(stages), 1)
            self.assertFalse(
                publisher.validate_published_bundle(stages[0]).publication_conforming
            )
            receipt = self.publish(bundle_id, source=source)
            self.assertTrue(
                publisher.validate_published_bundle(
                    receipt.final_path
                ).publication_conforming
            )

    def test_process_death_after_atomic_rename_leaves_complete_valid_leaf(self):
        bundle_id = "bundle-crash-after-rename"
        source = self.make_source(bundle_id)
        process = multiprocessing.get_context("spawn").Process(
            target=crash_immediately_after_rename,
            args=(
                str(source),
                str(self.publication_root),
                self.summary(bundle_id),
            ),
        )
        process.start()
        process.join(timeout=10)
        self.assertFalse(process.is_alive())
        self.assertEqual(process.exitcode, 74)
        final = self.publication_root / bundle_id
        report = publisher.validate_published_bundle(final)
        self.assertTrue(report.publication_conforming, report.errors)
        self.assertEqual(
            list(self.publication_root.glob(f".{bundle_id}.staging.*")),
            [],
        )

    def test_existing_and_symlink_final_are_never_overwritten(self):
        bundle_id = "bundle-collision"
        self.publish(bundle_id)
        final = self.publication_root / bundle_id
        before = self.file_bytes(final)
        second_source = self.root / "source-collision-second"
        second_source.mkdir()
        (second_source / "raw.txt").write_text("second", encoding="utf-8")
        original_approval = self.make_source("approval-helper") / publisher.APPROVAL_FILENAME
        approval = json.loads(original_approval.read_bytes())
        approval["evidence_bundle_id"] = bundle_id
        approval["approved_final_path"] = str(final.resolve())
        (second_source / publisher.APPROVAL_FILENAME).write_bytes(
            publisher._canonical_json_bytes(approval)
        )
        with self.assertRaises(publisher.EvidenceCollisionError):
            publisher.publish_evidence(
                second_source,
                self.publication_root,
                self.summary(bundle_id),
            )
        self.assertEqual(self.file_bytes(final), before)

        symlink_id = "bundle-symlink"
        symlink_target = self.root / "symlink-target"
        symlink_target.mkdir()
        (symlink_target / "owned.txt").write_text("owned", encoding="utf-8")
        (self.publication_root / symlink_id).symlink_to(
            symlink_target, target_is_directory=True
        )
        target_before = self.file_bytes(symlink_target)
        with self.assertRaises(publisher.EvidenceCollisionError):
            self.publish(symlink_id)
        self.assertEqual(self.file_bytes(symlink_target), target_before)

    def test_two_publishers_same_id_have_exactly_one_owner(self):
        bundle_id = "bundle-concurrent"
        sources = [
            self.make_source(f"temporary-{index}") for index in range(2)
        ]
        for source in sources:
            approval_path = source / publisher.APPROVAL_FILENAME
            approval = json.loads(approval_path.read_bytes())
            approval["evidence_bundle_id"] = bundle_id
            approval["approved_final_path"] = str(
                (self.publication_root / bundle_id).resolve()
            )
            approval_path.write_bytes(publisher._canonical_json_bytes(approval))
        barrier = threading.Barrier(2)
        outcomes = []
        mutex = threading.Lock()

        def worker(source):
            barrier.wait(timeout=5)
            try:
                publisher.publish_evidence(
                    source,
                    self.publication_root,
                    self.summary(bundle_id),
                )
                outcome = "published"
            except publisher.EvidenceCollisionError:
                outcome = "collision"
            with mutex:
                outcomes.append(outcome)

        threads = [threading.Thread(target=worker, args=(source,)) for source in sources]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(outcomes), ["collision", "published"])
        report = publisher.validate_published_bundle(
            self.publication_root / bundle_id
        )
        self.assertTrue(report.publication_conforming, report.errors)

    def test_two_process_publishers_same_id_have_exactly_one_owner(self):
        bundle_id = "bundle-concurrent-process"
        sources = [self.make_source(f"process-source-{index}") for index in range(2)]
        for source in sources:
            approval_path = source / publisher.APPROVAL_FILENAME
            approval = json.loads(approval_path.read_bytes())
            approval["evidence_bundle_id"] = bundle_id
            approval["approved_final_path"] = str(
                (self.publication_root / bundle_id).resolve()
            )
            approval_path.write_bytes(publisher._canonical_json_bytes(approval))

        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        outcomes = context.Queue()
        processes = [
            context.Process(
                target=competing_publish,
                args=(
                    str(source),
                    str(self.publication_root),
                    self.summary(bundle_id),
                    barrier,
                    outcomes,
                ),
            )
            for source in sources
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=15)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
        observed = sorted(outcomes.get(timeout=2) for _ in processes)
        self.assertEqual(observed, ["collision", "published"])
        report = publisher.validate_published_bundle(
            self.publication_root / bundle_id
        )
        self.assertTrue(report.publication_conforming, report.errors)

    def test_inventory_tamper_missing_extra_and_path_rules_fail(self):
        bundle_id = "bundle-tamper"
        self.publish(bundle_id)
        final = self.publication_root / bundle_id

        (final / "raw" / "events.jsonl").write_bytes(b"tampered\n")
        self.assertFalse(
            publisher.validate_published_bundle(final).publication_conforming
        )

        missing_id = "bundle-missing-inventory"
        self.publish(missing_id)
        missing_final = self.publication_root / missing_id
        (missing_final / publisher.INVENTORY_FILENAME).unlink()
        self.assertFalse(
            publisher.validate_published_bundle(missing_final).publication_conforming
        )

        extra_id = "bundle-extra-file"
        self.publish(extra_id)
        extra_final = self.publication_root / extra_id
        (extra_final / "unlisted.txt").write_text("extra", encoding="utf-8")
        self.assertFalse(
            publisher.validate_published_bundle(extra_final).publication_conforming
        )

        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._parse_inventory(
                b"0" * 64 + b"  ./../escape\n"
            )
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._parse_inventory(
                (b"0" * 64 + b"  ./a\n") * 2
            )
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._parse_inventory(
                b"0" * 64 + b"  ./b\n" + b"0" * 64 + b"  ./a\n"
            )
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._parse_inventory(
                b"0" * 64 + b"  ./files.sha256\n"
            )

    def test_inventory_changed_during_verification_is_rejected(self):
        bundle_id = "bundle-inventory-race"
        receipt = self.publish(bundle_id)
        final = receipt.final_path
        original_enumerate = publisher._enumerate_regular_files
        changed = False

        def mutate_after_scan(root, *, source, root_fd=None):
            nonlocal changed
            records = original_enumerate(
                root,
                source=source,
                root_fd=root_fd,
            )
            if not changed and Path(root).resolve() == final.resolve() and not source:
                inventory = final / publisher.INVENTORY_FILENAME
                inventory.write_bytes(inventory.read_bytes() + b"\n")
                changed = True
            return records

        with mock.patch.object(
            publisher,
            "_enumerate_regular_files",
            side_effect=mutate_after_scan,
        ):
            report = publisher.validate_published_bundle(final)
        self.assertTrue(changed)
        self.assertFalse(report.publication_conforming)

    def test_source_rejects_symlink_hardlink_fifo_and_socket(self):
        cases = []

        symlink_id = "bundle-source-symlink"
        symlink_source = self.make_source(symlink_id)
        (symlink_source / "raw" / "link").symlink_to("events.jsonl")
        cases.append((symlink_id, symlink_source))

        hardlink_id = "bundle-source-hardlink"
        hardlink_source = self.make_source(hardlink_id)
        os.link(
            hardlink_source / "raw" / "events.jsonl",
            hardlink_source / "raw" / "hardlink.jsonl",
        )
        cases.append((hardlink_id, hardlink_source))

        fifo_id = "bundle-source-fifo"
        fifo_source = self.make_source(fifo_id)
        os.mkfifo(fifo_source / "raw" / "fifo")
        cases.append((fifo_id, fifo_source))

        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            socket_id = "bundle-source-socket"
            socket_source = self.make_source(socket_id)
            socket_path = socket_source / "raw" / "socket"
            try:
                unix_socket.bind(str(socket_path))
            except PermissionError:
                # Some CI sandboxes prohibit AF_UNIX bind. Exercise the exact
                # non-regular-file rejection branch with a scoped stat mock.
                socket_path.write_bytes(b"socket-placeholder")
                original_stat = publisher.os.stat

                def simulated_socket(path, *args, **kwargs):
                    observed = original_stat(path, *args, **kwargs)
                    if (
                        os.fspath(path) == socket_path.name
                        and kwargs.get("dir_fd") is not None
                    ):
                        values = list(observed)
                        values[0] = publisher.stat.S_IFSOCK | 0o600
                        return os.stat_result(values)
                    return observed

                with mock.patch.object(publisher.os, "stat", simulated_socket):
                    with self.assertRaises(publisher.EvidenceValidationError):
                        publisher.publish_evidence(
                            socket_source,
                            self.publication_root,
                            self.summary(socket_id),
                        )
                self.assertFalse(
                    os.path.lexists(self.publication_root / socket_id)
                )
            else:
                cases.append((socket_id, socket_source))
            for bundle_id, source in cases:
                with self.subTest(bundle_id=bundle_id):
                    with self.assertRaises(publisher.EvidenceValidationError):
                        publisher.publish_evidence(
                            source,
                            self.publication_root,
                            self.summary(bundle_id),
                        )
                    self.assertFalse(
                        os.path.lexists(self.publication_root / bundle_id)
                    )
        finally:
            unix_socket.close()

    def test_corrected_derivative_binds_predecessor_and_preserves_old_bytes(self):
        original_id = "bundle-original"
        original_source = self.make_source(original_id)
        original_receipt = self.publish(original_id, source=original_source)
        original_path = self.publication_root / original_id
        original_before = self.file_bytes(original_path)

        corrected_id = "bundle-corrected"
        corrected_source = self.make_source(corrected_id)
        correction = {
            "kind": "derived_correction",
            "supersedes": {
                "evidence_bundle_id": original_id,
                "summary_sha256": original_receipt.summary_sha256,
                "inventory_sha256": original_receipt.inventory_sha256,
                "bundle_root_sha256": original_receipt.bundle_root_sha256,
            },
            "reason_code": "summary_schema_correction",
            "reason": "Correct the derived summary schema without changing raw bytes.",
            "raw_artifacts_changed": False,
            "repaired_properties": ["summary_schema"],
            "not_repaired": sorted(publisher.HISTORICAL_NONREPAIRABLE),
        }
        receipt = self.publish(
            corrected_id,
            source=corrected_source,
            draft=self.summary(corrected_id, correction=correction),
            predecessor_path=original_path,
        )
        self.assertEqual(self.file_bytes(original_path), original_before)
        report = publisher.validate_published_bundle(
            receipt.final_path,
            predecessor_path=original_path,
        )
        self.assertTrue(report.publication_conforming, report.errors)

        wrong = copy.deepcopy(correction)
        wrong["supersedes"]["summary_sha256"] = "0" * 64
        wrong_id = "bundle-correction-wrong"
        wrong_source = self.make_source(wrong_id)
        with self.assertRaises(publisher.EvidenceValidationError):
            self.publish(
                wrong_id,
                source=wrong_source,
                draft=self.summary(wrong_id, correction=wrong),
                predecessor_path=original_path,
            )
        self.assertFalse((self.publication_root / wrong_id).exists())
        self.assertEqual(self.file_bytes(original_path), original_before)

        (original_path / "raw" / "events.jsonl").write_bytes(b"tampered predecessor\n")
        tampered_id = "bundle-correction-tampered-predecessor"
        with self.assertRaises(publisher.EvidenceValidationError):
            self.publish(
                tampered_id,
                source=self.make_source(tampered_id),
                draft=self.summary(tampered_id, correction=correction),
                predecessor_path=original_path,
            )
        self.assertFalse((self.publication_root / tampered_id).exists())

    def test_correction_cannot_claim_historical_atomicity_repaired_or_change_raw(self):
        original_id = "bundle-correction-base"
        original_receipt = self.publish(original_id)
        original_path = self.publication_root / original_id
        correction = {
            "kind": "derived_correction",
            "supersedes": {
                "evidence_bundle_id": original_id,
                "summary_sha256": original_receipt.summary_sha256,
                "inventory_sha256": original_receipt.inventory_sha256,
                "bundle_root_sha256": original_receipt.bundle_root_sha256,
            },
            "reason_code": "fixture",
            "reason": "fixture correction",
            "raw_artifacts_changed": False,
            "repaired_properties": ["original_atomic_publication"],
            "not_repaired": [],
        }
        bad_id = "bundle-illegal-repair"
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher.publish_evidence(
                self.make_source(bad_id),
                self.publication_root,
                self.summary(bad_id, correction=correction),
                predecessor_path=original_path,
            )

        changed_id = "bundle-raw-changed"
        changed = copy.deepcopy(correction)
        changed["reason_code"] = "summary_schema_correction"
        changed["repaired_properties"] = ["summary_schema"]
        changed["not_repaired"] = sorted(publisher.HISTORICAL_NONREPAIRABLE)
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher.publish_evidence(
                self.make_source(changed_id, raw=b"changed raw\n"),
                self.publication_root,
                self.summary(changed_id, correction=changed),
                predecessor_path=original_path,
            )

        contradictory = copy.deepcopy(changed)
        contradictory["not_repaired"] = ["summary_schema"]
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_summary(
                self.summary("bundle-contradictory", correction=contradictory),
                draft=True,
            )

        same_id = copy.deepcopy(changed)
        same_id["supersedes"]["evidence_bundle_id"] = "bundle-same-id"
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_summary(
                self.summary("bundle-same-id", correction=same_id),
                draft=True,
            )

        mismatched_reason = copy.deepcopy(changed)
        mismatched_reason["reason_code"] = "derived_metadata_correction"
        with self.assertRaises(publisher.EvidenceValidationError):
            publisher._validate_summary(
                self.summary(
                    "bundle-mismatched-correction",
                    correction=mismatched_reason,
                ),
                draft=True,
            )

    def test_unsupported_atomic_rename_fails_closed_without_final_leaf(self):
        bundle_id = "bundle-no-rename"
        original = publisher._rename_noreplace

        def unsupported(_source, _destination, **_kwargs):
            raise publisher.EvidencePublicationError("renameat2 unavailable")

        publisher._rename_noreplace = unsupported
        try:
            with self.assertRaises(publisher.EvidencePublicationError):
                self.publish(bundle_id)
        finally:
            publisher._rename_noreplace = original
        self.assertFalse(os.path.lexists(self.publication_root / bundle_id))
        self.assertEqual(
            len(list(self.publication_root.glob(f".{bundle_id}.staging.*"))),
            1,
        )


if __name__ == "__main__":
    unittest.main()
