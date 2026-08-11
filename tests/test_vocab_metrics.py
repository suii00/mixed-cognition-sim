import tempfile
import unittest
from pathlib import Path

from tools import vocab_metrics


@unittest.skipIf(
    vocab_metrics.JanomeTokenizer is None,
    "Janome is required for Japanese tokenization tests",
)
class JapaneseTokenizationTests(unittest.TestCase):
    def test_tokenize_mixed_japanese_and_english_text(self):
        tokens = vocab_metrics.tokenize(
            "エージェントはL_barの境界に近づいているが、"
            "安全な距離を保つため右へ移動する。Danger is nearby."
        )

        self.assertIn("l_bar", tokens)
        self.assertIn("境界", tokens)
        self.assertIn("近づく", tokens)
        self.assertIn("安全", tokens)
        self.assertIn("距離", tokens)
        self.assertIn("保つ", tokens)
        self.assertIn("danger", tokens)
        self.assertNotIn("エージェント", tokens)
        self.assertNotIn("移動", tokens)
        self.assertNotIn("右", tokens)
        self.assertNotIn("する", tokens)

    def test_tokenize_removes_common_japanese_adverbs(self):
        tokens = vocab_metrics.tokenize(
            "さらに境界を調査し、まだ安全な経路を確認する。"
        )

        self.assertEqual(["境界", "調査", "安全", "経路", "確認"], tokens)

    def test_report_uses_japanese_labels(self):
        distinctive = {"alpha": [("安全", 1.25)]}
        events = [{
            "source_bloc": "alpha",
            "word": "安全",
            "target_bloc": "beta",
            "first_step": 2,
            "total_uses": 3,
        }]

        with tempfile.TemporaryDirectory() as temp_dir:
            vocab_metrics.write_report(temp_dir, distinctive, events)
            report = Path(temp_dir, "vocab_report.md").read_text(
                encoding="utf-8"
            )

        self.assertIn("# 語彙伝搬レポート", report)
        self.assertIn("## ブロック: alpha", report)
        self.assertIn("## 越境イベント", report)
        self.assertIn("| alpha | 安全 | beta | 2 | 3 |", report)


if __name__ == "__main__":
    unittest.main()
