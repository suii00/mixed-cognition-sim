# Gate 4 Evidence Publication Specification

Version: `gate4-backend-evidence-publication-v1.1.0`

Status: `IMPLEMENTATION CONTRACT — CPU VALIDATION ONLY — NOT RUN AUTHORIZATION`

## 1. Purpose and boundary

This specification defines how a completed Gate 4 capture becomes a published,
publisher-immutable evidence bundle. It does not define model acceptance,
authorize a GPU run, freeze a backend, pass Gate 4A, or make a run
research-eligible.

Every report keeps three independent axes:

```text
operational_backend_result
evidence_publication_conformance
formal_gate4_pass / research_eligible / backend_freeze.status
```

Version 1.1.0 implements only the generic `publication_structure_only` profile.
Because that profile has no content-derived workload validator, it must record
`operational_backend_result=NOT_EVALUATED`; it cannot publish PASS, FAIL,
ABORTED, or warning classifications. A later capture-profile version may
publish those outcomes only after a repository-owned, profile-specific
validator derives them from the captured raw bytes. Publication conformance
never turns an operational result into a Gate or research PASS.

The nonconforming evidence bundle `prompt6-20260816T082431Z` and its immutable
pre-execution specification are historical inputs only. This contract does not
retroactively repair their publication order, atomicity, or authorization
record.

## 2. Publication layout and eligibility

The capture process writes only to a fresh source-capture directory. The
publisher copies those regular files into a fresh hidden sibling staging leaf:

```text
<publication-root>/.<evidence-bundle-id>.staging.<nonce>/
```

The publisher then adds its owned artifacts:

```text
approval.json                         copied source authority
capture-manifest.json                 exact copied-source path/hash set
run-summary.json                      closed-schema canonical summary
publication/gate4_evidence_publisher.py
publication/GATE4_EVIDENCE_PUBLICATION_SPEC.md
files.sha256                          every regular file except itself
```

Only this final path is a published bundle:

```text
<publication-root>/<evidence-bundle-id>/
```

A hidden staging leaf, a source-capture directory, a final-looking directory
without a valid complete inventory, or any directory whose basename differs
from `run-summary.json:evidence_bundle_id` is not published evidence.

All staging and final paths must be on the same filesystem. After every file
and directory is flushed and a fresh read-only verifier passes, the publisher
uses a no-replace atomic directory rename. Lack of no-replace support fails
closed. It must not fall back to `os.replace`, `shutil.move`, copying into the
final leaf, or any operation that can overwrite an existing final path.

`publisher-immutable` means this publisher performs no write after the atomic
rename. It does not mean that filesystem permission bits prevent later
third-party writes. Exact S/I/R commitments and an independent read-only
verifier are therefore required for every later acceptance check.

The caller supplies the expected source-capture and publication-root directory
identities as exact `{device,inode}` pairs. The publisher opens every absolute
path component from `/` with `O_DIRECTORY|O_NOFOLLOW`, compares the expected
source/root identities with the opened descriptors, and retains the complete
source, publication-root, repository, staging, and final descriptor chains
through publication. The public receipt returns the exact source and final
published-directory identities in addition to S/I/R. A later component must
reject a named path that no longer identifies that receipt inode even when a
replacement tree has byte-identical contents.

## 3. Approval record

`approval.json` is intended to be written before GPU work by the capture
orchestrator. The standalone publisher validates its bytes before enumerating
or copying the rest of a completed capture, but it cannot retroactively prove
that the file predated the workload. A GPU orchestrator must therefore call the
same no-follow preflight validator before its first GPU operation and bind the
exact approval hash into capture-start metadata. That integration is not part
of this generic publisher and remains a blocking prerequisite for another GPU
run. The canonical approval has exactly these fields:

```json
{
  "schema_version": "gate4-gpu-run-approval-v1.0.0",
  "evidence_bundle_id": "<safe bundle id>",
  "approved_final_path": "<absolute final evidence path>",
  "logical_generation_limit": 6,
  "wall_clock_limit_seconds": 900,
  "gpu_uuids": ["GPU-..."],
  "stop_conditions": ["..."],
  "approved": true,
  "approval_reference": "<non-empty reference>"
}
```

