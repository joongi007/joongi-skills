# 인증과 JWT (PLAYBOOK §19)

## 목차

- JWT 구조 — RS256 (§19.1)
- Bearer 의존성 체인 (§19.2)
- WebSocket 단발 티켓 (§19.3)
- 비밀번호 (§19.4)
- 로그인 흐름 (§19.5)
- Fresh 토큰 (민감 작업 전 재인증) — §19.6
- 토큰 갱신 — Refresh Rotation (§19.7)
- 로그아웃 (§19.8)
- must_change_password (§19.9)
- CORS (§19.10)
- 프론트엔드 토큰 저장 (관련 §20.2)

## JWT 구조 — RS256 (§19.1)

```python
# 키 파일 분리: api/pem/private.pem, api/pem/public.pem
# api-initor 컨테이너가 최초 1회 생성 → named volume으로 api 컨테이너와 공유

class JwtAccessPayload(TypedDict):
    jtt: str        # "access"   ← standard `typ` 대신 `jtt` 사용
    iss: str
    sub: int        # user_idx
    aud: str
    iat: datetime
    nbf: datetime
    exp: datetime
    jti: str        # 고유 토큰 ID
    rjti: str       # 연결된 refresh jti (연쇄 무효화)
    fresh: bool     # 로그인 직후 발급 여부

class JwtRefreshPayload(TypedDict):
    jtt: str        # "refresh"
    ...
    jti: str
    fjti: str       # 최초 jti (갱신 체인 식별자)
```

**핵심 포인트:**
- `jtt`로 access/refresh를 명시 구분 (standard `typ` claim 대신).
- `rjti` / `fjti`로 갱신 체인 추적 → 리프레시 토큰 교체 시 이전 체인 무효화.
- 만료 시간은 환경 변수로 `parse_duration("15m")` → `timedelta`:
  ```python
  ACCESS_TOKEN_EXPIRE: str = "15m"   # API_ACCESS_TOKEN_EXPIRE
  REFRESH_TOKEN_EXPIRE: str = "7d"   # API_REFRESH_TOKEN_EXPIRE
  ```

## Bearer 의존성 체인 (§19.2)

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

- `request.state.jwt`에 `UserInfoManager`를 심어두면 라우터 내 어디서든 `request.state.jwt.get_user()`.
- `UserInfoManager`: Redis 캐시 → DB fallback (TTL 5분).

## WebSocket 단발 티켓 (§19.3)

```
1. 클라이언트 → GET /api/v1/auth/token/ws-ticket  (access token 필요)
2. 서버 → Redis SETEX {ns}:ws:ticket:{uuid} 60s payload
3. 클라이언트 → WS /api/v1/ws?ticket={uuid}
4. 서버 → Redis GET + DEL (단발: 재사용 불가)
5. 서버 주기적으로 v1/request/ticket 이벤트 전송
6. 클라이언트 → 새 티켓 발급 후 v1/ticket/renew 전송
```

- 티켓 TTL 짧게(1분), 단발 삭제 → **WS 연결 하이재킹 방어**.
- 티켓에 사용자 권한 포함 → WS 연결 후 별도 인증 불필요.

## 비밀번호 (§19.4)

- **bcrypt 직접 사용**. `passlib` 등 래퍼 금지 (버전 의존성 충돌 위험).
- `utils/hash.py` 한 곳에서만 hash/verify.

## 로그인 흐름 (§19.5)

```
POST /api/v1/auth/login
  Body: { id: str, password: str }

1. DB에서 id로 사용자 조회
   → 없거나, bcrypt verify 실패, is_active=False 이면 모두 동일한 401
     (사용자 존재 여부를 분리해서 노출하지 않는다)
2. refresh payload 생성 (fjti = 새 UUID4 ← 이 세션 체인의 식별자)
3. access payload 생성  (rjti = refresh.jti, fresh=False)
4. Redis 세션 저장
     key: {ns}:users:{user_idx}:fjti:{fjti}
     value: {"current_jti": refresh.jti}
     TTL: REFRESH_TOKEN_EXPIRE
5. Redis user_info, user_settings 캐시 (TTL: USER_INFO_CACHE_EXPIRE)
6. must_change_password = (user_pwd.created_at == user_pwd.updated_at)
7. Response: { access_token, refresh_token, must_change_password }
```

- **`fresh=True`는 로그인 직후가 아니라 `POST /token/fresh`** 에서만 발급 (§19.6).

## Fresh 토큰 (민감 작업 전 재인증) — §19.6

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

- fresh 토큰의 수명은 일반 access token과 동일 (짧아서 민감 작업 직후 만료).
- 의존성 주입으로 강제하지 않고 **API 명세로 규약** — 클라이언트가 민감 엔드포인트 호출 전에 거치게.

## 토큰 갱신 — Refresh Rotation (§19.7)

```
POST /api/v1/auth/token/refresh
  Header: Authorization: Bearer <refresh_token>

1. refresh token 서명 검증 (jtt == "refresh")
2. 응답 유실 대비 grace period 캐시 확인
     key: {ns}:users:{user_idx}:jwt:{old_jti}
     있으면 캐시된 토큰 쌍 그대로 반환 (재시도 안전)
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

**핵심 포인트:**
- **Lua 원자성**: GET·비교·SET을 단일 트랜잭션 → 레이스 컨디션 방지.
- **JTI 불일치 감지**: 탈취된 토큰으로 먼저 갱신됐다는 뜻 → 세션 즉시 삭제.
- **fjti**: 로그인부터 로그아웃까지 한 세션 체인을 묶는 식별자. Redis 키에 포함되어 세션 단위 강제 종료에 사용.

## 로그아웃 (§19.8)

```
POST /api/v1/auth/logout
  Header: Authorization: Bearer <refresh_token>

1. refresh token 검증 → sub, fjti 추출
2. Redis 세션 키 DEL
     {ns}:users:{user_idx}:fjti:{fjti}
3. access token은 자연 만료 (짧은 수명)
4. Response: { message }
```

## must_change_password (§19.9)

- **판별**: `user_pwd.created_at == user_pwd.updated_at` → 한 번도 변경되지 않음.
- 로그인 응답에 포함 → 클라이언트가 변경 페이지로 강제 이동.

```
POST /api/v1/auth/password/initial   ← 최초 변경 전용
  - created_at == updated_at 검증 (이미 변경했으면 403)
  - 새 비밀번호로 updated_at 갱신 → 이후 이 엔드포인트 재호출 불가

POST /api/v1/auth/password/change    ← 일반 변경
  - 현재 비밀번호 확인 후 교체
```

## CORS (§19.10)

```python
# __init__.py — app 생성 직후
app.add_middleware(
    CORSMiddleware,
    allow_origins=env.CORS_ORIGINS,   # API_CORS_ORIGINS (콤마 구분 목록)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- `CORS_ORIGINS`는 **정확한 origin 목록**만. **`*` 와일드카드는 `allow_credentials=True`와 함께 못 씀**.
- 프록시(Traefik 등)로 같은 오리진으로 묶이면 CORS 자체 불필요 — 그쪽 먼저 검토 (§11).

## 프론트엔드 토큰 저장 (관련 §20.2)

- **Access token → `sessionStorage`** (탭 닫으면 사라짐).
- **Refresh token → `localStorage`** (탭 간 공유, 장기 유지).
- 동시 다발 401 시 refresh 큐(promise) 하나만 실행, 나머지는 대기 후 일괄 재시도.

자세한 인터셉터 코드는 `frontend.md` 참고.
