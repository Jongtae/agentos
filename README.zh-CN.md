# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## 始终属于你的个人智能体

我们希望能接着昨天的话题聊下去，想法还没理清也可以随口说出来，没做完的事可以一起继续。无论是安排日程、调查问题，还是准备购物，都不必每次从头介绍自己；承载这些背景信息的环境也应该值得信任。

**Personal AgentOS 尝试在一个由你自己安装、自己掌控的环境里，构建能与你持续协作的个人智能体（PA）。** 像助手一样提供帮助是重要的起点，但不是它唯一的角色。

助手回答问题，计算机智能体执行指令。而个人智能体还应该在不同的对话、工作类型，以及 AI 的更替之间，持续与你协作。我们把这种持续性称为 **Presence**。

<!-- readme-section:ownership -->

## 你的智能体，由你掌控

智能体协助的事情越多，谁保有它的记忆、谁决定它能做什么，就越重要。你们积累的背景信息，不应该受限于某一家服务商、某一个模型或某一次会话。

AgentOS 把记忆、正在进行的工作和权限保存在你的环境里。由你选择 AI，决定它可以使用哪些信息、获得哪些访问权限。不同领域的能力服务于同一个人；更好的 AI 出现时，你的智能体可以做更多事，而你不必从头再来。

本地优先（local-first）不等于只在本地（local-only）。你可以选择本地模型或云端模型。使用云端模型时，请求所用的上下文会发送给该服务商。

<!-- readme-section:presence -->

## 让对话延续的结构

Presence 需要的不只是一份很长的聊天记录。智能体需要把对你的了解、当前的情况、正在做的事、你允许的范围，以及实际发生过的事联系起来。

元数据可以记录会议的时间、地点和参与者。**本体结构（ontology）**还要说明这场会议与人、目标和承诺有什么关系：这只是一份邀请，还是有人接下了后续工作？日程视角用它协调时间，项目视角用它追踪决定与责任。两种视角都应指向同一场有来源的会议，不能把邀请直接当作承诺。

这种区别不只适用于日程。假设所有者持有某只股票的 1,000 股。个人资产管理的视角关心这笔持仓在整体财务中意味着什么；受托投资管理的视角则先核对它是否属于明确的委托范围及其限制。两者使用同一笔有来源的持仓事实，但角色名称本身不会赋予交易权限。

AgentOS 所追求的共同结构，把事实、各角色的解释、你委托的工作、实际权限和执行依据联系起来。这样，即使 AI 更换或工作中断，也能找到继续的位置。这些是设计示例，并非已经提供的资产管理、受托投资服务或已观测的运行结果。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.zh-CN.narrow.svg">
  <img src="docs/assets/readme/presence-overview.zh-CN.svg" alt="概念插图：助手回答 NVIDIA 问题，电脑代理执行 Amazon 指令，Personal AgentOS 延续跨越时间的对话。你与同一个 PA 交流，上下文、工作和权限保留在 AgentOS 中，底层 AI 和工具可以替换。这些示例用于说明产品方向，并非真实观测或已发布的集成功能。">
</picture>

AgentOS 通过判断层选择所需的 AI 和工具，并检查它们的结果。你与 PA 交谈，AgentOS 在对话之下维系这套结构。**同一个 PA，不同的 AI。**

<!-- readme-section:conversation -->

## 话可以很短，前后仍能接上

*这是产品方向示例，并非实际观测的运行，也不代表已发布的购物功能。*

下方中文版图片以所有者提供的韩语画面为基础，缩短并改写了对话。三个场景分别是分享位置后寻找回家路上的晚餐、比较高尔夫腰带并在加入购物车前请求登录账户，以及从餐厅照片接着聊附近的散步地点。它是经过编辑的说明性重构图，不是产品画面的原样截图，也不能证明这些集成功能已经发布。

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation.zh-CN.png">
  <img src="docs/assets/readme/owner-pilot-conversation.zh-CN.png" alt="根据所有者提供的画面改写的中文版三段 PA 对话：分享位置后寻找回家路上的餐厅，比较高尔夫腰带并请求登录账户，再从餐厅照片延续到附近散步。说明性重构图，不是产品画面的原样截图。">
