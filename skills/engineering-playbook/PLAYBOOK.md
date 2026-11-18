# 엔지니어링 가이드북

기존 프로젝트의 요구사항·제약·결정을 먼저 확인하고, 필요한 주제만 읽는다.
이 본문은 판단 기준과 읽는 순서를 제공한다. 코드 예제·프레임워크 설정은 `references/`에 둔다.
특정 언어·라이브러리·배포 구조를 모든 프로젝트에 적용하지 않는다.

## 목차

- 시작·구조·구현: §1–§11
- 측정·완료 판단·환경: §12–§16
- 선택한 스택의 구현 예시: §18–§23
- 보안·인프라·검증: §24–§29
- 개편 기록: §17

기존 §번호는 주제 식별자로 유지한다. 세부 §번호와 예제는 해당 참조에 있다.
매 작업마다 본문과 모든 참조를 전부 읽을 필요는 없다.

## 1. 이 문서를 쓰는 방법

1. 목적·수용 조건·실패 시 영향을 짧게 정한다.
2. 현재 코드·문서·배포 제약에서 이미 결정한 사항을 확인한다.
3. 작업에 맞는 참조만 선택한다. 관련 없는 스택 예제는 적용하지 않는다.
4. 구현 뒤 정상·실패·권한·복구 경로를 검증하고 문서를 맞춘다.

사용자 지시와 저장소의 구체적인 계약을 우선한다. 관례를 적용하려고 무관한 기술 전환을 하지 않는다.

## 2. 동시성·성능: 무엇이 어디에 강한가

I/O 대기·CPU 작업·순서 보장·처리량·지연 목표를 구분한다.
동시성을 늘리기 전에 병목을 측정하고, 큐·동시 실행·메모리·재시도에 상한을 둔다.
세부 선택: [동시성](references/concurrency.md).

## 3. 시스템 구조를 말할 때의 최소 단위

역할·실행 단위·데이터 원천·신뢰 경계를 적는다. 구성요소마다 의존 대상과 실패 영향을 설명한다.
그림은 필요할 때 사용하고 현재 코드·배포와 다른 희망 구조를 실제 구조로 표현하지 않는다.
[아키텍처](references/architecture.md).

## 4. 아키텍처 판단 (요구가 들어왔을 때)

짧은 동기 작업은 단순하게 시작한다. 긴 작업·부분 실패·재시도가 있으면 작업 수명과 상태를 설계한다.
새 패턴·서비스·인프라는 해결할 문제, 도입 비용, 제거·복구 조건을 함께 정한다.
[아키텍처](references/architecture.md), [패턴과 규모](references/patterns-scale.md).

## 5. 모듈화·의존성 (백엔드 예: Python)

관심사·데이터 소유권으로 경계를 나누고 공개 진입점을 둔다. 파일 수를 늘리는 것 자체를 목표로 삼지 않는다.
언어별 파일명·re-export 예시는 해당 프로젝트의 관례에 맞춰 선택한다.
[명명·린트](references/lint-naming.md), [Python API](references/python-api.md).

## 6. REST API 설계에서 반복하는 공통 구조

입력·출력·오류·권한·페이지 크기·멱등성 계약을 먼저 정한다.
요청 형식이 동적이면 검증 범위와 상한을 명시한다. 특정 프레임워크의 타입만이 유일한 검증 방법은 아니다.
[웹 보안](references/web-security.md), [스캐폴딩](references/scaffolding.md).

## 7. DB 소유권·`shared` 패키지 (기본 vs 예외)

스키마·마이그레이션·쓰기 책임자를 분명히 한다. 프로세스가 다르다는 이유만으로 별도 서비스를 만들지 않는다.
독립 서비스는 내부 ORM 공유보다 공개 계약을 선호한다. 같은 애플리케이션의 API·worker가
DB를 공유하면 트랜잭션·권한·배포·마이그레이션 호환성을 정의하고 결정을 기록한다.
[DB 소유권 판단](references/architecture.md).

## 8. 신규 프로젝트 스캐폴딩 (호스트에 Python/Node 안 깔 때)

선택한 언어·실행 환경·지원 버전·lockfile을 기록한다. 기존 프로젝트를 예제 버전에 맞춰 재생성하지 않는다.
컨테이너 초기화가 필요하면 빈 작업 경로와 파일 소유권을 확인한다.
[스캐폴딩](references/scaffolding.md).

