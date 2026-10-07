# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## ジャービスが他社のサービスだったら？

トニー・スタークが長いあいだジャービスと働いてきたとします。自分の文脈を共有し、判断を保留し、仕事を任せながら、一緒に働く方法を積み重ねてきました。

そこに、もっと優れた AI が登場します。

**トニーはその AI を使うために、ジャービスまで失う必要があるのでしょうか。**

知能の提供者が変わるという理由だけで、ジャービスが覚えている自分の文脈、まだ終わっていない仕事、任せた権限、積み重ねた働き方まで最初から作り直すべきでしょうか。

**AI は替えられても、自分のパーソナルエージェントは自分のものであり続けるべきです。**

Personal AgentOS はこの考えを探るオープンソースのパーソナルエージェント環境です。PA の文脈・未完の仕事・権限・実行の根拠を自分で管理する環境に残し、その下で働く AI は選び、替えられるようにします。

目標は履歴が長いだけのチャットボットではありません。AI が替わっても続く、一つのパーソナルエージェントです。

**同じ PA。違う AI。**

> **現在の状態：** Personal AgentOS は動かせる探索段階のプロジェクトであり、完成した自律アシスタントではありません。公開版では自分のモデルを接続できますが、下の会議・地図・買い物の場面は、明記がない限り製品の方向性です。

<!-- readme-section:ownership -->

## 何が違うのか

多くの AI 製品では、会話するアシスタントと知能を提供する会社が一体のものに見えます。Personal AgentOS はその二つを分けられるかを探ります。

| | Personal AgentOS |
| --- | --- |
| **文脈** | PA が引き継ぐ文脈を自分の環境に置く |
| **未完の仕事** | 終わっていない仕事をチャット履歴に埋めず、続けられる形で残す |
| **AI** | ローカル・外部・サブスクリプション型の AI が同じ PA のために働ける |
| **権限** | 情報アクセスと重要な行動をオーナーの管理下に置く |
| **根拠** | モデルが言ったことと、実際に起きたことを分けて残す |

現在のリリースには二つのオーナー制御が含まれます。自分が選んだ AI が事実を Memory に保存すると後から知らせ、正確に取り消せます。また各 Work は、自分のどの情報を使い、どこへ送ったかを記録します。

ローカルファーストはローカル限定ではありません。外部モデルを選ぶ場合、その依頼に必要な文脈は提供者へ送信されます。

問いはシンプルです。**明日もっと良い AI が出たとき、なぜ自分との働き方を知っているエージェントまで作り直す必要があるのでしょうか。** [誰のエージェントか](docs/whitepapers/whose-agent.ko.md) ではこの問いを製品・産業の観点から掘り下げます。

<!-- readme-section:presence -->

## 今すぐ試す

