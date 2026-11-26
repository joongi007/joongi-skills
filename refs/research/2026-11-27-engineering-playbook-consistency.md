# Engineering playbook 정합성 검토

검토일: 2026-11-27. 대상은 `skills/engineering-playbook/SKILL.md`, `PLAYBOOK.md`, 기존 참조 37개다.
이번 변경에서 공통 적용 계약 참조 1개를 추가했다. 실행 코드의 취약점 재현·성능 측정이나 여러 모델의 비교 평가를 수행한 기록은 아니다.

## 확인한 문제와 변경

| 문제 | 변경·기준 문서 |
|---|---|
| 본문은 선택형인데 Python·Compose·린트 예시는 개인 규칙을 일괄 강제 | 적용 계약으로 공통 원칙·표준·프로젝트 결정·예시를 구분; 관련 상세 문서도 직접 수정 |
| 동시성·병렬성·비동기 작업의 수명 혼용 | concurrency는 실행 모델, background-jobs는 영속 상태·전달·복구, async-patterns는 Python 수명 관리로 분리 |
| 단일 인스턴스·프로세스별 메모리 일괄 금지 | 손실·정합성·복제본 조정 요구에 따라 선택 |
| GIL·to_thread·무제한 큐·timestamp 크기 추측 | 실제 runtime 구분, bounded queue·취소 한계·명시적 clock domain/단위 |
| 비밀은 환경변수·공용 .env에만 두라는 규칙 | 저장·주입·메모리 수명 분리, 서비스별 최소 권한, URL builder 우선 |
| 메이저 태그를 버전 고정으로 설명, build·pull 기본값을 안전으로 단정 | tag/digest 구분, 명시적 이미지 준비, 환경별 pull 정책 |
| DI 메서드명만으로 query마다 commit한다고 설명 | Repository·Unit of Work·flush/commit·응답 전 실패 전달 구분 |
| 이전 localStorage/sessionStorage 권고가 현재 문서와 충돌 | BFF/TMB 기준 참조로 통합; 실제 토큰 위치·XSS/CSRF 경계 유지 |
| retry cache가 폐기 검사를 우회하거나 rotation과 따로 기록되는 절차 | 세션 검사·원자적 교체·재시도 결과 공개·폐기 경합을 같은 계약으로 검증 |
| custom claim·로그아웃·timestamp가 철회/비밀번호 정책을 보장한다고 오해 | 명시적 서버 정책·Access Token 철회 계약·서버 집행으로 수정 |
| 모든 Access Token을 JWT로 가정, 메모리 가이드가 BFF 보관까지 금지 | opaque token 검증 경로, 의도적 자격 저장과 우발적 요청 참조 보존 구분 |
| 웹 보안의 통계 근거 없는 순위·타입만으로 안전하다는 표현 | 위협 모델 기반 우선순위, 실제 사용 지점·권한·자원 상한 검증 |
| SSRF·경로·압축·redirect·CSRF 예시에 충분조건으로 읽힐 표현 | DNS/연결 결합·TOCTOU·실제 해제량·고정 route·검증된 CSRF 방어 명시 |
| 로그 이름 문법 충돌·내부 ID를 비개인정보로 단정·stdout 일괄 사용 | 계약별 명명·식별자 정책·MCP stdio의 로그 sink 분리 |
| RPO/RTO 목표와 실측 결과를 같은 이름으로 기술 | 목표 대비 실제 손실 구간·복구 시간으로 비교 |
| nginx의 과거 수정 버전이 최신 안전 목록으로 읽힐 여지 | 확인일·적용 조건 유지, 공식 신규 TLS 1.3 공지 추가 |

관련 상세의 기준은 [적용 계약](../../skills/engineering-playbook/references/application-contract.md)에 둔다.
원칙의 짧은 요약·주제 라우팅은 남기고, 동일한 상세 설정·알고리즘의 중복은 줄였다.

## 시나리오별 의미 대조

문서를 읽고 다음 기대 판단이 서로 충돌하지 않는지 대조했다. 여러 에이전트의 실측 점수나 자동 테스트 통과로 해석하지 않는다.

| 입력 상황 | 문서가 유도해야 하는 판단 | 대조한 참조 |
|---|---|---|
| 작은 동기 Express CRUD 변경 | Python 폴더·JWT·큐·k3s 설치를 강제하지 않음 | application-contract, architecture, scaffolding |
| API·worker가 같은 앱 DB 사용 | 별도 서비스라는 이유로 모든 접근을 HTTP로 바꾸지 않음 | architecture, python-api, background-jobs |
| GIL-enabled Python에서 긴 CPU 연산 | async 선언만으로 병렬성·응답성을 얻지 않음 | concurrency, async-patterns, web-security |
| 프로세스 종료 뒤 결과를 보존해야 함 | in-memory task ID·shield만으로 완료하지 않음 | concurrency, background-jobs, async-patterns |
| password에 공백·+·@ 포함 | builder에 원문 구성요소 전달, 이중 인코딩하지 않음 | config-secrets, scaffolding, PLAYBOOK §15 |
| Compose 환경변수와 서비스별 비밀 | environment 허용, 전체 비밀 공용 주입을 기본으로 삼지 않음 | docker, config-secrets, security-ops |
| 같은 메이저 이미지 태그로 재배포 | 동일 바이트 보장으로 기록하지 않음 | docker, terminology, PLAYBOOK §16 |
| refresh와 로그아웃이 동시에 발생 | cache hit가 폐기를 우회하지 않음; Access Token 종료는 별도 계약 | auth-jwt, frontend, jwt-jwks |
| BFF의 서버 토큰 보관 | 브라우저 미노출·전용 저장 수명을 설계; 요청 참조 무기한 보존과 구분 | browser-backends, memory-secrets, identity-authorization |
| PostgreSQL tenant 정책·조회 최적화 | RLS 실행 role·정책 검사; FK·정규화·인덱스를 구분 | database-design, web-security, architecture |
| 주기 취약점 점검 기한 경과 | 관련 engineering/운영 점검에서 실제 스택 조사; 문구 수정에 운영 변경을 강제하지 않음 | vulnerability-management, SKILL, checklist |
| 이 변경처럼 Markdown 가이드만 수정 | 링크·라우팅·번들·렌더 검사; 코드 전용 scan 미실행을 통과라고 표시하지 않음 | agent-security-review, checklist, PLAYBOOK §31 |

## 검증 범위와 한계

검증 명령은 `bash build.sh --check`, `scripts/check_docs.py`, `scripts/check_contracts.py`,
`tests.test_site_docs`·`tests.test_site_analytics`·`tests.test_pages`, `git diff --check`다.
실행 결과는 해당 변경의 PR·CI에 남긴다. 구조 검사는 자연어의 의미적 무모순이나 모델 간 동일 판단을 보증하지 않는다.
전용 코드 보안 스캔은 문서만 변경하는 이 작업의 대상이 아니다. 런타임 인증 구현을 수정·검수한 것으로 기록하지 않는다.

새 결정은 관련 주제의 기준 문서에 반영하고 기존 링크·스택 예시·거부/실패 시나리오를 함께 대조한다.
공식 자료를 참조한 변경은 해당 참조 문서에 URL과 확인일을 남겼다.
