# 엔지니어링 플레이북 (팀 공통)

이 문서는 **특정 저장소 한 곳이 아니라**, 앞으로 어떤 프로젝트를 하더라도 같은 결을 내리기 위한 **개인·팀 엔지니어링 원칙**을 모은 것이다.  
여기 없는 요령은 맨 아래 **「추가 메모」**에 날짜와 함께 누적하면 된다.

---

## 목차

파일에 적힌 순서 그대로. §번호는 이 문서 안에서 인용하는 기준이다.

- §1 이 문서를 쓰는 방법
- §2 동시성·성능: 무엇이 어디에 강한가
- §3 시스템 구조를 말할 때의 최소 단위
- §4 아키텍처 판단 (요구가 들어왔을 때)
- §5 모듈화·의존성 (백엔드 예: Python)
- §6 REST API 설계에서 반복하는 공통 구조
- §7 DB 소유권·`shared` 패키지 (기본 vs 예외)
- §8 신규 프로젝트 스캐폴딩 (호스트에 Python/Node 안 깔 때)
- §9 UI·API “개발 원칙” = 코드 분할·모듈 분할
- §10 주석·이름·로그
- §11 UI와 API 계약 (기술)
- §12 최적화·운영에 대한 태도
- §13 신규 작업 체크 (짧게)
- §14 Docker Compose 패턴 (개발 환경)
- §15 비밀번호·URL 인코딩 (`quote_plus`)
- §16 Docker Compose 이미지 설정 패턴
- §18 Python API 구조 패턴 (FastAPI 실무)
- §19 인증·보안 패턴 (JWT RS256 + WS 티켓)
- §20 UI 아키텍처 패턴 (React + Zustand + Axios)
- §21 구조화 로그 (structlog)
- §22 린트·포맷 구체 설정
- §23 파이프라인 비동기 패턴
- §24 웹 백엔드 보안 체크리스트
- §25 인프라·고가용성·장애 복구
- §26 문서 정합성·테스트 품질·병렬 작업
- §27 규모와 디자인 패턴
- §17 추가 메모 (다른 프로젝트에서 옮겨 적기)

---

## 1. 이 문서를 쓰는 방법

- 새 기능·새 레포를 시작할 때 **한 번 훑고**, 논쟁이 생기면 **근거를 여기에 추가**한다.
- “왜 이렇게 했는지”는 ADR을 쓰지 않아도 되지만, **PR이나 이슈에 한 줄이라도** 남긴다.

---

## 2. 동시성·성능: 무엇이 어디에 강한가

### 2.1 한 줄 요약

| 방식 | 네트워크·디스크 등 **I/O 대기** | **CPU 연산** 위주 |
|------|-------------------------------|-------------------|
| **비동기(async)** | 대기 동안 다른 작업으로 넘길 수 있어 **효율적** | 이벤트 루프를 **점유하면 전체가 멈춘다**. **매우 약함** |
| **스레드** | 블로킹 I/O를 격리할 수는 있으나, 스케줄·락·컨텍스트 비용으로 **단순 대기만** 처리하기엔 설계가 무거워지기 쉬움 | Python은 **GIL** 때문에 순수 Python CPU 연산은 **한 시점에 한 스레드만** 실행되는 경우가 많음. 다만 **네이티브 코드**(일부 NumPy/암호화 라이브러리 등) 구간에서는 병렬성이 나올 수 있음 |
| **프로세스** | IPC·직렬화 비용이 큼 | **CPU 병렬**이 필요할 때 후보(GIL을 프로세스 단위로 분리) |

### 2.2 비동기(async)가 강한 이유 (I/O·네트워크)

- 대부분의 요청 처리 시간은 **CPU가 아니라 “응답을 기다리는 시간”**이다.
- `async`/`await`는 **한 스레드 안에서** “기다리는 동안 다른 코루틴에게 제어권을 넘긴다”.
- 그래서 **동시에 많은 느린 I/O**(DB, HTTP, 소켓)를 **적은 스레드**로 감당하기 좋다.

### 2.3 비동기가 약한 이유 (CPU)

- 이벤트 루프는 **한 번에 하나의 코루틴만** 실행한다(대기 제외).
- **무거운 CPU 작업**(대형 JSON 파싱, 이미지 리사이즈, 큰 리스트 집계 등)을 코루틴 안에서 그대로 돌리면, 그동안 **다른 모든 요청·타이머·하트비트가 굶는다**.
- 해결 방향 예:
  - **`asyncio.to_thread()`** 로 스레드 풀에 넘기기(I/O와 섞일 때 타협).
  - **`ProcessPoolExecutor`** 등으로 **프로세스 밖**에서 CPU 작업(대량·장시간).
  - 아예 **배치 워커·큐**로 빼고 API는 “작업 접수만” 하기.

### 2.4 스레드가 강한 쪽·약한 쪽

- **강함**: 블로킹 전용 API만 있을 때(레거시 SDK 등) **제한된 수의 스레드 풀**로 격리.
- **약함**: “스레드를 많이 늘리면 빨라진다”는 식의 단순 I/O 확장은 **문맥 전환·락 경합**으로 이득이 줄거나 역전될 수 있음.
- Python에서 **순수 CPU 병렬**을 스레드만으로 기대하기 어려운 이유가 **GIL**이다(언어 구현 특성).

### 2.5 선택 절차 (짧게)

1. 이 코드가 **대기(I/O)가 대부분**인가 → **async 파이프라인**을 먼저 검토.
2. **CPU가 오래** 걸리는가 → **루프 밖**으로(스레드/프로세스/배치) 빼는지 결정.
3. **외부 시스템 보호**(rate limit)가 필요한가 → 동시성 수·간격·타임아웃을 **설정값**으로 노출.

### 2.6 수평 확장: 멀티 프로세스·클러스터·다중 Pod

- **기본 전제**: “지금은 인스턴스 하나로도 된다”만으로 설계를 닫지 않는다. **정말 단일 프로세스로 충분하다는 근거가 있을 때만** 단일화를 택한다.
- **API**: 복제본 N개를 띄워도 되게 **로컬 메모리에만 두면 안 되는 상태**(세션·rate limit 카운터 등)는 Redis·DB·스토리지로 빼고, 헬스·리더 선출이 필요하면 **분산 락·오케스트레이션 규약**을 문서에 남긴다.
- **워커·수집기**: 동일 입력을 여러 Pod가 나눠 받을 때 **멱등 키·파티션·락**으로 중복·경합을 감당할 수 있게 설계한다.
- **예외**: 트래픽·팀 규모상 **당분간 단일 Pod/단일 프로세스로 간다**는 결정은 가능하되, 그 경우에도 **replica 수만 늘리면 되는지** 한 번 검토한 뒤 “의도적 단일”이라고 남긴다.

### 2.7 수신부 ↔ 처리부 분리(버퍼·생산자-소비자)

- 데이터 **수신**(HTTP·소켓·폴링 등)과 **처리**(검증·변환·저장·외부 연쇄 호출)를 **한 흐름에 몰아넣지 않고**, 사이에 **버퍼(큐)** 를 두는 구조를 **기본 그림**으로 떠올린다.
- **프로세스 간**(또는 Pod 간): 수신 쪽은 **버퍼에 빠르게 적재**만 하고, 처리 쪽은 **버퍼에서 꺼내서** 속도를 맞춰 처리한다. 버스트를 흡수하고, 수신과 처리를 **서로 다른 스케일**로 늘리기 쉽다.
- **스레드 간**(한 프로세스 안): `queue.Queue` 등으로 같은 패턴을 **축소 적용**할 수 있다. 다만 Python에서는 **CPU 처리가 GIL에 묶일 수 있어**, 무거운 CPU는 **프로세스 분리(§2.3)** 와 함께 보는 편이 안전하다.
- 구현체는 Redis Stream·RabbitMQ·Kafka·파일 스풀·DB 큐 등 **프로젝트에 맞게** 고르되, **“수신 완료”와 “처리 완료”의 경계**를 코드·로그·메트릭에서 구분할 수 있게 한다.

---

## 3. 시스템 구조를 말할 때의 최소 단위

- **논리**: 역방향 프록시, API, 워커, DB, 캐시, UI — 각각 **역할 한 줄**로 적을 수 있어야 한다.
- **물리**: 컨테이너/프로세스 단위로 **무엇이 무엇에 의존하는지**(DB 주소, Redis 유무)를 그림이나 표로 고정한다.
- **데이터**: “원장의 단일 소스”가 어디인지(DB인지, 이벤트 스트림인지)를 먼저 정한다. 캐시는 **부가물**이다.

(리버스 프록시·라벨·네트워크 격리 같은 구체 기술은 **팀이 정한 스택**에 맞게 적되, 원칙은 **“같은 호스트에서 라우팅이 섞이지 않게 제약을 건다”** 정도로 일반화한다.)

---

## 4. 아키텍처 판단 (요구가 들어왔을 때)

- **요청–응답 안에 끝나는가** → API/함수 레벨로 충분한지.
- **수 분 이상·재시도·부분 실패**가 있는가 → 워커·큐·스케줄러 후보.
- **캐시**를 쓸 때: 미스 시 **항상 같은 원천**으로 수렴하는가, **TTL vs 무효화** 중 무엇인가.
- **비밀·토큰**: 저장소에 넣지 않고 **환경 변수**, 예시는 **`.env.example`만**.
- **외부 API 부하**: 간격·동시성 상한·타임아웃을 **환경 변수**로 노출해 운영에서 조절 가능하게.

