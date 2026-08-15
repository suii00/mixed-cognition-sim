# Gate 2 Independent QA — 2026-08-16

## 判定

- **PASS — Gate 2 independent QA checker**
- No code changes required.
- Freeze candidate SHA: `34c6b802958781b9a8d25420742e092a8a0bee3c`
- Overall protocol readiness: **NOT READY**
- Pilot authorization: **NO**

## Audited revision

- Repository root: `C:\Users\swan0\repo\mixed-cognition-sim`
- Detached QA worktree: `C:\Users\swan0\repo\mcs-gate2-check-34c6b80`
- Audited SHA: `34c6b802958781b9a8d25420742e092a8a0bee3c`
- Implementation commit: `4f893b3926db37e508b49dadbf47f1372bec3ed6`
- Protocol evidence commit: `34c6b802958781b9a8d25420742e092a8a0bee3c`
- Gate 2 management baseline: `98eb2fcb2d4bb2f4dd1bc605f77bf62e7f5b4d71`
- Gate 1 peeled SHA: `932f53112189c8e1b6125974bf7ad03ab37e5d4c`
- Gate 0 peeled SHA: `86fad23bc1cddf624550c044348566dc5c212bc7`
- Candidate parent: `4f893b3926db37e508b49dadbf47f1372bec3ed6`
- Implementation parent: `98eb2fcb2d4bb2f4dd1bc605f77bf62e7f5b4d71`
- Management baseline parent: `932f53112189c8e1b6125974bf7ad03ab37e5d4c`
- Baseline ancestry check: PASS
- Initial original-worktree status: clean
- Initial detached-worktree status: clean
- Final original-worktree status: clean
- Final detached-worktree status: clean

## Recalculated hashes

- `engine/prompts.py`: `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`
- `docs/METRIC_V2_SPEC.md`: `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d`
- `docs/PHASE_PARALLELISM_SPEC.md`: `77c187277544c116de75273e62d7e13412ad932b38bf9a8e2d5c831347fb105a`
- `tools/metric_v2_core.py`: `9cc874ef1d8d2fdbb3fde30ac34d0102093e6afd2b6e959cd49e79e6994553f2`
- `tools/vocab_metrics.py`: `ef48fafed83bde7df5ecfb8ddb2016146df33af90c4af69516e9f76238de544b`

## Regression suite

- Full command: `python -m unittest discover -s tests -v`
- Full result: **136/136 PASS**
- Full unittest time: `7.978 s`
- Full wall time: `8.614213 s`
- Targeted command: `python -m unittest tests.test_phase_parallelism -v`
- Targeted result: **19/19 PASS**
- Targeted unittest time: `0.419 s`
- Targeted wall time: `0.673850 s`
- `python -m compileall -q engine tests tools main.py`: PASS
- `git diff --check`: PASS
- Existing tests changed or weakened: none; Gate 2 adds
  `tests/test_phase_parallelism.py` without modifying existing test files.

## Findings

- None

Critical, High, Medium, Low findingsはありません。

## Independent probes

- Config default/provenance: PASS。省略時のeffective valueは`1`で、disk上の
  `run_meta.json.config.llm_defaults.max_concurrency`にも保存。
- Config object immutability: PASS。`Simulation`生成前後のcaller configは
  deep-copy比較で同一。
- Config hash distinction: PASS。同一configでconcurrencyだけを`1`/`3`にした
  場合、保存config hashは異なる。
- Request isolation: PASS。11 fieldを確認し、duplicate request ID・duplicate
  agent IDを拒否。request側overrideを変更してもcaller config、effective
  config、Agent mapping、別requestは不変。
- Result contract: PASS。identity、parsed、raw output、local telemetry、error
  classification/objectのみ。transport/unexpected exceptionは元objectを保持した
  result dataとして返る。
- Patch compatibility: PASS。`Simulation`生成後の
  `mock.patch("engine.sim.call_ollama", ...)`が6 requestすべてに有効。
- Worker-local telemetry: PASS。Event停止中はworkerがHTTP telemetryを生成済み
  でも、対応batchのlifecycle/simulation counterは未反映。
- Coordinator-only mutation: PASS。instrumentした68 shared-mutation callと15
  stdout callはすべてcoordinator thread上。
- Concurrency bound: PASS。実測peakはconcurrency 1で`1`、concurrency 3で`3`、
  2 requests / limit 8で`2`。
- All Phase 1 prompts before dispatch: PASS。最初のPhase 1 transport時点で
  `3/3` prompts構築済み。
