# 커밋·PR 전 체크리스트 (PLAYBOOK §13)

작업을 마치기 전에 한 번 훑는다. 항목 옆에 §번호는 PLAYBOOK.md의 해당 섹션.

## 목차

- 일반
- 보안 (§24)
- DB / 워커
- 모듈 경계
- API (Python)
- 인증 (`auth-jwt.md`)
- UI (`frontend.md`)
- 비동기 / 파이프라인 (`async-patterns.md`)
- 로그 (`logging.md`)
- 비밀 / 설정 (`config-secrets.md`)
- Docker (`docker.md`)
- 린트 / 명명 (`lint-naming.md`)
- 인프라·복구 (§25)
- 문서·검증 (§26–§27)

## 일반

- [ ] 이 작업은 **I/O 바운드**인가 **CPU 바운드**인가 — `concurrency.md` §2와 맞는가.
- [ ] 실패 시 **사용자/운영자**에게 무엇이 보이는가 (에러 메시지, 로그 이벤트).
- [ ] 설정이 **환경 변수로 노출**되는가, 기본값이 안전한가.
- [ ] 한 저장소 안에서 **의존성 경계**(공유 vs 앱 전용)가 깨지지 않았는가.

## 보안 (§24)

전체는 `web-security.md` 부록 A. 아래는 **어떤 변경이든** 걸리면 멈추고 확인하는 것들.

- [ ] 리소스 조회/수정에 **소유권 조건이 쿼리 안에** 있는가 (`if`로 사후 검사하지 않았는가) — `web-security.md` §1.1.
- [ ] 모든 엔드포인트에 `response_model`이 있고, 입력 스키마에 `extra="forbid"`가 있는가 (§1.3).
- [ ] `Any` / `Dict[str, Any]`로 받는 입력이 없는가 (§3.2).
- [ ] `text()` + f-string, `shell=True`, `Template(user_input)`, `pickle.loads`, `yaml.load`가 없는가 (§3).
- [ ] ORDER BY·컬럼명이 화이트리스트로 처리되는가 (§3.1).
- [ ] `async def` 안에 블로킹/CPU 작업이 없는가 (§6.2). 외부 호출에 전부 타임아웃이 있는가 (§6.4).
- [ ] 목록 API에 `Query(50, le=200)` 형태의 상한이 있는가 (§6.5).
- [ ] 잔액·재고·쿠폰이 **원자적 UPDATE 또는 락**으로 처리되는가 (§7.1). 결제에 멱등성 키가 있는가 (§7.2).
- [ ] 업로드가 있으면: 바디 크기 제한, 매직바이트 검증, 파일명 재생성, 웹 루트 밖 저장 (§4).
- [ ] 서버가 사용자 URL을 fetch하면 사설 IP·메타데이터(`169.254.169.254`) 차단 (§5.4).
- [ ] 프로덕션 `/docs`·`debug` 차단, `TrustedHostMiddleware`, 보안 헤더 미들웨어 (`security-ops.md` §9, §13).

## DB / 워커

- [ ] DB에 워커 등이 직접 붙는 경우, **`shared` ORM 예외는 구두 승인 + 기록**이 있는가 (기본은 §7.1, `architecture.md`).
- [ ] 부하가 늘었을 때 **replica·워커 수를 늘릴 수 있는가** (§2.6). 수신과 처리가 붙어 있지 않다면 **버퍼·큐 경계**가 명확한가 (§2.7).

## 모듈 경계

- [ ] UI는 **훅·상태·feature 경계** (§9.1, `frontend.md`), API는 **도메인·router/service/schema** (§9.2, `python-api.md`)가 지켜졌는가.
- [ ] UI–API 연결은 **§11.3** 순서로 검증했는가 (단일 진입점·상대 `/api` 우선, 불필요한 Vite 프록시 남발 없음).

## API (Python)

- [ ] **Repository `inject` vs `inject_autocommit`** 선택이 맞는가 (§18.3, `python-api.md`).
- [ ] `dependencies.py`에 Annotated 앨리어스 있는가.
- [ ] 라우터: HTTP·검증·`Depends` 조립만, 비즈니스 로직 없음.
- [ ] 서비스: HTTP/Request 의존성 없음, 다른 도메인의 테이블 직접 만지지 않음.

## 인증 (`auth-jwt.md`)