---

## 5. 모듈화·의존성 (백엔드 예: Python)

- **엔트리 패키지 이름**은 `<프로젝트 코드명>_<역할>` 형태 한 단어로 고정한다(예: `rc_api`, `rc_record`). 다른 서비스의 이름이나 범용 `app`보다 **레포와 묶이는 명확한 이름**이 나중에 헷갈리지 않는다.
- **설정(`config`)과 애플리케이션(`<패키지명>`)은 분리**한다. 환경·연결 문자열·상수는 설정 쪽, HTTP·라이프사이클은 앱 쪽.
- **도메인 경계**는 `<패키지>/modules/<도메인>/` 처럼 **폴더로 나누고**, 라우터는 얇게·비즈니스는 서비스 모듈로.
- **의존성 잠금**: 실행 단위(서비스)마다 lock 파일을 두고, **이미지 빌드에는 dev 도구를 넣지 않는다**(린트는 로컬/CI).
- **`__init__.py` re-export**: `__all__` 대신 파일 상단 `# ruff: noqa: F401`을 쓴다. ruff F401(unused import) 경고만 억제하고 `__all__` 동기화 부담을 없앤다.
  ```python
  # ruff: noqa: F401
  from rc_hub.registry.plugin import PluginRegistry
  ```

---

## 6. REST API 설계에서 반복하는 공통 구조

여러 프로젝트를 거치며 **계속 쓰는 패턴**을 여기에 고정한다(프레임워크는 FastAPI 기준이지만, 원칙은 이식 가능).

| 요소 | 공통 |
|------|------|
| **버전 prefix** | 모든 브라우저/클라이언트용 JSON API는 **`/api/v1`** 아래에만 둔다. 루트 `/`는 헬스·문서 등 **인프라·내부용**만 최소로. |
| **라우터 등록** | `APIRouter(prefix="/api/v1")` 하나에 도메인별 라우터를 `include_router`로 묶는 **`register_routers(app)` 한 함수**로 모은다. |
| **도메인 폴더** | 도메인마다 `router.py` · `service.py` · `schema.py` 를 두고, HTTP는 라우터·규칙은 서비스·입출력 형태는 스키마에만 둔다. |
| **횡단 관심** | `dependencies.py`(DB 세션, Redis 등 `Depends`), `security.py`(비밀번호 해시·JWT·Bearer)는 **모듈 루트에 한 벌** 두고 재사용한다. |
| **설정** | `pydantic-settings` + **환경 변수 prefix** 한 종류(예: `API_`)로 통일, URL·비밀은 `Field(description=…)` 로 `.env` 편집자에게 힌트를 준다. |
| **부트스트랩** | 관리자·기본 마스킹 행 등 시드는 **Alembic 데이터 마이그레이션**으로 넣고 `INSERT … ON CONFLICT DO NOTHING` 등으로 멱등하게 한다. API lifespan에서 DB 시드를 돌리면 멀티 워커·재시작마다 중복 비용·레이스가 생기므로 피한다. |
| **헬스** | 로드밸런서·오케스트레이션용 **`/healthz`** 는 인증 없이 짧은 JSON으로. 프록시에서 SPA와 경로가 겹치면 **라우팅 우선순위**로 API 쪽으로 보낸다. |
| **비밀번호** | 검증된 **bcrypt 직접 사용** 등, 오래된 래퍼+최신 네이티브 조합으로 깨지는 형태는 피한다. |
| **인증** | 상태 없는 API는 **Bearer JWT** + `HTTPBearer` 조합을 기본으로 두고, 예외가 있으면 문서에만 적는다. |

---

## 7. DB 소유권·`shared` 패키지 (기본 vs 예외)

### 7.1 기본(문서·플레이북 기준)

- **DB 스키마·ORM·마이그레이션은 API 서비스 한 곳에서만** 다룬다.
- 워커·배치·다른 프로세스는 **DB에 직접 붙지 않고**, 그 API가 노출한 **REST(또는 합의된 내부 API·이벤트)** 로만 읽고 쓴다.
- 이렇게 하면 **배포 단위·팀 경계**가 나뉘어도 결합이 덜하고, “스키마의 단일 소스”가 명확하다.

**누가 물으면(기본 답)** 이렇게 말하면 된다: “DB는 API만 담당하고, 나머지는 API를 통해서만 붙인다.”

### 7.2 예외: `shared`에 ORM을 두는 모노레포 방식

- API와 워커가 **같은 패키지로 모델을 공유**하는 방식은 **기본 허용 목록에 넣지 않는다.**
- **구두로 명시적으로 허용했을 때만** 쓴다(예: “이번 건은 shared로 가자”처럼 담당자가 입으로 승인).
- 예외를 택한 프로젝트는 **README나 이슈에 한 줄이라도** “`shared` ORM 사용 — 구두 승인(일자·누구)”를 남겨, 나중에 기본으로 되돌릴 때 근거를 찾을 수 있게 한다.

### 7.3 나중에 바꿀 때

- 조직·트래픽이 커지면 예외였던 저장소도 **§7.1 기본**으로 맞추는 것이 자연스럽다(워커 → API만 호출, 스키마는 API 쪽만).

---

## 8. 신규 프로젝트 스캐폴딩 (호스트에 Python/Node 안 깔 때)

다른 사람이 “어떻게 초기화했냐”고 물으면 **아래를 그대로 안내**하면 된다.

**Python(uv, Python 3.14 이미지)**

```bash
docker run --rm -v "$(pwd)":/app -w /app ghcr.io/astral-sh/uv:python3.14-bookworm-slim uv init
```

**UI(Vite + React + TypeScript)**

```bash
docker run --rm -it -v "$(pwd)":/app -w /app node:24-slim \
  npm create vite@latest . -- --template react-ts
```

- 빈 디렉터리에서 실행하는 것이 안전하다(`.` 대신 새 폴더를 마운트해도 된다).
- 팀 표준 Node/uv 태그가 바뀌면 **이 문서의 버전만 갱신**한다.

---

## 9. UI·API “개발 원칙” = 코드 분할·모듈 분할

여기서 말하는 원칙은 **색·간격 같은 순수 UX 체크가 아니라**, 서로 다른 프로젝트에도 그대로 이식되는 **파일 경계·훅·상태·의존성 방향**이다. (밀도·타이포·접근성 등은 **제품별 `docs`**에 둔다.)

### 9.1 UI (예: React + TS)

- **폴더 축**: `pages`(또는 `routes`) / `components` 만으로 끝내지 말고, 팀이 정한 규칙에 따라 **`features/<도메인>/`** 처럼 **기능 단위**로 묶을 수 있으면 묶는다.
- **파일당 책임**: 한 화면 파일에 마크업·fetch·폼·derived state를 전부 넣지 않는다. **표시(프레젠테이션)** 와 **데이터를 가져와 조합하는 층**을 나눈다.
- **hook**:
  - `useXxx`는 **하나의 관심사**(한 자원의 fetch, 한 폼의 lifecycle, 한 interval)에 대응시킨다.
  - 두 화면 이상이 쓰면 **`hooks/` 또는 `features/...` 안으로** 올리고, **여러 무관한 일을 하는 god hook**은 쪼갠다.
- **상태를 어디에 두는지**:
  - **서버에서 온 진실**(목록·설정·집계): 가능하면 **요청 캐시·무효화가 있는 도구**(TanStack Query, SWR 등)로 두고, 전역 Context에 API 응답을 복붙하지 않는다.
  - **UI만의 상태**: 기본은 **컴포넌트 로컬**; 형제끼리만 공유면 **가까운 공통 부모로 lift**; 앱 전역은 **정말 필요한 키만** Context·외부 스토어에 둔다.
- **코드 스플릿**: 라우트 단위 **lazy import**, 차트·에디터 등 무거운 묶음은 **동적 import**로 초기 번들을 줄인다.
- **모듈 경계**: `features/A`가 `features/B`의 내부 구현 파일을 직접 import하지 않게, **공개 entry(`index.ts`)·타입만** 바깥으로 노출하는 식으로 **의존 방향**을 고정한다.

### 9.2 API (백엔드)

- **도메인 = 디렉터리**: `router` / `service` / `schema` 를 한 덩어리로 두고(§6과 같이), **한 도메인 service가 다른 도메인의 테이블을 몰래 직접 만지지** 않게 한다. 여러 도메인을 한 트랜잭션으로 묶어야 하면 **명시적인 “유스케이스” 함수**나 상위 계층에서 조합한다.
- **라우터**는 HTTP·검증·`Depends` 조립만; **규칙·분기**는 service; **입·출력 형태**는 schema — **한 파일에 세 역할을 섞지 않는다.**
- **횡단 관심**(DB 세션, 현재 사용자, Redis)은 **`dependencies.py` 등 한곳**에서만 조립해 라우터에 주입한다.
- **순환 import**가 나오면 “모듈 나눔이 잘못된 신호”로 보고, **DTO·프로토콜 이동**으로 끊는다.
- **공개 API 경로**(`/api/v1` 등)는 **한 곳에서** 라우터 트리에 붙인다(§6).

