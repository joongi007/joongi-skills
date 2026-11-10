---
name: engineering-playbook
description: 개인 프로젝트의 구현·리뷰·설계·인프라·테스트·운영에 기본 적용하는 엔지니어링 규칙이다. Python/FastAPI/SQLAlchemy, React/TypeScript, JWT, Docker, 웹 보안·ReDoS, Valkey/Redis/Sentinel, TCP·Java 타임아웃, PostgreSQL 복구, Kubernetes/Helm, 설계 패턴·문서 정합성·뮤테이션 테스트·병렬 작업을 다룬다. inject_autocommit Repository, jtt JWT claim, DB URL의 quote_plus, Ruff 등 개인 관례를 우선한다. 언어별 예시는 해당 스택에만 적용하며 시각 디자인은 applying-design-systems를 함께 참고한다.
---

# 엔지니어링 플레이북

개인 프로젝트의 작업 규칙이다. 원본은 `PLAYBOOK.md`이며 §24는 웹 백엔드 보안 체크리스트다.
이 문서는 작업별로 필요한 참조만 읽기 위한 안내다.
설명은 한국어로 작성하고 코드·식별자·로그 이벤트는 프로젝트의 영어 표기를 유지한다(§10).

## 적용 범위와 절차

기능 구현·버그 수정·리뷰·리팩터링·테스트·CI·성능·보안·설계·라이브러리 선택에 기본 적용한다.
한 줄 수정이나 타인의 코드 검토도 포함한다. 이 스킬을 명시적으로 요청할 필요는 없다.
문장 교정처럼 엔지니어링과 무관한 작업에는 적용하지 않는다.

1. 작업 종류를 파악하고 아래 표에서 해당 참조를 읽는다. 관련 주제가 여러 개면 함께 읽는다.
2. 일반적인 관례보다 이 플레이북의 규칙을 우선한다. 사용자의 명시적 지시는 그보다 우선한다.
3. 중요한 결정이나 지적에는 원본의 § 번호를 적어 사용자가 대조할 수 있게 한다.
4. 기술 스택이 문맥에서도 불분명하면 확인한다. 참조를 고르기 어렵다면 원본에서 해당 절을 찾는다.

## 작업별 참조

| 작업 | 읽을 자료 |
|---|---|
| async·스레드·프로세스, I/O·CPU 작업, 큐·수평 확장 | `references/concurrency.md` |
| 시스템·서비스 경계, DB 소유권, shared ORM 예외, worker·큐 도입 | `references/architecture.md` |
| FastAPI 구조, 패키지 이름, router·service·schema, Repository, NATS, constants.py | `references/python-api.md` |
| JWT RS256·jtt·rjti·fjti, 로그인·갱신·로그아웃, 재인증, WebSocket ticket, bcrypt, CORS | `references/auth-jwt.md` |
| React 구조·hooks·Zustand, Axios 401 갱신, WebSocket, 서버 상태와 UI 상태 | `references/frontend.md` |
| Compose 환경변수·볼륨·초기화 컨테이너, build·image, pull_policy, 이미지 버전 | `references/docker.md` |
| structlog, 로그 이벤트 이름·exc_info, 개인정보 기록 금지 | `references/logging.md` |
| Ruff, ESLint v9 flat config, 파일·식별자 이름 | `references/lint-naming.md` |
| asyncio.to_thread, 이벤트 루프·worker 스레드, Task 수명, 타임스탬프 변환 | `references/async-patterns.md` |
| DB·Redis 비밀번호의 quote_plus, pydantic-settings·cached_property | `references/config-secrets.md` |
| uv·Python·Vite 프로젝트 구성, UI–API 계약, /api/v1, 역방향 프록시 단일 진입점 | `references/scaffolding.md` |
| 인가·IDOR, 인증, injection·ReDoS, 업로드·경로 이탈, SSRF·CORS·CSRF, DoS, 경쟁 상태, XSS | `references/web-security.md` |
| 보안 헤더·CSP, 개인정보·암호화, 비밀 유출, 공급망, 컨테이너·외부 연결·백업 | `references/security-ops.md` |
| 가용성 목표, Redis·Valkey 라이선스, Sentinel quorum·majority·장애 도메인 | `references/infrastructure-ha.md` |
| TCP 연결 장애, Java·JDBC·클라이언트 타임아웃, keepalive·재연결·재시도 | `references/network-failure.md` |
| PostgreSQL 복제·지연·fencing·failover, 백업·RPO·RTO | `references/database-recovery.md` |
| k3s·Kubernetes·etcd, probe·topology spread·PDB, Helm 배포·업그레이드 | `references/kubernetes-helm.md` |
| 문서 번호·ADR·정합성, 테스트 품질·뮤테이션 테스트·병렬 작업 단위 | `references/documentation-testing.md` |
| 프로젝트 규모, 설계 패턴·adapter·circuit breaker·outbox·코드 그래프 | `references/patterns-scale.md` |
| PR·커밋 전 최종 점검 | `references/checklist.md` |

