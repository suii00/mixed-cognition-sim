# Gate 3 Independent Recheck — FAIL (2026-08-16)

## Decision

- **FAIL — Gate 3 independent recheck**
- Corrected candidate SHA: `1cb5e8702b92537ecc2157588bdb435a81a0b060`
- Freeze recommendation: **DO NOT FREEZE**
- Overall readiness: **NOT READY**
- Pilot authorization: **NO**

前回の Critical defect は、実装済み4層では修正されています。scripted-smoke が research PASS になる経路は再現されませんでした。ただし、eligibility classification に関係する未解決 Medium finding が2件あるため、Gate 3 は PASS にできません。

## Audited revision

- Repository: `https://github.com/suii00/mixed-cognition-sim`
- Detached QA worktree: `C:\Users\swan0\repo\mcs-gate3-recheck`
- Corrected candidate／correction evidence: `1cb5e8702b92537ecc2157588bdb435a81a0b060`
- Correction implementation: `6e1d13e3313e0bf35537db5352df61e261e8417e`
- Previous failed candidate: `255e50798bef1ed2f9136c1e78a2ed8e6e7da849`
- Gate 2 peeled SHA: `34c6b802958781b9a8d25420742e092a8a0bee3c`
- Gate 1 peeled SHA: `932f53112189c8e1b6125974bf7ad03ab37e5d4c`
- Gate 0 peeled SHA: `86fad23bc1cddf624550c044348566dc5c212bc7`
- Remote branch、local branch、detached HEAD はすべて corrected candidate と一致
- 両 ancestry check: exit `0`
- 元 worktree／detached worktree: initial・final とも clean

## Recalculated hashes

- `engine/prompts.py`: `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`
- Metric v2 specification: `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d`
- Phase parallelism specification: `77c187277544c116de75273e62d7e13412ad932b38bf9a8e2d5c831347fb105a`
- Corrected matrix specification: `3dc9bb16823755c2b358cfe312a279f02d4c24b8e2d788e9dc1996f2a427e08b`
- Metric v2 core: `9cc874ef1d8d2fdbb3fde30ac34d0102093e6afd2b6e959cd49e79e6994553f2`
- Legacy metric: `ef48fafed83bde7df5ecfb8ddb2016146df33af90c4af69516e9f76238de544b`

Protocol は corrected matrix hash を正確に記録しています。

## Regression suites

- Full suite: **160/160 PASS**
  - unittest: `19.840 s`
  - wall: `20.156490 s`
- Communication policy: **5/5 PASS**, `0.313 s` / wall `0.566078 s`
- Eight-cell runner: **10/10 PASS**, `4.779 s` / wall `5.036987 s`
- Research validator: **9/9 PASS**, `7.240 s` / wall `7.501830 s`
- Phase parallelism: **19/19 PASS**, `0.428 s` / wall `0.657716 s`
- Metric v2: **39/39 PASS**, `4.802 s` / wall `4.982677 s`
- Strict validator: **17/17 PASS**, `0.798 s` / wall `1.057080 s`
- `compileall`: PASS
- `git diff --check`: PASS
- Skip／expected failure: なし

修正 test diff は `+220/-0`。既存 test・assertion の削除や弱化はありません。最初の sandbox 内実行は Windows temporary-directory ACL で開始前に失敗しましたが、package install や network を使わず同一 suite を再実行し、上記結果を得ました。

## Correction review

変更は6ファイル、`551 insertions / 29 deletions` です。

- `tools/research_validator.py`
- `tools/eight_cell_core.py`
- `tests/test_research_validator.py`
- `docs/EIGHT_CELL_MATRIX_SPEC.md`
- `docs/EXPERIMENT_PROTOCOL.md`
- 過去 FAIL report の追加

Prompt、agent/world、phase transport、Metric v2、legacy metric、MVP artifacts、Gate 1/2 frozen report に変更はありません。

実装済みの `batch_meta → planned rows → generated configs → run_meta config` の4層については、mode の unanimous derivation、scripted-smoke の exit 2、矛盾の exit 3、persisted true による promotion 防止が機能しました。

## Independent consistency fixtures

すべて fresh fixture として OS temp 配下に作成し、通常の hash／manifest を再計算して public CLI を実行しました。