---

## 10. 주석·이름·로그

- **식별자·이벤트 키**: 영어 `snake_case`.
- **도메인 설명·운영 메모·사용자에게 보이는 짧은 문장**: 팀 언어(한국어 가능).
- 주석은 **비즈니스 규칙·보안/운영 주의·임시 우회(이슈 번호)** 에만 남긴다. 자명한 한 줄은 이름으로 해결한다.
- 구조화 로그는 **한 줄 JSON + 고정 이벤트 이름**, PII는 넣지 않는다.

---

## 11. UI와 API 계약 (기술)

- 브라우저가 부르는 API 경로에 **버전 prefix**를 둔다(예: `/api/v1/...`).
- 클라이언트 `baseURL`은 **상대 경로(`/api/...`)** 를 기본으로 두어, 배포·리버스 프록시 뒤에서 **동일 오리진**을 유지하기 쉽게 한다.
- 브라우저에 **시크릿을 넣지 않는다**. 공개만 해도 되는 값만 빌드 타임 env로.

### 11.1 개발할 때 UI는 무엇으로 띄우나

- **UI만 빠르게 고칠 때**는 호스트에서 **`npm run dev`**(Vite dev 서버)가 보통 가장 편하다. 컨테이너로 동일하게 돌려도 되지만, “에디터 저장 → 즉시 반영” 루프를 우선한다.
- **리버스 프록시(Traefik 등)로 검증**할 때는, 브라우저가 **프록시가 노출한 단일 URL**(예: `http://127.0.0.1:9443`)만 보면 되게 두고, 그 뒤에서 **`/api` → API**, **`/` → Vite** 처럼 **경로(prefix)로 분기**한다.
- 이 구성에서는 브라우저 입장에서 **이미 같은 오리진**이므로, UI 쪽에 **Vite `server.proxy` 같은 이중 프록시를 꼭 둘 필요가 없다**. `fetch('/api/...')`만으로 프록시가 API로 넘긴다(HMR용 `clientPort` 등 **웹소켓 예외**는 별도).

### 11.2 로컬에서 Vite만 단독으로 켠 경우(프록시 없이 API 호스트가 다를 때)

- 브라우저가 `localhost:5173`이고 API가 다른 포트·호스트면 **CORS·절대 URL** 문제가 생긴다. 이때만 **Vite 프록시** 또는 **API의 CORS 허용** 같은 추가 수단을 택한다. **§11.1처럼 한 진입점으로 묶을 수 있으면 그쪽을 먼저** 본다.

### 11.3 네트워킹·배포는 “단순 확인 → 복잡화” 순서

- 먼저 **브라우저 한 탭으로** “진입 URL에서 UI가 뜨는지”, **`/healthz`·대표 API 한두 개**가 기대대로 오는지 확인한다.
- 그다음에만 **추가 도메인·TLS 종단·이중 프록시·헤더 트릭** 등으로 넓힌다. 처음부터 복잡한 솔루션으로 가지 않는다.

---

## 12. 최적화·운영에 대한 태도

- 먼저 **측정 가능한 병목**(쿼리 한 번, N+1, 불필요한 직렬화)을 없앤 뒤, **동시성을 늘린다**.
- **외부 시스템**은 “내 서버가 버틴다”보다 **상대가 망가지지 않게** 스로틀·백오프·타임아웃을 기본값으로 둔다.
- 프록시 뒤에서는 **좁은 경로 규칙이 넓은 규칙보다 우선**하도록 우선순위를 설계한다(SPA 폴백과 API 경로 충돌 방지).

---

## 13. 신규 작업 체크 (짧게)

- [ ] 이 작업은 **I/O 바운드**인가 **CPU 바운드**인가 — 위 §2와 맞는가.
- [ ] 실패 시 **사용자/운영자**에게 무엇이 보이는가(에러 메시지, 로그 이벤트).
- [ ] 설정이 **환경 변수로 노출**되는가, 기본값이 안전한가.
- [ ] 한 저장소 안에서 **의존성 경계**(공유 vs 앱 전용)가 깨지지 않았는가.
- [ ] DB에 워커 등이 직접 붙는 경우, **`shared` ORM 예외는 구두 승인 + 기록**이 있는가(기본은 §7.1).
- [ ] 부하가 늘었을 때 **replica·워커 수를 늘릴 수 있는가**(§2.6). 수신과 처리가 붙어 있지 않다면 **버퍼·큐 경계**가 명확한가(§2.7).
- [ ] UI는 **훅·상태·feature 경계**(§9.1), API는 **도메인·router/service/schema**(§9.2)가 지켜졌는가.
- [ ] UI–API 연결은 **§11.3** 순서로 검증했는가(단일 진입점·상대 `/api` 우선, 불필요한 Vite 프록시 남발 없음).
- [ ] API: **Repository `inject` vs `inject_autocommit`** 선택이 맞는가(§18.3). `dependencies.py`에 Annotated 앨리어스 있는가.
- [ ] JWT: **RS256 키 파일 분리**, `jtt`/`rjti`/`fjti` claims 포함, 만료 **환경 변수**로 설정(§19.1).
- [ ] 로그인: 성공/실패 모두 **동일한 401 메시지**, `is_active` 확인, 세션을 `fjti` 키로 Redis 저장(§19.5).
- [ ] Refresh: **Lua 원자적 교체** + `current_jti` 불일치 시 세션 DEL. grace period 캐시로 재시도 안전(§19.7).
- [ ] 로그아웃: 세션 키(`{ns}:users:{idx}:fjti:{fjti}`) **DEL**(§19.8).
- [ ] 민감 엔드포인트(비밀번호 변경 등): `POST /token/fresh`로 재인증 후 `fresh=True` access token 획득 흐름 명세(§19.6).
- [ ] **CORS origins 환경 변수화**, 와일드카드 `*` 미사용(§19.10).
- [ ] WS: 단발 티켓 패턴 사용(§19.3). 이벤트 이름 `v1/<domain>/<action>` 형식(§20.4).
- [ ] UI: **access token → sessionStorage**, **refresh token → localStorage**(§20.2). 동시 401 방어 큐 있는가.
- [ ] 파이프라인: **blocking I/O는 이벤트 루프 밖으로** (`asyncio.to_thread` / `queue.Queue` 워커)(§23.1). Task 참조 집합으로 추적(§23.2).
- [ ] 로그: `snake_case` 이벤트 이름, `exc_info=e`, PII 없음(§21).

---

## 14. Docker Compose 패턴 (개발 환경)

### 14.1 env_file + 베이스 변수 참조 구조

환경 변수는 **인프라 베이스 → 서비스별 변수 참조** 방식으로 `.env` 한 파일에서 관리한다.  
docker-compose 서비스에는 `env_file: .env` 한 줄만 붙이고, 개별 `environment:` 블록에 값을 하드코딩하지 않는다.

```dotenv
# 인프라 베이스
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=myapp
POSTGRES_PASSWORD=secret

# 서비스별 (베이스 참조)
API_POSTGRES_HOST=${POSTGRES_HOST}
API_POSTGRES_PORT=${POSTGRES_PORT}
API_POSTGRES_USER=${POSTGRES_USER}
API_POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

```yaml
services:
  api:
    env_file: .env   # API_POSTGRES_* 전부 자동 주입
  worker:
    env_file: .env   # WORKER_POSTGRES_* 도 같은 파일에서
```

- **로컬(Docker 없이)**: `POSTGRES_HOST=localhost` 로만 바꾸면 된다.
- **`.env`는 gitignore**, **`.env.example`은 커밋** — 실제 비밀은 `.env`에만.

### 14.2 개발용 볼륨 마운트 (Hot-reload)

프로덕션 이미지는 코드를 COPY하지만, **개발 환경에서는 소스 폴더를 컨테이너에 마운트**해 저장 즉시 반영되게 한다.  
venv·node_modules 같은 **빌드 산출물은 named volume으로 분리**해 호스트 디렉터리를 오염시키지 않는다.

```yaml
services:
  api:
    volumes:
      - ./api:/app/api          # 소스 — 호스트와 동기화
      - ./shared:/app/shared
      - api-venv:/app/.venv     # 패키지 — 컨테이너 전용 named volume

  sample-ui:
    volumes:
      - ./sample-ui:/app
      - sample_ui_node_modules:/app/node_modules   # node_modules 분리

volumes:
  api-venv:
  sample_ui_node_modules:
```

### 14.3 컨테이너 로그 설정

프로덕션·장기 실행 서비스에는 로그 드라이버 옵션을 명시해 **디스크 무제한 증가를 막는다**.

```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 14.4 초기화 컨테이너 패턴 (Initor)

마이그레이션·설정 파일 생성 등 **1회성 초기화 작업**은 별도 서비스로 분리한다.  
본 서비스는 `service_completed_successfully` 조건으로 대기한다.

```yaml
services:
  api-init:
    image: myapp-api
    env_file: .env
    command: ["uv", "run", "alembic", "upgrade", "head"]
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"          # 완료 후 재시작 안 함

  api:
    image: myapp-api
    env_file: .env
    depends_on:
      api-init:
        condition: service_completed_successfully
```

---

