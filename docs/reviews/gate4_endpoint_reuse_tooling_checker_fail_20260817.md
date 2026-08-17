# Gate 4 Endpoint-Reuse Tooling Checker FAIL

Date recorded: `2026-08-17` (Asia/Tokyo)

Status: `RETAINED FAIL REPORT — HISTORICAL TOOLING STATE — NOT RUN AUTHORIZATION`

## 1. Audited starting state

The supplied checker report and local preflight fixed all repository references
to:

```text
branch:   feat/gate4-backend-smoke
local:    9d737cd8adaa7c334f065932ea6772ff53363d1b
tracking: 9d737cd8adaa7c334f065932ea6772ff53363d1b
remote:   9d737cd8adaa7c334f065932ea6772ff53363d1b
worktree: clean
tag:      none
```

The endpoint-reuse suite passed `13/13` in 2.236 seconds and the full suite
passed `256/256` in 25.698 seconds. Those existing positive tests did not cover
the contradictions below and therefore did not make the tooling freezeable.

The supplied self-contained CPU fixtures were:

- `/tmp/gate4_timeout_selfcontained_checker.py`, SHA-256
  `cf73fea7ffcfa872ab64c5bbe77e0aeadf1274d396cfaaa643655472f3bf35a0`;
- `/tmp/audit_persisted_validation_self_contained.py`, SHA-256
  `11905bf8e643a548adc6add1c224aaa4b6e535a9d9456477f170b4dc6514acab`.

They were external temporary checker inputs, not repository artifacts. This
report records their findings; it does not claim that those `/tmp` paths are a
durable evidence store.

## 2. Checker decision

```text
CHECKER FAIL
tooling freeze prohibited
real approval prohibited
GPU execution prohibited
```

### 2.1 Generation continued after terminal timeout

In the self-contained synthetic fixture, Qwen raised `TimeoutError`, after
which queued Llama and Gemma requests still entered `backend.generate`. Three
actual backend-generation calls were observed. Cleanup ran and publication was
withheld, but the approval's terminal `timeout` stop condition was not enforced
at the final backend-dispatch boundary.

The frozen Gate 2 executor's submit-and-settle behavior was not itself a defect
and was not authorized for modification. The missing control was a Gate 4
workload-local pre-generation stop gate.

### 2.2 Generation budget and Phase 3 precondition were post hoc

`maximum_generation_calls=6` was schema checked, but no atomic reservation
prevented a seventh direct transport call from reaching a fake backend. A Phase
3 request submitted before Phase 1 completion also initiated all three endpoint
unloads before the state transition failed. The approved count and phase
preconditions therefore were not enforced before side effects.

### 2.3 Persisted workload decision could contradict acceptance

Changing only persisted `workload-validation.json` to
`FAIL / evidence_publication_eligible=false` before publication still allowed:

```text
published workload-validation.json: FAIL / eligible=false
published-byte recomputation:       PASS / eligible=true
independent verifier:               valid=true
external receipt:                   evidence_verified / PASS
```

The persisted decision was absent from the workload artifact index and was not
byte-compared with an independently derived canonical result at every source,
staging, and final boundary.

### 2.4 Directory identity was not continuous across components

A byte-identical alternate directory inode could replace a path between the
workload validator, publisher, and standalone verifier. The workload validator
also resolved a supplied symlink root before rejecting the supplied root
itself, while the standalone verifier rejected that path. Passing only path
text and S/I/R did not bind the source and final filesystem objects across the
component handoffs.

### 2.5 Cleanup report contradicted failed unload evidence

A final unload record with `done=false` correctly caused overall FAIL and no
publication, but `checks.cleanup` could remain `PASS`. That subcheck depended on
whether error text contained the substring `cleanup`, rather than explicit
cleanup evidence booleans.

### 2.6 Non-blocking collision classification defect

In a concurrent approval-ID claim, one owner was retained, but a losing process
could expose raw `FileExistsError` instead of the documented controlled
collision class and stable CLI collision status.

## 3. Boundaries that did pass at the failed tooling state

The checker retained these narrower positive findings:

- approval hash, source SHA/dirty state, and artifact-hash binding;
- CLI workload-override rejection;
- normal Phase 1 x3, unload x3, Phase 3 x3 order;
- reload prevention after incomplete unload;
- PID, port, GPU UUID, and model-digest drift rejection;
- cleanup and nonpublication after a failure;
- partial hidden-stage rejection as formal evidence;
- normal publisher, verifier, and published-byte validator order;
- unknown-warning nonpublication;
- verifier implementation independence from the publisher; and
- no overwrite on sequential or concurrent reuse of one approval ID.

These positive boundaries do not negate the five blocking contradictions.

## 4. Bounded remediation recorded later

This report remains a FAIL for the immutable `9d737cd...` state. It is not
retroactively converted to PASS. The bounded repository correction was recorded
in:

- `05546a1174179fc04636dbfa263301a04bb8e203`,
  `fix: enforce approval-bound endpoint execution stops`;
- `6835508e3c20a2f3d7576746dcc76583eb944550`,
  `fix: bind Gate 4 validation and directory identities`;
- `5d5fc5e1b8822f01599b482ec496b18850f1e47d`,
  `chore: repin prompt6 runner to updated evidence ledger`.

Repository-owned CPU regression after the bounded correction recorded:

```text
endpoint-reuse suite              28/28 PASS
publisher + independent verifier  47/47 PASS
prompt6 regression                10/10 PASS
complete repository suite        272/272 PASS
compileall                         PASS
git diff --check                  PASS
```

The timeout fixture, when rerun against the corrected local implementation,
recorded exactly one actual generation (`qwen:TimeoutError`), no Llama/Gemma
generation start, cleanup called, and no publication. The historical persisted-
contradiction fixture no longer reached its old accepted-state assertion: it
stopped where it required `publication_verified is True`. Repository tests
separately cover source, staging, final, and reverse persisted mismatches. These
are local correction checks, not the requested combined independent tooling
recheck.

No protected Gate 0--3, Metric v2, phase-parallelism, simulator phase/prompt,
eight-cell, `output_mvp_demo`, `main`, or requirements file was changed. No real
network, Ollama, NVIDIA, sudo, process-control, or GPU action occurred, and no
real approval or tooling tag was created.

## 5. Current classification boundary

```text
Gate 4A tooling corrected implementation candidate: PASS
Combined independent tooling recheck: PENDING
Tooling freeze: NOT DONE
Endpoint-reuse execution approval: NO
Real endpoint-reuse execution: NOT PERFORMED
Formal Gate 4A: NOT PASSED / NOT FROZEN
Backend freeze: not_frozen
Research eligibility: false
```

The existing prompt6 evidence remains unchanged and retains:

```text
operational result: PASS_WITH_WARNINGS
publication: NONCONFORMING / NOT FORMALLY ACCEPTED
formal evidence eligibility: false
```

This report does not present its author as the combined independent checker and
does not authorize a real endpoint-reuse or GPU run.
