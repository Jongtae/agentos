# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**由你安装、拥有和掌控，并能真正完成有用工作的个人 AI 环境。**

Personal AgentOS 是面向单一所有者的本地优先个人 AI 运行环境。你提出目标，选择模型和获准资料，完成工作并保留有用结果。长期目标是像安装应用一样安装和替换 Agent，同时让个人 Memory、权限、Work、Artifact 和 Evidence 始终属于你。

> **Personal AgentOS = Personal AI Kernel + Open Agent Distribution Platform**

只有控制而没有用途的管理工具不是目标；只有流畅回答而无法核实执行结果也不是目标。初期可以只有少量内置 Agent，但不能把基本功能质量低当成合理的产品策略。

## 当前实现与后续计划

| 状态 | 范围与证据 |
| --- | --- |
| 现有代码 | 本地浏览器设置和聊天、模型适配器、受限工具、笔记、获准文件夹和工作空间结果。具体支持路径见 [QUICKSTART](QUICKSTART.md)。 |
| 文件工作空间开发完成 | #314、PR #320/#324：原件保留、受限读取、保存结果、重启后复用；证据来自自动测试与临时本地文件。 |
| v0.1 契约完成 | #334、PR #350：核心对象和 AgentPackage 的 schema、静态/语义验证及 fixtures；不是包执行或安装实现。 |
| DOGFOOD-01 开发完成 | #351、PR #354–#356：模拟提供者的 HTTP/文件/重启验收与操作说明；真实模型和浏览器使用观察单独记录。 |
| 计划中的产品工作 | #358 基本任务质量，#359 真实执行记录与控制界面，#360 安装、使用、撤销、卸载及复用体验，以及 #333 未完成子任务。 |

没有声称已经支持任意第三方代码、公开 Registry/Marketplace、通用兼容或自动购买。现有声明型插件不等于计划中的可执行 AgentPackage。历史真实测试仅证明其记录的任务、版本与提供者条件。

## 首先做好三类工作

**研究到决策。** 根据公开来源比较选项，区分来源时间、价格条件、已确认事实和未知内容，形成有用的决策摘要。当前网页搜索只是搜索结果片段，不等于读取完整页面、确认库存或核对结账总额。

**个人文件到成果。** 读取明确允许的文档，整理关键事实、分歧和下一步行动，保存为普通文件。不仅检查文件存在，也检查内容质量；不得修改原件。

**跟进、纠正和重启复用。** 接受条件变更并继续相关工作，重启后找回结果，而不是反复要求用户重建上下文。不会默默把全部聊天都变成永久 Memory。

[基本功能质量计划](docs/default-agent-usefulness.en.md) 包含24个合成测试案例。这只是评估规格，不是已运行的模型评测成绩。必须在真实支持路径上测量成功率、依据、延迟、费用和用户干预。

## 所有者应能行使的六项控制权

[Owner Control Contract](docs/owner-control-contract.en.md) 定义待实现并验证的权利：

1. 查看包来源、发布者、精确版本、执行位置和请求权限。
2. 选择各 Agent 可用的资料、记忆和账户。
3. 知道哪些信息会发送到哪些服务。
4. 将安装和连接与具体行为授权分开。
5. 停止工作、撤销权限，并了解进行中外部操作的不确定性。
6. 卸载或替换 Agent 后仍保留自己的成果和已接受记忆。

控制必须由执行边界落实，而不仅是要求模型遵守规则。进度来自真实 Work/工具事件；详细记录应显示必要的脱敏输入、目的地、授权与结果。隐藏推理、系统提示词和秘密值不是这些记录的必要内容。

本地安装不等于本地处理。本地包可能调用外部模型并发送获准 Context。安装远程 Agent 的连接器，并不意味着控制该远程服务器。断开连接、撤销权限、卸载 Agent 与删除保留数据是不同操作。停止按钮不能保证收回已经发送的信息或撤销已完成的外部行为。

## 架构和应用模型

Kernel 保持 Agent-independent，产品体验可以 Agent-centric。

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

其上是 `AgentPackage · Package Manager · Registry · Marketplace/Discovery · Trust/Verification`。模型、Codex、Claude Code、MCP 和可选 Ruflo 只是可替换 worker，不是个人状态的权威。

`downloaded != installed != enabled != connected != authorized-for-action`

默认以禁用状态安装；安装不创建 Grant。扩大权限、数据范围、目的地、Memory 或后台行为的更新需要重新授权。第三方持久记忆更改默认是 MemoryCandidate，由所有者策略决定是否接受。卸载撤销包权限，但保留所有者成果和适当证据。

Registry 管理精确身份、版本、摘要、兼容性和撤销信息；Marketplace 管理搜索、排序、评论和未来商业分发。流行度不授予权限，签名也不保证行为安全。个人 Context 不是商店搜索数据。

先验证一个真正有用的 Files 参考包与公开 SDK 路径。同捆与第三方 Agent 使用同一公开契约，没有隐藏特权。只有格式、许可和权限可以明确对应时才引入 MCP/skill/plugin 兼容。大型商店、付款和 Ruflo 不是第一阶段用途的前提。

## 使用当前预览版

```sh
brew install jongtae/agentos/agentos
agentos start
```

**此命令安装的是最新已发布版本 `v1.0.4`（2026-09-07），它远落后于 `main`** — 不包含 Gmail 连接器、`agentos service`、PA1 连接器契约或记忆服务。Homebrew 是 macOS 自托管路径；较新的功能请使用源码检出。发布流程见 [release procedure](docs/release.en.md)。请遵循 [QUICKSTART](QUICKSTART.md) 的专用测试文件夹流程。该文件工作空间测试使用受支持的直接模型连接，不使用订阅引擎。计划中的包功能不能写成已经可用的命令。

支持的持久状态可通过 `scripts/agentos-backup.py DATA ARCHIVE` 与 `scripts/agentos-restore.py ARCHIVE EMPTY_DATA` 导出恢复。迁移归档不包含提供者凭据、会话、本地文件夹权限、模型选择或 Telegram pairing；新环境必须重新声明并连接。这不同于可能含秘密的整个数据目录备份。

## 开发治理

参阅[架构](docs/personal-agentos-architecture.en.md)、[PRD](PRD.md)、[AGENTS.md](AGENTS.md)、[Development Constitution](docs/development-constitution.en.md)、[Goal Execution Contract](docs/goal-execution-contract.en.md)和[路线图](docs/roadmap.md)。

本项目不是 coding harness、swarm 框架或 macOS/Linux 替代内核。GitHub/Codex 自动化是开发基础设施。#357 只对齐文档、评估规格与计划；#358–#360 及未完成的平台任务在单独明确激活前保持未执行。

完成标准不只是 schema、文件数和 CI：**必须同时证明成果有用，以及不允许的行为确实被阻止。**