## 15. 비밀번호·URL 인코딩 (`quote_plus`)

DB/Redis URL을 코드에서 직접 조립할 때, **비밀번호에 특수문자(`!@#$%` 등)가 들어오면 URL 파싱이 깨진다.**  
반드시 `urllib.parse.quote_plus`로 인코딩한다.

```python
from urllib.parse import quote_plus

# ❌ 특수문자 비밀번호가 들어오면 파싱 오류
url = f"postgresql+asyncpg://{user}:{password}@{host}/{db}"

# ✅ quote_plus로 인코딩
url = f"postgresql+asyncpg://{user}:{quote_plus(password)}@{host}/{db}"
```

- **`.env`에서 비밀번호를 읽어 URL을 조립하는 모든 곳**에 적용한다.
- `quote_plus`는 공백을 `+`로, 나머지 특수문자를 `%XX`로 인코딩한다.
- `pydantic-settings`의 `@cached_property`로 URL을 한 번만 계산한다.

```python
@cached_property
def DATABASE_URL(self) -> str:
    return (
        f"postgresql+asyncpg://{self.POSTGRES_USER}:{quote_plus(self.POSTGRES_PASSWORD)}"
        f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    )

@cached_property
def REDIS_URL(self) -> str:
    if self.REDIS_PASSWORD:
        return f"redis://:{quote_plus(self.REDIS_PASSWORD)}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
```

---

## 16. Docker Compose 이미지 설정 패턴

### 16.1 `build` + `image` 조합 — 로컬 빌드 이미지를 태그하고 재사용

`build`만 쓰면 이미지 이름이 없어서 다른 서비스가 참조할 수 없다.  
`build` + `image`를 함께 쓰면 빌드 결과에 이름이 붙어 **같은 이미지를 다른 서비스에서 재사용**할 수 있다.

```yaml
# api 서비스: 빌드하면서 이름 부여
api:
  build:
    context: .
    dockerfile: docker/Dockerfile.api
  image: myapp-api          # 빌드 결과 이미지 이름
  pull_policy: never

# api-init: 빌드 없이 위에서 만든 이미지를 그대로 참조
api-init:
  image: myapp-api          # build 없음 — api가 먼저 빌드되어 있어야 함
  pull_policy: never
  command: ["uv", "run", "alembic", "upgrade", "head"]
  restart: "no"
```

> **주의**: `docker compose up`은 `depends_on` 순서와 무관하게 `api`를 먼저 빌드한다.  
> `api-init`에 `build`가 없으면 `api` 이미지가 로컬에 존재해야 하므로,  
> **첫 실행 시에는 반드시 `api` 서비스가 먼저 빌드되어야 한다.**  
> (실제로는 `docker compose up --build`로 한 번에 해결된다.)

---

### 16.2 `pull_policy: never` — 레지스트리 pull 차단

로컬 전용 이미지에는 반드시 추가한다.  
없으면 Docker가 동일 이름의 이미지를 레지스트리에서 pull하려다 실패하거나, 예상과 다른 이미지가 내려올 수 있다.

```yaml
api:
  image: myapp-api
  pull_policy: never    # 로컬 빌드 이미지 → 레지스트리 조회 금지
```

공식 이미지(`postgres`, `redis` 등)는 `pull_policy`를 생략하면 기본값(`missing` = 없을 때만 pull)이 적용되어 안전하다.

---

### 16.3 인프라 이미지 버전 태그 고정

`latest`는 사용하지 않는다. **메이저 버전 + `-alpine` / `-slim`** 태그로 고정한다.

```yaml
postgres:
  image: postgres:16-alpine   # ✅ 버전 고정
  # image: postgres:latest    # ❌ 업데이트 때 예기치 않은 변경

redis:
  image: redis:7-alpine

traefik:
  image: traefik:v3

# Node 기반 개발 서버 (Dockerfile 없이)
ui:
  image: node:22-bookworm-slim
  working_dir: /app
  command:
    - sh
    - -c
    - npm ci --no-audit --no-fund && exec npm run dev
```

`-alpine`은 이미지 크기가 작고, `-bookworm-slim`은 Debian 기반으로 호환성이 높다.

---

### 16.4 멀티 컴포즈 파일 운영 시 이미지·프로젝트 이름 충돌 방지

같은 호스트에서 여러 컴포즈 파일을 함께 운영하면 이미지 이름이 같아 서로 덮어쓸 수 있다.  
**각 컴포즈 파일마다 이미지 이름과 `name:`을 다르게 설정한다.**

> rnd-dashboard 예시: 내부 운영용 `docker-compose.yml` + 외주처에 전달하는 샘플용 `docker-compose.sample.yml`

```yaml
# docker-compose.yml (내부 운영용)
name: myapp
api:
  image: myapp-api

# docker-compose.sample.yml (외주 샘플용 — 포트 노출, 코드 볼륨 마운트 포함)
name: myapp-sample
api:
  image: myapp-sample-api    # suffix로 이미지 이름 분리
```

`name:`이 다르면 컨테이너·볼륨 이름도 자동으로 분리된다.

---

### 16.5 전체 구조 요약

```
docker-compose.yml          → 내부 운영/배포용
  name: myapp
  api:      build + image: myapp-api,       pull_policy: never
  api-init: image: myapp-api,               pull_policy: never, restart: "no"
  collector: build + image: myapp-collector, pull_policy: never
  ui:       image: node:22-bookworm-slim    (Dockerfile 없음)

docker-compose.sample.yml   → 외주 전달용 샘플 (포트 노출 + 코드 볼륨 마운트)
  name: myapp-sample
  api:      build + image: myapp-sample-api, pull_policy: never
  api-init: image: myapp-sample-api,         pull_policy: never, restart: "no"
  collector: build + image: myapp-sample-collector, pull_policy: never
  ui:       image: node:22-bookworm-slim    (동일 — 빌드 불필요)
```

- 샘플용 컴포즈에서만 소스 코드를 볼륨 마운트해 **핫리로드** 지원
- 인프라 포트(`5432`, `6379`)는 샘플용에서만 호스트로 노출

---

## 18. Python API 구조 패턴 (FastAPI 실무)

### 18.1 폴더 골격

```
<패키지>/          # 예: rc_api/
  __init__.py      # FastAPI app + lifespan
  logger.py        # structlog 설정
  models/          # SQLAlchemy ORM 모델 (한 파일 = 한 엔티티)
  modules/
    __init__.py    # 모든 라우터를 register_routers()로 묶음
    <도메인>/
      router.py    # HTTP 엔드포인트만 (검증·Depends 조립)
      service.py   # 비즈니스 로직·분기 (HTTP 없음)
      schema.py    # Pydantic 입출력 모델
    ws/            # WebSocket 별도 폴더
      router.py
      connection.py
      registry.py  # 이벤트 → 핸들러 매핑
    dependencies.py  # Annotated 타입 앨리어스 전부
    jwt.py           # 토큰 생성·검증
    security.py      # Bearer 의존성·UserInfoManager
  nats/
    router.py      # NatsEventRouter (데코레이터 기반 구독)
    handlers.py    # @nats_router.on(subject) 핸들러들
    broadcaster.py # WS 브로드캐스트 유틸
  middleware/
  enums/
  utils/
config/
  env.py           # pydantic-settings, API_ prefix
  constants.py     # NATS subject, Redis key, WS event 상수
  db.py            # AsyncSession + BaseRepository
```

### 18.2 라우터 등록 패턴

```python
# modules/__init__.py
def register_routers(app: FastAPI) -> None:
    app.include_router(v1_auth_router)
    app.include_router(v1_records_router)
    ...
```

- 라우터 이름: `v1_<도메인>_router = APIRouter(prefix="/api/v1/<도메인>", tags=["<도메인>"])`
- 한 함수에서만 `include_router` — 경로가 분산되지 않게.

### 18.3 Repository 패턴

```python
class BaseRepository[T: Base]:
    def __init__(self, session: AsyncSession): self.session = session
    async def add(self, model: T) -> T: ...  # flush & refresh

    @classmethod
    def inject(cls, session: DbSession) -> Self:           # 수동 커밋
        return cls(session)

    @classmethod
    def inject_autocommit(cls, session: AutocommitDbSession) -> Self:  # 자동 커밋
        return cls(session)

class RecordsRepository(BaseRepository[RecordModel]):
    async def get_by_idx(self, idx: int) -> RecordModel | None: ...
```

- **`inject`**: 트랜잭션을 라우터에서 직접 제어할 때.
- **`inject_autocommit`**: 각 쿼리 즉시 커밋 (상태 변경 없는 INSERT 등).
- `dependencies.py`에 `Annotated` 앨리어스로 모음:
  ```python
  RecordsDep = Annotated[RecordsRepository, Depends(RecordsRepository.inject)]
  RecordsAutocommitDep = Annotated[RecordsRepository, Depends(RecordsRepository.inject_autocommit)]
  ```

### 18.3.1 요청 컨텍스트 밖에서 Repository 사용 (lifespan·백그라운드 태스크)

`inject` / `inject_autocommit`은 FastAPI `Depends` 체인 안에서만 동작한다.  
lifespan, 백그라운드 태스크 등 **요청 컨텍스트가 없는 곳**에서 Repository가 필요하면 `AsyncSessionLocal`을 직접 여는 classmethod를 Repository에 추가한다.

