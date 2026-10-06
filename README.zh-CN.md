# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## 我们想要的个人助手

我们希望能接着昨天的话题聊下去，想法还没理清也可以随口说出来，没做完的事可以一起继续，而不必每次都从头介绍自己的生活。也希望承载这些记忆的环境值得信任。

**Personal AgentOS 尝试在一个由你自己安装、自己掌控的环境里，构建这样的个人助手（PA）。**

助手回答问题，计算机智能体执行指令。而个人智能体还应该在不同的对话、任务，以及 AI 的更替之间，持续与你协作。我们把这种持续性称为 **Presence**。

<!-- readme-section:ownership -->

## 你的助手，由你掌控

助手越了解你的生活，谁保有它的记忆、谁决定它能做什么，就越重要。你与它建立的关系，不应该受限于某一家服务商、某一个模型或某一次会话。

AgentOS 把记忆、正在进行的工作和权限保存在你的环境里。由你选择 AI，决定它可以使用哪些信息、获得哪些访问权限。更好的 AI 出现时，应该是你的助手变得更有能力，而不是让你从头再来。

本地优先（local-first）不等于只在本地（local-only）。你可以选择本地模型或云端模型。使用云端模型时，请求所用的上下文会发送给该服务商。

<!-- readme-section:presence -->

## 让对话延续的结构

Presence 需要的不只是一份很长的聊天记录。助手需要把对你的了解、当前的情况、正在做的事、你允许的范围，以及实际发生过的事联系起来。

AgentOS 用一组共同的概念及其关系来表达这些内容，这就是它的**本体结构（ontology）**。一项工作会关联自己的上下文、权限、结果和依据。新的事件或更正，可以影响下一步判断。这样，即使 AI 更换或工作中断，它之前了解了什么、应该从哪里继续，也能保留下来。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.zh-CN.narrow.svg">
  <img src="docs/assets/readme/presence-overview.zh-CN.svg" alt="你始终与一个 PA 对话。AgentOS 关联并保存记忆与上下文、工作与权限、结果与依据。下方的判断层协调可替换的 AI 和工具，你的状态始终留在你的环境中。">
</picture>

AgentOS 通过判断层选择所需的 AI 和工具，并检查它们的结果。你与 PA 交谈，AgentOS 在对话之下维系这套结构。**同一个 PA，不同的 AI。**

<!-- readme-section:conversation -->

## 话可以很短，前后仍能接上

> “咖啡快没了。”<br>
> 几小时后：“我准备出门了，路上有地方可以买到吗？”<br>
> 之后：“没时间了，就买上次那款吧。”

想要的体验很简单：PA 能接上前文，理解要买的是什么、“上次那款”指什么，结合相关的上下文，只在需要时询问缺少的信息或权限。你继续说话就好，不必自己编排工作流程。

*这是产品方向示例，并非实际观测的运行，也不代表已发布的购物功能。*

<!-- readme-section:try-today -->

## 先试试看

在 macOS 上使用 [Homebrew](https://brew.sh)：

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. 浏览器打开 [http://127.0.0.1:8787](http://127.0.0.1:8787/) 后，选择 **바로 시작하기**（立即开始）。
2. 连接自己的模型并完成连接测试。可以使用支持工具调用的本地 Ollama 模型，或凭自己的 API 访问权限连接 OpenAI、OpenAI 兼容服务或 Anthropic。目前设置界面为韩语。
3. 试着说：**“帮我一起想想，这周应该重点做些什么。”**

Homebrew 会一起安装 Python，模型的使用权限需另行准备。[QUICKSTART](QUICKSTART.md) 介绍了模型设置、文件处理、Telegram，以及如何从源码运行最新版本。

**当前阶段：** Homebrew 安装的是较早的预览版 **v1.1.0**（2026-09-23），后续的 Presence 实现在 `main` 中。该版本无法创建日程，调研功能仅部分可用。具体范围见[版本清单](docs/release-manifest.json)。[当前状态](docs/product-status.en.md)区分了哪些功能可以使用、哪些经过验证、哪些仍是目标。

<!-- readme-section:more -->

## 进一步了解

- [为什么做这个项目](VISION.md) — 我们希望与计算机建立怎样的关系。
- [架构与本体](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) — 个人状态、工作和控制权如何支撑一个持续协作的助手。
- [研究与参考资料](docs/acknowledgements.en.md) — 设计所参考的个人智能体、记忆、用户模型和信息来源方面的研究与实践。
- [文档导航](docs/README.md) · [参与贡献](CONTRIBUTING.md) — 查阅当前规范与实现，一起改进项目。内部文档以英文为准。

<!-- readme-section:license -->

## 开源

这是一个可以亲自运行、提出质疑、共同改进的探索。它不必是最终答案，也可以成为有意义的开始。

代码采用 [AGPL-3.0-only](LICENSE) 许可证。Personal AgentOS 的名称和标志遵循[商标声明](TRADEMARKS.md)。参考的外部工作列于[致谢与参考资料](docs/acknowledgements.en.md)。
