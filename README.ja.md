# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**自分でインストールし、所有し、管理する、実際に役立つ仕事のためのパーソナル AI 環境。**

Personal AgentOS は、一人の所有者が管理するホスト上で動作するローカルファーストの AI オペレーティング環境です。目標を伝え、選んだモデルと許可した資料で仕事を進め、有用な結果を残します。将来は Agent をアプリのようにインストール・交換しても、個人の Memory、権限、Work、Artifact と Evidence が所有者のもとに残ることを目指します。

> **Personal AgentOS = Personal AI Kernel + Open Agent Distribution Platform**

制御できるだけで役に立たない製品も、実行の根拠を確認できない製品も目標ではありません。初期の同梱 Agent は少数で構いませんが、基本機能の品質を意図的に低くしてよいという意味ではありません。

## 現在と計画を区別する

| 状態 | 範囲 |
| --- | --- |
| 既存コード | ローカルブラウザ設定・会話、モデル接続、制限されたツール、メモ、承認済みフォルダ、管理ワークスペースの結果。対応経路は [QUICKSTART](QUICKSTART.md) を参照。 |
| ファイル作業の開発完了 | #314、PR #320/#324。原本保持、限定アクセス、結果保存と再起動後の再利用を自動・一時ファイルで検証。 |
| v0.1 契約完了 | #334、PR #350。Core Primitive/AgentPackage のスキーマと静的・意味的検証。パッケージ実行の実装ではありません。 |
| DOGFOOD-01 開発完了 | #351、PR #354–#356。模擬モデルによる HTTP/ファイル/再起動テストと操作案内。実モデル・実ブラウザの利用観察は別記録。 |
| 計画中 | #358 基本機能の品質、#359 実行記録・制御 UI、#360 インストールから削除・再利用までの体験、および #333 の未完了項目。 |

任意の第三者コード実行、公開 Registry/Marketplace、万能な互換性、自動購入は提供済みとは主張しません。既存の宣言型プラグインは将来の実行型 AgentPackage と別です。過去の実測結果は当時のタスク、モデル、バージョンの範囲に限定します。

## 最初に役立つ三つの仕事

**調査から判断へ。** 公開資料で選択肢を比較し、出典・時刻・価格条件・不明点を分けた判断材料を作ります。現在の検索結果は抜粋であり、ページ全文、在庫、決済総額の確認とは異なります。

**自分の資料から成果物へ。** 許可した文書を読み、重要事項と次の行動をまとめ、通常のファイルとして保存します。ファイルの存在だけでなく内容の品質も評価し、原本は変更しません。

**続きの依頼と再起動後の再利用。** 条件の訂正を反映し、前の成果物を再利用します。すべての会話を黙って永続 Memory にすることはしません。

[品質計画](docs/default-agent-usefulness.en.md) の24件の合成評価ケースは評価仕様であって、実行済みモデル評価ではありません。実際の経路で成功率、根拠、待ち時間、費用、所有者の手間を測定します。

## 所有者が行使する六つの権利

[Owner Control Contract](docs/owner-control-contract.en.md) は、実装・検証すべき権利を定義します。

1. パッケージの出典、作成者、バージョン、実行場所、要求権限を確認する。
2. Agent が使える資料、Memory、アカウントを選ぶ。
3. どの情報をどのサービスへ送るか知る。
4. インストール・接続と個々の行動の権限を分ける。
5. 作業を止め、権限を取り消し、進行中の外部処理の不確実性も確認する。
6. Agent を削除・交換しても自分の成果物と承認済み Memory を保持する。

モデルへの指示だけでなく、実行境界がアクセスを拒否できる必要があります。進捗は実際の Work/ツールイベントから作成し、詳細には必要なマスク済み入力、送信先、承認と結果を表示します。隠れた推論、システムプロンプト、秘密情報の公開は必要ありません。

ローカルインストールとローカル処理は別です。外部モデルには許可済み Context が送られます。リモート Agent のコネクタを入れても、そのサーバーを所有することにはなりません。切断、権限取消、Agent 削除、保存情報の消去を区別し、すでに送信された情報や完了した外部操作を停止ボタンで取り消せるとは約束しません。

## アーキテクチャと Agent アプリ

Kernel は Agent-independent、体験は Agent-centric です。

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

その上に `AgentPackage · Package Manager · Registry · Marketplace/Discovery · Trust/Verification` を置きます。Codex、Claude Code、モデル、MCP、任意の Ruflo などは交換可能な worker であり、所有者の状態の権威にはなりません。

`downloaded != installed != enabled != connected != authorized-for-action`

インストールは無効状態が既定で Grant を作りません。権限・送信先・Memory・背景動作の拡張には再承認が必要です。第三者の永続 Memory 変更は基本的に MemoryCandidate として提出します。削除は Agent の権限を取り消しますが、所有者の結果は保持します。

Registry は正確な identity/version/digest/互換性/失効を、Marketplace は検索・ランキング・レビューと将来の流通を扱います。人気や署名は行動の安全性を保証しません。個人 Context は Marketplace の検索データではありません。

最初は有用な Files 参照パッケージと公開 SDK 経路を実証します。同梱 Agent と第三者 Agent は同じ契約を使い、隠れた特権を持ちません。MCP/skill/plugin の互換性は形式・ライセンス・権限を実際に対応付けられる場合のみ追加します。公開ストアや Ruflo は最初の体験の必須条件ではありません。

## 現在のプレビューを試す

```sh
brew install jongtae/agentos/agentos
agentos start
```

Homebrew は開発者・セルフホスト用で最新 main と異なる場合があります。[QUICKSTART](QUICKSTART.md) の専用テストフォルダ手順を使用してください。記載されたファイルワークスペースのテストには直接のモデル接続を使います。計画中の機能を実装済みのコマンドとして扱わないでください。

対応する永続状態は `scripts/agentos-backup.py DATA ARCHIVE` と `scripts/agentos-restore.py ARCHIVE EMPTY_DATA` で移動できます。接続秘密、セッション、フォルダ Grant、モデル選択、Telegram pairing は移行用アーカイブに含めず、新しい環境で再承認します。全データディレクトリのバックアップとは異なります。

## 開発

[アーキテクチャ](docs/personal-agentos-architecture.en.md)、[PRD](PRD.md)、[AGENTS.md](AGENTS.md)、[Development Constitution](docs/development-constitution.en.md)、[Goal Execution Contract](docs/goal-execution-contract.en.md)、[ロードマップ](docs/roadmap.md) に従います。

これはコーディングハーネスや macOS/Linux の代替ではありません。GitHub/Codex 自動化は開発インフラです。#357 は文書・評価仕様・計画の整合であり、#358–#360 や未完了のプラットフォーム項目は別途明示的に有効化されるまで実行しません。完了には、有用な結果と適切な拒否・復旧の両方の根拠が必要です。
