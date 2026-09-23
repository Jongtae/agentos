# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## 仕事を任せる。主導権は自分に残す。

**日常から仕事まで、実際の用事を任せられるパーソナル AI。**

欲しい結果を伝えてください。Personal AgentOS は、あなたが許可したファイル、ツール、アカウント、モデルを使い、その範囲内で作業し、重要な外部操作の前には承認を求め、有用な結果を owner-controlled state に残すことを目指します。

メンタルモデルは単純です。**「AI と会話する」より「自分の AI に仕事を任せる」**に近い製品です。

> **Personal AgentOS = 実際の仕事を委任するパーソナル AI + owner-authoritative な AI 環境**

![Personal AgentOS の委任フロー: 任せる、許可範囲で実行、重要操作を承認、結果を保持](docs/assets/readme/delegation-flow.svg)

<!-- readme-section:everyday-scene -->

## まず、日常の一場面で考える

<!-- capability:illustrative-product-direction -->

> **Product direction — 現在の対応機能を意味しません。**

> **あなた:** 「洗剤とキッチンペーパーがもうすぐ切れそう。いつもの商品か良い代替品を探して、価格と送料を比べ、購入の準備までして。注文する前には確認して。」
>
> **Personal AgentOS:** 許可されたコンテキストを集め、候補を調べ、確認済みの事実と未確認事項を分け、次の操作を準備し、承認境界で止まります。

これが目指す体験です。**面倒な部分は任せ、決定は自分で行う。**

**この場面は product direction を説明する例であり、現在 autonomous shopping や checkout が提供されているという意味ではありません。** 現在の対応範囲と証拠は下に分けて記載します。予約確定、決済、外部メッセージ送信などの consequential effect は、実装と証拠がある場合にのみ対応済みと表現します。

同じパターンは他の日常場面にも使えます。

- 「土曜の午後の予定に合う美容院を探して予約準備して。確定前に聞いて。」
- 「今週末は外出する。許可した予定や情報を見て、持ち物と買う物をまとめ、後で続けられるよう残して。」
- 「この許可済み資料を読んで、役立つ成果物にして保存し、再起動後にも見つけられるようにして。」

<!-- readme-section:delegation-flow -->

## こう考えると分かりやすい

**🗣️ 任せる → 🔎 許可の範囲で作業 → ✋ 必要な時に承認 → 📦 結果を残す**

1. **結果を委任する。** 統合手順を組み立てるのではなく、欲しい結果を伝えます。
2. **許可の範囲で働く。** AgentOS が承認済み Context、Capability、送信先、Runtime/Model を仲介します。
3. **重要な決定は owner に残す。** 新しい権限や意味のある外部効果には対応する承認が必要です。
4. **有用な状態を残す。** Artifact、受け入れ済み Memory、Work/Event 履歴、Evidence は交換可能な worker と分離して保持します。

<!-- readme-section:chatbot-difference -->

## 普通のチャットボットと何が違うのか

| 一般的なチャットボット | Personal AgentOS の方向性 |
| --- | --- |
| プロンプトに答える | 制限された権限の中でタスクを結果へ進める |
| 主な Context は現在の会話 | owner が許可したファイル、Memory、Connector、task context を使う |
| 結果が会話内で終わりやすい | 再利用できる Artifact と作業履歴を残す |
| Tool 権限が暗黙的またはサービス側中心になり得る | Owner policy と Grant が何をどこまで使うかを決める |
| モデルが製品の中心 | Model/Agent は owner authority の下にある交換可能な worker |

すべてを自動実行することが目的ではありません。**データ、権限、決定、永続状態のコントロールを手放さずに、実際の仕事を任せられるようにすること**が目的です。

個人向けの生産性ワークスペースは、AI のために目標・タスク・知識を整理できます。**Personal AgentOS が重視するのはその下の実行レイヤーです。** AI が何にアクセスできるか、何を実行できるか、実際に何が起きたか、worker を変えてもどの owner state が残るかを制御する環境です。

<!-- capability:current-supported-slice -->
<!-- readme-section:try-today -->

## 今、検証済みの範囲を試す

