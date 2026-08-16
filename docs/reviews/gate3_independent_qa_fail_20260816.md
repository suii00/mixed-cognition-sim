# Gate 3 Independent QA — FAIL (2026-08-16)

## Decision

- **FAIL — Gate 3 independent QA checker**
- Audited SHA: `255e50798bef1ed2f9136c1e78a2ed8e6e7da849`
- Freeze recommendation: **DO NOT FREEZE**
- Overall protocol readiness: **NOT READY**
- Pilot authorization: **NO**

## Audited revision

- Repository: `C:\Users\swan0\repo\mixed-cognition-sim`
- Detached worktree: `C:\Users\swan0\repo\mcs-gate3-check-255e507`
- Candidate SHA: `255e50798bef1ed2f9136c1e78a2ed8e6e7da849`
- Implementation commit: `c782356c596443b595f6383e568eea9e97ae1250`
- Initial status: original and detached worktrees clean
- Final directly observed status: clean; no tracked repository files were modified

## Regression evidence

- Full suite: **157/157 PASS**
  - unittest: `18.555 s`
  - wall: `19.458 s`
- `python -m compileall -q engine tests tools main.py`: **PASS**
- `git diff --check`: **PASS**

Recalculated frozen hashes:

- `engine/prompts.py`: `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`
- `docs/METRIC_V2_SPEC.md`: `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d`
- `docs/PHASE_PARALLELISM_SPEC.md`: `77c187277544c116de75273e62d7e13412ad932b38bf9a8e2d5c831347fb105a`
- `docs/EIGHT_CELL_MATRIX_SPEC.md`: `0b1ea989c956fa6e82800fc82ef41186ad460c96e6e38ce2a82e241e41add4db`

## Finding

- Severity: **Critical**
- Title: **Research eligibility does not require agreement with per-run execution mode**

Direct observation:

- Every planned row and generated run configuration continued to record
  `execution_mode = scripted_smoke`.
- In an isolated synthetic temporary copy, batch-level execution declarations
  and corresponding summary evidence were changed and regenerated.
- Underlying planned-run, generated-config, and run-level evidence still
  identified every run as scripted smoke.
- Nevertheless, the batch research validator returned OS exit code `0`,
  classification `PASS`, and `research_eligible = true`.
- The single-run research CLI also returned exit `0` while reporting
  `details.execution_mode = scripted_smoke`.
- No network request, GPU workload, model service, real LLM, or research run
  occurred.

Relevant control flow at the audited SHA:

- Planned rows and configs were required to remain scripted at
  `tools/research_validator.py:215`.
- Research eligibility instead consulted the separate batch metadata execution
  declaration at `tools/research_validator.py:315`.
- The resulting `research_eligible` value was derived without enforcing
  cross-layer execution-mode agreement at `tools/research_validator.py:99`.

Expected consistency rule:

- Batch metadata, plan rows, generated configs, run metadata, and validator
  output must agree on execution mode.
- A consistently scripted batch under the research profile must return
  `2 / UNVERIFIABLE`.
- Conflicting execution-mode evidence must return `3 / FAIL`.

Actual result:

- Contradictory scripted evidence was accepted as
  `0 / PASS / research_eligible=true`.

Scientific/reproducibility impact:

- A CPU orchestration smoke can be mislabeled as research-eligible evidence.
- This breaks the declared boundary between smoke validation and empirical
  research evidence.
- Consequently, Gate 3's fail-closed research-eligibility claim was not
  established at the audited SHA.

## Required remediation

1. Compute research eligibility from validated underlying run evidence.
2. Require execution-mode agreement across batch metadata, plan rows, generated
   configs, run metadata, and validator results.
3. Return exit `2` for a consistently scripted batch under the research profile.
4. Return exit `3` for any cross-layer execution-mode conflict.
5. Ensure batch-only declarations cannot make scripted runs research eligible.
6. Derive `research_eligible` during validation; do not treat persisted
   assertions as authoritative.
7. Repeat independent Gate 3 QA after correction.

Required regression tests:

- Consistent scripted run and batch: smoke profile `0`, research profile `2`.
- Batch declares non-scripted while any row/config/run says scripted: `3`.
- Reciprocal execution-mode mismatches across every layer: `3`.
- Recomputed summary/manifest evidence must not conceal an underlying mismatch.
- Persisted `research_eligible` values must not override derived eligibility.
- Run and batch CLI classifications must agree.
- All validation paths must remain read-only.

## Completed checks before the decisive finding

- Remote SHA, frozen tags, parent chain, and Gate 2 ancestry
- Detached-worktree creation and cleanliness
- Full 157-test regression suite
- Targeted suites: communication policy 5/5, eight-cell runner 10/10,
  research validator 6/6, phase parallelism 19/19, Metric v2 39/39, and strict
  validator 17/17
- Compileall and diff check
- Frozen-hash recalculation
- Gate 0–2 protected-path comparisons
- Review of required specifications, protocol, implementation, and tests
- Gate 3 implementation-diff review; no existing tests were modified or weakened
- Ordinary scripted batch: smoke profile `0`, research profile `2`
- Direct contradictory-evidence run and batch validation
- Raw-run byte immutability across those validations
- Network-call guard: zero real calls
- Protocol states confirmed as `PENDING`, `NOT DONE`, `NOT READY`, and pilot `NO`

## Unverified checks after the FAIL decision

- Exhaustive plan-schema rejection matrix
- Independent four-replicate rotation and homogeneous-profile reconstruction
- Independent paired-field and initial-position comparison
- Independent two-root static-bundle byte comparison
- Full standalone strict-validator communication reconstruction matrix
- Sequential and barrier-synchronized concurrent batch collision probes
- Controlled mid-batch failure, retention, and no-resume probe
- Independent per-cell communication recount across all eight smoke cells
- Complete controlled-consistency mutation matrix
- Standalone validator exit-code matrix for all `0/2/3/64` cases
- Final exhaustive specification/implementation/test correspondence table
- Real Ollama, vLLM, GPU, model-artifact, and production-registry verification
  remained outside Gate 3's demonstrated scope

## Operations

- Repository tracked files modified: no
- Commit: no
- Push: no
- Tag: no
- GPU: no
- Real LLM: no
- Research run: no
- Network services: no; only the authorized initial Git fetch occurred

## Recommendation

- Return to implementation.
- Do not freeze `255e50798bef1ed2f9136c1e78a2ed8e6e7da849`.
- Repeat independent Gate 3 QA after correcting the cross-layer eligibility
  defect.