- [ ] JWT: **RS256 키 파일 분리**, `jtt`/`rjti`/`fjti` claims 포함, 만료 **환경 변수**로 설정 (§19.1).
- [ ] 로그인: 성공/실패 모두 **동일한 401 메시지**, `is_active` 확인, 세션을 `fjti` 키로 Redis 저장 (§19.5).
- [ ] Refresh: **Lua 원자적 교체** + `current_jti` 불일치 시 세션 DEL. grace period 캐시로 재시도 안전 (§19.7).
- [ ] 로그아웃: 세션 키 (`{ns}:users:{idx}:fjti:{fjti}`) **DEL** (§19.8).
- [ ] 민감 엔드포인트 (비밀번호 변경 등): `POST /token/fresh`로 재인증 후 `fresh=True` access token 획득 흐름 명세 (§19.6).
- [ ] **CORS origins 환경 변수화**, 와일드카드 `*` 미사용 (§19.10).
- [ ] WS: 단발 티켓 패턴 사용 (§19.3). 이벤트 이름 `v1/<domain>/<action>` 형식 (§20.4).

## UI (`frontend.md`)

- [ ] **Access token → sessionStorage**, **refresh token → localStorage** (§20.2).
- [ ] 동시 401 방어 큐 있는가 (refresh 동시 발사 방지).
- [ ] `wsClient.on()` 반환 unsubscribe를 `useEffect` cleanup에서 호출.
- [ ] 스토어 파일명: `<name>Store.ts`.

## 비동기 / 파이프라인 (`async-patterns.md`)

- [ ] **blocking I/O는 이벤트 루프 밖으로** (`asyncio.to_thread` / `queue.Queue` 워커) (§23.1).
- [ ] Task 참조 집합으로 추적 (§23.2).
- [ ] 타임아웃 있는 대기는 `asyncio.shield`로 감싸서 원본 태스크 보호.

## 로그 (`logging.md`)

- [ ] `snake_case` 이벤트 이름, **`동사_목적어`** 형태.
- [ ] `exc_info=e` 추가 (예외 시).
- [ ] **PII 없음** (이름·이메일·비밀번호·전화·주민번호).
- [ ] f-string 메시지 대신 kwargs로 컨텍스트 전달.

## 비밀 / 설정 (`config-secrets.md`)

- [ ] DB/Redis URL 조립 시 비밀번호에 `quote_plus` 적용 (§15).
- [ ] `.env`는 gitignore, `.env.example`만 커밋.
- [ ] 빌드 타임 env (`VITE_*`)에 시크릿 없음.

## Docker (`docker.md`)

- [ ] `env_file: .env` 한 줄, `environment:` 블록에 하드코딩 없음 (§14.1).
- [ ] 로컬 빌드 이미지에 `pull_policy: never` (§16.2).
- [ ] 인프라 이미지는 메이저 버전 + alpine/slim 태그 고정 (§16.3).
- [ ] `name:` 명시 (멀티 컴포즈 충돌 방지, §16.4).

## 린트 / 명명 (`lint-naming.md`)

- [ ] Python: `ruff check --fix` + `ruff format` 통과.
- [ ] TS: `eslint` 통과, `tsc --noEmit` 에러 없음.
- [ ] 파일명·식별자 명명 규칙 (§22.3) 따름.
- [ ] `__init__.py` re-export는 `# ruff: noqa: F401` 패턴 (§5).


## 인프라·복구 (§25)

- [ ] 선택한 버전의 라이선스와 마이그레이션·롤백 조건을 기록했는가.
- [ ] quorum·과반수·독립 장애 영역과 클라이언트 전환까지 검증했는가.
- [ ] 연결·읽기·풀·전체 요청 시간 예산과 쓰기 재시도 안전성이 있는가.
- [ ] 백업 복원 실측 RPO/RTO와 replica lag·디스크 경보가 있는가.
- [ ] Kubernetes 배치·스토리지·probe·upgrade/rollback이 실제 환경에서 확인됐는가.

## 문서·검증 (§26–§27)

- [ ] 요구사항·결정·계약·수용 테스트·운영 문서가 같은 동작을 설명하는가.
- [ ] 테스트가 구현을 복사하지 않고 실패·경계·불변식을 검증하는가.
- [ ] 핵심 로직의 살아남은 mutation을 분석했는가. 미실행이면 그렇게 밝혔는가.
- [ ] 병렬 작업의 소유 파일과 계약이 겹치지 않고 실제 통합을 검증했는가.
- [ ] 채택한 패턴과 인프라가 측정한 규모·운영 요구를 해결하는가.