The key set is exact. GPU UUIDs and stop conditions are non-empty, sorted, and
unique. `logical_generation_limit` and `wall_clock_limit_seconds` are positive
integers; booleans are not integers. The approved path must resolve exactly to
the publisher's final path. Approval for one bundle ID or final path cannot be
reused for another. The file is opened without following symlinks, must be a
single-link regular file, and must remain stable for the authoritative read.

For the generic profile, the declared generation/time/GPU limits are retained
but are not compared with actual workload observations. That limitation is
mechanically included in `unverified_claims`.

## 4. Closed summary schema

The exact summary schema identifier is:

```text
gate4-backend-evidence-summary-v1.0.0
```

`run-summary.json` has exactly these top-level fields:

```text
schema_version
evidence_bundle_id
run_id
protocol_version
metric_version
execution_mode
operational_backend_result
evidence_publication_conformance
gate4_formal_pass
research_eligible
backend_freeze
authorization
claim_scope
warnings
unverified_claims
correction
source_capture
publisher
publication_contract
```

The following values are fixed for this version:

```text
operational_backend_result = NOT_EVALUATED
evidence_publication_conformance = CONFORMING
gate4_formal_pass = false
research_eligible = false
backend_freeze = {"status":"not_frozen"}
claim_scope = ["publication_structure_only"]
warnings = []
unverified_claims = [
  "execution_mode",
  "metric_version",
  "operational_backend_result",
  "protocol_version",
  "resource_and_workload_limits",
  "run_id"
]
```

`execution_mode` is exactly one of `reference_ollama`,
`vllm_openai_compatible`, or `scripted_smoke`, but the generic profile marks it
unverified together with the run, protocol, and metric labels. These fixed
scope fields prevent a caller-controlled draft or arbitrary raw fixture from
manufacturing an operational PASS or suppressing an observed warning. A
content-derived operational profile requires a new contract version.

`authorization` contains exactly `path` and `sha256` and binds the copied
`approval.json`. `source_capture` contains exactly `manifest_path` and
`manifest_sha256`. `publisher` and `publication_contract` each contain exactly
`path`, `sha256`, and `version`. All hashes are lowercase 64-character SHA-256.

Every object rejects unknown fields. Every required field is mandatory. JSON
booleans are not accepted as integers. Contract-owned JSON rejects duplicate
keys, NaN, Infinity, and noncanonical serialization.

## 5. Correction and supersession

`correction` always has exactly these fields:

```text
kind
supersedes
reason_code
reason
raw_artifacts_changed
repaired_properties
not_repaired
```

For an original bundle:

```json
{
  "kind": "original",
  "supersedes": null,
  "reason_code": null,
  "reason": null,
  "raw_artifacts_changed": false,
  "repaired_properties": [],
  "not_repaired": []
}
```

For a corrected derivative, `kind=derived_correction`; `reason_code`, `reason`,
and `repaired_properties` are non-empty; `raw_artifacts_changed=false`; and
`supersedes` has exactly:

```text
evidence_bundle_id
summary_sha256
inventory_sha256
bundle_root_sha256
```

The publisher independently and fully validates the predecessor as a
conforming original v1.1.0 bundle, recomputes those predecessor hashes, and
compares the actual predecessor capture bytes—not only its manifest—with the
new capture. Correction chains and legacy/nonconforming predecessors are not
accepted by this version. The old bundle is never edited. The historical
properties
`original_publication_order`, `original_atomic_publication`, and
`original_approval_completeness` may appear only in `not_repaired`, never in
`repaired_properties`.

The only repairable properties are `summary_schema`, `derived_metadata`, and
`inventory_metadata`, with corresponding closed reason codes.
`repaired_properties` and `not_repaired` are disjoint, and a correction must
use a new bundle ID.

## 6. Canonical bytes and inventory

Contract-owned JSON is UTF-8 with sorted keys, compact separators, no NaN, and
one trailing newline:

```python
json.dumps(
    value,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8") + b"\n"
```

Authoritative durations and counts use integers. Floating-point values are not
allowed anywhere in the closed summary or approval record.

`files.sha256` is ASCII, lexicographically sorted by relative POSIX path, and
contains every regular file exactly once except `files.sha256` itself:

```text
<lowercase-sha256><two spaces>./<safe-relative-path>\n
```