- Phase 1 delivery barrier: PASS。worker停止中、Phase 1 raw、message raw、
  received messages、memory、position、Phase 3 invocationは不変。
- All Phase 3 prompts before dispatch: PASS。最初のPhase 3 transport時点で
  `3/3` prompts構築済み。
- Phase 3 memory/movement barrier: PASS。worker停止中、memory raw、Agent
  memory、position、completed stepsは不変。
- Snapshot content/timing: PASS。Phase 3 promptは全Phase 2 deliveryを含み、
  次stepのPhase 1 promptは前stepのmemoryと移動後positionを含む。
- Reverse completion order: PASS。worker completionを各phaseで`2,1,0`にしても、
  raw、memory、movement、progress、observationは`0,1,2`。
- Agent-list-order invariance: PASS。一方の`self.agents`をreverseしても
  raw/state/RNG/counters/manifest/transcriptは同一。
- Concurrency 1/N equivalence: PASS。3 agents・2 steps・concurrency 1/3で
  全比較対象が同一。
- Phase 1 parse failure: PASS。`parsed=null`、parse-error記録、当該senderから
  deliveryなし。
- Phase 3 parse failure: PASS。stay、空direction/memory/reasoning、memory追加
  なし、movementなし。
- Phase 1 transport failure: PASS。全3 request settle、Phase 1 primary
  commit/delivery/Phase 3なし、completed steps不変、aborted。
- Phase 3 transport failure: PASS。Phase 1 rawとdeliveryは保持、Phase 3
  memory/log/movementなし、aborted。
- Multiple transport failures: PASS。Phase 1/3、concurrency 1/3、正順/逆順で
  確認。常に最小error agent IDを選択。
- Unexpected failure: PASS。元exception object/typeをcoordinator側でre-raiseし、
  statusは`failed`、phase commitなし。
- Mixed unexpected/transport priority: PASS。低IDのtransport errorより
  unexpected errorが優先。
- Multiple unexpected failures: PASS。completion `2,1,0`でもunexpected群の
  最小agent `0`を選択。
- Counter taxonomy: PASS。mock HTTPでlogical calls `2`に対してHTTP attempts
  `4`、generation retry `1`、transient transport failure `1`。HTTP retryを
  logical callとして重複計上していない。
- Parse + transport同batch: PASS。concurrency 1/3ともlogical `3`、HTTP `6`、
  generation retry `1`、transport failure `3`、syntax attempt failure `2`、
  final syntax failure `1`。
- No thread leak: PASS。normal、parse、transport、unexpected、mixed、reverse
  completion後に`gate2-llm*` threadは残存なし。
- No real network: PASS。guardされた`requests.post`の実network callは0。
  counter taxonomyの4 callは明示的なmock responseだけ。
- Strict validator compatibility: PASS。concurrency 1/3のcompleted run、および
  許容threshold付きparse-failure runはいずれもstrict validで、結果は
  concurrency間で同一。

Strict validatorの以下の事項は、従来どおり`UNVERIFIABLE`のままです。

- GPU/driver/CUDA provenance
- 一部model artifact details
- raw event IDによるglobal identity
- HTTP attempt/transport failureのevent-level truth
- model-response semantic validity
- Phase 3 parse-error completeness
- manifestの外部署名
- redaction前config secret identity

## Architecture

- Spec version: `phase-parallelism-v1.0.0`
- Executor: bounded `ThreadPoolExecutor`、prefix `gate2-llm`
- Concurrency default: effective `1`
- Worker count: `min(max_concurrency, request_count)`
- Empty batch: executorを作成せず`[]`
- Request contract: immutable dataclass identity/value envelopeとrequest-owned
  override copy
- Result contract: canonical identity、deep-copied parsed、raw、local telemetry、
  original error
- Local telemetry: HTTP attempts、generation retries、transport failures、
  syntax parse attempt failures
- Coordinator ownership: accounting、context、raw logs、delivery、memory、
  movement、progress
- Ollama reference path:
  [sim.py](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/engine/sim.py:219)で
  `engine.sim.call_ollama`をworker invocation時に解決
- vLLM status: deferred。現行provider validationはOllamaのみ

## Phase semantics

- Phase 1 snapshot: position、memory、received messages、places、place、occupancy
  をdispatch前にcopy。
- Phase 1 result commit: executor shutdownとterminal-error評価後のみ、agent
  ID順にcommit。
- Phase 2 delivery: Phase 1全commit後、step-start position snapshotを用いて
  sender/receiver ID順。
