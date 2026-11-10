# Agent Skills 작성 모범 사례 (요약)

> **출처**: https://platform.claude.com/docs/ko/agents-and-tools/agent-skills/best-practices
> **조회일**: 2026-09-05
> **이 파일은 원문이 아니라 실행 가능한 규칙만 추린 요약이다.** 애매하면 위 URL의 원문을 본다.

## 목차

- 하드 제약 (frontmatter 검증 규칙)
- 핵심 원칙 4가지
- 점진적 공개 (progressive disclosure)
- description 작성법
- 워크플로와 피드백 루프
- 안티패턴
- 공식 체크리스트

---

## 하드 제약 (frontmatter 검증 규칙)

`name`
- 최대 64자
- 소문자, 숫자, 하이픈만
- XML 태그 불가
- 예약어 불가: `anthropic`, `claude`

`description`
- 비어 있으면 안 됨
- 최대 1,024자
- XML 태그 불가
- **무엇을 하는지 + 언제 써야 하는지**를 둘 다 포함

`SKILL.md` 본문
- **500줄 미만** 유지. 넘으면 별도 파일로 분할.

---

## 핵심 원칙 4가지

### 1. 간결함

컨텍스트 윈도우는 공공재다. 시작 시에는 모든 스킬의 `name` + `description`만 미리 로드되고,
SKILL.md는 스킬이 관련될 때, 참조 파일은 실제로 필요할 때만 읽힌다.
그래도 SKILL.md가 로드되면 모든 토큰이 대화 기록과 경쟁한다.

**기본 가정: 모델은 이미 똑똑하다.** 각 문단마다 자문한다.
- 정말 이 설명이 필요한가?
- 이미 알고 있다고 가정할 수 있는가?
- 이 문단이 토큰 비용을 정당화하는가?

PDF가 무엇인지, 라이브러리가 어떻게 동작하는지 설명하지 않는다. 코드 예시 하나로 끝낸다.

### 2. 적절한 자유도

작업의 취약성과 가변성에 맞춰 구체성 수준을 조절한다.

| 자유도 | 언제 | 형태 |
|---|---|---|
| 높음 | 여러 접근이 유효, 결정이 컨텍스트 의존 | 텍스트 지침 ("코드 구조를 분석한다") |
| 중간 | 선호 패턴은 있으나 변형 허용 | 의사 코드, 매개변수 있는 템플릿 |
| 낮음 | 취약하고 오류 나기 쉬움, 순서가 중요 | 정확한 스크립트 ("이 명령을 그대로 실행. 플래그 추가 금지") |

비유: 양쪽이 절벽인 좁은 다리는 가드레일(낮은 자유도), 위험 없는 열린 들판은 방향만 제시(높은 자유도).

### 3. 일관된 용어

하나를 골라 문서 전체에서 그것만 쓴다.
"API endpoint / URL / API route / path"를 섞지 않는다. "extract / pull / get / retrieve"도 마찬가지.

### 4. 시간에 민감한 정보 금지

"2025년 8월 이전이면 구 API를 쓰세요" 같은 문장은 반드시 틀리게 된다.
현재 방식만 본문에 쓰고, 과거 내용은 별도 "Old patterns" 섹션에 `<details>`로 접어둔다.

---

## 점진적 공개 (progressive disclosure)

SKILL.md는 **온보딩 가이드의 목차**다. 상세 자료로 안내하는 개요 역할.

### 참조는 SKILL.md에서 한 단계 깊이

중첩 참조(SKILL.md → advanced.md → details.md)를 만들지 않는다.
중첩을 만나면 모델이 전체를 읽는 대신 `head -100` 같은 부분 읽기로 미리 보다가
**불완전한 정보를 얻는다.** 모든 참조 파일은 SKILL.md에서 직접 링크한다.

### 100줄 넘는 참조 파일은 상단에 목차

부분 읽기로 미리 볼 때에도 전체 범위를 볼 수 있게 한다.

### 도메인별로 구성

관련 없는 컨텍스트가 로드되지 않도록 나눈다.

```
bigquery-skill/
  SKILL.md              # 개요 및 탐색
  reference/
    finance.md          # 매출, 청구 지표
    sales.md            # 파이프라인
    product.md          # API 사용량
```

매출 질문이 오면 `finance.md`만 읽힌다. 나머지는 파일 시스템에 남아 토큰을 전혀 쓰지 않는다.

### 대용량 리소스 번들링에는 페널티가 없다

전체 API 문서, 광범위한 예시, 대용량 데이터셋을 넣어도 **실제로 읽히기 전까지는** 컨텍스트 비용이 0이다.
아끼지 말고 넣되, SKILL.md에서 찾아갈 수 있게 만든다.

### 검색 힌트를 준다

```bash
grep -i "revenue" reference/finance.md
```
같은 예시를 SKILL.md에 넣으면 전체를 읽지 않고 필요한 절만 찾아간다.

---

## description 작성법

description은 **스킬 발견의 전부**다. 100개가 넘는 스킬 중에서 이것 하나로 선택된다.

