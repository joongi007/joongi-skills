# JWT 검증·JWKS cache·서명 키 회전 (PLAYBOOK §19)

JWT(JSON Web Token)는 토큰 형식이며 인증·인가 프로토콜 자체가 아니다.
JWK(JSON Web Key)는 키 표현, JWKS(JSON Web Key Set)는 키 집합이다.
비대칭 서명 검증용 공개 JWKS를 공개하는 것은 정상적인 설계다. 개인키·대칭 서명 비밀은 공개하지 않는다.
API key·Access Token 원문을 저장하는 cache와 공개 verification key cache를 구분한다.

## 신뢰 경로와 검증

- 검증할 issuer·audience·허용 algorithm·token type을 사전에 정한다. 신뢰한 설정 또는 검증한
  OIDC/OAuth metadata의 `jwks_uri`에서 키를 가져온다. 요청의 임의 issuer URL로 discovery를 시작하지 않는다.
- 서명 전 header/claim은 untrusted input이다. `kid`는 해당 issuer의 신뢰한 키 집합 안에서
  후보를 고르는 selector이며 신원 증명이 아니다. URL·SQL·파일 경로로 해석하지 않는다.
- `jku`·`x5u`를 무조건 따라가지 않는다. discovery/JWKS 요청도 HTTPS·허용 목적지·redirect 정책·
  DNS/SSRF 경계·timeout·응답 크기·키 개수 상한을 적용한다. 키를 찾지 못하면 검증을 생략하지 않는다.
- 검증된 라이브러리로 algorithm·key type·용도와 서명을 검사한 뒤 issuer·audience·expiry·not-before 등
  계약을 검증한다. 허용 clock skew는 유한하게 정한다. 헤더가 고른 algorithm만 믿거나 `none`을 수용하지 않는다.
- ID Token·Access Token·다른 issuer의 JWT는 검증 규칙을 분리한다. 정상 서명만으로 목적·권한·
  계정 활성 상태가 보장되지 않는다. ID Token을 API Access Token 대신 쓰지 않는다.

## cache와 unknown kid

| 상황 | 동작 | 피할 실패 |
|---|---|---|
| 알려진 key·유효한 cache | 매 요청 원격 조회 대신 cache의 키로 검증 | 인증 서버 장애를 모든 요청에 직접 전파 |
| unknown `kid` | issuer별 bounded refresh·single-flight·cooldown 후 재검증 | 공격자가 무작위 kid로 fetch storm 유발 |
| refresh 실패 | 기존 신뢰 cache의 유효 기간·허용 stale 정책을 적용 | 무한 stale·signature bypass·신규 키를 임의 신뢰 |
| 최초 기동·사용할 키 없음 | 인증 실패/의존성 장애로 처리하고 관측 | fail-open |

cache는 issuer별로 분리하고 TTL·Cache-Control·운영 상한을 함께 설계한다. stale을 허용한다면
최대 시간과 긴급 key 폐기에 미칠 지연을 명시한다. 민감한 경로는 더 엄격한 정책을 택한다.
JWKS를 매 요청 무조건 갱신하거나 unknown kid를 무제한 negative cache에 넣지 않는다.

## 정상 회전과 긴급 폐기를 구분하기

정상 회전: 새 공개 키 게시 → verifier 전파 확인 → 새 개인키로 서명 시작 →
기존 토큰의 최대 유효 수명·clock skew·배포 지연을 고려한 overlap → 기존 공개 키 제거 순서로 설계한다.
`kid`는 issuer 안에서 명확히 식별되게 하고 서명 키와 암호화 키의 용도를 섞지 않는다.

개인키 유출 시에는 정상 overlap을 그대로 기다리지 않는다. 서명 중단·새 키 전환·verifier cache 갱신·
침해 키 거부·필요한 세션/토큰 폐기를 조정한다. JWKS에서 키를 제거해도 모든 verifier cache가 즉시 지워지지는 않는다.
일반적인 서명 검증만으로 개별 JWT의 즉시 철회가 되지 않으므로 짧은 만료·introspection·denylist·
세션/정책 version 검증 중 필요한 계약을 선택한다. 키 제거를 단순 사용자 로그아웃 수단으로 사용하지 않는다.

개인키는 가능하면 별도 signer/KMS/HSM에서 관리한다. 비추출 키도 허용된 signing API의 악용을 막지는 않으므로
호출 identity·권한·quota·감사·폐기를 적용한다.

검증: unknown kid flood, 잘못된 alg·issuer·audience·token type, 만료/clock skew, JWKS timeout·과대 응답·
악성 redirect, 회전 중 구/신 토큰, 침해 키와 stale cache, 여러 verifier의 전파 지연을 확인한다.

관련: [API key](api-key-security.md), [공통 인증](identity-authorization.md), [메모리 비밀](memory-secrets.md).
공식 자료 확인: 2026-11-25.
[JWK, RFC 7517](https://www.rfc-editor.org/rfc/rfc7517.html),
[JWT BCP, RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html),
[OAuth metadata, RFC 8414](https://www.rfc-editor.org/rfc/rfc8414.html).
cache와 정상/긴급 전환 절차는 위협·가용성 요구에 맞춰 구체화할 운영 계약이다.