macOS で [Homebrew](https://brew.sh) を使う場合：

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. `http://127.0.0.1:8787` が開いたら **바로 시작하기**（今すぐ始める）を選びます。
2. 自分のモデルを接続します。ツール呼び出し対応のローカル Ollama、OpenAI、OpenAI 互換サービス、Anthropic、または対応する Codex / Claude Code のサブスクリプション経路を利用できます。
3. **설정 → 외부 연결**（設定 → 外部接続）で自分の Telegram Bot を接続し、ペアリングリンクを開きます。
4. **「今週中に提案書の草案を仕上げたい。次にやることをいくつかの段階に整理して。」** と話しかけてみてください。

会話中は `agentos start` を実行したままにします。モデル設定、ファイル作業、Telegram、ソースからの実行は [QUICKSTART](QUICKSTART.md) にあります。

**公開版：** Homebrew は **v1.1.1**（2026-10-07）をインストールします。[リリース内容](docs/release-manifest.json)にソース範囲とインストール検証を記録し、[現在の状態](docs/product-status.en.md)で提供済みの動作・fixture の根拠・オーナーパイロット・製品方向を区別しています。

<!-- readme-section:conversation -->

## このプロジェクトが目指す体験

パーソナルエージェントなら、最後の質問に答えるだけでなく、一度始まったことを引き継げるべきです。

> 「来週のプロジェクト会議を気にかけておいて。提案の結論を出したい。」

PA は許可された文脈を会議につなぎ、未決の判断を残し、次に必要なことを準備し、自分の権限が必要なところで止まるべきです。下書きは送信ではありません。招待は引き受けた約束ではありません。モデルが「実行した」と言うだけでは実行の根拠になりません。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.ja.narrow.svg">
  <img src="docs/assets/readme/presence-overview.ja.svg" alt="アシスタント、実行型エージェント、未決事項を引き継ぐ PA の概念図。観測済みの動作や提供済み連携ではなく製品方向です。">
</picture>

この継続する関係を **Presence** と呼びます。親しみやすい人格ではなく、turn・ツール・worker・失敗・モデル変更をまたいでも文脈と仕事が続き、その間も事実性とオーナー権限が保たれる体験です。詳しい構造は[アーキテクチャとオントロジー](docs/personal-agentos-architecture.en.md)と [Presence experience contract](docs/presence-experience-contract.en.md)にあります。

## 日常の短い言葉にも同じ PA

> 「コーヒー、もうなくなりそう。」  
> 数時間後：「今から出るんだけど、途中で買えるところあるかな？」  
> その後：「時間ないな。前と同じものを買っておいて。」

目指すのは、自分でワークフローを組むのではなく会話を続けることです。PA が関連する文脈を引き継ぎ、足りない情報だけを尋ね、自分のアカウントや権限が必要な境界で止まります。

下の画像はオーナーパイロットの会話をもとに要約・匿名化して再構成したものです。**製品画面そのものの撮影でも、会話の証拠記録でもありません。** 地図・買い物の連携は提供済み機能ではなく製品方向です。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation.ja.png">
  <img src="docs/assets/readme/owner-pilot-conversation.ja.png" alt="位置共有から夕食を探し、ベルト比較後にログインを求め、レストラン写真から散歩へ続く三つの再構成場面。">
</picture>

[画像をフルサイズで見る](docs/assets/readme/owner-pilot-conversation.ja.png) · [元の参考画像を見る](docs/assets/readme/owner-pilot-conversation-reference.jpg)

**言葉や画像 → 出典と時刻のある許可された文脈 → 必要な質問やツール → 権限の境界 → 観測された結果**

<!-- readme-section:try-today -->

## 今できること、まだできないこと

このリポジトリは**動くソフトウェア**、**テスト/fixture の根拠**、**オーナーパイロットの観測**、**製品方向**を意図的に区別しています。

現在の公開版にはインストール可能なローカルランタイム、モデル接続、会話 surface があり、ソースには owner context、Work continuity、モデル切り替え、ブラウザー/ログイン handoff、skill routing、Presence behavior に関する実装が含まれます。インストール検証はパッケージ導入とローカル foreground 実行を確認します。

一方、自律購入、任意のコンピューター操作、万能な Web 検証、リアルタイム在庫・決済確認、公開エージェントマーケットプレイス、上の会議・買い物場面が v1.1.1 で end-to-end 動くことは現在主張していません。

正確な境界は[現在の状態](docs/product-status.en.md)、リリースごとの根拠は[リリース内容](docs/release-manifest.json)を参照してください。

<!-- readme-section:more -->

## さらに知る

- [このプロジェクトを作る理由](VISION.md) · [誰のエージェントか](docs/whitepapers/whose-agent.ko.md) — パーソナルエージェントの継続性をなぜオーナーが持つべきか。
- [構造とオントロジー](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) · [役割と委任](docs/research/role-ontology-and-mandate-2026-10-05.ko.md) — 文脈・仕事・権限・根拠をどう結ぶか。
- [研究と参考資料](docs/acknowledgements.en.md) — 設計に影響した先行研究とプロジェクト。
- [ドキュメント案内](docs/README.md) · [開発への参加](CONTRIBUTING.md) — 現在の契約、実装、貢献への入口。

<!-- readme-section:license -->

## オープンソース

Personal AgentOS は実際に動かし、問い直し、一緒に改善できる探索です。最終的な答えでなくても、意味のある始まりにはできます。

コードは [AGPL-3.0-only](LICENSE) です。Personal AgentOS の名前とロゴには[商標に関する注記](TRADEMARKS.md)が適用されます。外部の取り組みは[謝辞と参考資料](docs/acknowledgements.en.md)に記載しています。