**규칙:**
- 메서드 이름에 `_for_startup` / `_standalone` 등 용도를 명시해 요청 핸들러에서 실수로 호출하는 것을 방지한다.
- 해당 classmethod 안에서만 `AsyncSessionLocal`을 열고 세션 수명을 관리한다.
- 호출부(`lifespan` 등)에서 직접 `AsyncSessionLocal`을 열거나 세션·repo를 직접 조립하지 않는다.
- **import는 모듈 최상단**에 둔다. 함수 내부 lazy import는 금지 (순환 참조가 실제로 발생하는 경우에만 예외).

```python
# models/some_model.py
from config.db import AsyncSessionLocal, Base, BaseRepository, TimestampMixin

class SomeRepository(BaseRepository[SomeModel]):

    # 요청 컨텍스트용 — Depends 체인 내부에서만 사용
    @classmethod
    def inject(cls, session: DbSession) -> Self: ...

    # lifespan / 백그라운드 태스크 전용 — 이름으로 용도 제한
    @classmethod
    async def load_cacheable_for_startup(cls) -> list[SomeModel]:
        async with AsyncSessionLocal() as session:
            return await cls(session).list_cacheable()
```

```python
# rc_api/__init__.py (lifespan)
from rc_api.models.some_model import SomeRepository       # 모듈 최상단
from rc_api.modules.some.service import write_to_cache    # 모듈 최상단

async def lifespan(app: FastAPI):
    ...
    models = await SomeRepository.load_cacheable_for_startup()
    count = await write_to_cache(models, app.state.redis)
    logger.info("cache_preloaded", count=count)
```

**서비스 함수 시그니처**: repo 대신 **모델 리스트**를 받는다. lifespan이 DB 읽기(repo)와 부수 작업(redis 쓰기)을 명시적으로 분리·조율한다.

```python
# modules/some/service.py
async def write_to_cache(models: list[SomeModel], redis) -> int:
    for model in models:
        await redis.set(REDIS_SOME_KEY_FORMAT.format(id=model.id), ...)
    return len(models)
```

### 18.4 ORM 모델 베이스

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

### 18.5 NATS 이벤트 라우터

```python
nats_router = NatsEventRouter()

# Core subscribe — 실시간·유실 허용 데이터 (fire-and-forget)
@nats_router.on("<domain>.data.<resource>.>")
async def handle_data(msg: Msg) -> None: ...

# JetStream Pull Consumer — 신뢰성 필요 커맨드 (재시도·영속 보장)
@nats_router.on_js_pull(
    "<domain>.command.<action>.>",
    durable="<service>-<domain>",   # 컨슈머 이름: 서비스-도메인
    stream="<DOMAIN>S",             # 스트림 이름: 도메인 대문자 복수형
    batch=10,
    interval=1.0,
)
async def handle_command(msg: Msg) -> None: ...

# 시작
await nats_router.start(nc, js, redis)
```

**Core vs JetStream 선택 기준:**

| 상황 | 방식 |
|------|------|
| 실시간 센서·상태 스트림, 유실 허용 | Core subscribe |
| 커맨드·작업 요청, 재시도·중복 방지 필요 | JetStream Pull Consumer |
| 완료 이벤트를 다수 서비스가 수신 | JetStream Push Consumer |

- 핸들러는 **파일 하나(`handlers.py`)에만**, 라우터 정의는 별도 `router.py`에.

### 18.6 constants.py 작성 규칙

**상수 이름 패턴:**

```
NATS_SUBJECT_<DOMAIN>_<RESOURCE>_FORMAT     → subject에 자리 표시자 있음
NATS_SUBJECT_<DOMAIN>_<RESOURCE>            → 자리 표시자 없는 고정 subject
REDIS_<DOMAIN>_<QUALIFIER>_KEY_FORMAT       → Redis key에 자리 표시자 있음
WS_EVENT_<DOMAIN>_<ACTION>                  → WS 이벤트 이름 상수
```

**예시:**

```python
# NATS subject — <domain>.<tier>.<resource>.{id} 계층 구조
NATS_SUBJECT_DEVICE_DATA_METRIC_FORMAT   = "device.data.metric.{device_id}"
NATS_SUBJECT_DEVICE_DATA_METRIC          = "device.data.metric.>"      # 와일드카드
NATS_SUBJECT_JOB_COMMAND_START_FORMAT    = "job.command.start.{job_id}"

# Redis key — {ns}:<domain>:<qualifier>:{id}
REDIS_DEVICE_HASH_KEY_FORMAT  = "{ns}:device:{device_id}"
REDIS_USER_INFO_KEY_FORMAT    = "{ns}:users:{user_idx}:info"
REDIS_WS_TICKET_KEY_FORMAT    = "{ns}:ws:ticket:{ticket}"

# WS 이벤트 — v1/<domain>/<action>
WS_EVENT_DEVICE_STATE  = "v1/device/state"
WS_EVENT_JOB_NOTIFY    = "v1/job/notify"
```

**규칙 요약:**
- `*_FORMAT` suffix: `.format()` 자리 표시자 포함. 자리 표시자 없는 고정값은 suffix 생략.
- NATS subject 계층: `<도메인>.<tier>.<리소스>` — tier는 `data`(실시간), `command`(요청), `status`(완료 보고) 등으로 구분.
- `{ns}:` namespace: 같은 Redis 인스턴스를 여러 서비스가 공유할 때 키 충돌 방지. 회사명·팀·서비스 그룹 등 프로젝트 상황에 맞는 식별자를 하나 정해서 통일한다.

---

## 19. 인증·보안 패턴 (JWT RS256 + WS 티켓)

### 19.1 JWT 구조 (RS256)

```python
# 키 파일 분리: api/pem/private.pem, api/pem/public.pem
# api-initor 컨테이너가 최초 1회 생성 → named volume으로 api 컨테이너와 공유

class JwtAccessPayload(TypedDict):
    jtt: str        # "access"
    iss: str        # 발급자 (서비스명)
    sub: int        # user_idx
    aud: str        # 대상 (서비스명)
    iat / nbf / exp: datetime
    jti: str        # 고유 토큰 ID
    rjti: str       # 연결된 refresh jti (연쇄 무효화용)
    fresh: bool     # 로그인 직후 발급 여부

class JwtRefreshPayload(TypedDict):
    jtt: str        # "refresh"
    ...
    jti: str
    fjti: str       # 최초 jti (갱신 체인 식별자)
```

- `jtt` 필드로 access/refresh를 명시 구분 (standard `typ` claim 대신).
- `rjti` / `fjti`로 갱신 체인을 추적 → 리프레시 토큰 교체 시 이전 체인 무효화 가능.
- 만료 시간은 환경 변수로 `parse_duration("15m")` → `timedelta` 변환:
  ```python
  ACCESS_TOKEN_EXPIRE: str = "15m"   # API_ACCESS_TOKEN_EXPIRE
  REFRESH_TOKEN_EXPIRE: str = "7d"   # API_REFRESH_TOKEN_EXPIRE
  ```

### 19.2 Bearer 의존성 체인

```python
# security.py
BearerScheme = Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]

def required_access_token(request, payload: VerifiedPayload) -> JwtAccessPayload:
    if payload["jtt"] != "access":
        raise HTTPException(401, ...)
    request.state.jwt = UserInfoManager(payload)
    return payload

# dependencies.py
RequiredAccessPayload = Annotated[JwtAccessPayload, Depends(required_access_token)]
```

- `request.state.jwt`에 `UserInfoManager`를 심어두면 라우터 내 어디서든 `request.state.jwt.get_user()`로 접근.
- `UserInfoManager`: Redis 캐시 → DB fallback으로 사용자 정보 조회 (TTL 5분).

### 19.3 WebSocket 단발 티켓 패턴

```
1. 클라이언트 → GET /api/v1/auth/token/ws-ticket  (access token 필요)
2. 서버 → Redis SETEX {ns}:ws:ticket:{uuid} 60s payload
3. 클라이언트 → WS /api/v1/ws?ticket={uuid}
4. 서버 → Redis GET + DEL (단발: 재사용 불가)
5. 서버 주기적으로 v1/request/ticket 이벤트 전송
6. 클라이언트 → 새 티켓 발급 후 v1/ticket/renew 전송
```

- 티켓 TTL 짧게(1분), 단발 삭제로 **WS 연결 하이재킹 방어**.
- 티켓에 사용자 권한 포함 → WS 연결 후 별도 인증 불필요.

### 19.4 비밀번호

- bcrypt 직접 사용 (`passlib` 등 래퍼 금지 — 버전 의존성 충돌 위험).
- `utils/hash.py` 한 곳에서만 hash/verify.

### 19.5 로그인 엔드포인트 흐름

```
POST /api/v1/auth/login
  Body: { id: str, password: str }
```