現時点で最も明確な最初のタスクは file-workspace journey です。保存結果、原本保持、再起動後の再利用に具体的な repository evidence があります。

![現在サポートされるファイル作業フロー: 承認済み参照フォルダ、管理された結果、再起動と再利用](docs/assets/readme/file-workspace-flow.svg)

1. 専用の参照フォルダに小さな Markdown/text ファイルを置きます。
2. そのフォルダには read access、別の managed workspace には結果保存権限を与えます。
3. **“Summarize ‘Launch review’ and save it as ‘Launch notes’.”** と依頼します。
4. managed workspace に新しい Markdown 結果が現れ、原本が変更されていないことを確認します。
5. AgentOS を再起動し、保存結果をもう一度探すよう依頼します。

文書化された file-workspace path では、対応する direct model-provider connection を使い、reference folder と managed workspace を明示的に許可し、外部 provider に承認済み文書 Context を送る前に必要な共有承認を行います。

### インストール

```sh
brew install jongtae/agentos/agentos
agentos start
```

ブラウザは `http://127.0.0.1:8787` で開きます。

**この Homebrew コマンドがインストールする最新公開リリースは `v1.0.4` (2026-09-07) で、現在の `main` より遅れています。** `main` にはこのリリース以降の機能開発と first-user 改善が含まれます。正確な対応経路は [QUICKSTART](QUICKSTART.md)、公開状態は [release procedure](docs/release.en.md) を参照してください。

<!-- readme-section:status -->

## 現在できることと、まだ摩擦がある部分

