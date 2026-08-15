# Gate 1 Independent QA — 2026-08-16

## 判定

**PASS — Gate 1 independent QA checker**

監査対象コードの追加修正は不要です。

Freeze candidate SHA:

`932f53112189c8e1b6125974bf7ad03ab37e5d4c`

- Overall protocol readiness: `NOT READY`
- Pilot authorization: `NO`
- freeze tagは作成していません。

## 監査対象

- Remote branch SHA: `932f53112189c8e1b6125974bf7ad03ab37e5d4c`
- Local HEAD: remoteと一致
- Gate 0 peeled SHA: `86fad23bc1cddf624550c044348566dc5c212bc7`
- 修正実装commit: `76be8729a5d3c805bfddaba7a590b80047c6e1b1`
- `76be872...` から監査SHAまで実装・テスト・Metric仕様の差分なし
- 初期／最終worktree: clean

## 再計算したhash

- `engine/prompts.py`: `f414ab30a963636d80239644c2d3770672c77d5b8bdde027de2eb15a0d08bc3d`
- `docs/METRIC_V2_SPEC.md`: `226582354cd777663f5dda0944c66630ba2d7ee30a4cd9bf1ba3b847e895108d`
- `tools/vocab_metrics.py`: `ef48fafed83bde7df5ecfb8ddb2016146df33af90c4af69516e9f76238de544b`
- テスト用registry: `42b7bac1b4038f21e4fccf90ef5bc25b8fdeba6f5e237f5658e2dc3d8393e913`

すべてprotocol記載値と一致しました。

## 回帰テスト

- Full suite: **117/117 PASS**
  - unittest: 7.423秒
  - wall: 7.986秒
- Metric v2 targeted suite: **39/39 PASS**
  - unittest: 4.952秒
  - wall: 5.133秒
- `python -m compileall -q engine tests tools main.py`: PASS
- `git diff --check`: PASS
- Gate 0以降の `engine`、`tools/vocab_metrics.py`、`output_mvp_demo` 差分: なし

## 前回findingの再検証

前回の「中断後に、`completed` と記載された部分的final leafが残り、再試行できない」問題は解消されています。

[publication実装](../../tools/metric_v2_core.py#L1181)、[更新仕様](../METRIC_V2_SPEC.md#L229)、[中断テスト](../../tests/test_metric_v2.py#L850)を確認しました。

独立フィクスチャでは次の6地点すべてに失敗を注入しました。

- `analysis_meta.json` 書込み後
- `events.jsonl` 書込み後
- receiver status書込み後
- `summary.json` 書込み後
- manifest書込み途中
- manifest検証後、publish直前

全地点で以下を確認しました。

- final leafは存在しない
- raw runはbyte-identical
- 残留stagingは公開結果として扱われない
- 再試行は成功
- 再試行後は5ファイルすべて存在
- manifestのhash、bytes、linesが一致

さらに、publish所有プロセスを強制終了した場合も、OS lockが解放され、final leaf不在のまま再試行に成功しました。publish中の別試行は明確にcollisionとなりました。

## その他の独立チェック

- delivery-only: `eligible_no_reuse`
- same-step use: 除外
- prior use: 除外
- multiple exposure: 2 exposure、1 reuse、latency 3
- valid second hop: `0 → 1 → 2`
- exact normalization: case、全角、空白、句読点を確認
- partial word／逆順: non-match
- raw provenance: exact physical line hashとmessage hashが一致
- registry/spec hash mismatch: final leaf作成前に拒否
- zero denominator: JSON `null`
- 異なるderived root: final 5ファイルがbyte-identical
- staging内容改変: manifest検証で拒否され、再試行成功
- 既存final result: collision、既存bytes不変

CLIのOS process終了コードも確認しました。

- `0`: success
- `1`: injected write failure
- `2`: invalid input/spec
- `3`: collision

終了コード`1`の書込み失敗後はfinal leafが存在せず、通常CLIによる再試行が`0`で完了しました。

## Findings

Critical、High、Medium、Lowの新規findingはありません。

前回のMedium findingは修正済みです。

## Protocol

[EXPERIMENT_PROTOCOL.md](../EXPERIMENT_PROTOCOL.md#L165)は、この再監査前の状態として以下を正しく保持しています。

- 旧候補 `b7dcf1b...` のFAIL記録
- corrected candidateは未凍結
- independent recheck pending
- production registryは `NOT YET FROZEN`
- readinessは `NOT READY`
- pilot authorizationは `NO`

このPASS結果をfreeze記録へ反映する管理上の更新は必要ですが、Metric実装の追加修正は不要です。

## Operations

- tracked files modified: no
- commit: no
- push: no
- tag: no
- GPU: no
- real LLM: no
- research run: no
- package installation: no
- 一時worktree／QA script: 削除済み

## 推奨

`932f53112189c8e1b6125974bf7ad03ab37e5d4c` をGate 1 freeze candidateとして採用できます。

ただし、overall readinessは引き続き `NOT READY`、pilotは未承認です。
