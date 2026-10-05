# Personal AgentOS — 재사용 검토와 적용 대장 v0.2

작성일: 2026-10-05 · 연결 원고: 역할 기반 온톨로지와 위임 모델 v0.3 · 추가 검토: 11–20차

## 판단 요약

목표는 독창성의 증명이 아니라 기존 축적을 써서 사용자 일을 더 잘 끝내는 것이다. 이번에는 **내용·기준의 채택/조정**과 **현재 코드 접점의 대조**를 수행했다. 런타임 설치·이식·성능 실험은 수행하지 않았다. ‘자료가 있다’와 ‘쓸 수 있다고 검증했다’를 구분한다.

v0.1 보완서의 F28(실질적 선행·재사용 비교 누락)은 아래의 요구별 적용 판단, 현재 소스 확인, 본문 수정과 V7 최종 게이트로 검토한다. 과거 10차 승인을 자동으로 복원하지 않는다.

## 요구별 채택·조정·보류

### A01 · 역할 의미의 일관성

**참조:** X01, S1, S2 · **접점:** 공통 대상과 역할 해석

**판단:** Adapt. **이번 반영:** 3·4·5장에 관계적 역할/관점/인가/페르소나 구분과 매핑 상태를 반영.

**경계:** OntoUML 실행 엔진·범세계 온톨로지 도입 없음. **다음 확인:** 같은 대상의 역할 교체와 이름 충돌 반례.

### A02 · 요청을 책임과 완료까지 연결

**참조:** X02 · **접점:** 기존 Work/Event 의미

**판단:** Adapt. **이번 반영:** 6·10장에 역할 채택·수락·이행 구분과 한 원고의 수정 책임을 반영.

**경계:** MOISE 서버·Java/CARTAGO/NPL 설치 없음. **다음 확인:** 요청만 있는 사례·무응답·미션 취소와 부분 완료.

### A03 · 위임을 실행 허용과 혼동하지 않기

**참조:** X03, X04, R1 · **접점:** 기존 Grant/Approval

**판단:** Adapt for semantics; runtime defer. **이번 반영:** 6장에 ODRL 부분 매핑·Cedar 오류 진단 반례 반영.

**경계:** 현재 인가 엔진 교체·pilot 규칙 되돌림 없음. **다음 확인:** 실제 외부 정책 연동 요구가 생길 때 입력/진단/철회 시험.

### A04 · 역할별 수행 지침 재사용

**참조:** X06, R2, R3, R4 · **접점:** SkillLibrary/SkillBinding/기존 manifests

**판단:** Adopt existing seam; Adapt content. **이번 반영:** 12·13장과 1개 writing-review 텍스트 스킬 예제.

**경계:** 스킬 설치·활성화·별도 에이전트 실행 없음. **다음 확인:** 승인된 환경에서 한 스킬·리소스 로드와 같은 요청 대조.

### A05 · 개인 상황 중심 분석 절차

**참조:** X05, X13 · **접점:** Owner 목표·허용된 자료·분석 산출물

**판단:** Adapt practice; terminology mapping candidate. **이번 반영:** 9·12장에 상황/목표/대안/실행책임/후속 범위 브리프.

**경계:** FIBO 클래스 확정·거래권한·금융서비스 자격 미검증. **다음 확인:** 선택 도메인 URI 매핑과 가상 데이터 분석 누락 점검.

### A06 · 비서 업무 영역 누락 점검

**참조:** X12 · **접점:** 향후 역할의 업무 질문

**판단:** Limited reference. **이번 반영:** 12장에 제한된 범위 확인용 참조와 접근 실패 기록.

**경계:** 상세 BOK 미열람; 강제 체크리스트·시험비중 채택 없음. **다음 확인:** 상세 지침을 실제 사용할 때 공식 본문·사용조건 확인.

### A07 · 주장과 근거의 추적

**참조:** S4, R1 · **접점:** Artifact/Work/Evidence 식별자

**판단:** Adapt. **이번 반영:** 11장과 source/adoption/approval 기록 구조.

**경계:** 새 RDF 저장소·독립 검토 인증 없음. **다음 확인:** 같은 모델 요약의 중복 인용·원문 개정·근거 철회.

### A08 · 개인 상태의 의미 보존

**참조:** X07, X08 · **접점:** 기존 개인 상태의 소유 원칙