## 9. UI·API “개발 원칙” = 코드 분할·모듈 분할

UI는 사용자 작업과 상태 수명으로, API는 도메인 책임으로 나눈다.
서버 상태·편집 중 상태·캐시를 구분하고 비동기 응답이 최신 선택을 덮어쓰지 않게 한다.
[프론트엔드](references/frontend.md), [Python API](references/python-api.md).

## 10. 주석·이름·로그

식별자는 저장소 관례를 유지한다. 주석은 제약·이유·예외를 설명한다.
로그에는 조사에 필요한 식별자·결과를 남기고 비밀번호·토큰·개인정보 원문은 남기지 않는다.
[로그](references/logging.md).

## 11. UI와 API 계약 (기술)

호출 경로·인증·CORS·오류·시간 제한을 함께 검증한다. 단일 진입점·상대 경로를 쓸 수 있으면 우선한다.
분리된 origin이 필요하면 정확한 허용 origin과 자격증명 전달 방식을 정의한다.
[스캐폴딩](references/scaffolding.md), [프론트엔드](references/frontend.md).

## 12. 최적화·운영에 대한 태도

성공률·지연·비용·메모리와 실패 영향을 측정한다. 외부 의존성에는 시간 예산·호출 상한·취소·백오프를 둔다.
평균만 보지 말고 긴 지연·오류·복구 시간도 확인한다.
[동시성](references/concurrency.md), [네트워크 장애](references/network-failure.md).

## 13. 신규 작업 체크 (짧게)

완료 판단은 변경의 위험에 맞춘다. 작은 문구 수정에 운영 전체 검사를 강제하지 않는다.
권한·결제·데이터 손실·비밀 변경에는 실패·경계·복구 검사를 포함한다.
[완료 체크리스트](references/checklist.md).

## 14. Docker Compose 패턴 (개발 환경)

Compose를 선택한 프로젝트에서만 적용한다. readiness·네트워크·볼륨·비밀·종료·복구 경로를 확인한다.
예제 서비스를 쓰지 않는 프로젝트에 그대로 추가하지 않는다.
[Docker](references/docker.md).

## 15. 비밀번호·URL 인코딩 (`quote_plus`)

문자열 연결 대신 드라이버의 URL builder·파라미터 API를 우선한다.
URL의 일부를 직접 조립할 때만 해당 구성요소에 맞는 인코딩을 적용한다. 전체 URL을 인코딩하지 않는다.
[설정·비밀](references/config-secrets.md).

## 16. Docker Compose 이미지 설정 패턴

재현 가능한 버전·digest와 업데이트 절차를 정한다. `latest`·메이저 태그만으로 동일 이미지를 보장하지 않는다.
로컬 빌드와 배포 이미지의 pull 정책·플랫폼·권한·rollback을 구분한다.
[Docker](references/docker.md).

## 18. Python API 구조 패턴 (FastAPI 실무)

Python/FastAPI/SQLAlchemy를 쓰는 작업에서만 참조한다.
`inject`·`inject_autocommit` 같은 개인 패턴은 기존 코드의 트랜잭션 계약에 맞춰 사용한다.
다른 언어에 이 디렉터리 구조나 Repository 구현을 강제하지 않는다.
[Python API](references/python-api.md).

## 19. 인증·보안 패턴 (JWT RS256 + WS 티켓)

먼저 세션·OIDC·관리형 인증·자체 JWT 중 프로젝트에 필요한 방식을 결정한다.
JWT 예제의 `jtt`·`rjti`·`fjti`는 특정 계약의 사용자 정의 claim이며 모든 JWT의 필수 필드는 아니다.
선택한 방식의 갱신·폐기·재인증·권한 축소를 검증한다. 브라우저 저장은 XSS·CSRF를 함께 고려한다.
[기존 JWT 스택의 상세](references/auth-jwt.md), [프론트엔드](references/frontend.md).

## 20. UI 아키텍처 패턴 (React + Zustand + Axios)

해당 스택에서 상태·feature 경계·구독 해제·요청 재시도 예시를 선택한다.
React·Zustand·Axios를 쓰지 않는 프로젝트에 설치하거나 버전을 고정하라는 뜻이 아니다.
[프론트엔드](references/frontend.md). 시각 디자인은 applying-design-systems를 함께 본다.

