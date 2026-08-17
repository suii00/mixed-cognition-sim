# Gate 4 Endpoint-Reuse Approval Review FAIL

Date recorded: `2026-08-18` (Asia/Tokyo)

Status: `RETAINED APPROVAL FAIL — NOT RUN AUTHORIZATION`

## 1. Reviewed historical state

The reviewed tooling was frozen at annotated tag
`gate4a-endpoint-reuse-tooling-frozen-20260817`, which peels to
`225ae755f3dff2400d2fa8a60b1d1bb9a3e17071`. That tag remains immutable,
but this review supersedes it for any future real endpoint-reuse execution.

The rejected candidate is retained outside the repository:

```text
approval ID:     gate4a-endpoint-reuse-fp16-20260817T124139Z
approval JSON:   /home/iitsuka/mcs-backend-smoke/approvals/gate4a-endpoint-reuse-fp16-20260817T124139Z.json
approval SHA-256: b97d603b2e34c0e7157398a916ae6485e60bc6304746cb2189a1db11187756d4
review summary:  /home/iitsuka/mcs-backend-smoke/approvals/gate4a-endpoint-reuse-fp16-20260817T124139Z.md
summary SHA-256: 06f8c71a5f5fa8a299e9152b8535305a72da4ac263bfa52e3c29c70e278a821f
file modes:      0444 / 0444
```

The files were re-hashed read-only before this report. They were not edited,
replaced, deleted, reauthorized, or executed. Their approval ID, proposed
bundle ID, and SHA are not reusable.

## 2. Approval decision

```text
Approval candidate: REJECTED
Approval review: FAIL
Execution authorization: NO
Real endpoint-reuse execution: NOT PERFORMED
Formal Gate 4A: NOT PASSED / NOT FROZEN
Backend freeze: not_frozen
Research eligibility: false
```

Candidate preparation had made read-only GET requests to the pre-existing
11434 Ollama service to capture its then-current identity. It did not invoke
the endpoint-reuse orchestrator, start ports 11440--11442, send generation or
unload requests, use sudo, invoke an NVIDIA probe, or start a GPU workload.

## 3. Blocking warning-policy defect

The rejected approval used six whole-line warning globs beginning with
`time=*`. Python whole-line `fnmatch` semantics allow that `*` to span arbitrary
intervening content. The collector could also classify captured content as
WARN merely because it found `level=WARN`, even if the same record contained a
second ERROR or FATAL event. Consequently, a later approved warning fragment
could hide preceding fatal, request-failure, watchdog, stale-memory, or unknown
diagnostic content.

Editing only those six glob strings could not make the approval safe. Warning
collection, event parsing, severity precedence, allowlist identity, and raw
trace binding required a tooling correction. Therefore the historical tooling
tag cannot authorize execution and the approval cannot be repaired in place.

## 4. Bounded structured correction

Commit `3d87d22ff2ddd75b0e219b9ac9fda30cccec9ba0`,
`fix: require structured Gate 4 warning events`, made the bounded correction.
Commit `0bd7b5eed26ae10047b78aa1d504ffab48e9d77c`,
`chore: repin prompt6 runner to warning-policy ledger`, atomically recorded the
updated ledger and its one-way prompt6 runner pin. Historical prompt6 evidence
was not altered, repaired, republished, or reclassified.

The corrected contract uses:

```text
endpoint-reuse spec:      gate4-ollama-endpoint-reuse-v1.2.0
approval schema:          gate4-ollama-endpoint-reuse-approval-v1.1.0
observation schema:       gate4-ollama-endpoint-reuse-observations-v1.2.0
workload validation:      gate4-ollama-endpoint-reuse-validation-v1.2.0
```

Each physical diagnostic line is retained separately with role, stream, line
sequence, exact base64 raw bytes, and raw SHA-256. A complete logfmt-like parse
must yield one severity, one source, one message, and a closed unique attribute
set. Embedded line breaks, duplicate fields, malformed quoting, mixed severity,
invalid source/time, and ignored trailing tokens are rejected.

The executable approval schema now contains exactly six structured warning
identities: two fixed startup events for each approved role/GPU UUID. Matching
is exact across role, WARN level, source file/line, message, complete attribute
set, and maximum occurrence count. Timestamp syntax is validated but timestamp
is not part of the identity. No whole-line wildcard matcher remains in the
acceptance path.

Operational classification is:

- exact allowed events only: `PASS_WITH_WARNINGS`, eligible if all other checks
  pass;
- no warning: `PASS`;
- valid but unapproved WARN, including request-failure, watchdog, or stale-
  memory warnings: `MANUAL_REVIEW_REQUIRED`, not publishable;
- parsed or malformed ERROR/FATAL/PANIC, OOM, crash, segfault, CUDA-error, or
  Xid evidence: `FAIL`, not publishable;
- malformed nonfatal warning-like evidence: `MANUAL_REVIEW_REQUIRED`, not
  publishable; and
- duplicate/excess allowed occurrences: `MANUAL_REVIEW_REQUIRED`, not
  publishable.

An approved event on the same or a later physical line cannot downgrade an
earlier failure.

## 5. Recorded CPU regression evidence

The repository-owned CPU fixtures recorded:

```text
endpoint-reuse targeted suite     38/38 PASS
publisher + independent verifier  47/47 PASS
prompt6 regression                10/10 PASS
complete repository suite        282/282 PASS
compileall                         PASS
git diff --check                  PASS
```

The exact-six structured fixture publishes atomically, passes standalone S/I/R
verification, and produces a success receipt while retaining formal and
research eligibility as false. Unknown WARN, request failure, watchdog,
stale-memory, excess occurrence, malformed input, and ERROR/FATAL combinations
are non-publishable. This repository-owned result is not the combined
independent tooling recheck.

The correction pins are:

```text
publication spec: 8201013f77d98cc0c63559fe31a7c3c8d4dc90b4d1eda0f245d0e56f77ba7b6c
publisher:        83bb7a19f945023e3de0ad7a470eab82123d34d7b1e213b69aaaab4ff8298734
standalone verifier:
                  c31fe2f06eba5f86086092e6dc3e2682c9c1be5c5eb76d24664a6e0fac6f5e5b
endpoint spec:    b445f3ee303dd5a1cde98c63489b1bd501d77174ec98f01133b3bfd6fc9a1b4d
workload validator:
                  01df6039ee2701ab831ffca44bd2fe6ee7cc47d10745703d0831448ad7fb5644
orchestrator:     d7c17e92607eeb3e8ab59ae4f6d972282327c70fda070627ca1225d95f720915
evidence ledger: a1cf681d2626b44f7587d75d4498e19c73a9164e611bfb4d27306ff93e9b4167
```

No GPU, `nvidia-smi`, Ollama/API, sudo, network, temporary server, process
signal, real approval, or endpoint execution was used by this implementation
task. No push or replacement tooling tag was performed.

## 6. Current boundary

```text
Gate 4A warning-policy corrected tooling candidate: PASS
Combined independent tooling recheck: PENDING
Replacement tooling freeze: NOT DONE
Old tooling tag: HISTORICAL / SUPERSEDED FOR EXECUTION
Rejected approval: NOT AUTHORIZED / NOT EXECUTED
New approval candidate: NOT CREATED
Formal Gate 4A: NOT PASSED / NOT FROZEN
Backend freeze: not_frozen
Research eligibility: false
```

A future path requires remote fixation, a combined independent tooling recheck,
a replacement tooling tag, and a new canonical approval with a new ID and SHA.
This report does not grant any of those steps and does not present its author as
the independent checker.