```
1. DB에서 id로 사용자 조회
   → 없거나, bcrypt verify 실패, is_active=False 이면 동일한 401
     (사용자 존재 여부를 분리해서 노출하지 않는다)
2. refresh payload 생성  (fjti = 새 UUID4 ← 이 세션 체인의 식별자)
3. access payload 생성   (rjti = refresh.jti, fresh=False)
4. Redis에 세션 저장
     key: {ns}:users:{user_idx}:fjti:{fjti}
     value: {"current_jti": refresh.jti}
     TTL: REFRESH_TOKEN_EXPIRE
5. Redis에 user_info, user_settings 캐시 (TTL: USER_INFO_CACHE_EXPIRE)
6. must_change_password = (user_pwd.created_at == user_pwd.updated_at)
     ← 비밀번호가 한 번도 변경되지 않았으면 True
7. Response: { access_token, refresh_token, must_change_password }
```

- `fresh=True`는 로그인 직후가 아니라 **`POST /token/fresh`** 에서만 발급됨(§19.6).
- `must_change_password`는 클라이언트가 비밀번호 변경 페이지로 강제 이동할 때 사용(§19.8).

### 19.6 Fresh 토큰 발급 (민감 작업 전 재인증)

민감 작업(비밀번호 변경 등) 직전에 클라이언트가 아이디·비밀번호를 재입력해 `fresh=True` access token을 얻는다.

```
POST /api/v1/auth/token/fresh
  Header: Authorization: Bearer <refresh_token>
  Body: { id: str, password: str }

1. refresh token 검증 (jtt == "refresh")
2. Redis 세션 키 존재 확인 (없으면 세션 만료 → 401)
3. 아이디·비밀번호 재검증
4. fresh=True인 access token 발급 (refresh token은 교체 없음)
5. Response: { access_token }
```

- **fresh 토큰의 수명은 일반 access token과 동일** (짧아서 민감 작업 직후 바로 만료).
- 의존성 주입으로 강제하는 대신, 클라이언트가 민감 엔드포인트 호출 전에 이 흐름을 거치도록 API 명세로 규약한다.

### 19.7 토큰 갱신 (Refresh Rotation)

```
POST /api/v1/auth/token/refresh
  Header: Authorization: Bearer <refresh_token>
```

```
1. refresh token 서명 검증 (jtt == "refresh")
2. 응답 유실 대비 grace period 캐시 확인
     key: {ns}:users:{user_idx}:jwt:{old_jti}
     있으면 캐시된 토큰 쌍을 그대로 반환 (재시도 안전)
3. 새 refresh payload 생성 (jti=새 UUID, fjti=old.fjti 유지)
4. 새 access payload 생성  (fresh=False, rjti=new_refresh.jti)
5. Lua 스크립트로 세션 원자적 교체
     GET {ns}:users:{user_idx}:fjti:{fjti}
       → NOT_FOUND: 세션 만료 → 401
       → current_jti 불일치: 토큰 탈취 의심 → 세션 DEL + 401
       → 일치: SET {"current_jti": new_jti, "prev_jti": old_jti}
6. grace period 캐시 저장 (TTL: REFRESH_TOKEN_GRACE_PERIOD)
     key: {ns}:users:{user_idx}:jwt:{old_jti}
7. Response: { access_token, refresh_token }
```

- **Lua 원자성**: GET·비교·SET을 단일 트랜잭션으로 처리해 레이스 컨디션 방지.
- **JTI 불일치 감지**: 탈취된 토큰으로 먼저 갱신이 이루어졌다는 뜻 → 세션 즉시 삭제.
- **fjti**: 로그인부터 로그아웃까지 하나의 세션 체인을 묶는 식별자. Redis 키에 포함되어 세션 단위 강제 종료에 사용.

### 19.8 로그아웃

```
POST /api/v1/auth/logout
  Header: Authorization: Bearer <refresh_token>

1. refresh token 검증 → sub, fjti 추출
2. Redis 세션 키 DEL
     {ns}:users:{user_idx}:fjti:{fjti}
3. access token은 자연 만료 (짧은 수명으로 별도 처리 불필요)
4. Response: { message }
```

### 19.9 `must_change_password` (비밀번호 변경 강제)

- **판별**: `user_pwd.created_at == user_pwd.updated_at` → 비밀번호가 생성 후 한 번도 변경되지 않은 상태.
- **로그인 응답**에 `must_change_password` 포함 → 클라이언트가 변경 페이지로 강제 이동.

```
POST /api/v1/auth/password/initial   ← 최초 변경 전용
  - created_at == updated_at 검증 (이미 변경했으면 403)
  - 새 비밀번호로 updated_at 갱신 → 이후 이 엔드포인트 재호출 불가

POST /api/v1/auth/password/change    ← 일반 변경
  - 현재 비밀번호 확인 후 교체
```

### 19.10 CORS 설정

```python
# __init__.py — app 생성 직후
app.add_middleware(
    CORSMiddleware,
    allow_origins=env.CORS_ORIGINS,   # API_CORS_ORIGINS 환경변수 (콤마 구분 목록)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- `CORS_ORIGINS`는 **정확한 origin 목록**만 (`*` 와일드카드는 `allow_credentials=True`와 함께 쓸 수 없음).
- 프록시(Traefik 등)로 같은 오리진으로 묶이면 CORS 자체가 불필요 — 그쪽을 먼저 검토(§11).

---

## 20. UI 아키텍처 패턴 (React + Zustand + Axios)

### 20.1 폴더 골격

```
src/
  api/             # HTTP 클라이언트 래퍼 (도메인별 파일)
    http.ts        # axios 인스턴스 + 인터셉터
    auth.ts / <domain>.ts / ...
  components/
    features/      # 도메인 복합 컴포넌트 (<Domain>Panel, <Domain>View …)
    layout/        # 페이지 골격 (NavigationBar, Sidebar …)
    common/        # 재사용 원자 컴포넌트 (Button, Modal …)
  hooks/           # useXxx.ts — 관심사 하나당 파일 하나
  pages/           # 라우팅 단위 페이지 (<Name>Page/)
  stores/          # Zustand 스토어 (<name>Store.ts)
  types/           # index.ts 한 파일에 전체 타입 모음
  ws/              # WsClient 싱글톤
  constants/
  utils/
  theme/           # MUI 테마 설정
```

### 20.2 HTTP 클라이언트 패턴 (Axios)

```typescript
// api/http.ts
const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '' });

// Request: Authorization: Bearer <access>
http.interceptors.request.use((config) => {
  const token = getAccessToken();  // sessionStorage
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response: 401 → refresh → retry (큐로 동시 refresh 방지)
http.interceptors.response.use(undefined, async (error) => {
  if (error.response?.status !== 401) throw error;
  // POST /api/v1/auth/token/refresh → new tokens → retry
});
```

- **Access token → `sessionStorage`** (탭 닫으면 사라짐).
- **Refresh token → `localStorage`** (탭 간 공유, 장기 유지).
- 동시 다발 401 시 refresh 큐(promise) 하나만 실행, 나머지는 대기 후 일괄 재시도.

### 20.3 Zustand 스토어 패턴

```typescript
interface AuthState {
  user: UserInfo | null;
  isAuthenticated: boolean;
  setLogin(accessToken, refreshToken, user, mustChange): void;
  clearAuth(): void;
}
export const useAuthStore = create<AuthState>((set) => ({ ... }));
```

- 스토어 파일명: `<name>Store.ts`.
- 스토어 분리 기준: auth / `<domain>`(도메인 상태) / settings(사용자 설정).
- **외부에서 직접 읽기 (stale closure 방지)**: `useXxxStore.getState()` 사용 (React 훅 외부).

### 20.4 WebSocket 클라이언트 싱글톤

```typescript
// ws/wsClient.ts
class WsClient {
  on<T>(event: string, handler: (body: T) => void): () => void  // unsubscribe 반환
  send(event: string, body: unknown): void
  async connect(): Promise<void>
  startAutoConnect(): void   // 3초 재연결 루프
  disconnect(): void
}
export const wsClient = new WsClient();
```

**WS 메시지 포맷:**
```json
{ "header": { "version": "v1", "event": "v1/<domain>/<action>" }, "body": { ... } }
```

- 이벤트 이름: `v1/<domain>/<action>` (슬래시 구분, 버전 prefix).
- `wsClient.on()` 반환값(unsubscribe 함수)을 `useEffect` cleanup에서 반드시 호출.

### 20.5 기술 스택 (UI)

| 역할 | 라이브러리 |
|------|-----------|
| 상태관리 | Zustand 5 |
| HTTP | Axios 1.x |
| 라우팅 | React Router 7 |
| UI 컴포넌트 | MUI 7 (Material-UI) |
| CSS | Tailwind CSS 4 (유틸리티) + Emotion (CSS-in-JS) |
| 시각화 | Recharts |
| 알림 | Notistack |
| 빌드 | Vite 7 |
| 타입 | TypeScript 5.9 |

> 영상 스트리밍·지도·3D 렌더링 등 도메인 특화 라이브러리는 프로젝트마다 다르므로 별도 문서에 기재한다.

---

## 21. 구조화 로그 (structlog)

### 21.1 logger.py 설정 (Docker/stdout 환경)

stdlib logging을 structlog로 통합해 **모든 로그를 JSON 한 줄로** stdout에 출력한다.  
Docker/컨테이너 환경에서 로그 수집기(Loki, CloudWatch 등)가 stdout을 그대로 가져가는 구조에 최적화되어 있다.

```python
# <패키지>/logger.py
import logging
import sys
import structlog
from config import env  # LOG_LEVEL 환경변수

shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.CallsiteParameterAdder(
        {
            structlog.processors.CallsiteParameter.PATHNAME,
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.PROCESS_NAME,
            structlog.processors.CallsiteParameter.FUNC_NAME,
            structlog.processors.CallsiteParameter.LINENO,
        }
    ),
    structlog.stdlib.ExtraAdder(),
]

structlog.configure(
    processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=shared_processors,
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.JSONRenderer(),
    ],
)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