- Phase 3 snapshot: Phase 2 delivery完了後、memory/movement前に作成。
- Phase 3 memory commit: 全worker settle・terminal-error評価後、agent ID順。
- Phase 4 movement: 全Phase 3 memory/reasoning commit後、agent ID順。
- Canonical ordering: prompt construction、submit、result return、raw、parse
  error、delivery、memory、movement、progressで確認。

## Failure semantics

- Parse failure: non-terminal。Phase別fallbackは仕様どおり。
- Transport failure: all-request settlement後に`aborted / transport_failure`。
  当該phaseはprimary/state非commit。
- Unexpected worker failure: transportへ変換せず
  `failed / unhandled_exception`。元exception type/objectを保持。
- Error priority: `unexpected > transport > parse > normal`
- Deterministic failure context: 選択error class内の最小agent ID。
- Submitted-request settlement: early failure、正順、逆順で全request
  settlementを確認。
- Counter treatment: phase abort時も全submitted requestのlocal telemetryを
  反映。error resultはfinal parse failureへ誤計上しない。
- KeyboardInterrupt/SystemExit:
  [parallel_transport.py](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/engine/parallel_transport.py:100)
  のwrapperはoriginal `BaseException`をresultへ保持し、
  [sim.py](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/engine/sim.py:308)で
  既存terminalizationへ戻す。既存lifecycle/CLI fixturesもPASS。

## Equivalence

- Tested concurrency values: `1`, `3`。worker-cap probeではlimit `8` /
  requests `2`も確認。
- QA fixture: 3 agents、2 steps、fixed seed/positions/sampling/scripted
  responses。
- Raw files compared byte-for-byte:
  - `phase1_raw.jsonl`:
    `177d661cd4b9b1d7e1383ed4b37030d09387fbe7b93bc351bd2b3ae96aa1d303`
  - `messages.jsonl`:
    `b133e7f98374685c00af8a984e4223ab6fa5ae369d2ba3a6021fe6b6c64264d6`
  - `memory_reasoning.jsonl`:
    `fb9d4138a7778b8eb99f51b71f7cfaf386bd20deb8a13174efce7b6c4cc85f6a`
  - `parse_errors.jsonl`:
    `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- State compared: position、memories、received messages、RNG state、parse count、
  total calls。
- Lifecycle compared: logical/HTTP/generation/transport/syntax/schema counters、
  completed steps、observed agents、raw manifest。
- Normal-scenario counters: logical `12`、HTTP `12`、completed steps `2`、
  observed agents `3`、failure counters `0`。
- Request transcript compared: step、phase、agent ID、request ID、exact prompt、
  prompt SHA-256、model、base URL、temperature、max tokens、timeout、override
  mapping。12/12 rows同一。
- Reverse completion result: scientific stateとcommit orderはcompletion order
  非依存。
- Agent-order result: scientific stateとraw evidenceは`self.agents` list order
  非依存。
- `run_meta.json`全体はrun ID、timestamps、concurrency、config hashが意図的に
  異なるためbyte比較から除外。
- Claim boundary: deterministic scripted transportに限定。実LLM本文の一致は
  主張しない。

## Protected paths

Gate 1 frozen tagからのdiffはすべて空でした。

- Prompt: unchanged
- LLM client: unchanged
- Provenance: unchanged
- Agent/world: unchanged
- `main.py`: unchanged
- Metric v2 spec/core/CLI/tests: unchanged
- Legacy metric `tools/vocab_metrics.py`: unchanged
- `output_mvp_demo`: unchanged
- Gate 1 QA report: management baselineからunchanged
- Prompt SHAおよびMetric v2 specification SHA: expected値と一致

## Spec/protocol consistency

主要対応表:

| Requirement | Specification | Implementation | Regression / independent check |
|---|---|---|---|
| Spec version | Spec `1 | Protocol `6 | Hash再計算 |
| Concurrency default | Spec `3 | `config.py:13-35` | Targeted + default probe |
| Config validation | Spec `3 | `config.py:28-33` | 7 invalid values |
| Effective provenance | Spec `4 | `sim.py:34-65` | disk `run_meta`確認 |
| Request contract | Spec `5 | `parallel_transport.py:17-36` | field/isolation probe |
| Result contract | Spec `6 | `parallel_transport.py:72-139` | direct result probe |
| Worker-local telemetry | Spec `7 | `parallel_transport.py:40-69` | Event-stop probe |
| Coordinator-only mutation | Spec `8 | `sim.py:234-283` | thread instrumentation |
| Phase 1 snapshot | Spec `10 | `sim.py:147-173` | snapshot transcript |
| All Phase 1 prompts before dispatch | Spec `10 | `sim.py:179-217,337-341` | first-worker count |
| Phase 1 commit barrier | Spec `10 | `sim.py:342-369` | blocked/terminal probes |
| Phase 2 delivery barrier | Spec `11 | `sim.py:370-408` | blocked-delivery probe |
| Phase 3 snapshot | Spec `12 | `sim.py:409-413` | post-delivery transcript |
| All Phase 3 prompts before dispatch | Spec `12 | `sim.py:409-413` | first-worker count |
| Phase 3 memory barrier | Spec `12 | `sim.py:414-457` | blocked-memory probe |
| Phase 4 movement barrier | Spec `13 | `sim.py:459-468` | blocked/reverse probes |
| Canonical ordering | Spec `9 | `sim.py:118-119`ほか | reverse/list-order probes |
| Parse failure | Spec `14 | `sim.py:261-263,358-367,419-453` | Phase 1/3 probes |
| Transport failure | Spec `15 | `sim.py:265-283,313-319` | atomicity probes |
| Unexpected worker failure | Spec `16 | `parallel_transport.py:119-130` | original-error probes |
| Error priority | Spec `16 | `sim.py:265-272` | mixed-error probe |
| Deterministic failure agent | Spec `16 | `sim.py:272` | multi-error probes |
| All submitted requests settle | Spec `17 | `parallel_transport.py:165-181` | early-failure probe |
| Concurrency 1/N equivalence | Spec `19 | `sim.py` phase path | independent 3×2 scenario |
| No thread leak | Spec `17 | executor context manager | four-class leak checks |
| Ollama reference path | Spec `18 | `sim.py:219-232` | post-init patch probe |
| vLLM deferred | Spec `18 | provider rejects non-Ollama | full suite/static review |
| Prompt unchanged | Spec ``2,20 | protected path | hash/diff |
| Raw schema unchanged | Spec `20 | existing JSONL fields | strict validators |
| Version bump rule | Spec `20 | Protocol `6 | static consistency review |

