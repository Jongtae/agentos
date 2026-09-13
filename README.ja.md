# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS は、一人の所有者が自分の環境にインストールして管理する、ローカルファーストのパーソナル AI オペレーティング環境です。**

個人用 PC と個人用 OS が一人の所有者に持続的なコンピューティング環境を提供するように、Personal AgentOS は会話、タスク、ツール、モデルの変更をまたいで続く個人 AI 環境を目指します。所有者が管理する Mac／ランタイム上で動作し、ポリシー、個人コンテキスト、ワークスペース、権限、承認、作業状態、証跡、復旧を AgentOS 側の境界で保持します。

Codex、Claude Code、外部モデル、ローカルモデル、ツール、専門 Agent は、AgentOS が利用する交換可能なワーカー／機能です。これらは個人状態の原本ではありません。実行エンジンを変更しても、所有者のコンテキスト記録、権限、承認履歴、復旧可能な作業、証跡を失わないことが重要です。

**Personal AgentOS はコーディングハーネスや Agent swarm フレームワークではありません。** コーディング自動化は一つのサービスになり得ますが、このリポジトリの GitHub/Codex 開発自動化は製品を作るための開発インフラです。また macOS/Linux を置き換えるカーネルやハイパーバイザーではなく、所有者が管理するホスト上の持続的な個人 AI 層です。

## 製品モデル

長期アーキテクチャは、持続する所有者状態と交換可能なワーカーを分離します。

- **Owner plane** — identity/policy、個人コンテキストと記憶の境界、資料／管理ワークスペース、権限、承認、作業状態、証跡、復旧。
- **Capability plane** — ツール、connector、assistant、専門機能、runtime/engine registry。
- **Worker plane** — 制限された Codex、Claude Code、モデルプロバイダ、ローカル runtime。
- **Experience plane** — 対応するローカル UI、Telegram、companion からの会話と作業。

英語の正本アーキテクチャは [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md) です。ここでいう **OS** はホスト OS の代替ではなく、一人の AI 状態と権限を持続的に所有する層を意味します。

## 現在の実装ベースライン

最初の利用可能な製品スライスは **ファイル／フォルダ型パーソナルワークスペース**です。[#314 プログラム](https://github.com/Jongtae/personal-agentos/issues/314) は完了しており、統合実装は [PR #320](https://github.com/Jongtae/personal-agentos/pull/320)、検証と終了記録は [PR #324](https://github.com/Jongtae/personal-agentos/pull/324) にマージされています。

参照フォルダは既定で読み取り専用、書き込みは所有者が許可した管理ワークスペース内に限定されます。原本、派生資料、下書き、最終記録を区別し、再構築可能な検索インデックスを永続的な作業・承認・証跡・復旧・認証状態から分離し、再起動後も保存した結果を再利用できます。

現在の完了証拠は deterministic model と一時ローカルフォルダによる自動検証です。これだけで外部モデル、Telegram、Google Drive/OAuth、定期 scheduler、個人フォルダの実運用が確認されたとは主張しません。任意の Drive 作業と公開サイトの公開は現在コア経路から延期されています。最新状態は [roadmap](docs/roadmap.md) を参照してください。

## 所有者の管理境界

- 接続するフォルダ、サービス、ツール、assistant、runtime は所有者が選択します。
- 外部 AI、messenger、他 Agent、受信者への送信はローカル保存とは別の policy/approval 境界です。
- 外部送信や破壊的なファイル／アカウント変更などの重要な操作には明示的な権限が必要です。
- ローカルファーストは「情報が一切端末外に出ない」という意味ではありません。外部機能を選択した場合、承認済みのコンテキストはその機能のポリシーに従って送信されることがあります。

## 開発用インストール

```sh
brew install jongtae/agentos/agentos
agentos start
```

Homebrew 経路は、一般ユーザー向けインストール体験を改善している間、開発者とセルフホスト利用者向けに維持されます。

## 開発ガバナンス

このリポジトリの issue、branch、PR、CI、Goal Execution Contract、implementer/reviewer handoff は **Personal AgentOS を構築するための開発インフラ**であり、エンドユーザーの AgentOS runtime や実運用済み自律動作の証拠ではありません。

実装前に [AGENTS.md](AGENTS.md)、[PRD.md](PRD.md)、[TASKS.md](TASKS.md)、[roadmap](docs/roadmap.md) を確認してください。
