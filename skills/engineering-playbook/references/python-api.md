# Python·FastAPI 패턴 (PLAYBOOK §5, §6, §9.2, §18)

## 목차

- 패키지 명명 (§5)
- REST API 공통 구조 (§6)
- 도메인 분리 (§9.2)
- 폴더 골격 (§18.1)
- 라우터 등록 패턴 (§18.2)
- Repository 패턴 (§18.3) — 매우 중요
- ORM 모델 베이스 (§18.4)
- NATS 이벤트 라우터 (§18.5)
- constants.py 작성 규칙 (§18.6)

## 패키지 명명 (§5)

- 엔트리 패키지는 `<프로젝트 코드명>_<역할>` **한 단어**로 고정. 예: `rc_api`, `rc_record`, `rc_hub`.
- 범용 `app` 또는 다른 서비스 이름 금지 — 레포와 묶이는 명확한 이름이 나중에 헷갈리지 않는다.
- **설정(`config`)과 애플리케이션(`<패키지명>`)은 분리.**
- **도메인 경계**는 `<패키지>/modules/<도메인>/` 폴더로.
- 의존성 잠금: 실행 단위(서비스)마다 lock 파일. **이미지 빌드에 dev 도구 넣지 않는다** (린트는 로컬/CI).
- `__init__.py` re-export: `__all__` 대신 파일 상단 `# ruff: noqa: F401`:

```python
# ruff: noqa: F401
from rc_hub.registry.plugin import PluginRegistry
```

## REST API 공통 구조 (§6)

| 요소 | 규칙 |
|---|---|
| **버전 prefix** | 모든 브라우저용 JSON API는 `/api/v1` 아래만. 루트 `/`는 헬스·문서 등 인프라용 최소. |
| **라우터 등록** | `register_routers(app)` **한 함수**에서 도메인 라우터를 `include_router`로 묶음. |
| **도메인 폴더** | `router.py` · `service.py` · `schema.py` 한 덩어리. |
| **횡단 관심** | `dependencies.py` (DB 세션, Redis `Depends`), `security.py` (해시·JWT) — 모듈 루트에 한 벌. |
| **설정** | `pydantic-settings` + 환경 변수 prefix 한 종류 (예: `API_`). URL·비밀은 `Field(description=…)`. |
| **부트스트랩** | 시드는 **Alembic 데이터 마이그레이션** + `INSERT … ON CONFLICT DO NOTHING`. lifespan에서 시드 금지 (멀티 워커 중복·레이스). |
| **헬스** | `/healthz` 인증 없이, 짧은 JSON. 프록시에서 SPA와 겹치면 **라우팅 우선순위**로 API 우선. |
| **비밀번호** | bcrypt 직접 사용. `passlib` 등 래퍼 금지 (버전 충돌). |
| **인증** | 상태 없는 API는 **Bearer JWT + `HTTPBearer`** 기본. 자세한 건 `auth-jwt.md`. |

## 도메인 분리 (§9.2)

- **라우터**: HTTP·검증·`Depends` 조립만.
- **서비스**: 규칙·분기. HTTP 없음.
- **스키마**: 입출력 형태 (Pydantic).
- **한 도메인 서비스가 다른 도메인의 테이블을 몰래 직접 만지지 않는다.** 여러 도메인을 한 트랜잭션으로 묶어야 하면 **명시적 "유스케이스" 함수**나 상위 계층에서 조합.
- **순환 import**가 나오면 모듈 나눔이 잘못된 신호 → DTO·프로토콜 이동으로 끊는다.
- 횡단 관심(DB 세션, 현재 사용자, Redis)은 **`dependencies.py` 한곳**에서만 조립해 라우터에 주입.

## 폴더 골격 (§18.1)

```
<패키지>/                # 예: rc_api/
  __init__.py            # FastAPI app + lifespan
  logger.py              # structlog 설정 (logging.md 참고)
  models/                # SQLAlchemy ORM (한 파일 = 한 엔티티)
  modules/
    __init__.py          # register_routers()
    <도메인>/
      router.py
      service.py
      schema.py
    ws/                  # WebSocket 별도 폴더
      router.py
      connection.py
      registry.py        # 이벤트 → 핸들러 매핑
    dependencies.py      # Annotated 타입 앨리어스 전부
    jwt.py               # 토큰 생성·검증
    security.py          # Bearer 의존성·UserInfoManager
  nats/
    router.py            # NatsEventRouter (데코레이터 기반)
    handlers.py          # @nats_router.on(subject)
    broadcaster.py       # WS 브로드캐스트 유틸
  middleware/
  enums/
  utils/
config/
  env.py                 # pydantic-settings, API_ prefix
  constants.py           # NATS subject, Redis key, WS event 상수
  db.py                  # AsyncSession + BaseRepository
```

## 라우터 등록 패턴 (§18.2)

```python
# modules/__init__.py
def register_routers(app: FastAPI) -> None:
    app.include_router(v1_auth_router)
    app.include_router(v1_records_router)
    ...
```

- 라우터 이름: `v1_<도메인>_router = APIRouter(prefix="/api/v1/<도메인>", tags=["<도메인>"])`
- **한 함수에서만** `include_router` — 경로가 분산되지 않게.

## Repository 패턴 (§18.3) — 매우 중요

```python
class BaseRepository[T: Base]:
    def __init__(self, session: AsyncSession): self.session = session
    async def add(self, model: T) -> T: ...  # flush & refresh

    @classmethod
    def inject(cls, session: DbSession) -> Self:               # 수동 커밋
        return cls(session)

    @classmethod
    def inject_autocommit(cls, session: AutocommitDbSession) -> Self:  # 자동 커밋
        return cls(session)

class RecordsRepository(BaseRepository[RecordModel]):
    async def get_by_idx(self, idx: int) -> RecordModel | None: ...
```