</picture>

[以完整尺寸查看中文版图片](docs/assets/readme/owner-pilot-conversation.zh-CN.png) · [查看所有者提供的原图](docs/assets/readme/owner-pilot-conversation-reference.jpg)。

图中的对话是：

1. **回家路上的晚餐：**“下班路上要不要吃个晚饭？”PA 先询问当前位置，再列出三家店的距离和营业状态。所有者选了第二家。
2. **帮我找这条腰带：** 所有者发来照片，PA 比较三款腰带。所有者请它把第一款放进购物车时，PA 先要求登录购物账户，然后才会继续。
3. **我在这里，接下来呢？** 所有者发来餐厅照片，问饭后做什么。PA 提供附近的散步、咖啡馆和酒吧选项。所有者选择散步，PA 表示会核对路线和营业时间。

隔了几个小时才说出的简短一句话，也需要这样的连续性。

> “咖啡快没了。”<br>
> 几小时后：“我准备出门了，路上有地方可以买到吗？”<br>
> 之后：“没时间了，就买上次那款吧。”

想要的体验很简单：PA 能接上前文，理解要买的是什么、“上次那款”指什么，结合相关的上下文，只在需要时询问缺少的信息或权限。你继续说话就好，不必自己编排工作流程。

<!-- readme-section:try-today -->

## 先试试看

在 macOS 上使用 [Homebrew](https://brew.sh)：

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. 浏览器打开 [http://127.0.0.1:8787](http://127.0.0.1:8787/) 的设置页面后，选择 **바로 시작하기**（立即开始）。
2. 连接自己的模型并完成连接测试。可以使用支持工具调用的本地 Ollama 模型，或凭自己的 API 访问权限连接 OpenAI、OpenAI 兼容服务或 Anthropic。目前设置界面为韩语。
3. 在 **설정 → 외부 연결**（设置 → 外部连接）中，填入自己通过 BotFather 创建的机器人的令牌并连接。在 Telegram 中打开生成的配对链接，点击**开始**。
4. 在这个 Telegram 对话里试着说：**“帮我一起想想，这周应该重点做些什么。”**

Homebrew 会一起安装 Python，模型的使用权限需另行准备。对话期间请保持 `agentos start` 运行。[QUICKSTART](QUICKSTART.md) 介绍了模型设置、文件处理、Telegram，以及如何从源码运行最新版本。

**当前阶段：** Homebrew 安装的是较早的预览版 **v1.1.0**（2026-09-23），后续 `main` 中的 Presence 实现尚未包含在此版本中。该版本无法创建日程，调研功能仅部分可用。具体范围见[版本清单](docs/release-manifest.json)。[当前状态](docs/product-status.en.md)区分了哪些功能可以使用、哪些经过验证、哪些仍是目标。

<!-- readme-section:more -->

## 进一步了解

- [为什么做这个项目](VISION.md) · [谁的智能体？](docs/whitepapers/whose-agent.ko.md)（韩语战略白皮书）— AI 更换后，智能体的连续性应由谁掌握。
- [架构与本体](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) · [角色与委托](docs/research/role-ontology-and-mandate-2026-10-05.ko.md)（韩语研究提案）— 个人状态、工作和控制权如何支撑跨越不同角色的同一个智能体。
- [研究与参考资料](docs/acknowledgements.en.md) — 设计所参考的个人智能体、记忆、用户模型和信息来源方面的研究与实践。
- [文档导航](docs/README.md) · [参与贡献](CONTRIBUTING.md) — 查阅当前规范与实现，一起改进项目。内部文档以英文为准。

<!-- readme-section:license -->

## 开源

这是一个可以亲自运行、提出质疑、共同改进的探索。它不必是最终答案，也可以成为有意义的开始。

代码采用 [AGPL-3.0-only](LICENSE) 许可证。Personal AgentOS 的名称和标志遵循[商标声明](TRADEMARKS.md)。参考的外部工作列于[致谢与参考资料](docs/acknowledgements.en.md)。