参照ファイル:

- [PHASE_PARALLELISM_SPEC.md](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/docs/PHASE_PARALLELISM_SPEC.md:5)
- [parallel_transport.py](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/engine/parallel_transport.py:17)
- [config.py](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/engine/config.py:16)
- [sim.py](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/engine/sim.py:333)
- [test_phase_parallelism.py](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/tests/test_phase_parallelism.py:214)
- [EXPERIMENT_PROTOCOL.md](C:/Users/swan0/repo/mcs-gate2-check-34c6b80/docs/EXPERIMENT_PROTOCOL.md:373)

Protocol確認:

- Gate 0 frozen record: maintained
- Gate 1 frozen record/tag/SHA: maintained and correct
- Gate 2 implementation commit: correct
- Gate 2 candidate evidence: test counts/resultsと整合。独立再実行時間は別環境計測値
- Phase parallelism spec path/hash: correct
- Gate 2 checker state: `PENDING`
- Gate 2 freeze state: `NOT DONE`
- Overall readiness: `NOT READY`
- Pilot authorization: `NO`
- Production registry: `NOT YET FROZEN`
- vLLM: deferred
- GPU/real-LLM performance claim: none
- Self-referential Gate 2 freeze SHA: none
- Gate 2全体を`PASS / FROZEN`とする記載: none

## Remaining unverified scope

- 実Ollama/実LLMでのconcurrency 1/N本文一致
- Ollama batch/order依存性
- vLLM transport/API contractとbackend smoke
- OllamaとvLLMの出力同値性
- GPU speedup・throughput・resource behavior
- backend変更時の意味論同値性
- Production candidate registry
- 実験条件、pilot seed、通信intervention、matrix runner
- Pilot/confirmatory run readinessとrun-start approval

## Operations

- Tracked files modified: no
- Repository内QA script作成: no
- Commit: no
- Push: no
- Tag: no
- GPU: no
- Real LLM: no
- Research run: no
- Package installation: no
- Network beyond optional initial git fetch: no。git fetchも未実施
- Independent fixtures: OS temporary directoriesのみ。終了時に削除
- Detached QA worktree: 指定pathにcleanな状態で残置

## Recommendation

`34c6b802958781b9a8d25420742e092a8a0bee3c`をGate 2 freeze candidateとして
採用できます。

checkerはtagを作成していません。Overall protocol readinessは引き続き
**NOT READY**、Pilot authorizationは**NO**です。
