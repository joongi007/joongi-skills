---
name: engineering-playbook
description: 구현·설계·리뷰·테스트·운영과 보안 검수 가이드다. Codex Security·Claude /security-review, Zero Trust·탐지·복구, API key·JWT/JWKS·BFF/TMB, ReDoS·이미지 압축 폭탄, 문서·테스트 품질, 아키텍처·비동기 작업·캐시, DB 설계·RLS·테넌트 격리·EXPLAIN·인덱스·삭제 정책, Keycloak·OpenFGA, WSL·VHDX 용량 회수, HA·네트워크·DB 복구를 다룬다. Python/FastAPI/SQLAlchemy, React/TypeScript/JWT, Java/Actuator, Valkey/Sentinel/PostgreSQL/Kubernetes 예시는 해당 스택에서만 적용한다. 기존 프로젝트의 계약을 우선하며 개인 패턴·도구를 강제하지 않는다.
---

# 엔지니어링 가이드

구현·리뷰·설계·테스트·운영 작업에 적용한다. 문장 교정처럼 엔지니어링과 무관한 작업에는 적용하지 않는다.
`PLAYBOOK.md`는 판단 기준과 주제별 읽는 순서다. 전체 본문과 모든 참조를 매번 읽지 않는다.

## 적용 순서

1. [적용 계약](references/application-contract.md)에 따라 목적·수용 조건·범위·기존 결정을 확인한다. 공통 원칙·표준·프로젝트 결정·예시를 구분한다.
2. 아래 표에서 관련 참조만 선택한다. 언어·프레임워크 예시는 그 스택에서만 적용한다.
3. 사용자 지시와 저장소의 구체적인 계약을 우선한다. 예제를 적용하려고 기술을 교체하지 않는다.
4. 변경 위험에 맞는 정상·실패·권한·복구 검사를 하고, 동작이 바뀐 문서를 함께 갱신한다.

## 작업별 참조

| 작업 | 읽을 자료 |
|---|---|
| async·스레드·프로세스, I/O·CPU 작업, 큐·수평 확장 | `references/concurrency.md` |
| Hexagonal·Clean Architecture·Modular Monolith 조합, Java/FastAPI/Express 경계·DB 소유권 | `references/architecture.md` |
| TASK ID 비동기 처리, API·worker·scheduler 분리, 멱등성·재시도·복구 | `references/background-jobs.md` |
| 외부 통신 adapter, 캐시 계층·cache-aside·refresh·bypass·정합성 | `references/external-cache.md` |
| Keycloak·OpenFGA 선택, OIDC·BFF·SSO, 자원 권한·tenant·원장·반영·복구 | `references/identity-authorization.md` |
| 로그인·계정 UI, Keycloak 테마 상속·다국어·배포·회귀 검사 | `references/identity-ui.md` |
| API key 발급·verifier·cache·회전·만료·폐기, 공개 문서·자동화 공격 | `references/api-key-security.md` |
| BFF·Token-Mediating Backend(TMB)·browser-only OAuth, API aggregation | `references/browser-backends.md` |
| JWT·JWK·JWKS, issuer·kid·cache·서명 키 회전·긴급 폐기 | `references/jwt-jwks.md` |
| 공통 기준·지침 충돌·기준 문서·에이전트 판단 기록 | `references/application-contract.md` |
| CS 명칭·약어·의미 구분과 문서 용어 일치 | `references/terminology.md` |
| Spamhaus DROP·IP/CIDR/ASN reputation, IPv6·proxy·피드 갱신·차단·rollback | `references/network-reputation.md` |
| FastAPI 구조, 패키지 이름, router·service·schema, Repository, NATS, constants.py | `references/python-api.md` |
| JWT RS256·jtt·rjti·fjti, 로그인·갱신·로그아웃, 재인증, WebSocket ticket, bcrypt, CORS | `references/auth-jwt.md` |
| React 구조·hooks·Zustand, Axios 401 갱신, WebSocket, 서버 상태와 UI 상태 | `references/frontend.md` |
| Compose 환경변수·볼륨·초기화 컨테이너, build·image, pull_policy, 이미지 버전 | `references/docker.md` |
| structlog, 로그 이벤트·exc_info·민감정보 최소화·MCP stdio 로그 경계 | `references/logging.md` |
| Ruff·ESLint 설정 선택, 파일·식별자·프로토콜 명명 | `references/lint-naming.md` |
| asyncio.to_thread, 이벤트 루프·worker 스레드, Task 수명, 타임스탬프 변환 | `references/async-patterns.md` |
| 설정·비밀 주입·연결 URL builder·구성요소 인코딩·설정 cache | `references/config-secrets.md` |
| 신규 프로젝트 구성·지원 버전·UI–API 경로·실행·중지 계약 | `references/scaffolding.md` |
| 인가·IDOR, 인증, injection·ReDoS, 업로드·이미지 압축 폭탄·디코딩 자원 제한·경로 이탈, SSRF·CORS·CSRF, DoS, 경쟁 상태, XSS | `references/web-security.md` |
| Zero Trust·host 침해·MSA/mTLS, 보안 헤더·CSP·비밀·공급망·백업 | `references/security-ops.md` |
| 기술 도입·배포 전 취약점 확인, 30일 경과 시 전체 스택 재점검·중대 취약점 대응 | `references/vulnerability-management.md` |
| nginx 보안 공지·수정 버전·배포판 backport 확인 | `references/nginx-security.md` |
| Codex Security·Claude /security-review 등 에이전트 개발 보안 검수 | `references/agent-security-review.md` |
| 침해 탐지·알림·자동 차단·격리·키 폐기·복구·훈련 | `references/incident-response.md` |
| Java·Spring Boot Actuator, heapdump·관리 endpoint·JMX 노출 | `references/java-actuator.md` |
| 요청 컨텍스트 정리, ThreadLocal·async 전파, 메모리 비밀·core/heap dump | `references/memory-secrets.md` |
| 가용성 목표, Redis·Valkey 라이선스, Sentinel quorum·majority·장애 도메인 | `references/infrastructure-ha.md` |
| TCP 연결 장애, Java·JDBC·클라이언트 타임아웃, keepalive·재연결·재시도 | `references/network-failure.md` |
| PostgreSQL 복제·지연·fencing·failover, 백업·RPO·RTO | `references/database-recovery.md` |
| DB 설계·RLS·멀티테넌시 격리, PK·인덱스·EXPLAIN·읽기/쓰기 측정, 정규화·FK·ON DELETE | `references/database-design.md` |
| 로컬 Compose·k3s 선택, 프로젝트 격리·자원·중지, etcd·probe·PDB·Helm | `references/kubernetes-helm.md` |
| 문서 번호·ADR·정합성, 테스트 품질·뮤테이션 테스트·병렬 작업 단위 | `references/documentation-testing.md` |
| 프로젝트 규모, 설계 패턴·adapter·circuit breaker·outbox·코드 그래프 | `references/patterns-scale.md` |
| WSL·Windows 설치 경계, 캐시·VHDX 용량 진단, 필요 시 compact 절차 | `references/wsl-development.md` |
| PR·커밋 전 최종 점검 | `references/checklist.md` |

