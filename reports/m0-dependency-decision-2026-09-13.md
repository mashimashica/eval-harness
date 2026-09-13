<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# M0 開始前判断 — 2026-09-13

判定：未解決。合意したM0の停止条件を適用し、M1以降の実装を開始せず停止した。移行完了やPR04受入は主張しない。

| 項目 | 結果 |
| --- | --- |
| 実施した到達点 | 保存head照合、現行の正式リリース確認、既存grader候補lockへの標準CVE検査1回、Solの独立したメタデータ確認 |
| 品質証拠 | pip-audit 2.10.1：160依存、既知の脆弱性1件、skip 0件、exit 1。NLTK 3.10.3にPYSEC-2026-3740 / CVE-2026-81726 / GHSA-8mgp-746c-j5xp。fix_versionsは空 |
| 未解決事項 | 公式PyPIとNLTK Releasesの最新版は3.10.3。公式advisoryは影響範囲を3.10.3以下、修正版なしと記載。現行基準を満たす正式リリースによる解決経路を確認できなかった |
| 作業量 | 調査03:40:37–03:42:55 UTC、約2分18秒。上限30分以内・1調査ラウンド。親の調査ツール呼び出し11回、Solの独立確認1回。保存・報告の操作は別。課金トークンの実測値は取得していない |
| 次の工程 | 現行M0停止条件のまま待機。継続する場合は、以下の範囲変更を先に判断する |

## 検証の対象と限界

対象lock：contracts/pr04-evidence/bigcodebench-v0.2.5-candidate-py311.lock

SHA-256：8d62cac6880124652638ff8716532d46d459aaf5cbe6e8c36b506a4d1e4de9bd

監査結果JSON：reports/m0-evidence/grader-pip-audit.json

SHA-256：3d18536f4070cd1eb90179203e84bf1d147c755bf44d577fddeb8de41532310a

実行コマンド：

```bash
uvx --from pip-audit==2.10.1 pip-audit --require-hashes --disable-pip --strict --aliases --format json --requirement contracts/pr04-evidence/bigcodebench-v0.2.5-candidate-py311.lock --output m0-grader-pip-audit.json
```

Solは公式PyPI・NLTK Releases・advisoryのメタデータを独立して確認した。正式な修正版の公開を確認できなかった。ルート側の標準監査も保存済みの問題を再検出した。この調査は、考え得るすべての依存構成や新規実装の不可能性を証明するものではない。現時点で受入可能な具体策が確立していないという判定である。

実装変更、依存パッケージの差し替え、不採用パッチや再現コードの実行、検査除外、CVEゲート変更は行っていない。実モデル呼び出し・merge・releaseも行っていない。

## 選択肢

| 案 | 作業範囲 | 費用と完了への影響 |
| --- | --- | --- |
| A：停止を維持 | 修正版または受入可能な対処の新しい証拠が得られるまで、実装・追加調査を行わない | 追加消費を抑える。移行全体は未完了のまま |
| B：PR02cだけを完了させる（推奨） | M0での全体停止をこの範囲に限って変更し、PR04受入を保留したまま、既に実装が進んでいるPR02cを実作業90分以内で仕上げる | 保存・レビュー済みの成果を一つの受入済みPRにまとめられる。PR04以降と全体完了は未確定 |

BでもPR02c自身の必須品質ゲートをすべて満たす。PR04のCVE問題を解消済みとは扱わず、90分上限または反復停止条件で報告する。新しい依存構成や自前修正版の追加開発は、この選択肢に含めない。

実装保存head：2aa8c28b3f074f5e8887fcdccf883123b85199a1。変更していない。コードとテストの現在の未完了状態はこのheadの作業記録から復元できる。

## 一次資料

- [NLTK公式advisory](https://github.com/nltk/nltk/security/advisories/GHSA-8mgp-746c-j5xp)
- [NLTKのPyPI掲載](https://pypi.org/project/nltk/)
- [NLTK公式リリース](https://github.com/nltk/nltk/releases)
- [v3.10.3](https://github.com/nltk/nltk/releases/tag/v3.10.3)
- [承認された実行・報告計画](https://github.com/mashimashica/eval-harness/blob/a45e0108f4cc049a82478978c2525f14a926ba90/reports/migration-completion-plan-proposal.md)

