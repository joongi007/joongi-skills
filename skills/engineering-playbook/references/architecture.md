# 시스템 아키텍처와 DB 소유권 (PLAYBOOK §3, §4, §7, §12)

## 목차

- 시스템 구조의 최소 단위 (§3)
- 아키텍처 판단 (§4)
- 계층형·헥사고날·모듈형 구조 선택 (§4)
- Hexagonal·Clean Architecture·Modular Monolith의 조합
- DB 소유권 (§7)
- 최적화·운영 태도 (§12)

## 시스템 구조의 최소 단위 (§3)

역할(API·worker·DB·cache·UI), 실행 단위(프로세스·컨테이너·호스트), 데이터 원천과
신뢰 경계를 설명한다. 구성요소마다 의존성·권한·상태 수명·실패 영향을 적는다.
기술 이름은 선택한 프로젝트에 맞추며 cache를 원장으로 오해하지 않게 한다.

## 아키텍처 판단 (§4)

- 요청 안에 끝나는 작업은 함수·모듈부터 시작한다.
- 긴 작업·재시도·부분 실패는 작업 상태·취소·멱등성·복구를 먼저 설계한다.
- cache는 원천·TTL·무효화·오래된 값 허용 범위를 정한다.
- 외부 의존성에는 timeout·동시성·호출량·백오프를 둔다.
- 비밀은 코드 밖의 OS 저장소·시크릿 매니저 등에서 관리한다. 환경변수도 로그·덤프 노출을 검토한다.

## 계층형·헥사고날·모듈형 구조 선택 (§4)

Java에서도 헥사고날 아키텍처를 자동 기본값으로 삼지 않는다. 업무 규칙의 복잡도,
외부 연동 교체·독립 테스트 필요, 팀이 유지할 수 있는 추상화 비용으로 판단한다.
Ports & Adapters는 Java 전용이 아니며 아래 기준은 다른 언어에도 적용한다.

| 상황 | 출발점 | 확인할 비용 |
|---|---|---|
| 단순 CRUD, 변화가 적은 작은 서비스 | controller–service–repository 계층형 | controller·ORM에 업무 규칙이 흩어지는지 |
| 복잡한 업무 규칙, HTTP·배치·메시지에서 같은 유스케이스 실행 | 헥사고날: application/domain + port + adapter | 의미 없는 interface·DTO 변환·간접 호출 증가 |
| 여러 업무 영역을 한 배포 단위에서 관리 | 도메인별 모듈형 모놀리스, 필요 경계에 port | 내부 테이블·구현을 우회 참조하는지 |

모듈형 모놀리스 안에 계층형 또는 헥사고날을 쓸 수 있다. 코드 의존성 구조와
API·worker의 실행 프로세스 분리는 서로 다른 결정이다. 서비스 분리는 아래 DB 소유권 기준도 확인한다.

Java의 주문 견적 예: `QuoteController`가 입력을 검증하고 `QuoteService`를 호출한다.
application이 소유한 `PricePort`를 `HttpPriceAdapter`가 구현하며,
`CachedPriceAdapter`가 같은 port를 감싸면 캐시 정책을 업무 규칙과 분리할 수 있다.
Spring 구성 지점에서 구현을 주입한다. domain/application은 HTTP client·Spring MVC·JPA entity에
직접 의존하지 않도록 경계를 정하고, 외부 DTO를 업무 타입으로 변환한다.
트랜잭션은 유스케이스의 원자성 요구로 정하며, 느린 외부 호출 내내 DB 락을 잡지 않는다.

검증: 유스케이스는 fake port로 정상·오류를 검사하고 HTTP·DB adapter는 실제 계약으로
통합 검사한다. 패키지 의존성 검사로 경계 위반을 찾되 interface 개수를 품질 지표로 삼지 않는다.
단순 CRUD에 이 계층이 불필요하면 기존 구조를 유지하고, 선택 이유와 전환 조건을 ADR에 남긴다.

