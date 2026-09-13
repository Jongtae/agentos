# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS は、一人の所有者が自分の環境にインストールして管理する、ローカルファーストのパーソナル AI オペレーティング環境です。**

長期的な製品方針は次のとおりです。

> **Personal AgentOS = Personal AI Kernel + Agent Distribution Platform**

個人用 PC と個人用 OS が一人の所有者に持続的なコンピューティング環境を提供するように、Personal AgentOS は会話、タスク、ツール、Agent、モデルの変更をまたいで続く個人 AI 環境を目指します。所有者が管理するホスト／ランタイム上で動作し、ポリシー、個人 Context/Memory、ワークスペース、Grant、承認、Work/Event、Artifact、Evidence、復旧を AgentOS 側の境界で保持します。

Kernel は意図的に **Agent-independent** です。Codex、Claude Code、外部／ローカルモデル、MCP server、専門 Agent、Ruflo のような multi-agent runtime は交換可能な worker/capability です。これらは canonical Memory、Grant、Work state、Evidence の所有者にはなりません。

一方、ユーザー体験は **Agent-centric** にできます。良い第三者 Agent をアプリのように発見、確認、インストール、権限付与、実行、更新、ロールバック、無効化、削除できることを目指します。Agent を交換しても、所有者の Personal AI environment は維持されるべきです。

**Personal AgentOS はコーディングハーネスや Agent swarm フレームワークではありません。** コーディング自動化や multi-agent orchestration は AgentOS 上の service/runtime になり得ます。このリポジトリの GitHub/Codex 開発自動化は製品を作るための開発インフラです。また macOS/Linux を置き換えるカーネルやハイパーバイザーではなく、所有者が管理するホスト上の持続的な個人 AI 層です。

## 製品モデル

- **Owner plane** — identity/policy、Context/Memory、owner data/workspace、Grant/approval、Work/Event、Artifact、Evidence、recovery。
- **Capability plane** — tools/connectors、capability registry、runtime/engine boundary。
- **Distribution plane** — AgentPackage、Package Manager、Registry、trust metadata、Marketplace/discovery boundary。
- **Worker plane** — bounded Codex、Claude Code、model provider、local runtime、Ruflo など。
- **Experience plane** — local UI、Telegram/companion、将来の Agent inspect/install/permission UI。

英語の正本アーキテクチャは [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md) です。Distribution Platform の段階計画は [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md) と [#333](https://github.com/Jongtae/personal-agentos/issues/333) を参照してください。

### Kernel primitives

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

Distribution plane はその上に次を追加します。

`AgentPackage · Package Manager · Registry · Marketplace/Discovery · Trust/Verification`

## AgentPackage と権限

AgentPackage はインストール可能な Agent/application unit です。Package manifest は package/publisher/version、AgentOS API compatibility、capability/action、runtime requirements、filesystem/data scope、network destinations、secret references、Memory policy、Event/background behavior、budgets、approval requirements、Artifact、dependencies、sandbox、health check、update/rollback/remove、provenance/signature/SBOM などを宣言する方向です。

インストールと権限は別です。

`discover → inspect → verify → installed-disabled → grant/connect/enable → run → update/rollback → disable → uninstall`

**downloaded、installed、enabled、connected、authorized-for-action は別の状態です。** Package install は Grant を自動作成しません。更新によって permissions、data scope、external destinations、Memory/background behavior が拡大する場合、新しい owner/policy review が必要です。

第三者 Package は canonical owner Memory を直接変更せず、デフォルトでは出典付きの MemoryCandidate を提案します。

## Registry と Marketplace

**Registry** は package/publisher identity、exact version/digest、compatibility、signature/provenance、trust metadata、advisory/revocation/quarantine を扱います。

**Marketplace/Discovery** は search、recommendation、ranking、review、curation、将来の commerce を扱えます。ただし人気や rating は execution authority ではなく、quarantine/signature/AgentOS policy を上書きできません。

Private owner Context/Memory/Work は Registry/Marketplace の状態にしません。Capability discovery は可能な限り structured/minimised metadata を使い、raw private prompt を store search にそのまま送ることを基本にしません。

## 初期エコシステム

初期 Personal AgentOS に最高品質の Agent がすべて同梱される必要はありません。General Assistant、Files、Research、Coding など少数の reference Agent で開始できます。目的は最高のアプリを自前で揃えることではなく、OS と公開 Package/Runtime/Grant contract を bootstrap することです。

Reference Agent も third-party Package と同じ public contract を使用し、隠れた first-party privilege を持ちません。

空の Marketplace 問題を減らすため、official format と license が許す範囲で MCP や選択された OpenAI/Codex・Claude skill/plugin ecosystem を AgentPackage として wrap/import する方針です。Ruflo は kernel ではなく将来の bounded delegated Runtime Adapter 候補です。

## 現在の実装ベースライン

最初の利用可能な製品スライスは **ファイル／フォルダ型パーソナルワークスペース**です。[#314 プログラム](https://github.com/Jongtae/personal-agentos/issues/314) は完了しており、統合実装は [PR #320](https://github.com/Jongtae/personal-agentos/pull/320)、検証と終了記録は [PR #324](https://github.com/Jongtae/personal-agentos/pull/324) にマージされています。

参照フォルダは既定で読み取り専用、書き込みは所有者が許可した管理ワークスペース内に限定されます。原本、派生資料、下書き、最終記録を区別し、再構築可能な検索インデックスを永続的な作業・承認・証跡・復旧・認証状態から分離し、再起動後も保存した結果を再利用できます。

現在の完了証拠は deterministic model と一時ローカルフォルダによる自動検証です。これだけで外部モデル、Telegram、Google Drive/OAuth、定期 scheduler、個人フォルダ、AgentPackage、Registry、Marketplace の実運用が確認されたとは主張しません。

[#333](https://github.com/Jongtae/personal-agentos/issues/333) と #334–#346 は **planned successor work** です。Issue が存在するだけでは実行は有効になりません。

## 所有者の管理境界

- 接続するフォルダ、サービス、ツール、AgentPackage、runtime は所有者が選択します。
- 第三者 package/runtime は canonical Memory をデフォルトで直接変更しません。
- 外部 AI、messenger、Agent、package/runtime、recipient への transmission は local storage とは別の policy boundary です。
- send、payment、destructive file/account change、privilege expansion などには explicit authority が必要です。
- package signature/provenance は identity/integrity evidence であり、behavioral safety の保証ではありません。

ローカルファーストは「情報が一切端末外に出ない」という意味ではありません。外部機能を選択した場合、承認済み Context はその capability policy に従って送信されることがあります。

## 開発用インストール

```sh
brew install jongtae/agentos/agentos
agentos start
```

Homebrew 経路は、一般ユーザー向けインストール体験を改善している間、開発者とセルフホスト利用者向けに維持されます。

## 開発ガバナンス

このリポジトリは [Development Constitution](docs/development-constitution.en.md) と Goal Execution Contract を使用し、`Constitution → Spec → Authority/Threat Model → Plan → Tasks → Implement → Verify → Converge` の流れを採用します。

Spec Kit、BuilderMethods Agent OS、Open AgentOS 系の有用な development patterns は参照しますが、Personal AgentOS runtime dependency にはしません。Repository automation は end-user runtime や live autonomy の証拠ではありません。

実装前に [AGENTS.md](AGENTS.md)、[PRD.md](PRD.md)、[TASKS.md](TASKS.md)、[roadmap](docs/roadmap.md) を確認してください。