**판단:** Adapt requirements; runtime defer. **이번 반영:** 11장에 보존/변환/누락/재승인 검토 구분.

**경계:** Pod·AgentFile converter·보편 무손실 이전 미구현. **다음 확인:** 구체적 이전 대상이 선택될 때 왕복·누락·권한 재연결.

### A09 · 실질적 검토와 재작성

**참조:** X09, R1 · **접점:** 기존 조정 루프·이번 문서 검토

**판단:** Adapt. **이번 반영:** 12·14장, 8개 페르소나의 V7 재사용 게이트와 E6 실제 적용 기준.

**경계:** LangGraph 설치·독립 모델 호출·모든 요청 10회 검증 없음. **다음 확인:** 허용된 예산의 작은 대조 작업에서 실제 발견/누락 집계.

### A10 · 재개와 외부 효과 구분

**참조:** X10, X11, R4 · **접점:** Work/버전/unknown 현재 경계

**판단:** Adapt test criteria. **이번 반영:** 13·14장에 스킬 철회 중단·버전 변경·재개 반례.

**경계:** 체크포인트만으로 외부 exactly-once 주장 없음. **다음 확인:** 선택된 복구 경계에서 중복 요청·철회·효과 미확인 시험.

## 검색·접근과 증거 범위

입력 v0.2와 선행 비교 v0.1을 보존하고, 연결된 공개 1차 자료를 확인했다. 현재 저장소의 검색 인덱스는 `skill` 검색에서 결과를 주지 않아, 확인된 경로를 GitHub 연결 도구로 읽었다. main의 기준 SHA는 735bfebe4a1555d4e8b7e4ce0acbc94fbd1f4e89였다. AGENTS.md와 준비 명세, manifests.py 및 skills.py의 선택 구간을 대조했다. 보완서의 잠정 판단을 근거 없이 실행 가능으로 승격하지 않았다.

IAAP 직접 본문은 접근 실패했고 공식 검색 발췌만 사용했다. MOISE 기본 문서는 읽었지만 include된 예제 원본·API 링크 전체를 확인하지 못했다. AgentFile의 V1 SDK 안내는 legacy이며 최신 통합의 증거로 사용하지 않는다. 외부 후보의 전체 소스 감사, 릴리스별 설치 시험, 라이선스 적합성 판정, 보안 감사와 운영 성능 측정은 이뤄지지 않았다. 이는 실패를 감추기 위한 N/A가 아니라 이번 적용 결정이 **콘텐츠와 의미 수준**에 머무르는 구체적인 경계다.

## 기존 보완서와 참조 번호 대응

보완서 v0.1의 S1→X01; S2·S3→X02; S4→X03; S5→X04; S6→X05; S7→X06; S8→X07; S9·S10→X08; S11→X09; S12→X11; S13→X10; S14→S4(PROV-O). 새 원고의 S1–S4는 W3C 의미/검증 자료다. X12·X13과 R2–R4는 이번 추가 검토에서 전문 실무와 실제 접점을 보강한다.

## 출처 대장

각 항목에는 확인한 범위, 적용 절, 무엇을 뒷받침하는지와 보장하지 않는 것을 남긴다. 확인일은 모두 2026-10-05. 최신 문서 링크는 변경될 수 있으며, 실제 실행 채택 시 정확한 버전·사용 조건·보안·호환성을 다시 확인한다. JSON 원장은 같은 레코드를 기계적으로 읽기 위한 표현일 뿐 별도의 실행 엔진이 아니다.

### [S1] W3C — OWL 2 Primer, Second Edition

