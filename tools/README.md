# tools/ — run 可視化ツールの使い方

run 出力ディレクトリ（`output_*/`）から MP4 動画・単一ファイル HTML レポートを生成するツール群の説明。
raw run ディレクトリは immutable として扱い、生成物はすべて `derived/` 配下に書き出す。

## 対象スクリプト

| スクリプト | 生成物 | 依存 |
|---|---|---|
| `render_video.py` | ステップごとのフレーム画像 → MP4 動画 | matplotlib、ffmpeg（PATH 上） |
| `render_report.py` | 単一ファイルのインタラクティブ HTML（外部依存なし・オフライン閲覧可） | なし（標準ライブラリのみ） |
| `viz_common.py` | 上記 2 つが共有するローダ／集計（直接実行しない） | — |
| `render_world.py` | ステップ PNG ＋ GIF（legacy。run ディレクトリ直下に書き出すため immutable 運用の run には使わない） | matplotlib、Pillow |

## 入力（run ディレクトリに必要なファイル）

- `run_meta.json` — bloc 構成・`half_space_size`・places・失敗カウンタ
- `memory_reasoning.jsonl` — step × agent の position / action / direction / memory / reasoning
- `messages.jsonl` — step × sender の message / reasoning / receiver_ids
- `parse_errors.jsonl` — 行数をメタ行に表示（無ければ 0 扱い）

ログに書かれている値のみを描画する。ログに無い量（意図・協調度など）は一切推定しない。

## 使い方

```bash
python tools/render_video.py output_vllm-3model24x60-3gpu-json-20260823-r002
```

```bash
python tools/render_report.py output_vllm-3model24x60-3gpu-json-20260823-r002
```

オプション：

- 共通 `--out DIR` — 出力先を明示。省略時は
  `<run の親ディレクトリ>/derived/<run 名>/viz-v1.0.0-<YYYYmmdd-HHMMSS>/`。
  既存ディレクトリへの上書きは拒否される（`os.makedirs(exist_ok=False)`）。
- `render_video.py --fps N`（既定 2.0）— 1 秒あたりのステップ数
- `render_video.py --trail N`（既定 6）— 軌跡として残す直近ステップ数
- `render_video.py --keep-frames` — 中間フレーム PNG（`frames/`）を削除せず残す

## 図の読み方（動画・HTML 共通）

- 点の色 = bloc（凡例に `bloc名 (model名)`。色は `viz_common.PALETTE` の順で bloc に固定割当）
- ● 塗りつぶし = `action=move`、○ 白抜き = `action=stay`
- 点の外側リング = そのステップで `messages.jsonl` に送信記録あり
- 薄い線 = 直近 N ステップの軌跡
- 積み上げバー = ステップごとの「送信ありエージェント数」（動画では move 数のバーも表示）、黒線 = 現在ステップ
- メタ行 = `run_meta.json` の status / steps / agents / 各失敗カウンタ / seed / git_sha をそのまま転記

通信は radius・edge_policy 次第で全員ブロードキャストになり得るため、送信エッジは描かず「送信の有無」のみを表示している。

HTML レポートの操作：スライダー・▶ 再生・←→ キーでステップ移動、バーをクリックでそのステップへ、
地図上の点（または右のカード）をクリックでそのエージェントの message / message reasoning / memory /
action reasoning 本文を表示。下部に bloc 別サマリ表（agent-steps・送信あり・move・stay）。

## 出力の位置づけ

生成物は derived artifact（engineering visualization）であり、formal な行動証拠ではない。
`derived/<run 名>/` 配下の各ディレクトリに由来 run・生成日時・SHA-256 を記した README を置く運用
（例: `derived/output_vllm-3model24x60-3gpu-json-20260823-r002/visualization-v1.0.0-20260823-101513/README.md`）。
