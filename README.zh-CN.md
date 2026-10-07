# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## AI 可以更换，但你的个人智能体不该从头开始

对话会结束，模型会更换，服务也可能消失。但你已经积累的上下文、尚未完成的工作，以及你授予的权限，不应随之一起消失。

**Personal AgentOS 是一个开源、自托管的个人智能体（PA）环境：把你的上下文和未完工作留在你掌控的环境中，同时允许你选择和更换底层 AI。**

目标不是一个聊天记录更长的聊天机器人，而是同一个持续存在的 PA：它的记忆、工作、权限和执行证据留在你控制的环境里。

**同一个 PA，不同的 AI。**

> **当前状态：** Personal AgentOS 是可运行的探索性项目，并非完成的自主助手。公开版本可以连接你自己的模型；下方会议、地图和购物场景，除非特别说明，均属于产品方向。

<!-- readme-section:ownership -->

## 有什么不同？

许多 AI 产品让“你交谈的助手”和“提供智能的厂商”看起来像同一件事。Personal AgentOS 探索把二者分开。

| | Personal AgentOS |
| --- | --- |
| **上下文** | PA 延续所需的上下文保存在你的环境中 |
| **未完工作** | 尚未结束的事项可以继续，而不是埋在聊天记录里 |
| **AI** | 本地、云端和订阅型 AI 都可以为同一个 PA 工作 |
| **权限** | 信息访问和重要行动受所有者控制 |
| **证据** | 区分模型说了什么与实际发生了什么 |

当前版本已包含两项所有者控制机制：你选择的 AI 把事实保存到 Memory 后会告知你并提供精确撤销；每个 Work 都记录使用了你的哪些信息以及这些信息被发送到哪里。

本地优先不等于只在本地。若选择云端模型，请求所需的上下文会发送给该服务商。

更大的问题很简单：**如果明天出现更好的 AI，为什么你必须连已经了解你工作方式的智能体也一起重建？** [谁的智能体？](docs/whitepapers/whose-agent.ko.md) 白皮书从产品和产业角度展开这一问题。

<!-- readme-section:presence -->

## 现在试用

在 macOS 上使用 [Homebrew](https://brew.sh)：

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. 浏览器打开 `http://127.0.0.1:8787` 后选择 **바로 시작하기**（立即开始）。
2. 连接自己的模型：支持工具调用的本地 Ollama、OpenAI、OpenAI 兼容服务、Anthropic，或支持的 Codex / Claude Code 订阅路径。
3. 在 **설정 → 외부 연결**（设置 → 外部连接）中连接自己的 Telegram Bot，并打开配对链接。
4. 试着说：**“我这周要完成提案初稿。帮我把接下来要做的事分成几个步骤。”**

对话期间请保持 `agentos start` 运行。[QUICKSTART](QUICKSTART.md) 介绍模型设置、文件处理、Telegram 和源码运行。

**公开版本：** Homebrew 安装 **v1.1.1**（2026-10-07）。[版本清单](docs/release-manifest.json)记录源码覆盖和安装检查；[当前状态](docs/product-status.en.md)区分已发布行为、测试依据、所有者试用依据和产品方向。

<!-- readme-section:conversation -->

## 这个项目想实现的体验

个人智能体不应只回答最后一句话，还应能继续一件已经开始的事。

> “帮我留意下周的项目会议，我们还要确定提案。”

PA 应把会议与获准使用的上下文关联，保留尚未解决的决定，准备下一步，并在需要你的权限时停下来。草稿不是已发送邮件，收到邀请不是接受承诺，模型说“做了”也不是实际执行的证据。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.zh-CN.narrow.svg">
  <img src="docs/assets/readme/presence-overview.zh-CN.svg" alt="助手、任务型智能体与延续未决工作的 PA 的概念图。属于产品方向，并非已观测运行或已发布集成。">
</picture>

项目把这种持续关系称为 **Presence**：不是亲切的人设，而是在多轮对话、工具、worker、失败和模型更换之间保持连续性，同时维持真实性和所有者权限。更多结构说明见[架构与本体](docs/personal-agentos-architecture.en.md)和 [Presence 体验契约](docs/presence-experience-contract.en.md)。

## 日常短句，仍是同一个 PA

> “咖啡快没了。”  
> 几小时后：“我准备出门了，路上有地方可以买到吗？”  
> 之后：“没时间了，就买上次那款吧。”

理想体验是你继续说话，而不是自己编排工作流：PA 延续相关上下文，只询问缺失的信息，并在需要你的账户或权限时停下。

下图基于所有者试用对话进行浓缩和脱敏重构。它**不是产品原始截图，也不是证据记录**；图中的地图和购物集成属于产品方向，并非已发布功能。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation.zh-CN.png">
  <img src="docs/assets/readme/owner-pilot-conversation.zh-CN.png" alt="三个重构的 PA 对话场景：分享位置寻找晚餐、比较高尔夫腰带并请求登录、从餐厅照片继续到附近散步。">
</picture>

[查看完整图片](docs/assets/readme/owner-pilot-conversation.zh-CN.png) · [查看原始参考图](docs/assets/readme/owner-pilot-conversation-reference.jpg)

**你说或展示的内容 → 有来源和时间的获准上下文 → 必要的问题或工具 → 权限边界 → 已观测结果**

<!-- readme-section:try-today -->

## 现在能做什么，还不能做什么

本仓库有意区分**可运行的软件**、**测试/fixture 证据**、**所有者试用观察**和**产品方向**。

当前公开版本提供可安装的本地运行环境、模型连接和对话界面；源码包含所有者上下文、Work 连续性、模型切换、浏览器/登录交接、skill routing 和 Presence 行为等工作。安装检查证明软件包安装与本地前台运行。

目前**不**声称支持自主购买、任意计算机操作、通用网页验证、实时库存或结账验证、公开智能体市场，也不声称上面的会议和购物场景已在 v1.1.1 中端到端运行。

精确边界见[当前状态](docs/product-status.en.md)，版本证据见[版本清单](docs/release-manifest.json)。

<!-- readme-section:more -->

## 进一步了解

- [为什么做这个项目](VISION.md) · [谁的智能体？](docs/whitepapers/whose-agent.ko.md) — 为什么个人智能体的连续性应由所有者掌握。
- [架构与本体](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) · [角色与委托](docs/research/role-ontology-and-mandate-2026-10-05.ko.md) — 上下文、工作、权限和证据如何连接。
- [研究与参考资料](docs/acknowledgements.en.md) — 影响设计的先行研究与项目。
- [文档导航](docs/README.md) · [参与贡献](CONTRIBUTING.md) — 查看当前契约、实现和贡献路径。

<!-- readme-section:license -->

## 开源

Personal AgentOS 是一个可以运行、质疑并共同改进的探索。它不必是最终答案，也可以成为有意义的开始。

代码采用 [AGPL-3.0-only](LICENSE)。Personal AgentOS 名称和标志遵循[商标声明](TRADEMARKS.md)。外部工作列于[致谢与参考资料](docs/acknowledgements.en.md)。