[1차 자료](https://www.w3.org/TR/2012/REC-owl2-primer-20121211/)

**판본/범위:** 2012-12-11; §§2–5

**증거 수준:** 공식 판본 본문 · **원고 연결:** 02–05장

**지원하는 내용:** 개체·클래스·속성·공리 및 개방세계 의미를 참조한다.

**프로젝트 판단:** 의미 정의에 참고(Adapt)

**한계:** DB 검증·인가 또는 AgentOS 품질 개선의 증거가 아니다.

### [S2] W3C — SKOS Reference

[1차 자료](https://www.w3.org/TR/2009/REC-skos-reference-20090818/)

**판본/범위:** 2009-08-18; §1.3

**증거 수준:** 공식 판본 본문 · **원고 연결:** 02·05장

**지원하는 내용:** 개념 조직과 형식 지식 표현을 구분한다.

**프로젝트 판단:** 용어 관계의 설명에 참고(Adapt)

**한계:** 프로젝트의 exact/partial 표기를 SKOS 공리라고 주장하지 않는다.

### [S3] W3C — SHACL

[1차 자료](https://www.w3.org/TR/2017/REC-shacl-20170720/)

**판본/범위:** 2017-07-20; §§1·3

**증거 수준:** 공식 판본 본문 · **원고 연결:** 02장

**지원하는 내용:** 조건 검증과 검증 보고서의 역할을 구분한다.

**프로젝트 판단:** 검증 책임의 설명에 참고(Adapt)

**한계:** 실행 권한·외부 사실의 진위를 보장하지 않는다.

### [S4] W3C — PROV-O

[1차 자료](https://www.w3.org/TR/2013/REC-prov-o-20130430/)

**판본/범위:** 2013-04-30; §3, Role/Plan/Delegation

**증거 수준:** 공식 판본 본문 · **원고 연결:** 05·11·12장

**지원하는 내용:** 원문·판단·결과와 수행 주체를 관계로 연결한다.

**프로젝트 판단:** 기존 기록 식별자에 의미를 대응(Adapt)

**한계:** 출처 관계만으로 진실·권한·독립성이 증명되지 않는다.

### [X01] OntoUML — Role

[1차 자료](https://ontouml.readthedocs.io/en/latest/classes/sortals/role/index.html)

**판본/범위:** latest 문서; Role 정의

**증거 수준:** 공식 프로젝트 문서 · **원고 연결:** 03·05장

**지원하는 내용:** 관계적 맥락의 역할과 대상 동일성을 구분한다.

**프로젝트 판단:** 역할 용어를 정밀화(Adapt)

**한계:** 전문적 관점·인가 역할·페르소나 전체가 같은 개념은 아니다.

### [X02] MOISE — ORA4MAS Basic Reference

[1차 자료](https://github.com/moise-lang/moise/blob/main/doc/ora4mas/readme.adoc)

**판본/범위:** blob 305e552446cf60a303b22eace2b61cb0322cec6f; Organisational perception / Example

**증거 수준:** 공식 저장소 본문 정적 읽기 · **원고 연결:** 05·06·10장

**지원하는 내용:** 역할 채택·미션 수락·목표·의무 이행의 구분과 집필 협업 예를 비교한다.

**프로젝트 판단:** 책임·완료 의미를 기존 Work 설명에 조정(Adapt)

**한계:** Java/CARTAGO/NPL 플랫폼을 설치하거나 예제를 실행하지 않았다. include된 원본들과 API 링크 전부를 확인하지 못했다.

### [X03] W3C — ODRL Information Model 2.2

[1차 자료](https://www.w3.org/TR/2018/REC-odrl-model-20180215/)

**판본/범위:** 2018-02-15; Policies, Offer, Agreement, Permission, Duty

**증거 수준:** 공식 판본 본문 · **원고 연결:** 05·06장

**지원하는 내용:** 행위·당사자·조건·의무와 정책 표현을 비교한다.

**프로젝트 판단:** Mandate 중 정책 표현 부분에 조정(Adapt)

**한계:** 개인 목표 전체·계약의 법적 효력·런타임 인가를 대체하지 않는다.

### [X04] Cedar — Authorization

[1차 자료](https://docs.cedarpolicy.com/auth/authorization.html)

**판본/범위:** 웹 문서; authorization algorithm / errors

**증거 수준:** 공식 프로젝트 문서 · **원고 연결:** 06·13장

**지원하는 내용:** principal/action/resource/context와 판단·집행 분리를 검토한다.

**프로젝트 판단:** 실행 인가 경계의 비교 기준; 엔진 채택 미선택

**한계:** 오류가 있는 정책을 건너뛸 수 있으므로 모든 오류가 자동 Deny인 것은 아니다. 진단·입력·매핑 시험 없이 교체하지 않는다.

### [X05] FIBO — Financial Industry Business Ontology

[1차 자료](https://spec.edmcouncil.org/fibo/)

**판본/범위:** About FIBO; 특정 ontology release 미선택

**증거 수준:** 공식 프로젝트 소개 · **원고 연결:** 05·09장

**지원하는 내용:** 금융 대상과 관계를 처음부터 새로 만들기 전 재사용 후보를 찾는다.

**프로젝트 판단:** 필요한 개념의 매핑 후보로 지정

**한계:** 정확한 클래스 URI 매핑·개인 투자전략·거래 호환성·성능은 미검증.

### [X06] Agent Skills — Specification

[1차 자료](https://agentskills.io/specification)

**판본/범위:** SKILL.md / optional directories / progressive disclosure

**증거 수준:** 공식 형식 문서 · **원고 연결:** 12·13장

**지원하는 내용:** 텍스트 지침과 references를 기존 로딩 경로에서 재사용한다.

**프로젝트 판단:** 기존 AgentOS 구현을 우선(Adopt), 역할 콘텐츠를 조정(Adapt)

**한계:** 형식 준수는 설치 승인·실행 권한·유용성 보장이 아니다. allowed-tools는 실험적 메타데이터.

### [X07] Solid Project — About

[1차 자료](https://solidproject.org/about)

**판본/범위:** About Solid

**증거 수준:** 공식 프로젝트 소개 · **원고 연결:** 11장

**지원하는 내용:** 데이터와 앱의 분리라는 관점을 개인 상태 소유에 참고한다.

**프로젝트 판단:** 이동성 요구를 정리하는 개념 참조

**한계:** Pod 도입·Work 이전·분산 동기화 구현을 선택하거나 검증하지 않았다.

### [X08] Letta — Agent File / AgentFile

[1차 자료](https://github.com/letta-ai/agent-file)

**판본/범위:** README + V1 SDK legacy 안내; 형식 릴리스 미고정

**증거 수준:** 공식 저장소·제품 문서 · **원고 연결:** 11장

**지원하는 내용:** 상태 내보내기의 범위와 누락 가능성을 비교한다.

**프로젝트 판단:** 보존·변환·누락·재승인 보고 기준에 조정(Adapt)

**한계:** 모든 프레임워크 간 무손실 변환·권한 이전은 미검증. https://docs.letta.com/v1-sdk/concepts/agent-file 는 legacy 문서다.

### [X09] LangGraph — Workflows and agents

[1차 자료](https://docs.langchain.com/oss/python/langgraph/workflows-agents)

**판본/범위:** Orchestrator-worker / Evaluator-optimizer

**증거 수준:** 공식 구현 안내·예제 읽기 · **원고 연결:** 10·12·14장

**지원하는 내용:** 위임·통합 및 평가·재작성 패턴을 비교한다.

**프로젝트 판단:** 기존 실행 조정과 편집 절차에 패턴 적용(Adapt)

**한계:** 라이브러리 설치·예제 실행·독립 에이전트 실행을 하지 않았다.

### [X10] LangGraph — Interrupts

[1차 자료](https://docs.langchain.com/oss/python/langgraph/interrupts)

**판본/범위:** Rules: side effects before interrupt; resume restarts node

**증거 수준:** 공식 구현 안내 · **원고 연결:** 14장

**지원하는 내용:** 재개 시 다시 실행될 수 있는 부수 효과를 검토한다.

**프로젝트 판단:** 버전 변경·중복·unknown의 검증 반례에 반영(Adapt)

**한계:** 체크포인트나 사용자 승인이 외부 exactly-once를 자동 보장하지 않는다.

### [X11] LangGraph — Persistence

[1차 자료](https://docs.langchain.com/oss/python/langgraph/persistence)

**판본/범위:** Persistence / checkpointing

**증거 수준:** 공식 구현 안내 · **원고 연결:** 14장

**지원하는 내용:** 상태 보존과 외부 효과 보존을 구분한다.

**프로젝트 판단:** 기존 Work 복구와 비교하는 참조

**한계:** AgentOS의 저장소 교체·체크포인터 통합·호환성 시험은 하지 않았다.

### [X12] IAAP — CAP Body of Knowledge

[1차 자료](https://www.iaap-hq.org/page/CAPBOK)

**판본/범위:** 공식 검색 결과의 6개 domain·Job Task Analysis·Performance Outcomes

**증거 수준:** 공식 사이트 검색 발췌만 확인; 직접 본문 403/접근 실패 · **원고 연결:** 12장

**지원하는 내용:** 업무 범위를 점검할 전문 실무 자료의 후보로 남긴다.

**프로젝트 판단:** 범위 확인용 제한적 참조; 상세 채택은 보류

**한계:** 상세 BOK·전문직 인증·시험 비중의 제품 우선순위 적용은 근거가 없다.

### [X13] CFP Board — Code of Ethics and Standards of Conduct

[1차 자료](https://www.cfp.net/ethics/code-of-ethics-and-standards-of-conduct)

**판본/범위:** C.1–C.7; 적용 대상과 engagement 범위

**증거 수준:** 공식 실무 기준 본문 · **원고 연결:** 09·12장

**지원하는 내용:** 상황·목표·대안·권고·실행·점검의 단계와 책임을 비교한다.

**프로젝트 판단:** 분석 브리프와 후속 범위에 조정(Adapt)

**한계:** CFP 전문가 대상 규범을 AI의 자격·법적 위임·세계 공통법으로 일반화하지 않는다.

### [R1] Personal AgentOS — AGENTS.md

[1차 자료](https://github.com/Jongtae/agentos/blob/735bfebe4a1555d4e8b7e4ce0acbc94fbd1f4e89/AGENTS.md)

**판본/범위:** 735bfebe4a1555d4e8b7e4ce0acbc94fbd1f4e89

**증거 수준:** 현재 저장소 규칙 읽기 · **원고 연결:** 전반·07·10·13·14장

**지원하는 내용:** C15/C16, 현재 pilot, 활성화·증거 경계를 유지한다.

**프로젝트 판단:** 기존 규칙 유지(Adopt)

**한계:** CONTRIBUTING.md·PR template도 대조. 문서 규칙은 라이브 기능 증거가 아니다.

### [R2] Supplied Skills and Reusable Execution — Preparation

[1차 자료](https://github.com/Jongtae/agentos/blob/735bfebe4a1555d4e8b7e4ce0acbc94fbd1f4e89/docs/skill-supply-execution-preparation.en.md)

**판본/범위:** 문서의 과거 baseline 4e51855…; §§1–7; §6 후속 amendment 표시

**증거 수준:** 준비 명세 읽기 · **원고 연결:** 12·13장

**지원하는 내용:** Supply first와 같은 AI 안의 스킬 재사용 방향을 이어받는다.

**프로젝트 판단:** 기존 설계와 연결(Adopt)

**한계:** 2026-10-01의 미구현 설명을 현재 코드 상태로 사용하지 않는다.

### [R3] Personal AgentOS — manifests.py

[1차 자료](https://github.com/Jongtae/agentos/blob/735bfebe4a1555d4e8b7e4ce0acbc94fbd1f4e89/src/personal_agent/manifests.py)

**판본/범위:** blob d43e54e08352e67129154b510ef4db8f3831ade0; 1–160 읽기

**증거 수준:** 선택 소스 정적 확인 · **원고 연결:** 12·13장

**지원하는 내용:** HOST_ACTIONS·스킬 선언·도구/역할 동시 선언 제한을 확인한다.

**프로젝트 판단:** 현재 경계를 재사용(Adopt)

**한계:** 스킬 선언만으로 독립 실행 역할·새 권한을 만들 수 없다.

### [R4] Personal AgentOS — skills.py

[1차 자료](https://github.com/Jongtae/agentos/blob/735bfebe4a1555d4e8b7e4ce0acbc94fbd1f4e89/src/personal_agent/skills.py)

**판본/범위:** blob 85af637fb3e7aaaa76fb7a4ff5f8abf15e264844; 1–175·470–675 읽기

**증거 수준:** 선택 소스 정적 확인 · **원고 연결:** 12·13장

**지원하는 내용:** SkillLibrary.read·SkillBinding.load/check_current/recall 및 로드 한도를 확인한다.

**프로젝트 판단:** 새 로더 대신 현재 경로 활용(Adopt)

**한계:** 코드 정적 읽기는 활성화·설치 성공·재시작·외부 동작 테스트가 아니다.

## 실행 채택을 검토할 때

실제 연결할 후보가 선택되면 그 경계만 대상으로 공식 API와 고정 revision, 라이선스와 재배포 조건, 유지보수·릴리스 상태, 플랫폼·의존성, 권한·데이터·공급망 영향, 작은 호환성 시험을 기록한다. 지금 충분한 기존 접점이 있으면 새 구성 요소를 만들지 않는다. 형식·스키마·로컬 시험·라이브 결과를 각각 구분한다. 구현 자체가 선택되지 않았다는 것을 이유로 개념·구조의 실질적 비교까지 생략하지 않는다.