Absolute paths, path traversal, duplicate entries, unsorted entries, symlinks,
FIFOs, devices, sockets, and external hard links are rejected. The inventory
must include `run-summary.json`, `capture-manifest.json`, `approval.json`, the
publisher source snapshot, and this contract snapshot.

Authoritative reads use no-follow directory/file descriptors, require regular
single-link files, and compare descriptor identity and stable metadata before
and after reading. The verifier rereads the complete file set and the exact
inventory bytes before returning a commitment.

The returned and independently recorded commitments are:

```text
S = SHA256(exact run-summary.json bytes)
I = SHA256(exact files.sha256 bytes)
R = SHA256(b"MCS-EVIDENCE-BUNDLE-ROOT-V1\0" + bytes.fromhex(I))
```

`I` and `R` are not inserted into an inventory-covered file, avoiding a hash
cycle. The ledger records `S`, `I`, and `R` after a separate read-only check.

The publisher receipt also records:

```text
source_directory_identity = {device,inode}
final_directory_identity = {device,inode}
```

Directory identities are handoff commitments, not content hashes. The
standalone verifier independently reopens the lexical final path component by
component without importing publisher helpers, reports the observed final
identity, and accepts an optional mandatory expected-final identity. A
different device or inode makes the independent result invalid even if S/I/R
would otherwise match.

## 7. Ordered atomic publication

The mandatory order is:

1. no-follow pin the caller's source/publication-root identities, validate the
   approval, and validate absence of the final leaf;
2. enumerate and hash the complete source capture;
3. copy raw/source artifacts exclusively into hidden staging;
4. verify copied bytes and prove the source capture did not change;
5. snapshot publisher and contract bytes;
6. write and verify `capture-manifest.json`;
7. build, closed-schema validate, write, and reread canonical
   `run-summary.json`;
8. generate `files.sha256` last;
9. use a preliminary read-only verifier pass to check exact path set, every
   hash, schema, canonical bytes, approval, and correction relation;
10. fsync every file, staging directory, and publication root with no-follow
    descriptor checks;
11. run a fresh full staged verification after fsync and fix S/I/R from that
    final pre-publication state;
12. atomically rename staging to the absent final leaf with no replacement;
13. run a fresh publisher-internal read-only verification of the final leaf,
    compare its S/I/R with the staged commitments, and recheck the named final
    inode before returning the identity-bearing receipt.

The final publisher pass in step 13 is distinct from the standalone,
independently implemented acceptance verifier. Before any ledger acceptance,
the acceptance workflow must run `tools/verify_gate4_evidence_bundle.py` with
the publisher receipt's exact S/I/R. `publish_evidence` does not perform or
claim that independent acceptance check.

There are no writes to the final leaf after step 12. A crash before step 12
leaves only an ineligible hidden stage. A crash after step 12 leaves a complete,
re-verifiable final leaf. Publishing content-derived negative or aborted status
requires a later profile-specific contract; this generic profile remains
`NOT_EVALUATED`.

## 8. Required CPU evidence before another GPU run

At minimum, CPU tests must cover:

- exact schema identifier, required fields, nested fields, types, and enums;
- rejection of every missing required field and top-level/nested unknown field;
- canonical byte identity, duplicate keys, NaN/Infinity, and bool-as-int;
- raw-before-summary and manifest-before-publication checkpoints;
- interruption after raw, summary, partial inventory, and verified inventory;
- mechanical ineligibility of every partial/staging tree;
- existing path, symlink path, and concurrent same-ID no-overwrite behavior;
- expected source/publication-root identity mismatch, source/final
  byte-identical inode replacement, and absolute parent-component replacement;
- explicit correction/supersession and predecessor-hash validation;
- inventory self-exclusion, sorting, exact path set, traversal, duplicate,
  missing, extra, and tamper rejection; and
- independent S/I/R reproduction after publication.

The suite must also prove that the generic profile rejects caller-asserted
operational outcomes, warnings, and broader claim scopes; that approval/source
symlinks and hard links fail closed; and that source, stage, summary, or
inventory changes during verification cannot yield a conforming receipt. The
standalone verifier must remain publisher-independent and must reject a final
identity mismatch separately from S/I/R mismatch.

Passing this CPU contract does not authorize endpoint reuse or any other GPU
test. A new versioned workload specification and explicit run approval remain
required.
