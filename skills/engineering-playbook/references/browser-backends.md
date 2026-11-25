# BFF·TMB와 브라우저 인증 (PLAYBOOK §19, §20)

BFF(Backend for Frontend)는 특정 frontend에 맞춘 backend다. API aggregation·응답 형태 최적화·
여러 서비스의 orchestration을 제공할 수 있으며 JWT 전용 개념이 아니다.
인증에서 말하는 proxying BFF는 그중 OAuth 토큰을 서버에 두고 API 요청을 대행하는 구체적 구성이다.
앱 세션은 opaque session ID일 수 있고 Access Token도 반드시 JWT인 것은 아니다.

## OAuth 배치 방식 비교

| 방식 | 토큰과 호출 경로 | 주요 판단 |
|---|---|---|
| Proxying BFF | Access/Refresh Token은 서버, 브라우저는 session cookie, BFF가 resource server 호출 | JS의 토큰 탈취 노출 축소, 모든 대행 트래픽·서버 세션 운영 비용 |
| TMB (Token-Mediating Backend) | OAuth 교환·Refresh Token은 서버, Access Token을 브라우저에 전달해 API 직접 호출 | 대용량·직접 API 경로의 필요와 JS의 Access Token 탈취 위험 비교 |
| Browser-only OAuth client | public client가 PKCE 흐름·토큰·API 호출 관리 | backend 운영은 적지만 브라우저의 토큰·갱신 위험과 공급자 정책 검토 |

토큰 탈취 위험을 줄여야 하고 API 대행이 가능한 앱은 BFF를 우선 검토한다.
모든 서비스에 무조건 최선인 것은 아니다. 데이터 크기·streaming·latency·API topology·운영 비용을 비교한다.
TMB는 Token-Mediating Backend를 뜻하며 별도 약어를 만들거나 token exchange와 같은 개념으로 쓰지 않는다.

- BFF도 XSS를 없애지 못한다. 악성 JS가 사용자의 session으로 요청·응답 탈취를 할 수 있다.
  HttpOnly·Secure·적절한 SameSite·CSRF/Origin 검사·CSP·출력 검증·세션 폐기는 계속 필요하다.
- TMB는 confidential client로 Code 교환을 처리한다. 브라우저에 client secret·Refresh Token을 주지 않고
  필요한 audience/scope와 짧은 수명의 Access Token만 반환한다. 메모리 저장도 XSS로부터 안전한 저장소는 아니다.
  토큰 발급 endpoint의 세션·CSRF·rate limit과 API CORS를 검증한다. CORS는 API 인증·인가의 대체 수단이 아니다.
- TMB의 토큰 cache는 요청한 scope보다 넓은 토큰을 반환하지 않게 하고 사용자·세션·audience를 분리한다.
  브라우저로 전달하는 토큰 응답은 저장되지 않게 한다. 로그아웃은 이미 발급한 Access Token의 즉시 무효화와 다르다.
- BFF가 generic proxy·SSRF 통로가 되지 않도록 upstream·route·method·header를 제한한다.
  브라우저가 임의 목적지·다른 사용자의 자격을 지정하게 하지 않는다.

## API aggregation·orchestration 경계

여러 서비스의 결과를 묶을 때 전체 deadline·각 호출 timeout·병렬 fan-out 상한·부분 실패 계약을 정한다.
대상 서비스마다 사용자·서비스 신원과 자원 권한을 검증한다. BFF가 인증했다는 이유로 내부 API의 인가를 생략하지 않는다.
도메인의 원자적 업무 규칙을 화면 전용 BFF에 중복 구현하지 않고, 독립 트랜잭션의 orchestration은
필요하면 전용 application/workflow 계층에 둔다. BFF를 모든 frontend의 거대한 공통 backend로 키우지 않는다.

검증: XSS·CSRF 가정, 잘못된 Origin·audience, 세션 폐기·갱신 경합, TMB의 scope 확대,
BFF 임의 URL 요청·upstream 장애·부분 성공·취소·fan-out 폭주를 확인한다.

관련: [공통 인증·권한](identity-authorization.md), [외부 통신](external-cache.md), [용어](terminology.md).
공식 자료 확인: 2026-11-25.
[OAuth 브라우저 앱 BCP, RFC 10017](https://www.ietf.org/ietf-ftp/rfc/rfc10017.html),
[OAuth Security BCP, RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html).