**선택 기준:**
- **`inject`**: 트랜잭션을 라우터에서 직접 제어할 때 (여러 INSERT/UPDATE를 한 트랜잭션으로).
- **`inject_autocommit`**: 각 쿼리 즉시 커밋 (단순 읽기, 상태 변경 없는 단발 INSERT 등).

`dependencies.py`에 `Annotated` 앨리어스로 모은다:

```python
RecordsDep = Annotated[RecordsRepository, Depends(RecordsRepository.inject)]
RecordsAutocommitDep = Annotated[RecordsRepository, Depends(RecordsRepository.inject_autocommit)]
```

### 요청 컨텍스트 밖에서 Repository (§18.3.1)

`inject`/`inject_autocommit`은 FastAPI `Depends` 체인 안에서만 동작. lifespan/백그라운드에서 필요하면 **별도 classmethod**:

```python
class SomeRepository(BaseRepository[SomeModel]):
    @classmethod
    def inject(cls, session: DbSession) -> Self: ...

    # lifespan / 백그라운드 전용 — 이름으로 용도 제한
    @classmethod
    async def load_cacheable_for_startup(cls) -> list[SomeModel]:
        async with AsyncSessionLocal() as session:
            return await cls(session).list_cacheable()
```

**규칙:**
- 메서드 이름에 `_for_startup` / `_standalone` 등 용도 명시 (요청 핸들러에서 실수로 호출 방지).
- classmethod 안에서만 `AsyncSessionLocal` 열고 세션 수명 관리.
- 호출부(`lifespan`)에서 직접 `AsyncSessionLocal` 열거나 세션·repo 직접 조립 금지.
- **import는 모듈 최상단**. 함수 내부 lazy import 금지 (실제 순환 참조일 때만 예외).

서비스 함수는 repo 대신 **모델 리스트**를 받는다 — lifespan이 DB 읽기와 부수 작업을 명시적으로 분리:

```python
# modules/some/service.py
async def write_to_cache(models: list[SomeModel], redis) -> int:
    for model in models:
        await redis.set(REDIS_SOME_KEY_FORMAT.format(id=model.id), ...)
    return len(models)
```

## ORM 모델 베이스 (§18.4)

```python
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

class Base(AsyncAttrs, DeclarativeBase):
    def to_dict(self) -> dict: ...   # datetime → isoformat 변환 포함
    def dumps(self) -> str: ...      # Redis 캐싱용 JSON 문자열
    @classmethod
    def loads(cls, s: str) -> Self: ...
```

## NATS 이벤트 라우터 (§18.5)

```python
nats_router = NatsEventRouter()

# Core subscribe — 실시간·유실 허용
@nats_router.on("<domain>.data.<resource>.>")
async def handle_data(msg: Msg) -> None: ...

# JetStream Pull Consumer — 신뢰성 필요 커맨드
@nats_router.on_js_pull(
    "<domain>.command.<action>.>",
    durable="<service>-<domain>",
    stream="<DOMAIN>S",
    batch=10,
    interval=1.0,
)
async def handle_command(msg: Msg) -> None: ...

await nats_router.start(nc, js, redis)
```

**Core vs JetStream 선택 기준:**

| 상황 | 방식 |
|------|------|
| 실시간 센서·상태 스트림, 유실 허용 | Core subscribe |
| 커맨드·작업 요청, 재시도·중복 방지 필요 | JetStream Pull Consumer |
| 완료 이벤트를 다수 서비스가 수신 | JetStream Push Consumer |

- 핸들러는 **`handlers.py` 하나에만**, 라우터 정의는 별도 `router.py`.

## constants.py 작성 규칙 (§18.6)

**상수 이름 패턴:**
- `NATS_SUBJECT_<DOMAIN>_<RESOURCE>_FORMAT` — subject에 자리 표시자 있음
- `NATS_SUBJECT_<DOMAIN>_<RESOURCE>` — 자리 표시자 없는 고정 subject
- `REDIS_<DOMAIN>_<QUALIFIER>_KEY_FORMAT` — Redis key에 자리 표시자
- `WS_EVENT_<DOMAIN>_<ACTION>` — WS 이벤트 이름

**예시:**
```python
# NATS subject — <domain>.<tier>.<resource>.{id} 계층
NATS_SUBJECT_DEVICE_DATA_METRIC_FORMAT  = "device.data.metric.{device_id}"
NATS_SUBJECT_DEVICE_DATA_METRIC         = "device.data.metric.>"     # 와일드카드

# Redis key — {ns}:<domain>:<qualifier>:{id}
REDIS_DEVICE_HASH_KEY_FORMAT = "{ns}:device:{device_id}"
REDIS_USER_INFO_KEY_FORMAT   = "{ns}:users:{user_idx}:info"
REDIS_WS_TICKET_KEY_FORMAT   = "{ns}:ws:ticket:{ticket}"

# WS 이벤트 — v1/<domain>/<action>
WS_EVENT_DEVICE_STATE = "v1/device/state"
WS_EVENT_JOB_NOTIFY   = "v1/job/notify"
```

**규칙 요약:**
- `*_FORMAT` suffix: `.format()` 자리 표시자 포함. 자리 표시자 없는 고정값은 suffix 생략.
- NATS subject 계층: `<도메인>.<tier>.<리소스>` — tier는 `data`(실시간), `command`(요청), `status`(완료) 등.
- `{ns}:` namespace: 같은 Redis 인스턴스를 여러 서비스가 공유할 때 키 충돌 방지.