- **항상 3인칭.** 시스템 프롬프트에 주입되므로 시점이 흔들리면 발견이 망가진다.
  - 좋음: `Processes Excel files and generates reports`
  - 피함: `I can help you...`, `You can use this to...`
  - `Use when ...`으로 트리거를 붙이는 형태는 공식 예시에서도 쓴다.
- **구체적인 트리거 용어를 넣는다.** 사용자가 실제로 쓸 단어(파일 확장자, 라이브러리명, 도메인 용어).
- 무엇을 하는지 + 언제 쓰는지 둘 다.

좋은 예:
```yaml
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
```

나쁜 예: `Helps with documents`, `Processes data`, `Does stuff with files`

### 이름 규칙

동명사 형태를 우선 고려한다: `processing-pdfs`, `analyzing-spreadsheets`, `testing-code`.
허용 대안: 명사구(`pdf-processing`), 행동 지향(`process-pdfs`).
피할 것: `helper`, `utils`, `tools`, `documents`, `data` 같은 모호하거나 지나치게 일반적인 이름.

---

## 워크플로와 피드백 루프

### 복잡한 작업에는 복사 가능한 체크리스트

```markdown
Copy this checklist and track your progress:

- [ ] Step 1: Read all source documents
- [ ] Step 2: Identify key themes
- [ ] Step 3: Cross-reference claims
```

명확한 단계는 중요한 검증을 건너뛰는 것을 막는다.

### 피드백 루프: 검증기 실행 → 오류 수정 → 반복

검증기는 스크립트일 수도 있고 **참조 문서일 수도 있다.**
"STYLE_GUIDE.md와 대조하고, 문제가 있으면 고치고, 다시 대조한다. 전부 통과할 때만 진행한다."

### 계획-검증-실행

일괄 작업·파괴적 변경·중대한 작업에는 중간 산출물(계획 파일)을 만들고 검증한 뒤 실행한다.
원본을 건드리지 않고 계획을 반복할 수 있고, 오류를 조기에 잡는다.

---

## 안티패턴

| 하지 말 것 | 이유 |
|---|---|
| Windows 경로 (`scripts\helper.py`) | Unix에서 깨진다. 항상 슬래시 |
| 선택지 나열 ("pypdf, pdfplumber, PyMuPDF 중에...") | 기본값 하나를 주고 예외 경로만 덧붙인다 |
| 깊게 중첩된 참조 | 부분 읽기로 불완전한 정보를 얻는다 |
| 도구가 설치돼 있다고 가정 | 필요한 패키지를 명시한다 |
| 매직 넘버 (`TIMEOUT = 47`) | 값의 근거를 주석으로 남긴다 |
| 스크립트가 오류를 모델에게 떠넘김 | 스크립트 안에서 명시적으로 처리한다 |
| 모호한 파일명 (`doc2.md`) | 내용을 나타내는 이름 (`form_validation_rules.md`) |

MCP 도구를 쓰면 `ServerName:tool_name` 형태의 **전체 이름**을 쓴다. 접두사가 없으면 못 찾는다.

---

## 평가와 반복

**광범위한 문서를 쓰기 전에 평가를 먼저 만든다.** 그래야 상상된 문제가 아니라 실제 문제를 푼다.

1. 스킬 없이 대표 작업을 시켜 보고 구체적인 실패를 기록한다 (기준선)
2. 그 격차를 테스트하는 시나리오 3개를 만든다
3. 평가를 통과할 만큼만 최소한으로 쓴다
4. 반복한다

관찰 포인트:
- 예상치 못한 탐색 경로 → 구조가 직관적이지 않다
- 참조를 따라가지 않음 → 링크가 더 눈에 띄어야 한다
- **같은 파일을 반복해서 읽음 → 그 내용은 SKILL.md에 있어야 한다**
- 번들 파일에 전혀 접근하지 않음 → 불필요하거나 안내가 부족하다

쓸 모든 모델(Haiku / Sonnet / Opus)로 테스트한다. Opus에서 충분한 지침이 Haiku에는 부족할 수 있다.

---

## 공식 체크리스트

**핵심 품질**
- [ ] description이 구체적이고 핵심 용어를 포함함
- [ ] description이 무엇을 하는지 + 언제 쓰는지를 모두 포함함
- [ ] SKILL.md 본문이 500줄 미만임
- [ ] 추가 세부 정보가 별도 파일에 있음
- [ ] 시간에 민감한 정보가 없음
- [ ] 전체적으로 일관된 용어 사용
- [ ] 예시가 추상적이지 않고 구체적임
- [ ] 파일 참조가 한 단계 깊이임
- [ ] 점진적 공개가 적절히 사용됨
- [ ] 워크플로에 명확한 단계가 있음

**코드와 스크립트**
- [ ] 스크립트가 문제를 떠넘기지 않고 직접 해결함
- [ ] 오류 처리가 명시적임
- [ ] 부두 상수(voodoo constants)가 없음
- [ ] 필요한 패키지가 명시됨
- [ ] Windows 스타일 경로가 없음
- [ ] 중요한 작업에 검증 단계가 있음

**테스트**
- [ ] 최소 세 개의 평가 생성
- [ ] 여러 모델로 테스트
- [ ] 실제 사용 시나리오로 테스트