root_logger = logging.getLogger()
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)
root_logger.addHandler(handler)
root_logger.setLevel(logging.getLevelNamesMapping()[env.LOG_LEVEL.value])

# 서드파티 로거 억제 — 필요한 것만 남긴다
# 예: uvicorn access 로그는 미들웨어에서 직접 구조화 로그로 찍으므로 uvicorn 로거는 ERROR만
for name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
    lg = logging.getLogger(name)
    lg.setLevel(logging.ERROR)
    lg.handlers = []
    lg.propagate = True

logger = structlog.stdlib.get_logger()
```

**설계 포인트:**
- `shared_processors`: structlog 자체 로거 + stdlib `logging`으로 들어오는 외부 로그(uvicorn, sqlalchemy 등) 양쪽에 동일 처리기 적용.
- `foreign_pre_chain`: stdlib `logging` 경유 로그도 같은 JSON 포맷으로 통일.
- `cache_logger_on_first_use=True`: 로거 인스턴스 재사용으로 퍼포먼스 확보.
- `CallsiteParameterAdder`: `pathname`, `filename`, `func_name`, `lineno` 자동 포함 — 로그만 보고 위치 추적 가능.

**env.py에 추가할 설정:**

```python
class LogLevel(StrEnum):
    CRITICAL = "CRITICAL"
    FATAL    = "FATAL"
    ERROR    = "ERROR"
    WARNING  = "WARNING"
    WARN     = "WARN"
    INFO     = "INFO"
    DEBUG    = "DEBUG"
    NOTSET   = "NOTSET"

class Settings(BaseSettings):
    LOG_LEVEL: LogLevel = LogLevel.INFO   # API_LOG_LEVEL
```

### 21.2 사용 방법

```python
# 각 모듈 최상단
from <패키지>.logger import logger

# 사용
logger.info("job_session_started", job_id=1, entity_id="abc")
logger.warning("external_task_timeout", job_id=1, timeout_sec=20.0)
logger.error("storage_write_failed", job_id=1, exc_info=e)
```

- **이벤트 이름**: `snake_case` 영어, `동사_목적어` 형태.
- **컨텍스트**: key=value 키워드 인자로 (위치 인자 사용 금지).
- **예외**: `exc_info=e` 추가 (스택트레이스 포함).
- PII(이름·이메일·비밀번호)는 로그에 넣지 않는다.
- 출력 필드: `event`, `level`, `timestamp`, `pathname`, `lineno` + 커스텀 키.

---

## 22. 린트·포맷 구체 설정

### 22.1 Python (Ruff)

```toml
# pyproject.toml
[tool.ruff]
target-version = "py314"
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "N", "SIM"]
# E/W: pycodestyle, F: pyflakes, I: isort, B: bugbear
# C4: comprehensions, UP: pyupgrade, N: pep8-naming, SIM: simplify

[tool.ruff.lint.isort]
combine-as-imports = true

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

- `ruff check --fix` + `ruff format` 두 단계로 끝냄 (Black·isort 별도 불필요).
- 줄 길이 88자 (Black 기본값과 동일).

### 22.2 TypeScript (ESLint v9 flat config)

```javascript
// eslint.config.js
export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  reactRefresh.configs.vite,
  { files: ["**/*.{ts,tsx}"], ... }
]
```

- ESLint v9 flat config(`eslint.config.js`) — 구형 `.eslintrc.*` 사용 금지.
- TypeScript strict mode (`"strict": true` in tsconfig).

### 22.3 파일·식별자 명명

| 대상 | 규칙 | 예시 |
|------|------|------|
| Python 상수 | `UPPER_SNAKE_CASE` | `NATS_SUBJECT_LIDAR` |
| Python 클래스 | `PascalCase` | `RecordsRepository` |
| Python 함수·변수 | `snake_case` | `get_by_idx` |
| Python private | `_leading` | `_parse_ts_ns` |
| TS 컴포넌트 파일 | `PascalCase.tsx` | `ControlPanel.tsx` |
| TS 훅 파일 | `camelCase.ts` | `useLiveKit.ts` |
| TS 스토어 파일 | `camelCaseStore.ts` | `robotStore.ts` |
| TS 타입 | `PascalCase` | `AuthState`, `RobotState` |
| WS/NATS 이벤트 키 | `snake_case` 영어 | `robot_state_updated` |

---

## 23. 파이프라인 비동기 패턴

### 23.1 이벤트 루프 ↔ 워커 스레드 분리

CPU 블로킹 작업(Parquet 쓰기, JPEG 인코딩 등)은 이벤트 루프에서 직접 호출하지 않는다:

```python
# ❌ 이벤트 루프 점유
def on_lidar(data):
    storage.write_parquet(data)  # blocking I/O

# ✅ asyncio.to_thread
async def on_stop():
    await asyncio.to_thread(session.flush_all)

# ✅ producer-consumer (queue.Queue)
class _SensorWorker:
    def __init__(self, storage):
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def put_lidar(self, ts, points, source, recv_ns):
        self._q.put_nowait(("lidar", ts, points, source, recv_ns))

    def _run(self):
        while True:
            item = self._q.get(timeout=1.0)
            ...  # 스레드에서 blocking I/O
```

- **이벤트 루프**: `put_nowait()` 호출만 (즉시 반환).
- **워커 스레드**: 큐 드레인 + 플러시 주기 관리.
- 종료 시 sentinel `("_stop", done_event, result)` 방식으로 깨끗하게 드레인.

### 23.2 asyncio Task 수명 관리

```python
# 태스크 참조를 보관하지 않으면 GC에 의해 조기 종료될 수 있음
encode_tasks: set[asyncio.Task] = set()
task = asyncio.create_task(...)
encode_tasks.add(task)
task.add_done_callback(encode_tasks.discard)

# 정리 시
await asyncio.gather(*encode_tasks, return_exceptions=True)
```

- **장기 태스크**: `session.livekit_task` 등 필드에 저장 → `on_stop()`에서 `await`.
- **단기 태스크**: 집합(`set`)으로 추적, `add_done_callback(set.discard)` 패턴.
- 타임아웃이 있는 대기: `asyncio.wait_for(asyncio.shield(task), timeout=N)` — `shield`로 원본 태스크 취소 방지.

### 23.3 타임스탬프 단위 변환 규칙

로봇은 `time.monotonic()` 초(float) 단위로 전송:
```python
def _parse_ts_ns(raw) -> int:
    v = float(raw or 0)
    if v < 1e12:          # 초 단위 (≤ ~31년 uptime)
        return int(v * 1_000_000_000)
    return int(v)         # 이미 ns (≥ 11.5일 ns)
```

- **저장 단위**: 내부 모든 타임스탬프는 **ns int64**.
- **판단 기준**: `1e12` (초 단위 최대 ~31년 << 1e12).
- 카메라 프레임: `timestamp_us * 1000` → ns (데이터 채널 경유 시).

---

## 24. 웹 백엔드 보안 체크리스트

프레임워크로 백엔드를 작성·리뷰할 때 확인하는 항목. 예시는 FastAPI/Starlette/SQLAlchemy 기준이지만
원리는 프레임워크 무관.

**전제: 파이썬과 FastAPI는 아래 어느 것도 기본으로 막아주지 않는다.**
Starlette은 바디 크기 제한이 없고, `re`는 타임아웃이 없고, uvicorn은 slowloris 방어가 약하다.
전부 명시적으로 설정해야 한다.

전문은 두 파일로 나뉘어 있다. 이 절은 요약이다.

- **코드 레벨** — `references/web-security.md`
  (§1 권한, §2 인증, §3 인젝션, §4 업로드, §5 HTTP, §6 DoS, §7 동시성, §8 클라이언트, 부록 A 체크리스트)
- **설정·인프라·운영** — `references/security-ops.md`
  (§9 보안 헤더, §10 개인정보, §11 리소스 탈취·공급망, §12 랜섬웨어·백업, §13 설정·운영)

### 24.1 핵심 원칙 4가지

판단이 애매하면 여기로 되돌아온다.

1. **입력을 타입으로 못박는다** — Pydantic strict 스키마 + `extra="forbid"`.
   NoSQL 인젝션, mass assignment, 상당수 인젝션이 여기서 걸린다.
2. **데이터와 코드를 절대 섞지 않는다** — 파라미터 바인딩, `shell=False`, 템플릿 분리, `safe_load`.
   인젝션 전체의 근본 원인.
3. **모든 접근에 소유권/권한 조건을 건다** — 그리고 의존성·미들웨어로 강제해서
   개별 핸들러에서 빼먹을 수 없게 만든다.
4. **불변 조건을 DB에 박는다** — UNIQUE, CHECK, 원자적 UPDATE.
   앱 로직 검사는 동시성 상황에서 무너진다.

### 24.2 작업 우선순위

