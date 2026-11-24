# 공통 인증·권한 기반 선택 (PLAYBOOK §19, §25)

여러 서비스에서 로그인·MFA·SSO를 공유하거나 자원·그룹·소속 관계에 따른 권한이 필요할 때 읽는다.
단일 앱의 단순 역할 검사라면 기존 프레임워크·관리형 IdP·DB 권한 테이블로 충분할 수 있다.
Keycloak·OpenFGA를 함께 설치하는 것 자체를 목표로 삼지 않는다. 운영 비용·장애 영향·대안과
실제 권한 조회 부하를 비교하고 선택을 ADR에 기록한다.

## 책임을 나누기

| 구성 요소 | 책임 | 대신하지 않는 것 |
|---|---|---|
| Keycloak 등 IdP | 계정·로그인·MFA·외부 IdP·토큰 발급 | 앱 가입·tenant 소속·모든 자원 권한 |
| BFF (선택) | 브라우저 세션, 서버 측 토큰 보관·갱신 | API의 자원 소유권 검사 |
| 권한 서비스 (선택) | 호출자·대상 범위 검증, 관계 변경·감사 API | 업무 데이터 API의 실제 집행 |
| OpenFGA 등 권한 엔진 | 모델·관계에 따른 접근 판단 | 사용자 인증, 호출 앱별 관계 변경 인가 |
| 업무 API | 검증된 주체·실제 데이터·행위를 연결해 권한 집행 | UI가 숨긴 기능에 대한 신뢰 |

공통 권한 서비스는 모든 앱에 엔진 쓰기 자격을 배포하지 않기 위한 선택지다.
별도 서비스가 불필요하면 앱 안의 명확한 경계로 구현할 수 있다. 엔진 API 인증 성공만으로
그 호출자가 모든 store·모델·tenant의 관계를 수정해도 된다고 해석하지 않는다.

## 인증 경로와 신뢰 경계

- 브라우저는 표준 OIDC Authorization Code + PKCE 흐름을 사용하고 state·nonce·redirect URI를 검증한다.
  BFF를 선택하면 토큰은 서버에, 브라우저에는 Secure·HttpOnly·적절한 SameSite 세션 쿠키를 둔다.
  CSRF·Origin 검사·로그아웃·세션 회전도 설계한다. SPA는 public client이며 client secret을 넣지 않는다.
- API는 ID Token 대신 자신을 대상으로 한 Access Token을 사용한다. 신뢰한 라이브러리로
  서명·허용 알고리즘·issuer·audience·만료를 검증하고 JWKS 갱신·키 교체도 시험한다.
  사용자 식별은 검증된 `(issuer, subject)`에서 얻는다. 이메일·표시 이름·요청 body의 사용자 ID는 인증 증거가 아니다.
- 기계 자체 작업의 Client Credentials와 사용자 대신 수행하는 호출을 구분한다.
  내부 위임이 필요하면 대상 audience에 맞는 토큰·Token Exchange·검증된 서비스 간 계약을 비교한다.
  사용자 토큰을 모든 서비스에 전달하거나 audience 검증을 끄는 방식으로 연결하지 않는다.
- Token Exchange는 도입할 때 지원 버전·realm/client 제약·대상·scope·요청 client 정책을 확인한다.
  교환 자체가 권한 축소·실제 송신자 증명·원본 폐기 전파·사용자 동의를 자동 보장하지 않는다.
  서비스 자격과 전달된 사용자 문맥을 신뢰하는 대안은 그 신뢰 범위·위조 방지책을 명시한다.
- 여러 BFF/API 복제본에서는 세션·OAuth state·갱신 토큰 회전·로그아웃 상태를 공유/조정한다.
  토큰 캐시는 세션·원본 토큰·대상 audience·scope를 구분하고 만료·폐기를 반영한다.
  교환 토큰 재사용과 자원 권한 결과 캐시는 서로 다른 정책이다.

## OpenFGA 모델·집행 계약

- 업무의 주체·행위·객체·tenant 경계부터 적고 관계와 상속을 모델링한다. 역할 이름은 앱 계약이다.
  플랫폼 관리자 권한과 고객 데이터 열람 권한, 로그인 계정과 서비스 가입·소속을 구분한다.
  Keycloak 그룹과 앱의 권한 그룹을 자동으로 같은 원장으로 취급하지 않는다.