| Fixture | Actual result |
|---|---|
| Supported-layer scripted batch / smoke | `0 PASS`, `smoke_valid=true`, eligible `false` |
| Supported-layer scripted batch / research | `2 UNVERIFIABLE`, eligible `false` |
| Supported-layer scripted run / smoke | `0 PASS`, eligible `false` |
| Supported-layer scripted run / research | `2 UNVERIFIABLE`, eligible `false` |
| Batch versus planned rows | batch/run `3 FAIL` |
| Batch versus generated configs | `3 FAIL` |
| Planned row versus generated config | `3 FAIL` |
| Generated config versus `run_meta` | batch/run `3 FAIL` |
| Manifest eligibility versus per-run evidence | `3 FAIL` |
| Persisted eligibility assertion | `3 FAIL` |
| Non-scripted, missing approval only | `2 UNVERIFIABLE`; missing itemは approval reference のみ |
| Invalid invocation | `64` |

Optional fully positive control は、repository-supported constructor が存在しないため指示どおり **UNVERIFIED** です。

詳細: [audit_results.json](C:/Users/swan0/AppData/Local/Temp/gate3-independent-fixtures-d9fdffb9f0934b7da449ff3d16e6b7c2/audit_results.json)

## Exit classification

- Exit `0`: reproduced
- Exit `2`: reproduced
- Exit `3`: reproduced
- Exit `64`: reproduced
- Printed classification と process exit は本検証ケースで一致

ただし `--help` の exit classification には Low finding があります。

## Eligibility invariant

- scripted run、矛盾、または missing evidence がある出力で `research_eligible=true`: **0件**
- Expected: `0`
- `requests.post` guard call count: **0**

## Existing Gate 3 controls

- 8-cell canonical order: PASS
- HET rotation: PASS
- QQQ/GGG/LLL assignment: PASS
- Paired hashes／initial positions: PASS
- Full cross-bloc communication: PASS
- Within-bloc communication保持／cross-bloc除去: PASS
- Sequential／concurrent batch collision: PASS
- Failed／not-started row retention: PASS
- Scripted-smoke boundary: PASS
- Real network: 呼び出しなし

## Immutability

各 fixture について以下が validation 前後で byte-identical でした。

- Raw JSONL: `32` files／fixture
- Batch artifacts: `13` files／fixture
- `run_meta.json` を含む full fixture tree
- Plan、planned rows、generated configs、batch metadata、batch manifest

## Findings

### Medium — Required execution-mode layers are absent

- Files:
  - [Plan schema](C:/Users/swan0/repo/mixed-cognition-sim/tools/eight_cell_core.py:46)
  - [Manifest-row schema](C:/Users/swan0/repo/mixed-cognition-sim/tools/research_validator.py:51)
  - [Batch-manifest schema](C:/Users/swan0/repo/mixed-cognition-sim/tools/research_validator.py:774)
  - [Corrected specification](C:/Users/swan0/repo/mixed-cognition-sim/docs/EIGHT_CELL_MATRIX_SPEC.md:130)

Direct observation:

- `plan.json` と `batch_manifest.json` は `execution_mode` を持てません。
- Plan に consistent `scripted_smoke` を追加すると exit `3`: `unknown=execution_mode`
- Manifest top-level に追加すると exit `3`: `batch manifest fields are not canonical`
- Manifest run row に追加すると exit `3`: `batch manifest run row 0 fields are not canonical`

Expected:

- Plan と manifest を含む全層一致 scripted control が smoke `0`、research `2`
- Plan↔row、manifest↔per-run mode disagreement が `3`

Actual:

- 全層一致 fixture 自体を canonical schema で表現できません。
- Frozen plan は実行 mode を拘束できず、manifest は per-run mode を照合できません。

Impact:

- Checker が要求する execution-mode evidence chain と regression coverage が不完全です。

Required remediation:

- Plan／manifest schema をversion bump
- 両方へ recognized `execution_mode` を永続化
- Out-of-band argument ではなく plan から生成
- 全要求層で一致を検証

Required regression:

- 全層一致 scripted control
- Plan↔row disagreement
- Manifest↔per-run disagreement
- Consistent mode を追加しても schema error にならないこと

Schema probe evidence: [schema_layer_results.json](C:/Users/swan0/AppData/Local/Temp/gate3-independent-fixtures-d9fdffb9f0934b7da449ff3d16e6b7c2/schema_layer_results.json)

### Medium — Persisted and derived eligibility necessarily diverge on a positive path

