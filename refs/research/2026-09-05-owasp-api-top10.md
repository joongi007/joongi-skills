# OWASP API Security Top 10 — 2019 vs 2023 대조 (2026-09-05)

> **출처**
> - 2023판: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
> - 2019판: https://owasp.org/API-Security/editions/2019/en/0x11-t10/
> - 조회일: 2026-09-05
>
> 항목명과 순위는 원문 그대로. 해석과 "우리한테 뜻하는 것"은 우리가 붙인 것이다.

## 왜 조사했나

플레이북 §24(웹 백엔드 보안)가 작업 우선순위를 **"권한 검사부터"** 로 잡으면서
근거로 "OWASP API Top 10에서 인젝션은 8위까지 밀렸고 1·3위가 전부 권한 문제"를 든다.
이 서술이 어느 판 기준인지, 지금도 유효한지 확인이 필요했다.

## 결론 (한 줄)

**우선순위 판단은 맞다. 다만 "인젝션 8위"는 2019판 기준이고, 2023판에는 인젝션 항목 자체가 없다.**
권한 문제는 2023판에서 오히려 **세 자리(API1·API3·API5)** 를 차지해 근거가 더 강해졌다.

## 2023판 (현행)

| # | ID | 항목 | 성격 |
|---|---|---|---|
| 1 | API1:2023 | Broken Object Level Authorization | **권한** — 사용자가 준 id로 객체에 접근할 때의 인가 누락 |
| 2 | API2:2023 | Broken Authentication | 인증 |
| 3 | API3:2023 | Broken Object Property Level Authorization | **권한** — 속성(필드) 단위 인가. 2019판의 Excessive Data Exposure + Mass Assignment 자리 |
| 4 | API4:2023 | Unrestricted Resource Consumption | 가용성·비용 |
| 5 | API5:2023 | Broken Function Level Authorization | **권한** — 관리자 기능 등 함수 단위 인가 |
| 6 | API6:2023 | Unrestricted Access to Sensitive Business Flows | 비즈니스 로직 자동화 남용 |
| 7 | API7:2023 | Server Side Request Forgery | SSRF |
| 8 | API8:2023 | Security Misconfiguration | 설정 |
| 9 | API9:2023 | Improper Inventory Management | 문서화·버전 관리 |
| 10 | API10:2023 | Unsafe Consumption of APIs | 서드파티 응답을 무비판 수용 |

**인젝션은 독립 항목으로 존재하지 않는다.**

## 2019판

| # | ID | 항목 |
|---|---|---|
| 1 | API1:2019 | Broken Object Level Authorization |
| 2 | API2:2019 | Broken User Authentication |
| 3 | API3:2019 | Excessive Data Exposure |
| 4 | API4:2019 | Lack of Resources & Rate Limiting |
| 5 | API5:2019 | Broken Function Level Authorization |
| 6 | API6:2019 | Mass Assignment |
| 7 | API7:2019 | Security Misconfiguration |
| 8 | **API8:2019** | **Injection** |
| 9 | API9:2019 | Improper Assets Management |
| 10 | API10:2019 | Insufficient Logging & Monitoring |

→ "인젝션 8위"는 여기서 나온 말이다.

## 우리한테 뜻하는 것

1. **권한 검사를 1순위로 두는 판단은 유지.** 2023판에서 10개 중 3개(1·3·5)가 권한이다.
   2019판보다 근거가 더 강해졌다.
2. **§24 서술은 "2019판 기준"임을 밝히도록 수정했다.** 판 번호 없이 "8위"라고만 쓰면
   지금 목록을 본 사람이 찾지 못한다.
3. **인젝션을 덜 중요하게 여기라는 뜻이 아니다.** 목록에서 빠진 이유는 위험이 사라져서가 아니라
   API 고유 위험에 집중하는 쪽으로 항목이 재편됐기 때문이다.
4. **2019판 Mass Assignment(API6) + Excessive Data Exposure(API3) → 2023판 API3 통합**은
   `web-security.md` §1.3(입출력 스키마 분리 + `response_model`)이 두 문제를 한 번에 푸는 것과 같은 관점이다.

## 스킬 반영 상태

- `skills/engineering-playbook/references/web-security.md` §0 — 우선순위 근거 문장에 판 번호 명시
- `skills/engineering-playbook/PLAYBOOK.md` §24.2 — 동일