색상·글꼴·간격·시각적 방향은 `applying-design-systems`를 함께 사용한다.
이 플레이북의 프론트엔드 참조는 컴포넌트 구조·hooks·상태·API 사용 규칙을 다룬다.
인프라·장애 복구·문서·테스트 원칙(§25–§27)은 여러 언어에 적용하되,
Python·React·Java 예시 때문에 다른 프로젝트의 기술 스택을 바꾸지 않는다. 중요한 구조·보안 결정은 ADR 등 기존 결정 기록에 남긴다.

## 공통 기준

- 입력·출력·권한·자원 상한을 명시하고 실패를 조용히 성공으로 처리하지 않는다.
- DB 작업은 테넌트/권한 경계·무결성·쿼리 계획·읽기/쓰기·용량·삭제/복구 비용을 검토한다. RLS·키·인덱스·정규화·CASCADE는 엔진과 워크로드에 맞춰 선택하고 증거를 남긴다.
- 데이터와 코드를 섞지 않는다. 안전한 parser·파라미터 바인딩·경로 및 소유권 검사를 사용한다.
- 예방과 함께 탐지·차단·복구를 설계한다. 알림에는 담당자와 다음 행동이 있어야 한다.
- 보안 검토는 `references/web-security.md`의 우선순위를 따르고 관측·대응은 `references/incident-response.md`를 본다.
- Python의 Repository 패턴·JWT 사용자 정의 claim·React 상태 도구는 선택형 예시다. 기존 계약을 임의 변경하지 않는다.
- 기술 도입·배포 전에는 관련 취약점 공지를 확인한다. 관련 엔지니어링·운영 점검 시 마지막 전체 스택 점검 후 30일 이상 지났거나 기록이 없으면 현재 프로젝트를 재점검한다. 긴급 공지는 기다리지 않는다.
- 에이전트 개발의 완료 전 보안 검수는 `references/agent-security-review.md`를 따른다. Codex는 Codex Security를 최소 단계로 두고 미실행을 통과로 처리하지 않는다.
- 중요한 결정은 이유·대안·검증·한계를 남긴다. 새 공통 원칙은 PLAYBOOK의 주제와 관련 참조를 함께 갱신한다.
- 기술 개념은 통용되는 CS 명칭·영어 원어·약어를 필요한 만큼 병기하고 의미를 구분한다. 설명은 자연스러운 한국어로 쓰며 프로젝트 glossary·식별자는 보존한다.