## 21. 구조화 로그 (structlog)

이벤트 이름·시간·결과·상관관계 ID를 일관되게 기록한다. 수집·보관·읽기 권한·유실 탐지도 설계한다.
structlog 예시는 Python을 사용할 때만 적용한다.
[로그](references/logging.md), [탐지·대응](references/incident-response.md).

## 22. 린트·포맷 구체 설정

저장소가 사용하는 도구와 명명 규칙을 따른다. 신규 선택에는 자동화·지원 버전·유지 비용을 고려한다.
변경 목적과 무관한 전체 포맷·의존성 교체를 하지 않는다.
[명명·린트](references/lint-naming.md).

## 23. 파이프라인 비동기 패턴

태스크의 소유자·취소·완료·참조 정리를 정의한다. 이벤트 루프를 막는 작업은 적절한 실행기로 옮긴다.
`shield`는 취소 후에도 살아 있어야 하는 작업에만 쓴다. 모든 대기를 무조건 보호하지 않는다.
[비동기 패턴](references/async-patterns.md).

## 24. 웹 백엔드 보안 체크리스트

최소 권한·소유권 검사·입력 제한·안전한 parser·자원 상한으로 공격 표면과 피해 범위를 줄인다.
이미지는 압축 바이트와 실제 치수·누적 프레임·디코딩 자원을 함께 제한한다(web-security §4.2).
예방만으로 끝내지 말고 탐지·차단·복구 경로까지 정의한다(§29).
[코드 보안](references/web-security.md), [운영 보안](references/security-ops.md).

## 25. 인프라·고가용성·장애 복구

필요한 가용성·RPO/RTO·운영 인력을 먼저 정한다. 제품 이름이나 규모만으로 복제·Kubernetes를 추가하지 않는다.
[HA](references/infrastructure-ha.md), [네트워크](references/network-failure.md),
[DB 복구](references/database-recovery.md), [Kubernetes·Helm](references/kubernetes-helm.md).

## 26. 문서 정합성·테스트 품질·병렬 작업

요구사항·결정·계약·수용 검사·운영 문서를 연결한다. 구현을 복제한 테스트보다 실패·불변식을 확인한다.
작업은 독립 검증 가능한 단위로 나누고 실제 통합을 확인한다.
[문서·테스트](references/documentation-testing.md).

## 27. 규모와 디자인 패턴

문제 → 선택 이유 → 최소 구현 → 비용·실패 → 검증 순서로 판단한다.
패턴 이름이나 예제 수를 채우려고 계층·큐·분산 시스템을 늘리지 않는다.
[규모·패턴](references/patterns-scale.md).

## 28. Actuator·메모리 비밀과 컨텍스트 수명

관리 인터페이스·JMX·attach·OS core·JVM heap dump를 각각 점검한다.
요청·작업 종료 시 소유한 컨텍스트·버퍼·참조를 정리하되 즉시 삭제나 root 공격 방어로 설명하지 않는다.
[Actuator](references/java-actuator.md), [메모리 수명](references/memory-secrets.md).

## 29. 빠른 탐지·차단·복구

침해 가능성을 전제로 예방과 함께 관측·알림·격리·자격증명 폐기·복구를 준비한다.
자동 차단은 신뢰도·영향 범위·해제 조건을 정의한 좁은 동작부터 적용한다.
위협 시나리오마다 신호·담당자·초기 조치·복구 확인과 시간 목표를 정하고 훈련으로 측정한다.
[탐지·대응 가이드](references/incident-response.md).

## 17. 추가 메모 (다른 프로젝트에서 옮겨 적기)

- 2026-11-18 · 조각난 규칙·중복 코드를 판단 가이드와 선택형 참조로 정돈했다.
- 2026-11-18 · 탐지·차단·복구(§29), 스택별 적용 범위, 완료 체크리스트를 갱신했다.
- 과거 원문은 [개편 전 본문](https://github.com/joongi007/joongi-skills/blob/738be0fd683846c8ec338a2fd6d060e6a78528a1/skills/engineering-playbook/PLAYBOOK.md)과 Git 이력에서 확인한다.
