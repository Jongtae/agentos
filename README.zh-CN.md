# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS 是面向单一所有者、由用户安装并掌控的本地优先个人 AI 运行环境。**

就像个人电脑和个人操作系统为一个人提供持续的计算环境一样，Personal AgentOS 旨在提供跨对话、任务、工具和模型变化持续存在的个人 AI 环境。它运行在所有者掌控的 Mac／运行时上，并在 AgentOS 自身的边界内保留策略、个人上下文、工作空间、权限、审批、工作状态、证据与恢复状态。

Codex、Claude Code、外部模型、本地模型、工具和专业 Agent 都是 AgentOS 可调用的可替换工作者或能力，而不是个人状态的唯一来源。更换执行引擎不应丢失所有者的上下文记录、权限、审批历史、可恢复工作或证据。

**Personal AgentOS 不是编码 harness，也不是 Agent swarm 框架。** 编码自动化可以成为其中的一项服务；本仓库使用的 GitHub/Codex 交付自动化则是构建产品的开发基础设施，而不是产品本身。它也不是 macOS/Linux 的替代内核或 hypervisor，而是运行在所有者控制的主机之上的持久个人 AI 层。

## 产品模型

长期架构把持久的所有者状态与可替换的工作者分开：

- **Owner plane** — 身份/策略、个人上下文与记忆边界、资料/受管工作空间、权限、审批、工作状态、证据、恢复。
- **Capability plane** — 工具、connector、assistant、专业能力、runtime/engine registry。
- **Worker plane** — 受限的 Codex、Claude Code、模型提供商或本地 runtime。
- **Experience plane** — 通过受支持的本地界面、Telegram 或 companion 进行对话与工作。

英文规范架构见 [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md)。这里的 **OS** 指的是持续拥有一个人的 AI 状态与权限的层，而不是替换宿主操作系统。

## 当前实现基线

第一个可用的产品切片是 **基于文件与文件夹的个人工作空间**。[#314 项目](https://github.com/Jongtae/personal-agentos/issues/314) 已完成；集成实现合并于 [PR #320](https://github.com/Jongtae/personal-agentos/pull/320)，验证与结束记录合并于 [PR #324](https://github.com/Jongtae/personal-agentos/pull/324)。

连接的参考文件夹默认只读；新结果只能写入所有者明确授权的受管工作空间。原件、派生资料、草稿和最终记录保持可区分，可重建的搜索索引与持久的工作、审批、证据、恢复和认证状态分离，并可在应用重启后重新找到和使用已保存结果。

当前完成证据来自 deterministic model 与临时本地文件的自动验证。这并不意味着已经验证外部模型、Telegram、Google Drive/OAuth、周期 scheduler 或个人文件夹的真实运行。可选 Drive 工作和公开信息站点发布目前均从核心路径延期。最新状态请参见[路线图](docs/roadmap.md)。

## 所有者控制与信任边界

- 所有者选择连接哪些文件夹、服务、工具、assistant 与 runtime。
- 向外部 AI、消息工具、其他 Agent 或收件人发送内容，是独立于本地存储的策略/审批边界。
- 外部发送或破坏性的文件/账户变更等重要操作需要明确授权。
- 本地优先不等于“任何信息都绝不会离开设备”。当所有者选择外部能力时，获准的任务上下文可能依据该能力的策略被发送出去。

## 开发安装

```sh
brew install jongtae/agentos/agentos
agentos start
```

在面向普通用户的安装体验继续完善期间，Homebrew 路径仍面向开发者和自托管用户。

## 开发治理

本仓库的 issue、branch、PR、CI、Goal Execution Contract 与 implementer/reviewer handoff 是 **用于构建 Personal AgentOS 的开发基础设施**，不是终端用户的 AgentOS runtime，也不是已经真实运行无人值守自治的证据。

实现前请阅读 [AGENTS.md](AGENTS.md)、[PRD.md](PRD.md)、[TASKS.md](TASKS.md) 和[路线图](docs/roadmap.md)。