最新の synthetic first-user audit は [#472](https://github.com/Jongtae/personal-agentos/issues/472) です。実際の製品構成に injected transports を使って検証しましたが、**live provider operation は実行していません。** fixture の成功は live service の証明ではありません。

| 領域 | 現在の証拠 |
| --- | --- |
| Install/start/restart | #472 で local deterministic first-use path は通過。新しい Mac での Homebrew/launchd 検証は別の operating gate です。 |
| Files | Synthetic **pass-with-friction**。承認フォルダ要約、managed save、restart/reuse は動作しますが、自然な「それをファイルに保存して」にはまだ gap があります (#481)。 |
| Gmail | Synthetic **pass-with-friction**。connect/re-auth/search/resume path はありますが、contextual resume と read/reply UX に未解決 defect があります (#473, #478)。 |
| Calendar | Synthetic **pass-with-friction**。bounded create/preview/correct/cancel/approve の evidence はありますが、query/approval UX gap が残ります (#475, #482, #483)。 |
| Research | Synthetic **pass-with-friction**。公開情報から source と known/unknown を分けた結果を作れますが、routing/context defect が残ります (#448, #474)。 |
| Memory | Synthetic **pass-with-friction**。remember/inspect/correct と owner-visible candidate はありますが、delete/receipt UX に摩擦があります (#479)。 |
| Agent distribution | v0.1 schema/contract はありますが、任意の第三者 AgentPackage 実行や公開 Marketplace は現在の product claim ではありません。 |

現在 **自動購入、任意の computer use、すべての Web ページ検証、live inventory/checkout total の確認、任意の第三者 package 実行、公開 Agent Marketplace** を対応済みとは主張しません。

<!-- readme-section:why-agentos -->

## なぜ “AgentOS” なのか

自分の personal AI が、特定のモデル、特定の会社、特定の Agent と同一であるべきではないからです。

Personal AgentOS は owner-authoritative な層と交換可能な worker を分離します。

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

Model、coding agent、Connector、delegated Runtime は交換できます。それらは Capability を要求し、AgentOS policy と owner が実際の authority を決めます。Worker を交換しても有用な personal state が一緒に消えないことが重要です。

<!-- readme-section:owner-control -->

## コントロールは owner に

[Owner Control Contract](docs/owner-control-contract.en.md) は六つの観察可能な権利を定義します。

1. **Inspect** — package/source、publisher、version、execution mode、requested authority を確認する。
2. **Choose data** — 使ってよい document、Memory、account を選ぶ。
3. **See destinations** — task 情報がどこへ送られるか確認する。
4. **Bound actions** — install/connect と実際の action authority を分ける。
5. **Stop and revoke** — authority を取り消し、in-flight uncertainty を正直に示す。
6. **Keep and move owner state** — worker を削除・交換しても owner state を保つ。

ローカルインストールと local-only processing は同じではありません。外部モデルを使う local package は承認済み Context をその provider に送ります。Disconnect、authority revoke、worker removal、remote retained data deletion は別の操作です。

<!-- readme-section:architecture -->

## 製品を理解した後に見るアーキテクチャ

| Layer | Responsibility |
| --- | --- |
| **Owner plane** | Owner identity/policy、Context/Memory authority、data/workspace、Grants/approvals、Work/Event、Artifacts、Evidence、recovery |
| **Capability plane** | Typed tools/connectors と bounded runtime interfaces |
| **Distribution plane** | AgentPackage、Package Manager、Registry、trust metadata、将来の Marketplace/discovery |
| **Worker plane** | 交換可能な model、Codex/Claude Code、local/API worker、optional delegated runtime |
| **Experience plane** | Conversation、useful result、inspectable progress、approval/control、将来の agent discovery |

Kernel は **agent-independent** に保ちつつ、製品体験は **agent-centric** にできます。

<!-- readme-section:bdi -->

## BDI-inspired attention lens

BDI は **概念的な設計レンズ**です。canonical BDI state machine が既に shipped しているという主張でも、hidden chain-of-thought を公開する要求でもありません。

- **Belief view:** 許可された task context、accepted Memory、関連 Evidence/Artifact、現在の Capability/Grant facts。
- **Desire:** owner が欲しい outcome と success criteria。
- **Attention:** 今重要なこと、許可されたこと、関係する destination/effect、approval が必要かどうか。
- **Intention:** 現在の bounded plan と次の executable step。
- **Execution:** Capability/Runtime mediation により observed Work/Event、Artifact、Evidence を作ります。

結果は次の task context に役立つ場合がありますが、すべてが自動で durable Memory になるわけではありません。第三者は `MemoryCandidate` を提案し、policy/owner が canonical Memory に採用するか決めます。

<!-- readme-section:ecosystem -->

## Agent ecosystem の方向性

AgentPackage lifecycle は次を意図的に区別します。

`downloaded != installed != enabled != connected != authorized-for-action`

Installation は Grant を自動生成してはいけません。Data、action、destination、Memory、background behavior を広げる update には新しい authority が必要です。Removal は package authority を revoke しつつ、owner-owned output と必要な Evidence は policy に従って保持します。

まず useful で bounded な Agent と public authoring path を証明することが先で、大規模 store や payment は最初の前提ではありません。詳しくは [architecture](docs/personal-agentos-architecture.en.md)、[PRD](PRD.md)、[platform foundation](docs/agent-distribution-platform-foundation.en.md)、[product vision](PRODUCT_VISION.ko.md)、[roadmap](docs/roadmap.md) を参照してください。

<!-- readme-section:portability -->

## Portability と限界

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

対応する owner state と reviewed declarations は integrity check と共に export/restore できます。Provider credential、session、local-folder Grant、engine/model selection、Telegram pairing は portable archive には含まれず、再接続または再承認が必要です。

Local-first は local-only や自動的な安全性を意味しません。Host security、package isolation、既に送信された data、remote provider retention は現実の境界です。

<!-- readme-section:development -->

## 開発ガバナンス

このプロジェクトは **coding harness、swarm framework、host kernel、macOS/Linux の代替ではありません。** GitHub/Codex delivery automation は Personal AgentOS を作る開発インフラであり、end-user product ではありません。

[AGENTS.md](AGENTS.md)、[Development Constitution](docs/development-constitution.en.md)、[Goal Execution Contract](docs/goal-execution-contract.en.md) に従い、issue → bounded branch → implementation → validation → 必要な independent review → merge/closeout の順で進めます。

Product completion は green CI、schema、file count だけでは判断しません。**useful outcome evidence と必要な denial/recovery evidence の両方が必要です。**
