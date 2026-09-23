# Research artifact: Personal AgentOS Presence and Settings UX

- **Date:** 2026-09-23
- **Evidence class:** focused Deep Research informed by live owner dogfooding, repository contracts, external HCI/design sources and product patterns
- **Role:** durable product-design research reference
- **Canonical implementation contract:** [Presence Experience Contract](../presence-experience-contract.en.md)
- **Experience convergence issue:** [PRESENCE-01 #508](https://github.com/Jongtae/agentos/issues/508)
- **Capability claim:** none. This document does not claim that the described target experience is shipped.
- **Authority:** this research does not create runtime authority, activate a delivery goal, weaken owner approval, or supersede Work/Event/Evidence truth semantics.

The report below is preserved in Korean because that is the completed owner-facing research artifact. Contributors should use the English canonical contract above for normative implementation/review decisions and this document for the research reasoning, examples and evidence synthesis.

---

# Personal AgentOS의 Presence와 설정 UX 연구

## 핵심 종합

가장 중요한 결론은 **Personal AgentOS의 핵심 문제는 ‘말투’가 아니라 ‘투영(projection)’ 문제**라는 것입니다.

내부적으로 `Work`, 엔진 선택, connector 상태, tool outcome, Grant, task card, retry, Evidence 같은 개념을 갖는 것은 적절합니다. 문제는 이런 **커널 내부 개념이 사용자의 대화와 설정 화면에 너무 직접적으로 노출되고 있다는 것**입니다.

실제 owner dogfooding에서 그 결과가 명확하게 드러났습니다. Telegram은 개인 비서와 대화하는 곳이라기보다 task/status console처럼 느껴지고, Settings에서는 사용자가 routing, capability ID, filesystem path와 같은 내부 개념을 이해해야 합니다.

반면 현재 저장소에는 이 문제를 해결하는 데 필요한 **대부분의 아키텍처적 기반은 이미 존재합니다.**

#381은 사용자가 “하나의 일관된 개인 비서”를 경험해야 한다고 정의하고 있고, model, subscription CLI, specialist runtime 등은 교체 가능한 worker로 남도록 설계합니다. #386과 #393도 자연스러운 Telegram 요청, contextual capability handoff, 연결/승인 이후 original Work의 exactly-once continuation을 이미 목표로 삼았습니다.

그러나 #504~#506의 실제 dogfooding 결과를 보면 AI route 선택, filesystem setup, external connection 관리 같은 중요한 경계에서 여전히 내부 구조가 사용자에게 노출되고 있습니다.

### Personal AgentOS에서 Presence의 정의

> **Presence란 사용자가 여러 turn, tool, worker, 실패, restart, capability handoff를 거치는 동안에도 하나의 지속적이고 맥락을 이해하는 개인 비서와 관계를 이어가고 있다고 느끼는 경험이다. 동시에 그 아래에서는 AgentOS가 사실성, 명시적 사용자 권한, 검증 가능한 Evidence를 계속 엄격하게 유지해야 한다.**

Presence는 시스템이 의식이 있는 척하는 것이 아닙니다.

더 장황하게 말하는 것도 아니고, 감정적인 연기를 하는 것도 아니며, 인위적인 대기 시간을 만드는 것도 아닙니다.

Presence란 다음과 같은 것입니다.

“다시 해봐”가 무엇을 가리키는지 알고, 허용된 관련 맥락을 기억하고, 하나의 제품 차원의 목소리로 말하며, 권한이 실제로 필요해지는 순간 요청하고, 내부 상태를 사용자가 알아야 할 최소한의 설명으로 번역하는 것입니다.

Bickmore와 Picard의 장기간 실험은 relational behavior가 시스템에 대한 호감, 존중, 신뢰, 지속적 상호작용 의향을 높일 수 있음을 보여줍니다. 반대로 Luger와 Sellen의 연구는 conversational agent가 인간적인 대화 기대를 만들면서도 실제 capability와 repair behavior가 따라가지 못하면 신뢰를 잃는다는 점을 보여줍니다.

따라서 목표는 **anthropomorphic theater가 아니라 continuity + 정확한 기대 관리**여야 합니다.

Anshad Ameenza의 “presence, not intelligence”라는 표현도 유용합니다. 그 글은 항상 연결되어 있음, 사용자가 원래 쓰는 communication channel, memory, 지속적 loop가 시스템을 “필요할 때 방문하는 도구”에서 “곁에 있는 agent”로 심리적으로 전환시킨다고 설명합니다.

다만 이는 공학적 에세이이지 통제된 HCI 실험은 아니므로, 특정 아키텍처의 증명보다는 **제품 프레이밍**으로 사용하는 것이 적절합니다.

### 가장 중요한 권고

**Personal AgentOS를 더 사람처럼 말하는 모델 중심으로 재설계하지 말고, authoritative kernel과 owner-facing channel 사이에 AgentOS가 소유하는 conversational projection layer를 두어야 합니다.**

내부는 계속 이렇게 엄격하면 됩니다.

`Work → Event → tool/runtime → Evidence → outcome`

하지만 사용자는 그것을 이런 형태로 경험해야 합니다.

`내 요청 → 비서가 이해 → 필요한 경우 권한 요청 → 작업 → 검증된 결과 → 자연스러운 후속 대화`

제품 역할은 다음처럼 나뉘어야 합니다.

**Conversation = 의도와 관계**  
**Local approval = 권한**  
**Settings = 관리**  
**Task/Evidence detail = 실행 기록과 진단**  
**Kernel = 진실의 기준**

이번 연구에서 가장 중요한 결론입니다.

---

# 증거 검토와 가설 평가

연구 결과는 세 종류의 증거에서 상당히 일관된 방향을 보입니다.

실제 owner dogfooding, 현재 repository contract, 외부 HCI 및 제품 패턴입니다.

특히 **continuity, contextual permission, truthful recovery, progressive disclosure**에 대한 근거가 강합니다.

반면 특정한 말투나 heartbeat 자체가 presence를 직접 만든다고 주장할 근거는 상대적으로 약합니다.

| 발견 | 근거 | 강도 | 한계 |
|---|---|---|---|
| 장기간의 relational behavior는 사용자와 시스템의 관계감을 강화할 수 있다. | Bickmore & Picard, *Establishing and Maintaining Long-Term Human-Computer Relationships*. 101명의 참가자가 한 달 동안 매일 시스템을 사용했고 relational version을 더 좋아하고 신뢰하며 계속 사용하고 싶어 했다. | 강함 | embodied exercise agent 연구이며 현대 LLM assistant와 동일하지는 않음 |
| 인간적인 대화 인터페이스는 실제 능력이 따라가지 못하면 오히려 기대 불일치를 만든다. | Luger & Sellen, CHI 2016, *Like having a really bad PA*. | 중간~강함 | 소규모 정성 연구이고 pre-LLM 시대 |
| 짧고 적절한 acknowledgement는 engagement를 높일 수 있지만 상태 메시지가 많을수록 좋은 것은 아니다. | Jang, Shin & Gweon, EMNLP Findings 2024. | 중간 | 상담형 대화 연구이며 task execution과 동일하지 않음 |
| repair는 자연스러운 대화에서 예외 상황이 아니라 정상적인 상호작용이다. | SIGDIAL 2024의 repair-initiation 연구 등 | 중간 | 언어학적 성격이 강하며 제품 UX 실험은 아님 |
| 불필요한 clarification을 줄이고 필요한 질문만 하는 것이 더 효율적이다. | Shekhar et al., COLING 2018, *Ask No More* | 중간 | visual dialogue task |
| 장기 memory는 continuity에 중요하지만 단순히 대화 기록을 많이 넣는 것만으로 해결되지 않는다. | 최근 ACL long-term memory 연구, TiMem 등 | 중간~강함 | benchmark가 presence 자체를 측정하지는 않음 |
| 현대 AI 제품들은 conversational memory와 inspect/correct/manage surface를 함께 제공하는 방향으로 가고 있다. | OpenAI Memory, Gemini past chats, Siri personal context | 강한 제품 패턴 | presence와의 직접 인과는 증명하지 않음 |
| Permission은 매우 context-sensitive하다. | Wijesekera 등의 USENIX Security permission field study | 강함 | 스마트폰 permission 연구이며 desktop folder/OAuth와 완전히 같지는 않음 |
| Settings는 개별 작업을 시작하기 위한 tutorial이라기보다 지속적인 preference/management surface에 더 적합하다. | Apple HIG Settings, Raycast Settings | 강한 디자인/제품 근거 | AgentOS에서의 직접 실험은 아님 |
| Failure message는 generic error label보다 무슨 일이 있었고 무엇을 할 수 있는지를 설명해야 한다. | Apple HIG Alert guidance | 강한 설계 가이드 | 통제 실험은 아님 |
| Proactivity는 살아 있는 느낌을 강화할 수 있지만 presence의 필수조건은 아니다. | Ameenza, Raycast Automations, Bickmore/Picard 비교 | 중간 | proactivity 자체의 인과 효과를 직접 측정한 것은 아님 |
| 하나의 interaction identity 아래 여러 model/tool을 둘 수 있다. | Raycast AI, Siri orchestration 등 | 강한 아키텍처적 선례 | 모든 multi-agent system에 그대로 적용된다는 뜻은 아님 |

### 가설 평가

H1, 즉 presence가 raw intelligence보다 continuity, memory, responsiveness, availability에서 주로 나온다는 가설은 **조건부로 지지**됩니다. “더 중요하다”라는 인과관계 자체가 실험적으로 완전히 증명된 것은 아니지만, 제품 가설로서는 상당히 강합니다.

H2, 내부 Work/tool/connector가 사용자에게 직접 말할 필요가 없으며 하나의 assistant voice가 이를 번역해야 한다는 가설은 **강하게 지지**됩니다.

H3, conversation이 intent surface이고 Settings가 management/review surface가 되어야 한다는 가설 역시 **강하게 지지**됩니다.

H4, 짧은 task에서 queued/running/completed를 계속 보여주는 것이 presence를 오히려 해친다는 주장은 **현재 제품의 실제 dogfooding 증거가 매우 강하며 외부 연구도 방향을 지지**합니다.

H5, failure를 시스템 상태명으로 보여주기보다 “무슨 일이 있었는지 + 다음에 할 수 있는 것”으로 설명하는 것이 낫다는 가설은 **강하게 지지**됩니다.

H6, contextual setup/just-in-time permission이 up-front Settings configuration보다 적절하다는 것도 **특히 현재 작업에 필요한 권한의 경우 강하게 지지**됩니다. 단, 장기 계정 설정과 같은 것은 여전히 Settings에 있을 수 있습니다.

H7, proactivity는 presence를 강화할 수 있지만 필수조건은 아니라는 가설은 **지지**됩니다.

H8, persistent assistant identity 아래 여러 specialist worker를 숨기는 것이 AgentOS에 잘 맞는다는 가설은 **아키텍처적으로 매우 강하게 맞습니다.**

---

# Presence 모델

Presence를 한 가지 visual feature나 말투로 정의하면 안 됩니다.

Personal AgentOS에서는 다음과 같이 이해하는 것이 좋습니다.

**Presence = Continuity + One Voice + Situational Responsiveness + Memory + Availability + Conversational Recovery**

그리고 여기에 두 가지가 강제 조건으로 들어갑니다.

**Truthfulness**  
**Owner authority**

Proactivity는 이 식의 필수항이 아니라 **선택적 증폭기**입니다.

### Continuity

새 turn이 최근 대화, 진행 중이거나 실패한 Work, correction, approval 상태를 참고해야 합니다.

실패 예:

`자 다시 되니?`

를 전혀 새로운 요청으로 취급하는 경우입니다.

### One Voice

AgentOS가 outbound wording과 identity를 소유해야 합니다.

Codex, Claude Code, Gmail connector, MCP tool, Calendar worker는 실행 주체이지 별도의 대화 상대가 아닙니다.

실패 예:

“subscription engine이 실패했습니다.”

처럼 내부 worker가 직접 사용자와 말하는 구조입니다.

### Situational Responsiveness

상황에 필요한 메시지만 보내야 합니다.

짧은 작업은 바로 답하고, 오래 걸리는 작업은 필요한 경우 한 번 acknowledgement를 하고, 권한이 필요한 경우 approval을 요청합니다.

모든 요청에 똑같은 lifecycle message를 보내는 것은 실패입니다.

### Memory

허용된 persistent preference와 이전 맥락을 활용해 반복을 줄여야 합니다.

그러나 memory는 inspect, correction, revoke가 가능해야 합니다.

### Availability

worker/model이 바뀌어도 같은 assistant relationship이 유지되어야 합니다.

Codex에서 API model로 바꾸는 것이 “새 assistant를 만나는 것”처럼 느껴져서는 안 됩니다.

### Conversational Recovery

실패, ambiguity, cancellation, partial result가 대화의 끝이 아니라 다음 turn으로 자연스럽게 이어져야 합니다.

“웹 콘솔에서 확인하세요”가 기본 복구 경로가 되면 presence가 깨집니다.

### Appropriate Proactivity

필요한 경우 먼저 말할 수 있지만 relevance, authority, timing이 정당화될 때만 가능합니다.

단순히 alive처럼 보이기 위해 heartbeat notification을 보내면 오히려 역효과입니다.

---

# Presence를 깨는 현재 Anti-pattern

| Anti-pattern | 문제 | 원하는 형태 |
|---|---|---|
| 모든 natural-language message가 visible Work card가 됨 | scheduler와 대화하는 느낌을 만듦 | Work는 내부에 유지하고 필요할 때만 노출 |
| 짧은 질문에도 received → running → completed → result | 결과보다 lifecycle이 더 큰 비중을 차지 | 즉시 답변 |
| engine 이름이 직접 말함 | worker와 assistant identity가 뒤섞임 | AgentOS assistant가 말하고 engine은 상세 정보에 표시 |
| failure의 기본 복구가 “웹을 열어라” | 대화 연속성이 가장 필요한 순간 끊김 | 대화 안에서 문제와 다음 행동 설명 |
| Settings-first connector/folder setup | 사용자가 필요도 알기 전에 architecture를 공부함 | task 발생 → contextual handoff → resume |
| raw capability ID 표시 | 기술 상태를 사용자가 해석해야 함 | Gmail, Drive 등 인간 친화적 서비스 상태 |
| configured/connected/active 혼동 | 실제로 어떤 AI가 실행될지 예측 불가능 | 현재 사용 중 / 사용 가능 / 설정됨을 구분 |
| failure/model change 이후 context 손실 | relationship이 stateless하게 느껴짐 | prior Work를 이어받음 |
| smooth language가 evidence를 덮음 | 자연스러워 보여도 신뢰 파괴 | Evidence가 먼저, 표현은 나중 |
| persona setting을 continuity 대용으로 사용 | 친근한 말투가 broken service를 가림 | tone과 continuity는 분리 |

---

# 제품 원칙 8개

**Conversation first; receipts on demand.**  
사용자가 먼저 보아야 하는 것은 유용한 답입니다. 기술 기록은 원하면 볼 수 있어야 합니다.

**One assistant voice over many workers.**  
model, CLI, connector, specialist가 몇 개이든 사용자는 한 AgentOS assistant와 대화합니다.

**Continue before restarting.**  
새 Work를 만들기 전에 이전 대화와 unresolved Work의 후속인지 먼저 판단합니다.

**Communicate semantic progress, not scheduler state.**  
“queued/running/completed”가 아니라 사용자에게 의미 있는 상태만 말합니다.

**Truth before fluency.**  
failed/partial/unknown/approval pending이 먼저 response를 제한하고 그 다음 자연스러운 표현을 적용합니다.

**Ask at the moment of need; manage afterward.**  
권한은 실제 필요해지는 순간 요청하고 Settings는 이미 생긴 연결/권한을 관리합니다.

**Memory must be useful, scoped and correctable.**  
Memory는 continuity를 돕되 silently permanent profile이 되어서는 안 됩니다.

**Proactivity must earn the interruption.**  
먼저 말을 거는 것은 가치와 권한이 정당화될 때만 합니다.

---

# 대화 예시

## A. 간단한 질문

현재:

“요청을 받았습니다.”  
“처리 중입니다.”  
“완료되었습니다.”  
“내일 첫 일정은 오전 10시입니다.”

목표:

“내일 첫 일정은 오전 10시예요.”

내부적으로 Work가 존재해도 사용자에게 lifecycle을 모두 보여줄 필요는 없습니다.

## B. model/runtime 실패

현재:

“구독 엔진이 작업을 완료하지 못했습니다.”  
“AgentOS 웹에서 실행 기록을 확인하세요.”

목표:

“아직 완료하지 못했어요. 지금 사용 중인 AI 연결에서 실행이 실패했고, 이번 시도의 내용은 결과로 취급하면 안 됩니다. 다시 시도하거나 다른 AI 연결로 바꿀 수 있어요.”

engine 이름은 해결에 실제로 필요할 경우만 상세로 보여줍니다.

## C. “자 다시 되니?”

현재:

새 독립 task로 들어가 같은 오류 sequence를 반복.

목표:

“방금 실패한 요청으로 다시 해볼게요.”

성공하면 결과를 말하고, 같은 오류라면:

“아직 같은 AI 연결에서 실패하고 있어요. 요청은 완료되지 않았습니다.”

retry 관계는 내부 Evidence에 남습니다.

## D. Gmail disconnected

“이 작업에는 Gmail 읽기 권한이 필요해요. Mac에서 Gmail을 연결하면 이어서 영수증을 찾을게요.”

`[Gmail 연결]`

성공:

“연결됐어요. 아까 요청하신 영수증을 계속 찾을게요.”

원래 Work는 exactly once resume됩니다.

## E. Local folder 필요

“계약서가 있는 폴더를 읽을 권한이 필요해요. 이 Mac에서 폴더를 선택해 주세요. 읽기 권한만 요청할게요.”

`[Mac에서 폴더 선택]`

Telegram이 직접 filesystem 권한을 갖는 것이 아니라 local approval surface가 처리합니다.

## F. Calendar 승인

“다음 일정을 만들 준비가 됐어요.

치과  
9월 25일 오전 10시~11시

참석자 초대는 없습니다.

만들까요?”

`[만들기] [취소]`

Approval은 정확한 effect preview에 묶여야 합니다.

## G. 오래 걸리는 연구

“현재 옵션과 출처를 확인해서 비교해볼게요. 준비되면 여기서 알려드릴게요.”

그 뒤 meaningful state가 생길 때만 update합니다.

## H. Partial result

“영수증 3개는 확인했어요. 다만 이전 Gmail 결과는 연결 문제 때문에 확인하지 못했습니다. 확인된 3개부터 보여드릴게요.”

partial과 success를 구분합니다.

## I. Unknown external effect

“Calendar 요청은 전송했지만 응답이 끊겨서 일정이 실제로 만들어졌는지 확인할 수 없어요. 중복 생성 위험이 있어서 자동으로 다시 만들지는 않을게요. 먼저 Calendar 상태를 확인하겠습니다.”

Unknown은 failure와도 다릅니다.

## J. Memory correction

사용자:

“아니, 난 채식주의자는 아니고 평일에 소고기만 안 먹어.”

실제로 canonical Memory가 업데이트됐다면:

“수정했어요. 평일에는 소고기를 피하는 선호를 현재 기준으로 기억할게요.”

아직 approval pending이라면:

“수정 내용을 준비했지만 아직 지속적인 기억으로 저장되지는 않았어요. 승인하면 반영됩니다.”

---

# Surface 책임 모델

| Surface | 역할 | 해서는 안 되는 것 |
|---|---|---|
| Telegram / Conversation | 자연어 intent, clarification, repair, answer, contextual handoff, 의미 있는 progress, recovery, 필요한 approval | Work.status와 engine log를 그대로 보여주는 operations console |
| Local approval | filesystem picker, read/write grant, owner-bound OAuth, consequential preview, allow/deny | Telegram link 하나로 Mac 권한을 바로 부여 |
| Settings | AI route, connector, folder grant, Memory와 preference의 inspect/manage/revoke/change | ordinary task를 하기 전에 꼭 공부해야 하는 onboarding |
| Task/Evidence detail | Work timeline, exact state, worker/tool ID, sources, error, approval, partial/unknown detail | 모든 failure의 기본 응답 화면 |
| Internal kernel | Work/Event/Evidence/Context/Memory/Grant/effect state/idempotency/routing | 사용자에게 보이는 personality |

---

# Settings에 대한 연구 결론

외부에서 참고해야 할 것은 특정 브랜드의 visual style이 아니라 **interaction grammar**입니다.

Apple HIG와 Raycast 같은 제품은 Settings를 related configuration을 안정적으로 관리하는 surface로 사용합니다.

AgentOS는 기본적으로 이런 식이 적절합니다.

```text id="m7ic5z"
AI

Codex                현재 사용 중        관리
OpenAI API           사용 가능           사용
Claude Code          사용 가능           사용

외부 연결

Telegram             연결됨              관리
Gmail                연결 안 됨          연결
Google Calendar      연결됨              관리
Google Drive         다시 연결 필요      다시 연결

폴더

계약서               읽기 권한           관리
Reports              파일 생성 권한      관리
```

provider endpoint, credential verification time, connector ID, scopes, capability ID, grant ID 등은 `세부 정보` 안에 있을 수 있습니다.

없애는 것이 아니라 **기본 사용자 scan path에서 뒤로 보내는 것**입니다.

#504에서 특히 중요한 점은:

**configured는 currently used와 절대 같은 의미로 보이면 안 됩니다.**

---

# 아키텍처 영향

이번 연구는 새로운 kernel architecture를 만들 근거를 제공하지 않습니다.

오히려 대부분은 **conversation/presentation policy layer와 약간의 continuity state**로 해결할 수 있습니다.

AgentOS에는 이미 필요한 핵심 개념이 있습니다.

현재:

```text id="hjr6xu"
internal state
    → task/status renderer
        → Telegram
```

목표:

```text id="2jyf42"
internal state
+ conversation focus
+ relevant memory
    ↓
truth / authority gate
    ↓
conversation projection policy
    ↓
Telegram
```

동시에:

```text id="2k64yx"
internal state
    → technical projection
        → Task / Evidence detail
```

그리고:

```text id="lgk4qn"
canonical configuration
    → preference projection
        → Settings
```

### Work

계속 durable execution/recovery unit로 유지합니다.

다만 모든 Work가 Telegram에서 visible task card가 되어야 할 이유는 없습니다.

### Event

실행 chronology는 유지합니다.

그러나 사용자에게는 다음처럼 의미 있는 event만 기본적으로 노출합니다.

권한 대기, 중요한 진척, blocker, partial completion, completion, cancellation, unknown effect.

### Evidence

consequential result claim의 기준이어야 합니다.

model prose가 Evidence보다 먼저 결과를 결정하면 안 됩니다.

### Memory / conversation focus

새 memory store를 만들지 않습니다.

`자 다시 해봐` 같은 short-horizon reference와 지속적 preference Memory는 서로 다른 scope입니다.

### Connector / Grant

내부의 정확한 state와 ID를 유지합니다.

owner-facing projection만 다음처럼 바꿉니다.

`연결됨`  
`연결 안 됨`  
`다시 인증 필요`  
`읽기 허용`  
`쓰기 허용`

### Approval

Conversational smoothness를 위해 제거할 friction이 아닙니다.

오히려 더 contextual하게 보여줘야 합니다.

무엇을, 어디에, 어떤 범위로 실행할지를 보여주고 승인합니다.

### Telegram adapter

scheduler vocabulary renderer 역할을 줄이고 product-owned conversation projection을 전달해야 합니다.

### Web management utility

conversation client로 확장할 필요가 없습니다.

관리와 Evidence inspection 역할을 유지하는 것이 맞습니다.

### Model/runtime selection

#504의 functional owner-control contract를 유지합니다.

선택된 실행 route는 명시적이어야 하고, worker가 바뀌어도 “누구와 대화하고 있는가”는 바뀌지 않아야 합니다.

### Attention

#383의 Attention은 basic reactive presence 이후입니다.

Presence를 만들기 위해 heartbeat부터 만들 필요는 없습니다.

---

# Keep / Change / Later

### KEEP

AgentOS-owned Work/Event/Evidence truth model, Grant와 Approval, exact external-effect semantics, unknown outcome 자동 재시도 금지, replaceable runtime 구조, 현재 Memory/MemoryCandidate ownership, local web의 management/evidence utility 역할은 유지해야 합니다.

### CHANGE NOW

Telegram lifecycle narration을 semantic conversation projection으로 바꾸는 것, 이전 Work와 follow-up/recovery를 연결하는 것, failure/partial/unknown 표현을 대화적으로 바꾸되 truthfulness를 유지하는 것, contextual capability handoff, #504의 effective AI route control, #506의 Settings grammar, #494의 truth-qualified history가 우선입니다.

### LATER

Attention/heartbeat/background preparation, multi-person collaboration, sophisticated notification ranking, rich persona customization은 이후 문제입니다.

Presence의 prerequisite로 만들면 안 됩니다.

---

# 기존 Issue 정리

| Issue | 판단 |
|---|---|
| #381 | PRESENCE-01의 설계/연구 predecessor. 일부 범위가 이미 포함되어 있음 |
| #383 | 별개. Attention/proactivity의 후속 문제 |
| #480 | Presence epic의 child로 흡수하는 것이 적절. 단순 카피 수정으로 닫으면 안 됨 |
| #476 | 이미 해결된 truthfulness invariant. 다시 열지 않고 regression constraint로 유지 |
| #488 | 완료된 Memory truthfulness invariant |
| #494 | 여전히 별도의 open truth/history defect |
| #504 | 새 issue를 만들지 말고 기존 issue를 child로 사용 |
| #505 | 기존 issue를 contextual capability handoff child로 사용 |
| #506 | 기존 issue를 Settings grammar child로 사용 |
| #386 | 완료된 역사적 foundation. 다시 열지 않음 |
| #393 | 완료된 natural handoff/exactly-once foundation. mechanism을 재사용 |

따라서 PRESENCE-01은 새로운 architecture epic보다 **experience convergence epic**이어야 합니다.

---

# 권장 Child 구조

| 순서 | Work unit | 내용 |
|---|---|---|
| 1 | PRESENCE-CONV-01 | one voice conversational projection. #480을 흡수하고 #476/#488 invariant 유지 |
| 2 | PRESENCE-CONT-01 | “자 다시 되니?”, correction/reference, failed-turn recovery, worker switch continuity |
| 병렬 가능 | #504 | effective AI route |
| 병렬 가능 | #505 | contextual folder/local authority handoff |
| 병렬 가능 | #506 | Settings preferences grammar |
| 필수 integrity | #494 | truth-qualified conversation history |
| 통합 | PRESENCE-EVAL-01 | A~J transcript acceptance matrix + owner dogfood |
| Later | #383 successor | Attention/proactivity |

---

# 가장 먼저 구현할 Slice

첫 구현은 Settings 재설계보다 **PRESENCE-CONV-01: conversational projection + recovery**가 좋습니다.

하나의 완전한 owner loop를 개선해야 합니다.

사용자 메시지가 들어오면 먼저 direct reply인지, clarification인지, capability handoff인지, long-running acknowledgement인지, approval인지 판단합니다.

내부 Work는 그대로 유지합니다.

하지만 모든 Work lifecycle transition을 Telegram bubble로 만들지 않습니다.

최종 owner reply는 raw model output이 아니라 **outcome/Evidence 기반으로 생성**합니다.

즉시 이어지는 “자 다시 되니?”는 이전 failed Work에 연결됩니다.

가능한 safe next action은 conversation 안에서 제시합니다.

technical receipt는 계속 inspect할 수 있습니다.

### 최소 Acceptance

짧은 Telegram 요청은 queued/running/completed boilerplate 없이 한 번의 정상적인 답을 줘야 합니다.

긴 요청은 필요하다면 간결한 acknowledgement 하나와 이후 결과를 보낼 수 있지만 Event 개수와 message 개수를 기계적으로 연결하면 안 됩니다.

실패한 요청은 사실에 맞는 설명과 가능한 다음 행동을 줍니다.

`partial`과 `unknown`은 success와 명확히 구분합니다.

직전 실패 이후 “다시 해봐”는 관련 previous Work를 참조해야 합니다.

unknown consequential effect는 자동 재실행하지 않습니다.

engine/worker 이름은 speaking identity가 되면 안 됩니다.

실제 사용된 worker는 technical details에서는 확인할 수 있어야 합니다.

#476과 #488의 truthfulness regression은 계속 통과해야 합니다.

그리고 중요한 점은 **internal status test만으로 완료를 판정하지 말고 실제 사용자가 보는 Telegram transcript를 acceptance evidence로 사용해야 한다**는 것입니다.

---

# GitHub Issue 초안

## PRESENCE-01: Make Personal AgentOS feel like one continuous personal assistant

### User outcome

사용자는 Telegram에서 Personal AgentOS와 **하나의 지속적인 개인 비서**처럼 대화할 수 있어야 한다.

내부 job, model, connector, tool은 바뀔 수 있지만 사용자가 execution architecture를 이해해야만 대화를 이어가거나 실패에서 복구하거나 capability를 연결할 필요가 없어야 한다.

Local web은 management와 Evidence surface로 남으며 두 번째 대화 클라이언트가 되지 않는다.

### Problem

2026-09-23 실제 owner dogfooding에서 기능적으로 구현된 personal-assistant architecture가 여전히 operations system처럼 사용자에게 투영되고 있음이 확인되었다.

관찰된 사례:

일반적인 요청도 administrative task/status bubble을 만든다.

Failure가 “완료하지 못했습니다”와 generic result-status action으로 표현된다.

복구 과정에서 자연스럽게 대화를 계속하는 대신 AgentOS web으로 사용자를 보낸다.

“자 다시 되니?” 같은 follow-up이 직전 실패의 continuation이 아니라 또 하나의 독립 job처럼 느껴진다.

AI configuration은 저장되어 보여도 실제 실행 route는 Codex에 남는다.

Local file 사용 전 Settings에서 raw path를 구성해야 한다.

External connection Settings가 내부 capability identifier를 노출한다.

이는 #480의 한국어 문구 문제보다 크다.

**Kernel state와 owner-facing conversational state 사이의 projection mismatch**이다.

### Product definition of presence

> Presence란 여러 turn, worker, tool, capability handoff, failure, restart를 거치더라도 사용자가 하나의 지속적이고 맥락을 이해하는 개인 비서와 관계를 이어간다고 느끼는 경험이며, 그 아래에서는 AgentOS가 truthful Evidence, explicit owner authority, inspectable technical state를 계속 소유하는 것이다.

### Principles

Conversation first; receipts on demand.

One assistant voice over many workers.

Continue before restarting.

Communicate semantic progress, not scheduler state.

Truth before fluency.

Ask at the moment of need; manage afterward.

Memory is scoped, inspectable and correctable.

Proactivity must earn interruption.

### Scope

Telegram conversational projection, short/long-work communication policy, follow-up/recovery continuity, failure/partial/unknown conversation, contextual capability handoff, assistant identity와 worker identity의 분리, Settings의 management 역할, explicit effective AI route, coherent Settings state/action grammar, technical receipts on demand, deterministic owner-visible acceptance scenario를 포함한다.

기존 issue가 이미 소유하는 구현은 새로 만들지 않고 해당 issue를 사용한다.

### Non-goals

Work/Event/Evidence/Grant/Memory를 새 conversation DB로 대체하지 않는다.

Approval과 owner authority를 약화하지 않는다.

Unknown consequential effect를 자동 재시도하지 않는다.

다른 paid provider로 silent fallback하지 않는다.

Heartbeat/Attention/background monitoring을 prerequisite로 만들지 않는다.

Instinct나 다른 제품을 복제하지 않는다.

Human/conscious being인 것처럼 속이지 않는다.

새 UI framework를 필수로 하지 않는다.

기술 Evidence를 owner에게 숨기지 않는다.

### Acceptance

짧은 Telegram 요청은 routine queued/running/completed bubble을 만들지 않는다.

Internal audit/recovery state는 그대로 유지한다.

Long-running request에는 필요할 경우 의미 있는 acknowledgement 하나가 가능하다.

Progress는 observed execution state에 기반해야 한다.

engine/tool/connector ID가 ordinary conversation에서 speaking identity가 되어서는 안 된다.

“자 다시 해봐”는 이전 failed Work에 연결된다.

Correction은 stale intent가 이후 실행되지 않게 한다.

Failed Work의 model prose는 검증되지 않은 결과로 노출되지 않는다.

Partial result는 확인된 부분과 실패한 부분을 분리한다.

Unknown external effect는 unknown으로 표현하고 자동 재시도하지 않는다.

가능한 safe recovery action은 Telegram에서 제시한다.

Web은 secondary inspection surface다.

Missing connector/folder authority는 contextual next action을 제공한다.

Filesystem selection은 owner-local surface에서 이루어진다.

successful handoff 이후 original Work가 exactly once resume된다.

Settings에는 exactly one effective AI route가 표시된다.

configured / available / currently used / needs attention을 구분한다.

worker가 바뀌어도 assistant identity는 유지된다.

AI, file, external connection Settings는 하나의 일관된 state/action grammar를 사용한다.

MemoryCandidate는 실제 저장되기 전에는 “기억했다”고 말하지 않는다.

### Evidence

A~J scenario에 대한 deterministic Telegram transcript.

실제 bubble 수와 순서.

Owner-visible claim과 Evidence의 일치 확인.

success/failed/partial/unknown opposing tests.

retry/reference tests.

필요한 restart tests.

AI route tests.

capability handoff deny/expiry/wrong-owner/replay tests.

Settings browser tests.

#476/#488 truthfulness regression 유지.

Synthetic evidence와 live owner validation은 구분한다.

### Child plan

PRESENCE-CONV-01 → PRESENCE-CONT-01 → #504/#505/#506/#494 병행 → PRESENCE-EVAL-01 순으로 진행하는 것이 적절합니다.

#383 Attention은 그 이후입니다.

### Completion rule

PRESENCE-01은 accepted child scope가 merge되거나 명시적으로 re-scope되고, A~J owner-visible acceptance matrix가 exact integration head에서 통과하며, short conversation이 task-lifecycle chatter를 기본값으로 사용하지 않고, prior failure와의 conversational recovery가 작동하고, contextual capability handoff가 Settings-first onboarding 없이 작동하며, effective AI route가 명확하고, Settings가 하나의 management grammar를 사용하고, failed/partial/unknown이 Telegram과 management/history 양쪽에서 truthful하며, worker 변경에도 하나의 assistant identity가 유지되고, Work/Event/Evidence가 계속 inspect 가능할 때 완료로 간주합니다.

---

연구의 마지막 문장이 전체 방향을 잘 요약합니다.

> 목표는 “더 인간적으로 말하는 chatbot”이 아니다.  
> **기계적이고 엄격한 owner-controlled kernel은 그대로 유지하면서, 그 복잡성이 하나의 지속적이고 사실에 충실한 개인 비서 관계 뒤로 물러나게 하는 것이다.**
