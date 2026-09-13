<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 移行進捗レポート — 2026-09-13 03:25 UTC

原計画の11区分では、受入済み2区分（PR01・PR03）、進行中1区分（PR02）、実装待ち8区分（PR04–11）です。PR02を分割した02a・02bを含め、4本のDraft PRの必須CI成功を再確認しました。すべて未マージです。設計文書の完成は、実装・受入の完了には数えていません。工程ごとの規模が異なるため、2/11を工数の進捗率には換算していません。

| 原計画 | 内容 | 現状 | 完了までの残タスク |
| --- | --- | --- | --- |
| 01 | 課題・採点入力の内容固定 | 受入済み。PR #38、必須CI成功 | 後続統合後の最終回帰検証 |
| 02 | 評価成果物の共通形式・受け渡し | 02a・02bは受入済み（#39・#40）。02cは実装・部分検証中 | 実Cursorアダプター＋偽CLIの共通経路テスト、Cursor fixture統合、全体テスト・96%以上・型・Ruff・CI、独立レビューとDraft PR公開 |
| 03 | Executor回答出力の統一 | 受入済み。PR #41、必須CI成功 | 後続スキーマ変更との整合と最終回帰検証 |
| 04 | graderの隔離 | 設計・依存関係・実装契約を保存。実装未着手 | 共通sandbox・worker・呼び出し元置換、実Linux境界検証、ネイティブ採点の一致、NLTKのCVE解消、全ゲート |
| 05 | Evaluatorの独立選択 | API・実装契約を保存。実装未着手 | registry、候補数1/2/Nの計画、独立評価CLI、匿名judge入力、生成・評価の再開と保存、全ゲート |
| 06 | GDPval rubric・pairwiseの共通基盤統合 | 意味論・比較fixture・実装契約を保存。実装未着手 | rubric/pairwise/panel実装、共通保存・再開接続、無効判定と障害の区別、旧採点との一致、全ゲート |
| 07 | Stirrup生成処理の分離 | 実行・通信・隔離・依存関係の契約を保存。実装未着手 | StirrupExecutor、共通HTTP、出力回収、実Apptainer検証、bundle v2の一括移行、全ゲート |
| 08 | AA-v2プロファイル・集計・再開 | プロトコル・数値fixture・再開契約を保存。実装未着手 | 45＋175の生成計画、アンカー選択・Elo、共通評価接続、途中再開と決定論的数値検証、全ゲート |
| 09 | Skillなし／skill-creator／＋ALPSの統合 | 入力・実行順序・隔離・再開契約を保存。実装未着手 | 共通snapshot・生成・評価へのN/S/A統合、Builder成果物受け渡し、欠損群の分母固定、全ゲート |
| 10 | 旧経路の廃止・文書更新 | 削除対象と移植すべき挙動の一覧を保存。削除未実施 | ./gdpval、旧runner/server/設定の削除、残るダウンロード処理の移植、CLI・テスト・文書更新、参照残存検査 |
| 11 | 全体受入・拡張性 | 第4ベンチマークと最終受入の契約を保存。実装未着手 | 共通コア無変更で第4fixtureを追加し生成・Builder・再評価・再開を通す。最終headで全必須ゲートと旧経路削除を確認 |

## 現在の検証証拠

| 対象 | 保存済みの結果 | 証拠の範囲 |
| --- | --- | --- |
| 公開済み4 Draft PR | 必須workflowすべて成功、headと未マージを再確認 | #38–41の記録されたhead |
| PR03全体 | 515 harnessテスト、6 shell統合、追加45＋5テスト。9,854/10,210 statements＝96.5132% | PR03 head d5ce0c10162cad788a17cb90f34b8f60574e7f75。最終移行headの値ではない |
| PR02c handoff | 13テスト、厳格型検査・Ruff成功 | 549339ab6f36a788a5eb7fa83851af9d7546fcf6。独立レビューの2件のテスト補強を実装中 |
| PR02c Builder等 | 関連48テスト成功。型の2件を修正後、該当テスト・5ファイルの厳格型検査・Ruff成功。独立レビュー指摘なし | 3a077a4 → 77f33247。主経路b2a4ea43へ統合済み |
| PR02c CLI | 14テスト、旧Cursor拒否shell、厳格型検査・Ruff成功 | e8571865decaa26fd101b90fa4aa3eb5091b0e32 |
| PR02c Cursor fixture | 43テスト、厳格型検査・Ruff成功。独立レビュー指摘なし | 9bcdee9ab8c5b8732bcb2a044ae998303154d0f5。主経路への統合待ち |
| 主環境の依存関係 | 153依存、脆弱性0件、skip 0件 | PR02cの変更されていない主環境lockのみ。PR04 grader環境は別 |
| 移行全体の最終head | 未検証 | 最終カバレッジ96%以上、全体型・Ruff・CVE・秘密情報・著作権・DCO検査は残作業 |

## 完了を妨げている事項と実行順

PR04の候補grader lockはNLTK 3.10.3のPYSEC-2026-3740 / GHSA-8mgp-746c-j5xp / CVE-2026-81726を1件報告しています。保存済みの代替パッチは独立レビューで不採用です。現状ではPR04のCVEゲートは通過できていません。検査除外や完了扱いにはしません。

作業順は、PR02cの統合と全体受入 → PR04隔離・依存問題 → PR05–09共通経路 → PR10旧経路削除 → PR11最終head受入です。互換ラッパーを残す案へ変更していません。実モデル実験は移行完了後の別段階であり、今回の完了判定には混ぜません。

前環境で未公開実装が失われた手戻りがあり、現在はその再構築中です。Astraが保存・統合・受入、Solが設計と独立レビュー、Lunaが範囲を固定した実装・テストを担当します。各バッチはテスト前にGitHubへ保存し、ref・commit・ファイル内容を読み戻して確認します。保存済み、部分検証済み、受入済みを別々に記録しています。

## 参照

- [原計画](https://github.com/mashimashica/eval-harness/blob/8518f25d107d9043df449a9198fbb41b00ba1c22/eval-harness-neutrality-migration-plan-2026-09-12.md)
- [状態記録](https://github.com/mashimashica/eval-harness/blob/65ba5260cc56973dee0251411401044e799e253a/MIGRATION-STATE.md)
- [PR01](https://github.com/mashimashica/eval-harness/pull/38)
- [PR02a](https://github.com/mashimashica/eval-harness/pull/39)
- [PR02b](https://github.com/mashimashica/eval-harness/pull/40)
- [PR03](https://github.com/mashimashica/eval-harness/pull/41)
- [PR03 CI](https://github.com/mashimashica/eval-harness/actions/runs/34716101531)
