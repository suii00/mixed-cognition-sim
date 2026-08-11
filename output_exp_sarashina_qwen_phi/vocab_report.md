# 語彙伝搬レポート

## ブロック: phi

| 順位 | 語彙 | 対数オッズ |
|------|------|------------|
| 1 | 境界 | 8.864 |
| 2 | 避ける | 8.405 |
| 3 | 向かう | 8.347 |
| 4 | 保つ | 8.040 |
| 5 | 危険 | 7.562 |
| 6 | 接触 | 7.529 |
| 7 | 警戒 | 5.921 |
| 8 | 近く | 5.517 |
| 9 | 指示 | 5.517 |
| 10 | 警告 | 4.138 |
| 11 | 注意深い | 4.138 |
| 12 | 観察 | 4.138 |
| 13 | 進む | 4.138 |
| 14 | 避難 | 4.138 |
| 15 | 近づく | 3.684 |
| 16 | 距離 | 1.488 |
| 17 | l_bar | 0.914 |
| 18 | 安全 | 0.590 |
| 19 | 求める | -0.477 |
| 20 | r_bar | -0.534 |

## ブロック: qwen

| 順位 | 語彙 | 対数オッズ |
|------|------|------------|
| 1 | 取る | 9.517 |
| 2 | メモ | 9.517 |
| 3 | 比較 | 9.517 |
| 4 | 状態 | 9.517 |
| 5 | 送信 | 3.810 |
| 6 | 情報 | 2.027 |
| 7 | 距離 | 0.923 |
| 8 | r_bar | 0.516 |
| 9 | l_bar | 0.046 |
| 10 | 確認 | -0.400 |
| 11 | 関連 | -0.805 |
| 12 | いただける | -0.805 |
| 13 | お願い | -0.805 |
| 14 | 助かる | -0.805 |
| 15 | エリア | -0.805 |
| 16 | 注目 | -0.805 |
| 17 | 密接 | -0.805 |
| 18 | 重点的 | -0.805 |
| 19 | 有無 | -0.805 |
| 20 | 達する | -0.805 |

## ブロック: sarashina

| 順位 | 語彙 | 対数オッズ |
|------|------|------------|
| 1 | 範囲 | 9.199 |
| 2 | 近傍 | 8.469 |
| 3 | 更新 | 8.432 |
| 4 | 右端 | 8.169 |
| 5 | 到達 | 7.946 |
| 6 | 調査 | 7.813 |
| 7 | 検討 | 7.739 |
| 8 | 継続 | 7.572 |
| 9 | 経路 | 7.572 |
| 10 | 詳細 | 7.477 |
| 11 | 探索 | 7.477 |
| 12 | 隣接 | 7.371 |
| 13 | 詳しい | 7.254 |
| 14 | 続ける | 7.120 |
| 15 | 維持 | 7.120 |
| 16 | 共有 | 6.785 |
| 17 | 確保 | 6.562 |
| 18 | 障害 | 6.275 |
| 19 | 目標 | 6.275 |
| 20 | 地点 | 6.275 |

## 越境イベント

