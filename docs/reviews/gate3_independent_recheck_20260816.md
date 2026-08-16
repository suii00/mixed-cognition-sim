# Decision

PASS — Gate 3 independent recheck
No code changes required.

- Audited SHA: `24b1ceba917f9853779b788d5ccab88c9c227c7b`
- Freeze recommendation: freeze current SHA; do not create a tag during this review
- Overall protocol readiness: `NOT READY`
- Pilot authorization: `NO`
- Production candidate registry: `NOT YET FROZEN`
- Backend/model artifacts: `NOT YET FROZEN`
- One non-blocking Low documentation finding is reported below.

## Audited revision

- Repository: `https://github.com/suii00/mixed-cognition-sim`
- Detached worktree: `C:\Users\swan0\repo\mcs-gate3-recheck-24b1ceb`
- Origin branch tip: `24b1ceba917f9853779b788d5ccab88c9c227c7b`
- Candidate parent / implementation: `88e462c9c079cc874023b4515082c976f0125752`
- Previous failed candidate: `7257fccda2f4f744d71225429f6a3f7542230af7`
- Correction ancestry: previous candidate is an ancestor of implementation
- Gate 2 peeled SHA: `34c6b802958781b9a8d25420742e092a8a0bee3c`
- Gate 1 peeled SHA: `932f53112189c8e1b6125974bf7ad03ab37e5d4c`
- Gate 0 peeled SHA: `86fad23bc1cddf624550c044348566dc5c212bc7`
- Original and detached worktrees: clean initially and finally
- Gate 1 and Gate 2 review blobs: unchanged

## Recalculated hashes

| Artifact | SHA-256 |
|---|---|
| `engine/prompts.py` | `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d` |
| Metric v2 specification | `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d` |
| Phase parallelism specification | `77c187277544c116de75273e62d7e13412ad932b38bf9a8e2d5c831347fb105a` |
| Matrix specification | `96a4ddefbef7a7c9ab8d5a41cb6d438edd7a18b20c78e8154681ac9c61c44e5a` |
| Metric v2 core | `9cc874ef1d8d2fdbb3fde30ac34d0102093e6afd2b6e959cd49e79e6994553f2` |
| Legacy metric | `ef48fafed83bde7df5ecfb8ddb2016146df33af90c4af69516e9f76238de544b` |

## Regression suites

| Suite | Result | unittest time | Wall time |
|---|---:|---:|---:|
| Full | 170/170 PASS | 48.895 s | 49.219 s |
| Research validator | 18/18 PASS | 37.473 s | 37.745 s |
| Eight-cell runner | 11/11 PASS | 4.781 s | 5.093 s |
| Communication policy | 5/5 PASS | 0.281 s | 0.573 s |
| Phase parallelism | 19/19 PASS | 0.446 s | 0.696 s |
| Metric v2 | 39/39 PASS | 4.590 s | 4.800 s |
| Strict validator | 17/17 PASS | 0.737 s | 0.990 s |

- `compileall`: PASS, bytecode redirected to OS temporary storage
- `git diff --check`: PASS
- Existing test methods: 166 before, 170 after
- Removed tests: 0
- Added tests: 4
- Skips/expected failures: 0
- No existing assertion weakening observed
- An initial sandboxed attempt was discarded because OS-temp writes were denied; the permission-corrected rerun above exercised the actual assertions.

## Shared context

Both public commands construct the same context through [`_build_validated_batch_context`](/C:/Users/swan0/repo/mcs-gate3-recheck-24b1ceb/tools/research_validator.py:807).

It binds:

- Plan, planned rows, generated configs, metadata, and manifest
- Every required run directory and lifecycle state
- Registry/backend freeze agreement
- Protocol, metric, matrix, execution mode, source and model-artifact evidence
- Run-start approval
- Independently derived per-run and batch eligibility
- All canonical persisted summaries

The public run path merges all batch findings and derives:

```text
selected_run_research_eligible
AND batch_research_eligible
```

at [`research_validator.py:1271`](/C:/Users/swan0/repo/mcs-gate3-recheck-24b1ceb/tools/research_validator.py:1271). Persisted summaries are compared only after derivation.

## Independent fixtures

Ten temporary fixtures were exercised through the public CLI parser. Each contained all eight canonical run IDs under `gate3-independent-r000-*`.

| Fixture | Batch smoke/research | All-run smoke/research | Research eligibility pattern¹ | Tree SHA-256 before = after |
|---|---|---|---|---|
| Scripted smoke | 0 / 2 | 0 / 2 | `F/F/F` | `ea489633ad9592697c0be85af651b8dffd7c612d8fe2d44aa1b84c203920a93f` |
| Positive control | 0 / 0 | 0 / 0 | `T/T/T` | `91a321caf4453a98d06d883068f7b16d2d35aa7a920ee6a3bbd09b18f2537195` |
| Plan/metadata contradiction | 3 / 3 | 3 / 3 | `T/F/F` | `03ab6e3d8471836acd5cb49946c4ac066b36dfb15e1a2aeb674136c8bb12d8b2` |
| Consistently not frozen | 0 / 2 | 0 / 2 | `F/F/F` | `46209311197bed3cbf487f1eefe7ed27005ce81ad3a2e56a8925c4efdba04db2` |
| Stale metadata summary | 3 / 3 | 3 / 3 | `T/F/F` | `5a87cdddcfd3a02650dcaacf60f8b34385632d8779049fae178308c71e8a4fd9` |
| Stale manifest summary | 3 / 3 | 3 / 3 | `T/F/F` | `c67b09236bf28c30cb0d0f51308bfaa50d98bc0d6ce1c16622de4bb998c0b201` |
| Unselected invalid run | 3 / 3 | 3 / 3 | Valid selected run `T/F/F` | `6dc78672b7050ac338ece4cb7b106613cf7e34665310a7aee781d4760b84c008` |
| Unselected unverified evidence | 0 / 2 | 0 / 2 | Unaffected selected run `T/F/F` | `654ffe6a5009d19e129c59730d7f2e057edb1cc107abbdc6a426b519c6db5cc5` |
| Persisted run-summary disagreement | 3 / 3 | 3 / 3 | `T/F/F` | `5a8faa9d553857d7394ba0805975e1b6d39102f47237a7dd84dcc4954866c416` |
| Missing canonical run summary | 3 / 3 | 3 / 3 | Final always false | `d930de2f2e0b264a410d394249851b831e0e5b749e7e99921915807c921bb8b0` |