- 서비스 설정에 store와 `authorization_model_id`를 고정한다. 새 모델 생성은 운영 전환이 아니다.
  모델·관계 데이터·앱 계약의 호환성, migration·rollback을 함께 검증한다.
- 읽기 Check와 권한 부여·회수·그룹 변경은 별도 작업으로 인가한다. 후자는 호출 서비스의 범위와
  실제 수행 주체의 관리 권한을 모두 확인한다. 사용자 입력으로 임의 store·model·tenant를 선택하게 하지 않는다.
- API는 자신의 DB에서 실제 데이터와 권한 객체의 연결을 확인한다. 클라이언트가 보낸
  허용 객체 ID와 다른 데이터 ID를 조합해 접근할 수 없어야 한다. 목록·검색·개수·감사 조회도 같은 경계를 적용한다.
- 조회 오류·timeout·동기화 불확실성을 허용으로 바꾸지 않는다. 거부와 의존성 장애는 관측·응답에서 구분한다.
  권한 회수 반영 시간을 정하고 엔진·앱의 캐시를 모두 고려한다. `HIGHER_CONSISTENCY`는 엔진 캐시를
  우회하지만 앱 DB에서 아직 전송하지 않은 관계를 동기화하거나 진행 중 작업을 취소하는 기능은 아니다.
  판단 후 실행까지의 경합이 위험한 작업은 버전 재검증·트랜잭션 등 추가 집행 계약을 둔다.

## 기준 데이터·반영·복구

관계의 원장을 엔진 또는 업무 DB 중 어디에 둘지 정한다. 같은 관계를 두 곳에서 독립 수정하지 않는다.
업무 DB를 원장으로 택하면 관계 변경·outbox·감사 intent를 함께 저장하고 엔진 반영을 재시도한다.
부분 성공·중복 배달·순서 역전·여러 반영 worker의 경합을 처리하고 완료한 버전만 기록한다.
이는 구현 선택지이며 모든 앱에 별도 DB·outbox를 추가하라는 뜻은 아니다.

특히 회수 미반영이 위험하면 영향받은 tenant·자원 범위의 판단을 일시 중단하는 등 실패 정책을 정한다.
필요 이상의 전역 차단을 피하고 지연·실패·원장/반영 버전 차이에 알림을 둔다.
각 DB 덤프를 복원했다고 같은 시점의 권한 상태가 되지는 않는다. 트래픽 재개 전에 원장 기준으로
엔진 관계를 재구성·대조하고 허용·거부 사례를 검증한다. 엔진을 원장으로 쓴 데이터도 별도로 보존한다.

## 운영 수용 조건

- 관리 API·엔진·DB는 최소 권한·네트워크 경계·TLS로 보호한다. 공개 로그인 endpoint와 관리 경로를 구분한다.
  중앙 IdP·권한 엔진 장애의 영향·시간 예산·복구·비상 관리자 접근·감사를 설계한다.
- 잘못된 issuer/audience·만료 토큰, 다른 tenant, 자기 권한 상승, 회수·재가입·상속 방향,
  권한 서비스 장애, 부분 반영·재시작·다른 시점의 백업 복원을 검증한다. 허용 사례만 시험하지 않는다.
- Keycloak 배포 버전의 hostname·신뢰 proxy header·TLS 설정을 확인한다. 관리자 hostname을 따로
  지정하는 것만으로 접근 통제가 되지 않는다. 관리 API와 health/metrics의 외부 노출도 별도로 제한한다.

관련: [인증 UI](identity-ui.md), [외부 통신·캐시](external-cache.md), [비동기 작업](background-jobs.md),
[운영 보안](security-ops.md), [DB 복구](database-recovery.md).
공식 자료 확인: 2026-11-25. 지원 범위·설정은 도입 버전에서 재확인한다.

- [Keycloak 브라우저 연동](https://www.keycloak.org/securing-apps/javascript-adapter), [Token Exchange](https://www.keycloak.org/securing-apps/token-exchange)
- [Keycloak reverse proxy](https://www.keycloak.org/server/reverseproxy)
- [OpenFGA 모델 고정](https://openfga.dev/docs/getting-started/immutable-models), [일관성 모드](https://openfga.dev/docs/interacting/consistency)
- [OpenFGA 운영](https://openfga.dev/docs/best-practices/running-in-production), [모델 테스트](https://openfga.dev/docs/modeling/testing)
