# Gate 4 Endpoint-Reuse Warning-Policy Recheck FAIL

Date recorded: `2026-08-18` (Asia/Tokyo)

Status: `RETAINED CHECKER FAIL — HISTORICAL TOOLING STATE — NOT RUN AUTHORIZATION`

## 1. Audited starting state

The replacement-tooling recheck fixed the audited repository state to:

```text
branch:         feat/gate4-backend-smoke
local HEAD:     5a3f17928bc02cf9cad995e6dfd6e50ed5ed7e18
local tracking: 5a3f17928bc02cf9cad995e6dfd6e50ed5ed7e18
worktree:       clean
```

The implementation task did not perform a network fetch because the same
task explicitly prohibited network use. The pre-existing local tracking ref
matched the required SHA. This report makes no claim about a later remote
state.

At that starting state, repository-owned baseline tests recorded endpoint-
reuse `38/38 PASS` in 4.077 seconds and the full suite `282/282 PASS` in
27.626 seconds. Those tests did not cover the three findings below.

## 2. Checker decision

```text
Warning-policy corrected tooling candidate: FAIL
Replacement tooling freeze: NOT DONE
New approval: NOT CREATED
Formal Gate 4A: NOT PASSED / NOT FROZEN
Backend freeze: not_frozen
Research eligibility: false
```

Commit `5a3f17928bc02cf9cad995e6dfd6e50ed5ed7e18` is not a tooling-freeze
candidate. The historical tag
`gate4a-endpoint-reuse-tooling-frozen-20260817` remains unchanged at
`225ae755f3dff2400d2fa8a60b1d1bb9a3e17071` and is superseded for execution.

## 3. Blocking findings

### 3.1 Invalid UTF-8 erased visible fatal diagnostics

Diagnostic extraction depended on successful UTF-8 decoding of the complete
physical line. If one unrelated byte was invalid, the persisted structured
event could retain an empty `diagnostic_indicators` array even when surrounding
ASCII bytes contained `ERROR` and `request failure`. A later exact approved
WARN could then leave the synthetic workload publishable.

### 3.2 Hyphenated out-of-memory was absent

The vocabulary recognized `OUT OF MEMORY` and `OOM`, but did not recognize
`OUT-OF-MEMORY`. A physical line containing `out-of-memory` followed by an
approved WARN was therefore not necessarily fatal.

### 3.3 Rejected approval identity was not executable policy

The specification said the rejected approval ID could not be reused, and its
old v1.0 schema was rejected. However, a syntactically valid current-schema
approval could reuse the same `approval_id` and `evidence_bundle_id`. No
machine-enforced retired identity set stopped it independently of schema or
contents.

## 4. Retained rejected approval

The rejected approval identity is:

```text
approval_id:       gate4a-endpoint-reuse-fp16-20260817T124139Z
evidence_bundle_id: gate4a-endpoint-reuse-fp16-20260817T124139Z
approval SHA-256:  b97d603b2e34c0e7157398a916ae6485e60bc6304746cb2189a1db11187756d4
summary SHA-256:   06f8c71a5f5fa8a299e9152b8535305a72da4ac263bfa52e3c29c70e278a821f
review:            FAIL
authorization:     NO
execution:         NOT PERFORMED
reason code:       warning_policy_overbroad
```

The JSON and summary were re-hashed read-only and remain mode 0444. They were
not edited, replaced, deleted, reauthorized, executed, or reissued.

## 5. Bounded correction recorded later

The FAIL above remains attached to immutable commit `5a3f179...`; it is not
retroactively promoted. The limited repository correction is:

- `90591089b75738cd15386a5452abb94b497ceacc`,
  `fix: preserve fatal diagnostics across invalid UTF-8`;
- `334ba662941bc4d16ffcaa914d2b06711ab5e21f`,
  `fix: retire rejected Gate 4 approval identity`; and
- `684ed41e86a7efd2b012ede652a5dd2949500cd1`,
  `chore: repin prompt6 runner to updated Gate 4 ledger`.

The raw-byte classifier performs bounded ASCII case folding and token-aware
matching before strict UTF-8 decoding. Invalid UTF-8 with fatal evidence is
`FAIL`; invalid UTF-8 without known fatal evidence is
`MANUAL_REVIEW_REQUIRED`. Every invalid UTF-8 event is retained and
non-publishable. Space, hyphen, and underscore variants of out-of-memory map
to `OUT_OF_MEMORY`.

An immutable executable registry now retires the historical identity for both
`approval_id` and `evidence_bundle_id` before schema-dependent validation,
evidence-root creation, backend preflight, or publication. The entry binds the
original approval SHA, status `rejected`, and reason code
`warning_policy_overbroad`; Markdown is not an enforcement source.

The resulting versions and hashes are:

```text
endpoint-reuse spec:
  gate4-ollama-endpoint-reuse-v1.2.1
  df5ec64e7272b7806c37d74544e9b6f78f59e344accf0bcf4ec63964c59d4881
approval schema:
  gate4-ollama-endpoint-reuse-approval-v1.1.1
workload validator:
  aa7737035c9514eea316157e73783a7c8c28492624589c4c467c8b4fb171c536
orchestrator:
  d7c17e92607eeb3e8ab59ae4f6d972282327c70fda070627ca1225d95f720915
evidence ledger:
  gate4-backend-evidence-ledger-v1.6.0
  fc9653572d242f309213e17a8a20fc3592cb4614d8febe9b986eb77b157f4c57
```

Observation and workload-validation schema fields did not change and remain
v1.2.0. Generic publisher contracts did not change.

## 6. CPU regression evidence and boundary

Repository-owned CPU tests after both bounded corrections recorded:

```text
endpoint-reuse targeted suite     44/44 PASS (4.270 s)
publisher + independent verifier  47/47 PASS (1.585 s)
prompt6 regression                10/10 PASS (0.258 s)
complete repository suite        288/288 PASS (27.664 s)
compileall                         PASS
git diff --check                  PASS
```

The exact-six WARN fixture still publishes and independently verifies, while
invalid-UTF8 fatal and hyphenated out-of-memory full fixtures do not publish or
create a success receipt. Old- and current-schema retired-ID fixtures fail. A
fresh-ID control performs schema validation only. Retired-ID orchestration
stops with zero backend preflights and no attempt, final, or receipt directory.

These are repository-owned correction tests, not the independent replacement
tooling recheck. No GPU, `nvidia-smi`, Ollama/API, sudo, external network,
temporary server, process signal, real approval, or endpoint execution was used.
No push or replacement tag was performed.

## 7. Current classification boundary

```text
Gate 4A diagnostics/approval corrected tooling candidate: PASS
Independent replacement tooling recheck: PENDING
Replacement tooling freeze: NOT DONE
Historical tooling tags: SUPERSEDED FOR EXECUTION
Rejected approval: NOT AUTHORIZED / NOT EXECUTED / ID RETIRED
New approval candidate: NOT CREATED
Formal Gate 4A: NOT PASSED / NOT FROZEN
Backend freeze: not_frozen
Research eligibility: false
```

This report does not present its author as the independent checker and does not
authorize a replacement tag, approval candidate, endpoint run, GPU run, pilot,
or research run.