- [Derived output calculation](C:/Users/swan0/repo/mixed-cognition-sim/tools/research_validator.py:93)
- [Persisted eligibility validation](C:/Users/swan0/repo/mixed-cognition-sim/tools/research_validator.py:351)
- [Matrix-spec rule](C:/Users/swan0/repo/mixed-cognition-sim/docs/EIGHT_CELL_MATRIX_SPEC.md:203)

Direct observation:

- すべての persisted `research_eligible` は常に `false` であることを要求されます。
- Validator output は、research profile に error／unverified がなければ `true` を導出します。

Mechanical derivation:

- Reachable research PASS は persisted `false` と derived `true` が必ず不一致になります。
- その不一致は exit `3` に分類されません。
- 逆に persisted `true` は、derived result と一致する場合でも無条件に拒否されます。

これは checker の「summary は promotion に使わず、独立導出結果との不一致は FAIL」という contract と一致しません。

Required remediation:

- Authoritative evidence だけから eligibility を先に導出
- Persisted summary を導出値と比較
- Stale false と unsupported true の双方を exit `3`
- Summary を入力として promotion しない

Required regression:

- Fully consistent positive logic control
- Derived true／persisted false mismatch
- Derived false／persisted true mismatch

Positive fixture は repository に存在しないため、指示に従い実行していません。

### Low — `--help` is classified as configuration failure

- [CLI exception handler](C:/Users/swan0/repo/mixed-cognition-sim/tools/research_validator.py:1014)

Direct observation:

```text
python -m tools.research_validator --help
ERROR: validator configuration failure: SystemExit
exit 64
```

`argparse` の正常な `SystemExit(0)` が broad handler に捕捉されています。Scientific eligibility には影響しないため non-blocking Low です。

Required remediation／test:

- 正常な help termination を許可
- `--help` が exit `0`、stderr 空になる regression test を追加

## Specification consistency

| Requirement | Spec | Implementation | Fixture | Result |
|---|---|---|---|---|
| Authoritative execution evidence | 4層のみ | 4層のみ | 4層 PASS | **Partial** |
| Summary evidence role | Always-false rule | Always-false check | Scripted mutation PASS | **Partial** |
| Cross-layer agreement | Plan/manifest不足 | Plan/manifest不足 | Schema probes FAIL | **Mismatch** |
| Scripted research ineligibility | Yes | Yes | Exit 2 | Aligned |
| Missing evidence → 2 | Yes | Yes | Approval-only exit 2 | Aligned |
| Contradiction → 3 | Yes | 実装4層のみ | Supported contradictions exit 3 | Partial |
| Derived eligibility | Agreement不足 | Positive pathで不一致 | Positive controlなし | **Mismatch** |
| Run-level validation | Yes | Yes | 0/2/3 reproduced | Aligned for implemented layers |
| Batch-level validation | Yes | Yes | 0/2/3 reproduced | Aligned for implemented layers |
| Exit 0/2/3/64 | Yes | Yes | Reproduced | Main cases aligned |
| Read-only validation | Yes | Yes | Hash equality | Aligned |
| No real network | Yes | Yes | Guard count 0 | Aligned |

## Protocol consistency

- Previous `255e507…` failure: retained
- Execution-mode finding: recorded
- Correction implementation／matrix hash／regression evidence: recorded
- Independent recheck state: `PENDING`
- Gate 3 freeze: `NOT DONE`
- Readiness: `NOT READY`
- Pilot authorization: `NO`
- Production registry: `NOT YET FROZEN`
- Backend/model artifacts: `NOT YET FROZEN`
- Self-referential Gate 3 freeze SHA: なし

## Remaining unverified scope

- Fully positive research eligibility fixture
- Real Ollama／vLLM
- Real LLM output behavior
- GPU／backend performance
- Production registry and model artifacts
- Pilot and confirmatory execution

## Operations

- Tracked files modified: no
- Commit／push／tag: no
- GPU／real LLM／research run: no
- Package installation: no
- Network beyond initial `git fetch`: no
- Synthetic fixtures: OS temp only
- Research run ID: none
- Matrix spec: `eight-cell-matrix-v1.0.1`
- Metric version: `metric-v2.0.0`

## Recommendation

**Return to implementation. Do not freeze `1cb5e8702b92537ecc2157588bdb435a81a0b060`.**
