# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS 是面向单一所有者、由用户安装并掌控的本地优先个人 AI 运行环境。**

长期产品方向可以概括为：

> **Personal AgentOS = Personal AI Kernel + Agent Distribution Platform**

就像个人电脑和个人操作系统为一个人提供持续的计算环境一样，Personal AgentOS 旨在提供跨对话、任务、工具、Agent 和模型变化持续存在的个人 AI 环境。它运行在所有者掌控的主机／运行时上，并在 AgentOS 自身的边界内保留策略、个人 Context/Memory、工作空间、Grant、审批、Work/Event、Artifact、Evidence 与恢复状态。

Kernel 有意保持 **Agent-independent**。Codex、Claude Code、外部/本地模型、MCP server、专业 Agent、Ruflo 等 multi-agent runtime 都只是可替换的 worker/capability。它们不能成为 canonical Memory、Grant、Work state 或 Evidence 的权威来源。

但产品体验可以是 **Agent-centric** 的：优秀的第三方 Agent 应该能够像应用一样被发现、检查、安装、授权、运行、更新、回滚、禁用和卸载，而不会接管所有者的个人 AI 状态。

**Personal AgentOS 不是编码 harness，也不是 Agent swarm 框架。** 编码自动化和 multi-agent orchestration 可以成为 AgentOS 上的 service/runtime；本仓库的 GitHub/Codex 自动化只是构建产品的开发基础设施。它也不是 macOS/Linux 的替代内核或 hypervisor，而是运行在所有者控制主机之上的持久个人 AI 层。

## 产品模型

- **Owner plane** — 身份/策略、Context/Memory、owner data/workspace、Grant/approval、Work/Event、Artifact、Evidence、recovery。
- **Capability plane** — tools/connectors、capability registry、runtime/engine boundary。
- **Distribution plane** — AgentPackage、Package Manager、Registry、trust metadata、Marketplace/discovery boundary。
- **Worker plane** — 受限的 Codex、Claude Code、model provider、local runtime、Ruflo 等。
- **Experience plane** — local UI、Telegram/companion，以及未来的 Agent inspect/install/permission UI。

英文规范架构见 [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md)。Distribution Platform 的分阶段计划见 [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md) 和 [#333](https://github.com/Jongtae/personal-agentos/issues/333)。

### Kernel primitives

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

Distribution plane 在此之上增加：

`AgentPackage · Package Manager · Registry · Marketplace/Discovery · Trust/Verification`

## AgentPackage 与权限

AgentPackage 是可安装的 Agent/application unit。长期 manifest 将声明 package/publisher/version、AgentOS API compatibility、capability/action、runtime requirements、filesystem/data scope、network destinations、secret references、Memory policy、Event/background behavior、budgets、approval requirements、Artifact、dependencies、sandbox、health check、update/rollback/remove、provenance/signature/SBOM 等信息。

安装和权限必须分离：

`discover → inspect → verify → installed-disabled → grant/connect/enable → run → update/rollback → disable → uninstall`

**downloaded、installed、enabled、connected、authorized-for-action 是不同状态。** 安装 package 不会自动创建 Grant。若更新扩大 permissions、data scope、external destinations、Memory/background behavior，则必须重新经过 owner/policy review。

第三方 Package 默认不能直接修改 canonical owner Memory，而应提交带来源的 MemoryCandidate。

## Registry 与 Marketplace

**Registry** 负责 package/publisher identity、exact version/digest、compatibility、signature/provenance、trust metadata、advisory/revocation/quarantine。

**Marketplace/Discovery** 可负责 search、recommendation、ranking、review、curation 以及未来的 commerce。但 popularity、rating、install count 都不是 execution authority，也不能覆盖 quarantine/signature/AgentOS policy。

Private owner Context/Memory/Work 不应成为 Registry/Marketplace 的状态。Capability discovery 应优先使用 structured/minimised metadata，而不是把 raw private prompt 直接发送给 store search。

## 初期生态策略

初期 Personal AgentOS 不需要自带所有最优秀的 Agent。可以从 General Assistant、Files、Research、Coding 等少量 reference Agent 开始。它们的目标不是由平台方包办最佳应用，而是让 OS 可用并验证公开的 Package/Runtime/Grant contract。

Reference Agent 与第三方 Package 应使用相同公开 contract，不应获得隐藏的 first-party privilege。

为了降低空 Marketplace 的 chicken-and-egg 问题，计划在官方格式与许可证允许的范围内，将 MCP 以及部分 OpenAI/Codex、Claude skill/plugin ecosystem wrap/import 成 AgentPackage。Ruflo 的定位是未来的 bounded delegated Runtime Adapter，而不是 AgentOS kernel。

## 当前实现基线

第一个可用的产品切片是 **基于文件与文件夹的个人工作空间**。[#314 项目](https://github.com/Jongtae/personal-agentos/issues/314) 已完成；集成实现合并于 [PR #320](https://github.com/Jongtae/personal-agentos/pull/320)，验证与结束记录合并于 [PR #324](https://github.com/Jongtae/personal-agentos/pull/324)。

连接的参考文件夹默认只读；新结果只能写入所有者明确授权的受管工作空间。原件、派生资料、草稿和最终记录保持可区分，可重建的搜索索引与持久的工作、审批、证据、恢复和认证状态分离，并可在应用重启后重新找到和使用已保存结果。

当前完成证据来自 deterministic model 与临时本地文件的自动验证。这并不意味着已经验证外部模型、Telegram、Google Drive/OAuth、周期 scheduler、个人文件夹、AgentPackage、Registry 或 Marketplace 的真实运行。

[#333](https://github.com/Jongtae/personal-agentos/issues/333) 与 #334–#346 是 **planned successor work**；issue 的存在本身不会激活执行。

## 所有者控制与信任边界

- 所有者选择连接哪些文件夹、服务、工具、AgentPackage 与 runtime。
- 第三方 package/runtime 默认不能直接修改 canonical Memory。
- 向外部 AI、messenger、Agent、package/runtime 或 recipient 传输内容，是独立于本地存储的 policy boundary。
- send、payment、destructive file/account change、privilege expansion 等需要 explicit authority。
- package signature/provenance 是 identity/integrity evidence，不是 behavioral safety 保证。

本地优先不等于“任何信息都绝不会离开设备”。当所有者选择外部能力时，获准的 Context 可能依据该 capability 的策略被发送出去。

## 开发安装

```sh
brew install jongtae/agentos/agentos
agentos start
```

在面向普通用户的安装体验继续完善期间，Homebrew 路径仍面向开发者和自托管用户。

## 开发治理

本仓库遵循 [Development Constitution](docs/development-constitution.en.md) 与 Goal Execution Contract，并采用：

`Constitution → Spec → Authority/Threat Model → Plan → Tasks → Implement → Verify → Converge`

我们会借鉴 Spec Kit、BuilderMethods Agent OS、Open AgentOS 类项目中有用的 development patterns，但不会把它们作为 Personal AgentOS runtime dependency。Repository automation 也不是 end-user runtime 或 live autonomy 的证明。

实现前请阅读 [AGENTS.md](AGENTS.md)、[PRD.md](PRD.md)、[TASKS.md](TASKS.md) 和[路线图](docs/roadmap.md)。