¹ Selected-run / batch / final effective eligibility.

The unselected-unverified fixture had four artifact-unverified and four unaffected runs because the catalog profile is shared. An unaffected selected run remained individually eligible but correctly returned exit 2 because batch eligibility was false.

### Implication results

- Run exit 0 with nonzero batch exit: `0`
- Batch exit 3 with run exit 0: `0`
- Batch exit 2 with run exit 0: `0`
- Expected violations: `0`

### Exit and read-only evidence

- OS-process batch/run exit 0: verified
- OS-process batch/run exit 2: verified
- OS-process batch/run exit 3: verified
- Invocation/configuration exit 64: verified for top-level and run invocation
- Help: exit 0, usage on stdout, stderr empty
- Printed classification matched every process exit
- Complete-tree-hashed validator operations: `187`
- Changed trees: `0`
- Guarded `requests.post` invocation count: `0`
- Temporary fixture root was automatically cleaned after execution

## Specification consistency

| Requirement | Spec | Implementation | Evidence |
|---|---|---|---|
| Specification v1.1.1 | Yes | Constant v1.1.1 | Hash and runner test |
| Shared `ValidatedBatchContext` | §25–26 | Yes | All fixtures |
| Plan ↔ metadata authority | Yes | Direct equality checks | Contradiction fixture |
| Registry/backend agreement | Yes | Shared batch checks | Exit 3 fixture |
| All-required-runs validation | Yes | Every manifest row traversed | Invalid/unverified fixtures |
| Selected-run derivation | Yes | Stored in shared context | Positive and negative controls |
| Batch derivation | Yes | Requires all run eligibilities | All fixtures |
| Final run formula | Yes | Selected AND batch | Asserted for every run |
| Run PASS ⇒ batch PASS | Yes | Enforced | 0 violations |
| Batch FAIL blocks run PASS | Yes | Findings merged | 0 violations |
| Batch UNVERIFIABLE blocks run PASS | Yes | Findings merged | 0 violations |
| Persisted-summary comparison | Yes | Post-derivation | Four mismatch fixtures |
| Contradiction → exit 3 | Yes | Yes | Process and fixture evidence |
| Missing evidence → exit 2 | Yes | Yes | Two independent fixtures |
| Positive control → exit 0 | Yes | Yes | Eight of eight runs |
| Read-only behavior | Yes | No write path | 187 hash checks |
| Real backend deferred | §31 | No backend call | Network count 0 |

## Finding

Low — Incorrect plan-schema identifier in matrix specification §28

- File: [`docs/EIGHT_CELL_MATRIX_SPEC.md:280`](/C:/Users/swan0/repo/mcs-gate3-recheck-24b1ceb/docs/EIGHT_CELL_MATRIX_SPEC.md:280)
- Direct observation: §28 says `eight-cell-plan-v1.1.0`.
- Required/actual identifier: `eight-cell-matrix-plan-v1.1.0`.
- Impact: documentation-only. Section 13, implementation, protocol, generated artifacts, and tests all use the correct identifier. No eligibility, schema, or exit-classification effect was observed.
- Remediation: correct the cross-reference in a future documentation-only change. Because that changes specification bytes, recalculate and re-pin its hash.
- Required regression: assert that schema identifiers named by the specification match `PLAN_SCHEMA_VERSION` and `BATCH_MANIFEST_VERSION`.
- Freeze impact under the supplied criteria: non-blocking.

## Existing controls and protocol consistency

The existing suites and independent smoke reconfirmed fixed cells/order, HET rotation, QQQ/GGG/LLL mapping, paired hashes and positions, full/within-bloc communication, sequential and concurrent collisions, failed/not-started retention, scripted no-network execution, and raw immutability.

`docs/EXPERIMENT_PROTOCOL.md` correctly retains:

- The `7257fcc...` FAIL and public run/batch inconsistency
- Correction commit `88e462c...`
- Matrix specification v1.1.1 and expected hash
- 170/170 and 18/18 correction evidence
- Shared context and selected-run/batch conjunction
- Independent recheck `PENDING`
- Gate 3 freeze `NOT DONE`
- Readiness `NOT READY`
- Pilot authorization `NO`
- Registry and backend artifacts `NOT YET FROZEN`

It does not describe the candidate as frozen.

## Remaining unverified scope

- Real Ollama and vLLM
- Real model artifacts and output quality
- Backend equivalence
- GPU/resource behavior
- Production registry
- Pilot, confirmatory, or research execution

## Operations

- Tracked files modified: no
- Commit/push/tag/merge: no
- GPU or real LLM: no
- Research run: no
- Package installation: no
- Network beyond the permitted initial fetch: no

Recommendation: freeze `24b1ceba917f9853779b788d5ccab88c9c227c7b`; do not create the tag as part of this review.
