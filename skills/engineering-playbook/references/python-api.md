# Python·FastAPI 구현 가이드 (PLAYBOOK §5, §6, §9.2, §18)

Python/FastAPI/SQLAlchemy를 선택한 프로젝트에서 읽는다. 구조 원칙은 [아키텍처](architecture.md),
트랜잭션·RLS·키·쿼리 계획은 [DB 설계](database-design.md)를 따른다.
파일명·패키지명·주입 메서드는 선택형 예시이며 FastAPI 표준 API가 아니다.

## HTTP와 업무 경계 (§5, §6, §9.2)

router는 HTTP 입력·응답·인증 의존성을 조립하고 application/service는 유스케이스를 처리한다.
입출력 schema와 DB model을 분리하고 허용 필드·오류·인가·자원 상한을 검증한다.
다른 도메인 내부 테이블을 무단 참조하지 않는다. 여러 모듈의 원자적 변경은 소유한 유스케이스에서 조합한다.
순환 import는 의존 경계를 재검토하되, lazy import가 항상 잘못된 것은 아니다.

`<project>_api`와 `app` 모두 가능한 패키지명이다. `modules/<domain>/{router,service,schema}.py`,
`dependencies.py`, `config/env.py` 등은 팀 관례로 선택한다. 단순 API에 빈 계층·폴더를 미리 만들지 않는다.
`register_routers(app)`는 라우팅 조립을 모으는 함수 예시다. FastAPI가 이 이름이나 단일 등록 함수를 요구하지 않는다.
버전 경로·health 경로는 [실행 계약](scaffolding.md)과 proxy/probe에 일치시킨다.

## Repository·Unit of Work (§18.3)

Repository는 영속 접근 경계, Unit of Work는 관련 변경의 확정 경계다.
단순 CRUD에서는 ORM 직접 사용도 가능하다. 선택은 테스트·업무 복잡도·외부 구현 교체 비용으로 판단한다.

- 세션 소유자·transaction 시작/commit/rollback·close 시점을 명시한다.
- 같은 유스케이스에서 원자적이어야 하는 변경은 같은 transaction을 사용한다.
- `flush`는 DB에 변경을 전달하는 동작이며 `commit`과 다르다. `refresh`도 commit이 아니다.
- SQLAlchemy의 일반 AsyncSession은 query마다 자동 commit하지 않는다.
  `inject`·`inject_autocommit` 같은 이름만으로 동작을 추정하지 않고 의존성 구현을 확인한다.
- `inject_autocommit`을 선택하면 dependency가 commit하는 시점·예외 rollback·응답 전 실패 전달을 계약으로 정한다.
  요청 종료 시 commit, SQL 단위 autocommit, DB driver isolation mode를 같은 의미로 쓰지 않는다.
- 성공 응답이 이미 나간 뒤 commit이 실패하는 구조를 피한다. 사용 FastAPI 버전의 dependency 종료 시점도 확인한다.
- 요청과 별도 worker/task에 같은 AsyncSession을 공유하지 않는다. 각 소유 작업에서 세션을 열고 닫는다.
- startup·lifespan·worker에서는 composition root나 명시적인 session factory/Unit of Work로 조립할 수 있다.
  모든 세션 생성을 Repository classmethod 안에 숨기라는 규칙은 없다.
- 세션 종료 뒤 전달할 데이터는 필요한 DTO·불변 값으로 변환한다. 미로딩 ORM 관계의 암묵 I/O를 피한다.

`RecordsRepository.inject`, `RecordsAutocommitDep`는 기존 코드에 있을 때 유지할 수 있는 사용자 정의 이름이다.
다른 프로젝트의 DI·transaction 계약을 이 예시에 맞춰 교체하지 않는다.

## ORM·초기화 (§18.1, §18.4)

모델 timestamp의 timezone·서버 생성·업데이트 주체를 명시한다. ORM의 `onupdate`가 모든 raw SQL·
다른 writer의 변경 시각을 자동 보장하지는 않는다. 응답·cache 직렬화는 허용 필드와 schema 버전으로 제한한다.
모든 ORM 필드를 `to_dict()`로 내보내 비밀을 누출하지 않는다.

migration·seed는 재실행·동시 기동·부분 실패·기존 데이터 업그레이드를 고려한다.
Alembic 데이터 migration·별도 bootstrap job 등에서 선택한다. lifespan의 멱등 초기화도 가능하지만
복제본별 중복 실행을 안전하게 처리해야 한다. 특정 위치만으로 동시성 안전을 보장하지 않는다.
인증 방식·password KDF는 [공통 인증](identity-authorization.md), [웹 보안](web-security.md)을 따른다.
bcrypt 직접 호출·JWT Bearer를 모든 API의 기본값으로 강제하지 않는다.

## 메시징·상수 (§18.5, §18.6)

NATS를 이미 사용하거나 요구에 맞춰 선택했을 때만 적용한다.
Core NATS와 JetStream의 보관·전달·재처리 보장을 구분한다. Push/Pull 선택만으로
fan-out·중복 방지·exactly-once가 생기지 않으며 consumer·ack·retention·업무 멱등성을 설계한다.
`NatsEventRouter`, `on_js_pull`, `handlers.py`는 사용자 정의 adapter·파일명 예시다.
작업 상태·outbox·복구는 [작업 계약](background-jobs.md)을 기준으로 한다.

`constants.py`에 NATS subject·Redis key·WS event를 모을 수 있다. 예:

```python
NATS_SUBJECT_ORDER_STATUS = "orders.status.created"
REDIS_ORDER_KEY_FORMAT = "{ns}:tenant:{tenant_id}:order:{order_id}"
WS_EVENT_ORDER_CREATED = "v1/orders/created"
```

이 문법은 선택형이다. namespace가 tenant 인가를 대신하지 않으며 cache key 범위·권한은
[캐시 계약](external-cache.md)을 따른다. 실제 producer·consumer의 이름·버전·호환성을 유지한다.