| 発信元ブロック | 語彙 | 伝搬先ブロック | 初出ステップ | 使用回数 |
|----------------|------|----------------|--------------|----------|
| qwen | 確認 | sarashina | 1 | 106 |
| qwen | 送信 | sarashina | 1 | 3 |
| qwen | l_bar | sarashina | 1 | 122 |
| qwen | 情報 | sarashina | 1 | 38 |
| qwen | r_bar | sarashina | 1 | 134 |
| phi | r_bar | sarashina | 1 | 134 |
| phi | 近づく | sarashina | 1 | 31 |
| phi | l_bar | sarashina | 1 | 122 |
| phi | r_bar | qwen | 1 | 54 |
| phi | 近づく | qwen | 1 | 46 |
| phi | l_bar | qwen | 1 | 142 |
| phi | 避ける | sarashina | 1 | 13 |
| phi | 指示 | sarashina | 1 | 10 |
| sarashina | 探索 | qwen | 1 | 16 |
| sarashina | 到達 | phi | 1 | 12 |
| sarashina | 範囲 | phi | 1 | 46 |
| sarashina | 目標 | phi | 1 | 6 |
| sarashina | 近傍 | qwen | 2 | 2 |
| sarashina | 範囲 | qwen | 2 | 77 |
| sarashina | 共有 | qwen | 2 | 1 |
| sarashina | 詳細 | qwen | 2 | 7 |
| qwen | 状態 | sarashina | 2 | 9 |
| phi | 避ける | qwen | 2 | 7 |
| sarashina | 確保 | phi | 2 | 7 |
| phi | 距離 | qwen | 3 | 53 |
| qwen | 距離 | sarashina | 3 | 25 |
| phi | 距離 | sarashina | 3 | 25 |
| phi | 進む | sarashina | 3 | 2 |
| sarashina | 到達 | qwen | 3 | 6 |
| sarashina | 共有 | phi | 3 | 4 |
| sarashina | 更新 | phi | 3 | 2 |
| sarashina | 維持 | phi | 3 | 23 |
| sarashina | 地点 | phi | 3 | 1 |
| phi | 境界 | qwen | 4 | 49 |
| phi | 保つ | qwen | 4 | 43 |
| qwen | 距離 | phi | 4 | 79 |
| qwen | l_bar | phi | 4 | 156 |
| phi | 指示 | qwen | 4 | 4 |
| phi | 向かう | qwen | 4 | 4 |
| qwen | エリア | phi | 4 | 2 |
| phi | 安全 | sarashina | 6 | 71 |
| phi | 保つ | sarashina | 6 | 19 |
| phi | 近く | sarashina | 6 | 6 |
| phi | 安全 | qwen | 6 | 23 |
| phi | 近く | qwen | 6 | 8 |
| sarashina | 維持 | qwen | 6 | 3 |
| sarashina | 経路 | qwen | 6 | 21 |
| phi | 進む | qwen | 6 | 16 |
| qwen | 情報 | phi | 6 | 7 |
| sarashina | 続ける | qwen | 7 | 4 |
| phi | 警戒 | sarashina | 8 | 5 |
| phi | 境界 | sarashina | 8 | 25 |
| qwen | 確認 | phi | 9 | 4 |
| sarashina | 探索 | phi | 9 | 1 |
| phi | 警戒 | qwen | 10 | 12 |
| sarashina | 地点 | qwen | 10 | 2 |
| phi | 警告 | sarashina | 11 | 8 |
| phi | 危険 | sarashina | 11 | 3 |
| phi | 警告 | qwen | 11 | 9 |
| phi | 危険 | qwen | 11 | 1 |
| qwen | 重点的 | sarashina | 11 | 1 |
| qwen | メモ | phi | 11 | 4 |
| qwen | 達する | sarashina | 12 | 18 |
| phi | 注意深い | sarashina | 14 | 1 |
| phi | 観察 | sarashina | 14 | 1 |
| phi | 注意深い | qwen | 14 | 1 |
| phi | 観察 | qwen | 14 | 2 |
| qwen | 状態 | phi | 18 | 4 |
| qwen | 注目 | sarashina | 21 | 1 |
| sarashina | 障害 | phi | 21 | 1 |
| qwen | r_bar | phi | 23 | 85 |
| qwen | 助かる | sarashina | 24 | 2 |
| qwen | いただける | sarashina | 24 | 2 |
| sarashina | 確保 | qwen | 25 | 1 |
| sarashina | 続ける | phi | 25 | 1 |
| qwen | 関連 | sarashina | 26 | 2 |
| qwen | 密接 | sarashina | 26 | 2 |
| qwen | エリア | sarashina | 26 | 3 |
| qwen | 取る | phi | 26 | 1 |
| qwen | 有無 | sarashina | 29 | 3 |
| phi | 求める | sarashina | 29 | 5 |
| qwen | お願い | sarashina | 30 | 2 |