원전: [Cockburn의 Ports & Adapters](https://alistair.cockburn.us/hexagonal-architecture).
외부 연동·캐시의 상세는 [외부 통신과 캐시](external-cache.md)를 본다.

## Hexagonal·Clean Architecture·Modular Monolith의 조합

이 셋은 배타적인 대안이 아니며 모든 Spring 프로젝트의 필수 조합도 아니다.
서로 겹치는 원칙을 중복 계층으로 구현하기보다 각각 결정하는 경계를 구분한다.

| 개념 | 결정하는 것 | 함께 적용하는 예 |
|---|---|---|
| Modular Monolith (모듈러 모놀리스) | 하나의 배포 단위 안에서 업무 모듈·공개 API·데이터 소유권 분리 | 주문·재고 모듈의 내부 구현을 외부에서 참조하지 않기 |
| Clean Architecture (클린 아키텍처) | 업무 정책으로 향하는 source-code dependency rule | application/domain이 HTTP·DB·framework 구현을 import하지 않기 |
| Hexagonal Architecture (헥사고날 아키텍처) | 외부 입출력을 port와 adapter로 연결 | 같은 유스케이스를 HTTP·worker adapter에서 실행 |

예: 하나의 배포물 안에 주문·재고 모듈을 두고, 모듈 내부에서 유스케이스·domain·port와
HTTP/DB adapter를 나눈다. 다른 모듈은 공개 application API·명시적 이벤트를 통해 접근한다.
공통 DB를 쓸 수 있지만 다른 모듈의 내부 ORM·테이블을 무단 참조하지 않는다. 모듈 간 트랜잭션·
순환 의존·이벤트의 발행/전달 보장은 별도 계약이다. 폴더만 나눈 것은 모듈 경계 검증이 아니다.

| 스택 | 같은 원칙의 적용 예 | 피할 결합 |
|---|---|---|
| Java / Spring | 업무별 package/module, application port와 Spring 구성 지점의 adapter 주입 | MVC/JPA 타입의 domain 유입·모듈 순환 |
| Python / FastAPI | 업무 package의 유스케이스·Protocol/필요한 interface, router/worker adapter와 조립 지점 | Depends·Request·ORM session을 업무 규칙 곳곳에 전달 |
| TypeScript / Express | 업무 module의 유스케이스·port, router/middleware adapter와 명시적 wiring | req/res·전역 service locator·ORM model에 핵심 정책 종속 |
| Go | 업무 package·소비자 측 작은 interface, handler/worker adapter와 생성자 wiring | net/http·DB driver 타입 유출·package import cycle |

Dependency Injection은 의존 객체를 제공하는 방식, Dependency Inversion은 의존 방향의 원칙이다.
DI container 설치나 interface 추가만으로 Clean Architecture가 되지는 않는다. 얇은 CRUD에는 필요한
경계만 두고, 무관한 mapper·port·레이어를 늘리지 않는다. domain event와 integration event도 구분한다.
fake port 기반 업무 검사, adapter 통합 검사와 모듈 간 import/순환 의존 검사를 조합한다.
Spring Modulith 등 도구는 선택지이며 FastAPI·Express에서 같은 검증을 특정 도구로 강제하지 않는다.

근거: [Clean Architecture 원전](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html),
[Spring Modulith 모듈 경계](https://docs.spring.io/spring-modulith/reference/fundamentals.html).

## DB 소유권 (§7)

### 책임과 계약 (§7.1)

스키마·마이그레이션·쓰기 책임자를 정하고 변경의 영향을 추적한다.
독립적으로 배포되는 서비스는 다른 서비스의 내부 ORM보다 공개 API·이벤트 계약을 선호한다.
프로세스나 worker가 분리됐다는 이유만으로 모든 DB 접근을 HTTP 호출로 바꾸지는 않는다.

### 같은 애플리케이션의 API·worker (§7.2)

DB·ORM 공유 여부는 트랜잭션 일관성·배포 단위·개발 비용·보안 요구로 판단한다.
공유하면 스키마 소유자, 최소 권한, migration 순서, 구버전 worker와의 호환성을 기록한다.
따로 관리하면 API 실패·지연·중복 이벤트·부분 성공을 처리한다.
이미 합의한 구조는 유지하고 변경이 필요할 때 이유·대안·검증을 ADR에 남긴다.

### 구조를 바꿀 때 (§7.3)

팀·권한·배포 독립성이 실제로 필요한지 측정한다. 사용자 수만으로 구조를 결정하지 않는다.
분리·공유 모두 데이터 이관·호환 기간·관측·rollback 계획을 포함한다.

## 최적화·운영 태도 (§12)

쿼리·직렬화·원격 호출 등 병목을 먼저 측정한다. 동시성을 늘려 외부 의존성을 과부하시키지 않는다.
좁은 라우팅 규칙·권한 경계를 명확하게 하고 장애·침해 때 관측·격리·복구 가능성을 함께 설계한다.
[탐지·대응](incident-response.md), [네트워크 장애](network-failure.md).
