# API key 수명주기와 공개 API (PLAYBOOK §19, §24, §28)

API key는 보통 possession으로 인증하는 bearer credential이다. 호출 앱·프로젝트의 식별과
최종 사용자의 인증·자원 인가를 구분한다. 고위험 작업은 정적 API key 하나에만 의존하지 않고
짧은 수명 자격·workload identity·추가 인가 등을 위험 모델에 맞춰 선택한다.

## 문서 공개와 공격 표면

API·OpenAPI 문서가 공개돼도 undocumented endpoint·숨은 필드·변형 입력까지 탐색된다고 가정한다.
문서 접근 제한은 security through obscurity를 보안 경계로 삼는 것과 구분한다.

- 공개 SDK·외부 연동용 계약은 공개할 수 있다. 사내 API·관리/진단 schema·운영 절차는 대상에 맞게
  인증·권한·네트워크 접근을 제한한다. 정적 schema 파일·구버전·직접 URL도 같은 정책을 적용한다.
- 문서의 로그인 여부와 무관하게 모든 endpoint에서 인증·자원별 인가·입력 검증을 집행한다.
  숨은 필드로 권한·소유자를 덮어쓰는 mass assignment와 미등록 경로·메서드도 검사한다.
  다른 사용자의 자원 ID와 절차를 건너뛴 비정상 호출 순서도 서버의 소유권·상태 전이 검사로 거부한다.
- API key·tenant·IP 등 여러 축의 rate limit·quota, 비용 큰 연산의 동시성·payload·큐 상한을 둔다.
  유효하지 않은 key의 요청도 비싼 검증 전에 제한한다. IP 하나나 WAF만으로 방어가 끝나지 않는다.
- 키 열거·다양한 경로의 실패·비정상 호출량·egress·사용 비용을 탐지하고 key/tenant별 차단·폐기를 준비한다.
  실 key·개인정보·내부 접속 정보는 문서 예제·Try it out·분석 수집에 포함하지 않는다.

## 검증용 저장과 재사용용 저장을 구분하기

| 서버가 해야 하는 일 | 저장 방식 | 중요한 한계 |
|---|---|---|
| 들어온 key가 맞는지 확인 | 비가역 verifier와 key 메타데이터 | 원문 복구·다른 서비스 호출에 사용 불가 |
| 외부 서비스에 key를 보내 호출 | secret manager/KMS 기반 암호화·최소 권한 사용 | 사용 시 평문·호출 권한이 필요하므로 hash만으로 대체 불가 |
| 공개 키로 서명 검증 | 신뢰한 JWKS의 공개 키 cache | API key 원문·대칭 비밀과 다른 데이터 |

서버가 발급하는 key는 CSPRNG로 충분한 entropy를 갖게 한다. 예를 들어 공개 key ID와
독립적인 32 random bytes의 secret을 조합할 수 있다. ID·prefix는 lookup용이며 secret의 entropy를 대신하지 않는다.
발급 때 TLS로 한 번 표시하고 재조회 대신 재발급을 제공한다. URL·로그·trace·예외에 원문을 넣지 않는다.

고엔트로피 random secret의 verifier에는 SHA-256 digest 또는 별도 보호한 서버 키를 쓰는
HMAC-SHA-256을 선택할 수 있다. HMAC 키를 같은 DB에 함께 두지 않고 버전·회전을 설계한다.
이는 예측 가능한 비밀번호에 빠른 hash를 사용해도 된다는 뜻이 아니다.
사람이 정하는 저엔트로피 비밀을 허용한다면 password KDF(예: Argon2id)와 비용 상한을 별도로 검토한다.
가능하면 그런 값을 API key로 받지 않고 서버가 생성한다.

bcrypt는 주로 password hashing용이다. 무조건 모든 API key에 적용하면 요청마다 CPU 비용이 커지고
구현에 따라 72-byte 제한도 문제가 된다. 기존 bcrypt verifier가 있으면 길이·비용·migration을 확인한다.
cache에는 원문 대신 verifier·scope·expiry·revocation version 등을 두고 안전한 비교 함수를 사용한다.
digest 자체를 클라이언트가 제시하는 인증 값으로 허용하지 않는다. 그것도 재사용 가능한 credential이 된다.

AWS/S3 SigV4처럼 요청 서명에 쓰는 자격은 검증용 digest만 보관해서는 호출할 수 없다.
가능하면 SDK와 role/workload identity의 단기 자격을 사용한다. 장기 자격이 필요하면 암호화 보관·
최소 권한·회전 또는 요청 서명을 지원하는 별도 경로를 검토한다. 일반 KMS 서명이 SigV4와
바로 호환된다고 가정하지 않는다. 실제 signing key 유도·요청 서명과 공급자 계약을 확인한다.

검증 중 요청에 들어온 원문은 잠시 메모리에 존재한다. 불필요한 복사·참조·보관을 줄이되
hash 저장을 프로세스 메모리 읽기·인증 코드 변조에 대한 완전한 방어라고 설명하지 않는다.

## 발급·회전·만료·철회 계약

key별 owner·tenant·허용 scope/resource·상태·생성/만료 시각·최근 사용·verifier 버전을 관리한다.
무기한 key는 기본값으로 두기보다 별도 사유·소유자·재검토 기한을 둔다.

| 위험·환경 | 선택할 정책 예 | 검증할 것 |
|---|---|---|
| 제한된 저위험 개발 연동 | dev 전용 scope·quota, 명시적 만료·수동 회전 | 운영 자원 접근 불가·만료 집행 |
| 서비스 간 운영 연동 | 앱별 key, 자동 만료·회전, 짧고 제한된 old/new overlap | 모든 호출자 교체·오래된 key 종료 |
| 고위험·규제·외부 노출 | 짧은 수명 토큰·workload identity·sender constraint 등 비교 | 침해 시 신속한 폐기·최소 권한·감사 |

평상시 회전은 새 key 발급 → 호출자 전환 → 관측 → 기존 key 폐기로 진행한다.
overlap의 종료 시각을 정하고 old key를 계속 연장하지 않는다. 유출 의심 시에는 overlap보다 즉시 폐기를 우선한다.
서버는 매 요청에서 만료·상태·scope를 집행한다. 표시만 만료되거나 신규 발급만 하는 것은 회전 완료가 아니다.
분산 verifier/인증 결과 cache의 TTL·무효화·version 검사를 정하고 철회가 모든 복제본에 반영되는 시간을 측정한다.
철회 확인 장애를 무조건 허용으로 바꾸지 않는다. 기존 연결·진행 중 작업의 중단 범위도 별도 계약이다.

검증: 원문 저장/로그 누출, 잘못된 key, 만료 경계, 회전 중 동시 호출, overlap 종료, 강제 폐기와
cache 지연, 다른 tenant/scope, 인증 실패 flood, HMAC 키 교체·복원 후 폐기 key 재활성화를 확인한다.

관련: [메모리 수명](memory-secrets.md), [JWKS](jwt-jwks.md), [침해 대응](incident-response.md).
공식 자료 확인: 2026-11-25.
[OWASP REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html),
[Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html),
[Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
[AWS SigV4의 자격·서명 구조](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv.html).
digest·HMAC·cache 구성은 위협 모델에 따른 설계 선택이며 특정 표준의 일괄 의무로 해석하지 않는다.
