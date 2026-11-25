# 인증과 JWT (PLAYBOOK §19)

기존 Python/JWT 계약을 구현·유지할 때 쓰는 예시다. 세션·OIDC·관리형 인증에 자체 JWT 구현을 강제하지 않는다.
`jtt`·`rjti`·`fjti`·`fresh`·`reauth_at`는 이 예시의 사용자 정의 claim이며 표준 필수 필드가 아니다.
Keycloak·OIDC·BFF·OpenFGA 선택과 책임은 [공통 인증·권한](identity-authorization.md),
로그인 화면의 브랜드 통일은 [인증 UI](identity-ui.md)를 먼저 본다.
일반 JWT/JWKS 검증은 [서명 키·JWKS](jwt-jwks.md), BFF·TMB의 차이는 [브라우저 backend](browser-backends.md)를 본다.

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
    jtt: str        # "access" — 이 계약의 사용자 정의 payload claim
    iss: str
    sub: str        # JWT subject는 문자열; 내부 숫자 ID와는 명시적으로 매핑
    aud: str
    iat: datetime
    nbf: datetime
    exp: datetime
    jti: str        # 고유 토큰 ID
    rjti: str       # 연결된 refresh jti (연쇄 무효화)
    fresh: bool     # 이 계약에서 민감 작업 재인증을 완료했는지
    reauth_at: datetime | None  # 서버가 확인한 재인증 시각; 없으면 None

class JwtRefreshPayload(TypedDict):
    jtt: str        # "refresh"
    ...
    jti: str
    fjti: str       # 최초 jti (갱신 체인 식별자)
```

**핵심 포인트:**
- `jtt`로 access/refresh를 명시 구분한다. JOSE header의 표준 `typ`과 별개인 사용자 정의 claim이다.
- datetime 표기는 애플리케이션 내부 타입 예시다. wire의 `iat`·`nbf`·`exp` 등 표준 시간 claim은 NumericDate로 직렬화·검증한다.
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
4. 서버 → Redis/Valkey GETDEL 또는 Lua로 검증·소비를 원자적으로 수행
5. 서버 주기적으로 v1/request/ticket 이벤트 전송
6. 클라이언트 → 새 티켓 발급 후 v1/ticket/renew 전송
```

- 짧은 TTL과 원자적 소비로 재사용을 제한한다. 별도 GET 다음 DEL은 동시 연결 두 개가 같은
  티켓을 읽을 수 있으므로 단발 보장이 아니다. 지원 버전·자료형을 확인하고 GETDEL/Lua 경로를 검사한다.
- 티켓은 검증된 주체·세션·대상에 연결하고 handshake의 Origin 허용 목록을 검증한다. WSS를 사용한다.
  query의 티켓도 bearer credential이므로 proxy·access log·trace에서 제거한다. 신규 발급 API는 POST와
  `Cache-Control: no-store`를 우선하며 기존 GET 계약을 유지할 때도 캐시·재발급·노출 위험을 검토한다.
- 연결 인증은 메시지별 객체·행위·tenant 인가를 대신하지 않는다. 티켓에 있던 오래된 권한만 믿지 않고
  구독·조회·변경마다 현재 권한을 집행한다. token/session 만료·로그아웃·권한 철회 시 재인증/연결 종료
  정책과 반영 시간을 정한다. renewal 메시지만 받았다고 유효 기간을 연장하지 않는다.
- 메시지 schema·크기·호출량·idle timeout·동시 연결 상한을 두고 만료·철회 연결이 계속 작업하지 못하게 한다.
  동시 티켓 소비, 다른 Origin·사용자/객체, 연결 후 권한 철회·만료·renewal 재사용을 회귀 검사한다.

근거: [OWASP WebSocket Security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html),
[Valkey GETDEL](https://valkey.io/commands/getdel/). 이 절은 문서 설계 보완이며 특정 앱 취약점의 재현 결과가 아니다.

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
3. token의 검증된 subject와 같은 사용자인지 확인하고 비밀번호/MFA 등 요구한 재인증 수행
4. fresh=True와 서버의 reauth_at을 담은 access token 발급 (이 예시는 refresh token 교체 없음)
5. Response: { access_token }
```

- 민감 endpoint는 서버의 dependency/middleware/policy에서 검증된 재인증 증거·subject·session·
  허용 경과 시간과 필요한 MFA 수준을 **강제**한다. 클라이언트 UI의 호출 순서·body의 fresh 값·명세 규약에 맡기지 않는다.
- 일반 Access Token이 유효해도 재인증 창을 넘기면 거부한다. 허용 시간은 작업 위험으로 정하며
  `fresh=True`만으로 발급 시점부터 만료까지 무제한 재사용하게 하지 않는다. 필요하면 행위·대상에 묶인
  짧은 수명·단발 step-up 증거를 쓰고 원자적으로 소비한다. OIDC의 auth_time/acr/amr는 신뢰한 IdP 계약으로 해석한다.
- 재인증 endpoint에도 인증·rate limit·안전한 오류를 적용한다. 재인증 없이 민감 API 직접 호출,
  오래된 증거·다른 사용자·위조 flag·세션 폐기·단발 증거의 동시 재사용이 거부되는지 검사한다.

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

- 브라우저 토큰 저장은 `frontend.md`의 HttpOnly 쿠키/BFF·XSS·CSRF 기준을 따른다.
- `localStorage`·`sessionStorage`에 인증·갱신 토큰을 저장하는 것을 공통 기본값으로 삼지 않는다.
- 동시 다발 401 시 refresh 큐(promise) 하나만 실행, 나머지는 대기 후 일괄 재시도.

자세한 인터셉터 코드는 `frontend.md` 참고.