실제 사고 비중 순서. 시간이 없으면 위에서부터.

1. 권한 검사 누락 (IDOR/BOLA)
2. 인증 견고화 — 특히 **계정 복구 경로**. 비밀번호를 강하게 해도 재설정이 뚫리면 끝난다
3. 인젝션 계열
4. 가용성 (커넥션 풀, 타임아웃, 크기 제한)
5. 보안 헤더, 그 외

> SQL 인젝션은 ORM 사용 시 대부분 사라진다. OWASP API Top 10 **2019판**에서 인젝션은 이미
> 8위(API8:2019)였고 **2023판에서는 독립 항목에서 빠졌다.** 권한은 2023판에서 API1·API3·API5
> 세 자리를 차지한다. **권한 검사부터 본다.**

### 24.3 자주 틀리는 것 (요약)

| 오해 | 실제 |
|---|---|
| FastAPI가 바디 크기를 제한해 준다 | 제한 없음. 순수 ASGI 미들웨어를 직접 작성 (`BaseHTTPMiddleware` 아님) |
| ORM을 쓰면 SQLi가 불가능하다 | `text()` + f-string, ORDER BY 식별자는 그대로 취약 |
| 로그인 확인 = 권한 확인 | 별개. 소유권 조건을 **쿼리에** 넣어야 한다 |
| Pydantic이 ReDoS를 막아준다 | v2 기본 엔진(rust-regex)만 안전. `re`는 여전히 취약 |
| React를 쓰면 XSS가 없다 | `dangerouslySetInnerHTML`, `href` 스킴, 마크다운은 그대로 |
| CORS가 WebSocket도 보호한다 | 적용되지 않음. Origin을 직접 검증해야 한다 |
| `pickle`은 그냥 직렬화 포맷이다 | 역직렬화 = 임의 코드 실행 |
| 백업이 있으니 랜섬웨어는 괜찮다 | 백업이 먼저 삭제된다. 불변 백업 + 복원 테스트 |
| 방화벽을 설정했다 | 대개 인바운드만. **아웃바운드 차단**이 실질 방어 |

### 24.4 FastAPI 기본 뼈대

새 프로젝트에는 §8 스캐폴딩과 함께 이 블록을 넣는다.

```python
app = FastAPI(
    docs_url=None if PROD else "/docs",     # 프로덕션 문서 차단
    redoc_url=None if PROD else "/redoc",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example.com"])
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(CORSMiddleware,
                   allow_origins=["https://app.example.com"],   # 환경 변수로 (§19.10)
                   allow_credentials=True,
                   allow_methods=["GET", "POST"])
app.add_middleware(MaxBodySizeMiddleware, max_size=10 * 1024 * 1024)

@app.exception_handler(Exception)
async def handler(request, exc):
    logger.exception("unhandled")                                  # 내부에는 남기고
    return JSONResponse({"detail": "Internal Server Error"}, 500)  # 외부에는 주지 않는다
```

### 24.5 계층별 책임

**보안은 단일 방어선이 아니라 계층**이다. 그리고 이 절의 상당수는 코드가 아니라 설정·운영이다.
코드 보안은 리뷰에서 잡히지만 백업 복원 테스트나 아웃바운드 정책은 아무도 시키지 않으면
영원히 하지 않게 된다. 캘린더에 넣는 것이 실질적으로 가장 효과가 크다.

| 계층 | 담당 |
|---|---|
| CDN/WAF | 볼륨 공격, 봇 |
| nginx | 바디 크기, slowloris, IP당 레이트리밋, Host 검증 |
| uvicorn | `--limit-concurrency`, keep-alive 타임아웃, proxy-headers 제한 |
| 앱 | 권한 검사, 스키마 검증, 인젝션 방어, 이벤트루프 보호 |
| DB | UNIQUE/CHECK 제약, RLS, 최소 권한 계정 |
| 인프라 | 컨테이너 하드닝, 아웃바운드 차단, 불변 백업 |

---

## 25. 인프라·고가용성·장애 복구

언어와 무관하게 적용한다. 운영 요구를 먼저 정하고 기술을 고른다.

### 25.1 가용성 목표

허용 중단, RPO/RTO, 장애 영역, 운영 담당자와 복원 실측을 기록한다.
복제본 수만으로 고가용성을 주장하지 않는다.

### 25.2 Redis / Valkey

라이선스는 제품·버전별로 확인한다. Valkey 선택은 기능·클라이언트·운영 도구와
마이그레이션 호환성 검증을 포함한다. 근거·버전·대안은 ADR에 남긴다.

### 25.3 Sentinel

장애 판정 quorum과 승격 승인 과반수를 구분한다. 보통 독립 노드에 3개 이상
홀수로 배치하며 짝수 자체가 금지는 아니다. Sentinel 하나·과반수·primary 장애와
클라이언트 재연결을 함께 검증한다. 비동기 복제의 쓰기 유실 가능성을 명시한다.

### 25.4 네트워크 장애

FIN/RST 없는 장애는 Java에 한정되지 않는다. connect/read/pool timeout과 전체
요청 deadline, keepalive를 구분한다. 쓰기 응답 유실은 멱등성·조회로 처리한다.

### 25.5 DB 복구

primary/replica 도입 목적을 구분하고 lag·승격·fencing·재연결을 설계한다.
복제는 백업을 대체하지 않는다. 격리 환경에서 PITR·업무 불변식·RPO/RTO를 검증한다.

### 25.6 k3s / Kubernetes / Helm

운영 여력과 다중 노드 요구에 따라 도입한다. etcd quorum, probe 역할, topology,
스토리지, drain, snapshot 복원을 검증한다. Helm은 lint/render/API 검증과 staging
upgrade/rollback을 거친다. chart rollback과 DB migration 복구를 별도로 다룬다.

세부 구현은 `references/infrastructure-ha.md`, `references/network-failure.md`,
`references/database-recovery.md`, `references/kubernetes-helm.md`.

---

## 26. 문서 정합성·테스트 품질·병렬 작업

### 26.1 문서 체계

각 주제의 `00-index.md`에서 읽기 순서를 안내한다. vision·scope·architecture·ADR·
development·operations를 구분하고 요구사항·결정·작업에는 경로와 독립인 ID를 둔다.

### 26.2 정합성

요구사항 → 설계 → 구현 → 수용 테스트 → 운영 문서를 연결한다. 경로·ID·계약 검사는
자동화하고 의미상 모순은 검토한다. AI의 판정만으로 정합성이 보장되지는 않는다.

### 26.3 테스트 품질

구현 계산식을 복제하지 말고 외부 관찰 결과·실패·경계·불변식을 검증한다.
핵심 로직에는 mutation testing을 적용해 살아남은 변이를 분석한다. 동등 변이를
구분하고 무조건 점수 100%를 요구하지 않는다.

### 26.4 병렬 작업

작업별 소유 파일, 의존성, 계약, 실패 예시, 수용 테스트, 검증 명령, 완료 증거를
정한다. 사람과 에이전트에 동일한 작업서를 사용하고 실제 구성요소의 통합을 검증한다.

세부 절차는 `references/documentation-testing.md`.

---

## 27. 규모와 디자인 패턴

문제 → 선택 이유 → 최소 예제 → 도입 조건 → 비용·실패 → 검증 순서로 설명한다.
Adapter·Registry·Bulkhead·Circuit breaker·Outbox·Cache-aside는 필요한 변화·실패가
있을 때 적용한다. 사용자 수만으로 마이크로서비스나 Kubernetes를 도입하지 않는다.
코드 그래프는 커밋·분석 시점과 동적 호출 한계를 명시하고 테스트를 대체하지 않는다.

실제 예시와 단계별 기준은 `references/patterns-scale.md`.

---

## 17. 추가 메모 (다른 프로젝트에서 옮겨 적기)

아래에 **날짜 · 프로젝트(코드명 가능) · 한 줄 요약**으로 계속 추가한다.

```
<!-- 예시
- 2026-04-21 · (프로젝트명) · 배치 잡은 ProcessPool로만 돌리고 API는 큐에 ID만 넣음
-->
```

- 2026-04-20 · rnd-dashboard · 비밀번호에 특수문자 포함되면서 DB/Redis URL 파싱 오류 → `quote_plus` 적용 (§15)
- 2026-04-22 · rc-server · §18~§23 추가: FastAPI Repository 패턴, JWT RS256 + WS 티켓, React/Zustand/Axios 패턴, structlog 규칙, Ruff 설정, 파이프라인 asyncio 패턴. §5 패키지 명명 규칙 실제 코드 기준으로 수정(`rc_api`처럼 프로젝트 코드명 사용).
- 2026-09-05 · (공통) · §24 웹 백엔드 보안 체크리스트 추가. 코드 레벨은 `references/web-security.md`, 설정·운영은 `references/security-ops.md`. 리뷰 시 보안 발견을 스타일보다 먼저 보고한다.

- 2026-11-05 · joongi-skills · §25 인프라·HA·장애 복구, §26 문서 정합성·mutation testing·병렬 작업, §27 규모·패턴 사례 추가. 언어 공통 원칙과 스택별 예시를 구분한다.

---

*이 파일은 저장소 어디에 두어도 된다. 다른 레포로 옮길 때는 이 한 파일만 복사해도 된다.*
