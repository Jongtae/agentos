# D-MP2-02 — 검토된 Capability 발견 및 추천 계약

> **과거 참고용 한국어 번역본.** 내부 개발 기준은 [영어 원본](d-mp2-02-capability-discovery-contract.en.md)을 따른다. 이 계약의 원래 권한은 owner-local read-only 추천까지였으며 marketplace 발견, download, installation, activation, credential 설정, permission Grant 또는 실행을 승인하지 않았다. 계획된 Agent Distribution Platform(#333)과 D-REG-01(#339)는 후속 계약이며 D-MP2-02가 과거에 구현·증명한 범위를 소급해 넓히지 않는다.

## 목표와 범위

소유자가 요청한 결과를 enable된 AgentOS capability가 안전하게 처리할 수 없을 때, AgentOS는 owner-local reviewed catalogue에서 검토된 MCP, 독립 A2A Agent, 격리 runtime을 추천할 수 있다. AgentOS는 추천과 경계를 설명할 뿐 download, install, activation, connection, execution을 하지 않는다.

이 문서는 contract-only 설계다. marketplace, network discovery, plugin download, capability install/activation, permission/scope grant, credential/OAuth flow, endpoint, external action, operating deployment을 구현하지 않는다.

## 소유자 결과와 추천 경계

소유자는 connector가 아니라 결과를 요청한다. AgentOS는 먼저 enable된 reviewed capability를 확인하고, 처리할 수 없을 때만 0개 이상의 추천과 평이한 이유·안전한 다음 행동을 돌려준다. 추천은 R0 정보이며 capability state를 바꾸지 않는다. model suggestion, catalogue entry, 단순 “예”는 install 또는 approval이 아니다.

catalogue는 owner-local curated shipped/reviewed set이며 공개 marketplace나 live web search 결과가 아니다. unknown URL, unpinned version, unsigned manifest, arbitrary code, runtime-defined tool은 거절한다.

## Catalogue record와 ranking

각 reviewed record에는 opaque capability ID, kind(`mcp`, `a2a`, `runtime`), 사람 이름과 declared outcome tag, provenance publisher/source, fixed version과 immutable artifact digest, license, declared tool, required permission/OAuth scope/data category/outbound host/isolation profile/cost class/health-check contract/removal-recovery procedure/compatibility constraint가 있다.

ranking은 설명 가능하고 결정적이다: exact declared outcome tag, owner-enabled compatibility, 최소 data/permission surface, local-first/isolation 선호, 낮은 declared cost class, stable capability ID 순서다. private message body를 catalogue search term이나 ranking input으로 쓰지 않는다. 추천 read model은 name, kind, outcome reason, declared boundary summary, cost class, health/recovery label, 미래 approval handoff ID만 보이고 secret, raw path, token, package URL, arbitrary manifest payload, internal score는 제외한다.

## 정책과 데이터 흐름

향후 `CapabilityRecommendationOrchestrator`가 유일한 정책 소유자다. owner ID, bounded outcome class, 현재 reviewed capability state를 받아 redacted recommendation model과 audit evidence를 만든다. HTTP, Telegram, local companion은 같은 read-only operation을 호출한다. 어떤 channel도 package manager, MCP transport, A2A peer, runtime launcher, `CapabilityRegistry.transition`을 직접 호출하지 않는다.

추천 audit에는 최소 classified outcome tag만 보관한다. full prompt, Personal Space 내용, 선택 문서, approval material, 외부 system identifier, secret, raw recommendation request는 portable evidence/export에서 제외한다. Restore는 안전한 terminal recommendation history만 보존하며 install queue를 만들지 않는다.

## 위협 모델과 복구

구현은 prompt-injected catalogue entry, confused-deputy installation, poisoned metadata, version substitution, dependency/license drift, misleading cost claim, recommendation replay, channel/owner confusion, secret exfiltration을 막아야 한다. stale/unavailable/incompatible entry는 이름 있는 recovery 설명과 함께 제외하며 arbitrary alternative로 조용히 대체하지 않는다.

## 명시적 미래 install handoff

이후 설계 iteration은 선택한 recommendation의 exact fixed record, requested permission/data boundary, isolation, cost, health check, removal/recovery plan을 보인 뒤에만 owner-visible approval/install handoff를 정의할 수 있다. 그 미래 contract는 명시 소유자 확인과 download integrity, activation, credential/OAuth configuration, rollback, live acceptance를 별도로 다뤄야 한다. D-MP2-02는 그 권한을 주지 않는다.

## I-MP2-02 진입 계약

I-MP2-02는 이 design PR merge, issue close, 영어 원본 문서/plan/ledger check, 새 goal-ready implementation issue 뒤에만 활성화할 수 있다. 최소 범위는 fixture-backed owner-local reviewed catalogue, deterministic ranking, redaction, audit/export/restore safety, HTTP/Telegram/local-companion parity를 가진 read-only recommendation model이다. 모든 installation, activation, connection, permission, scope, credential, OAuth, external action, operating-mode behavior는 제외한다.