색상·글꼴·간격·시각적 방향은 `applying-design-systems`를 함께 사용한다.
이 플레이북의 프론트엔드 참조는 컴포넌트 구조·hooks·상태·API 사용 규칙을 다룬다.
인프라·장애 복구·문서·테스트 원칙(§25–§27)은 여러 언어에 적용하되,
Python·React·Java 예시 때문에 다른 프로젝트의 기술 스택을 바꾸지 않는다. 예외와 이유는 ADR에 기록한다.

## 기본 기술과 관례

- 백엔드: Python 3.14, FastAPI, SQLAlchemy 2.x async, Alembic, uv, pydantic-settings. 서비스마다 환경변수 접두사를 구분한다.
- 프론트엔드: React·TypeScript·Vite, Zustand 5, Axios 1.x, MUI 7, Tailwind 4.
- 검사·포맷: Ruff check와 format, ESLint flat config와 TypeScript strict. Black·isort·구형 .eslintrc를 따로 도입하지 않는다.
- 로그: structlog JSON stdout, 영어 snake_case의 동작·대상 이름. 개인정보를 기록하지 않는다.
- API: 브라우저용 JSON은 /api/v1 아래에 두고 도메인별 router.py·service.py·schema.py로 나눈다.
- DB: API 서비스가 소유하고 worker는 API로 접근한다. shared ORM 예외는 명시적인 구두 승인이 필요하다(§7.2).
- 비밀: 환경변수로 전달하고 .env는 추적하지 않는다. 예시는 .env.example, URL 비밀번호는 quote_plus를 쓴다.
- 상태 원천: DB 또는 이벤트 스트림 중 하나를 정한다. 캐시는 보조 수단이다.

## 보안에서 항상 확인할 것

1. 입력 타입을 엄격히 제한한다. Pydantic strict schema와 extra="forbid" 등으로 예상하지 않은 구조를 거절한다.
2. 데이터와 코드를 섞지 않는다. 파라미터 바인딩·shell=False·yaml.safe_load를 쓰고 사용자 입력으로 템플릿을 만들지 않는다.
3. 소유권 조건은 조회 쿼리에 포함하고 공통 의존성·계층에서 적용한다.
4. UNIQUE·CHECK·원자적 UPDATE 등으로 DB에서도 불변 조건을 보장한다.

인증·권한, 사용자 입력으로 필터링하는 조회, parser·shell·template로 가는 입력,
파일 업로드·다운로드, 서버의 URL 조회, 잔액·재고·쿠폰·결제 변경을 다루면
완료 전에 `references/web-security.md`를 읽는다.
시간이 부족하면 인가 → 인증·계정 복구 → injection → 가용성 → 헤더 순서로 확인한다.

## 리뷰·원본 조회·규칙 추가

- 리뷰는 코드를 먼저 읽고 관련 참조를 적용한다. 보안 검토는 web-security.md 부록 A를 따라 우선 보고한다.
- 지적은 필수 수정·제안·확인한 정상 동작으로 구분하고 해당 §를 적는다. 마무리는 §13과 최종 체크리스트로 점검한다.
- 플레이북 밖의 논리 오류도 보고하되 개인 규칙 위반과 구분한다. 이 문서는 오류를 빠짐없이 열거하는 목록은 아니다.
- 원본 내용을 물으면 기억으로 요약하지 않고 실제 원본·참조를 열어 해당 절을 인용한다.
- 새 관례를 추가하라는 요청은 원본 §17에 날짜·프로젝트·한 줄 요약으로 남기고 관련 참조도 함께 갱신한다.
