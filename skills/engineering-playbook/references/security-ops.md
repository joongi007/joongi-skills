# 보안 운영 가이드 (PLAYBOOK §24, §29)

구현 단계의 검사는 [웹 보안](web-security.md), 관측·알림·격리·복구 절차는
[탐지·대응](incident-response.md)을 따른다. 아래 항목은 선택한 배포 환경과 위험에 맞춰 적용한다.
도입 전·30일 경과 시 점검은 [취약점 관리](vulnerability-management.md), nginx는 [보안 버전 확인](nginx-security.md)을 따른다.
Java 관리 경로는 [Actuator](java-actuator.md), 덤프·컨텍스트 수명은 [메모리 보안](memory-secrets.md)을 본다.

## 목차

- §9 브라우저·관리 진입점
- §10 개인정보·비밀
- §11 실행·공급망·네트워크
- §12 백업·복구
- §13 운영 준비와 검증
- §14 Zero Trust·호스트 침해·서비스 간 통신

## §9. 보안 헤더와 브라우저 경계

컨텐츠 종류·origin·embedding 요구에 맞는 CSP·보안 헤더를 정한다. CSP는 안전한 출력·parser를 대체하지 않는다.
API·HTML·문서·파일 서빙·MCP Apps iframe은 필요한 정책이 다르다. 전역 헤더로 정상 iframe·OAuth 흐름을 깨뜨리지 않는다.

- TLS를 적용하고 HTTPS 서비스에는 HSTS의 subdomain·preload 영향을 검토한다. 로컬 HTTP 예제를 그대로 배포하지 않는다.
- `nosniff`·Referrer-Policy·frame-ancestors·Permissions-Policy 등을 필요한 기능과 함께 검증한다.
- 앱과 프록시의 헤더 소유자를 정한다. 중복·상충·라우트별 예외를 검사한다.
- 관리 UI·진단 문서·debug 경로는 인증·네트워크 격리·노출 허용 목록으로 제어한다.
- custom 인증 chain·reverse proxy 설정이 기존 보안 기본값을 대체하는지 확인한다.

## §10. 개인정보와 비밀의 수명

필요한 데이터만 수집하고 목적·보관 기간·접근 권한·삭제·백업 정책을 정한다.
민감 필드의 저장 암호화와 키 버전·회전·폐기·복구 절차를 함께 설계한다.

- 키는 데이터와 분리된 OS 저장소·KMS·Vault 등에서 관리한다. 사용 순간의 평문과 특권 침해 한계는 남는다.
- 로그·trace·예외·쿼리 파라미터·응답·내보내기·문서 메타데이터를 통한 노출을 검사한다.
- 운영 데이터를 개발 환경에 복사하지 않는다. 검증에는 가짜 비밀·비식별 fixture를 사용한다.
- 인증 토큰의 브라우저 저장은 [프론트엔드 지침](frontend.md)을 따른다. 편의를 이유로 영구 저장을 기본으로 삼지 않는다.
- 유출된 자격증명은 폐기·재발급한다. Git 이력이나 파일 삭제만으로 노출이 취소되지 않는다.
- 사용자 통지·파기·법적 신고는 관할·계약·사고 유형을 확인하고 담당자와 절차를 정한다.

## §11. 실행·공급망·아웃바운드

공급망·관리 인터페이스·권한 오용·취약 parser·외부 의존성을 함께 검토한다.
특정 침투 경로가 언제나 가장 흔하다고 가정하지 않는다.

- 의존성 출처·이름·버전·lockfile·hash·서명을 검증하고 지원 버전·취약점 갱신 절차를 둔다.
- 내부 패키지는 신뢰할 registry에서만 해석되게 한다. 단순히 여러 인덱스의 순서를 정했다고 dependency confusion이 해결됐다고 보지 않는다.
- 실행은 비특권·최소 capability·최소 파일/네트워크 권한으로 제한한다. 필요한 쓰기 경로만 허용한다.
- read-only filesystem·도구 제거만으로 메모리 실행·허용된 경로의 악용까지 막는다고 주장하지 않는다.
- 필요한 egress 목적지·DNS·metadata 접근을 제한한다. 허용한 목적지를 통한 반출이나 기존 세션도 고려한다.
- 알려진 악성 네트워크를 보조 차단할 때는 [Spamhaus DROP·reputation 운영](network-reputation.md)의 이용 조건·갱신·오탐·rollback을 확인한다.
- 외부 MCP·플러그인은 설치·등록·연결·도구 실행을 구분한다. 검색·미리보기만으로 실행하지 않는다.
- 실행 정책·권한·이미지·외부 연결 변화와 탐지 수집 중단을 관측한다. 보안 제품 이름만 나열하고 완료로 취급하지 않는다.

## §12. 백업·복구·증거

복사 개수보다 실제 복원 가능성과 침해 시 권한 분리를 확인한다.
불변·오프라인·별도 계정 백업을 위험과 운영 여건에 맞춰 선택한다.

- 앱 권한으로 백업을 삭제·암호화할 수 없는지 확인한다. 보존 정책과 백업 수행 계정의 권한을 구분한다.
- 무결성·복원·시점 복구·데이터 일관성을 실제로 검사하고 RPO/RTO를 측정한다.
- 이미 침해된 백업만 남지 않도록 보관·검증·복구 시점 판단을 설계한다.
- 긴급 연락처·복구 절차는 주 서비스가 중단돼도 접근 가능하게 준비한다.
- 진행 중 피해를 제한하면서 가능한 증거를 보존한다. 무조건 재부팅하거나 조사 완료까지 반출을 방치하는 절차를 쓰지 않는다.
- 신뢰할 수 있는 이미지·키·설정으로 복구하고 기능·권한·추가 이상 징후를 확인한 뒤 제한을 해제한다.

## §13. 배포 전과 운영 중 검증

배포 준비는 정상 동작뿐 아니라 실패·관측 중단·오탐·rollback을 포함한다.

- 실제 production profile·네트워크·관리 경로·권한별 요청을 검증한다.
- 인증 실패·권한 변경·민감 조회·도구 실행·정책 변경 등 필요한 이벤트의 수집·마스킹·상관 분석을 확인한다.
- 알림 수신자·대체 경로·초기 대응·해제 담당자를 정하고 모의 사고로 도달 여부를 확인한다.
- 중앙 수집·불변 로그·자동 대응은 현재 위험·운영 인력·규모에 맞춰 선택한다.
- 탐지·확인·차단·복구 시간을 별도로 측정한다. 속도뿐 아니라 미탐·오탐·서비스 피해도 검토한다.

구체적인 시나리오 표와 훈련 방법은 [탐지·대응 가이드](incident-response.md)에 둔다.

## §14. Zero Trust·호스트 침해·서비스 간 통신

위협 모델에 OS·host administrator 침해를 포함한다. 앱은 OS가 제공하는 실행·메모리 경계에
의존하므로 같은 host의 root가 메모리·인증 코드를 통제하는 상황을 앱 단독으로 완전히 방어할 수는 없다.
목표는 prevention과 함께 lateral movement·blast radius를 줄이고 탐지·격리·복구 시간을 단축하는 것이다.

- 비특권·capability 축소·sandbox·VM·관리 영역 분리·패치로 침투와 확산 경로를 줄인다.
  같은 host의 container나 namespace를 침해된 host로부터의 완전한 방어 경계로 설명하지 않는다.
- 장기 비밀은 별도 KMS/HSM/signer에 두고 workload identity·짧은 수명 자격·작업별 최소 권한을 사용한다.
  비추출 키도 침해된 앱이 허용된 API로 악용할 수 있어 원격 정책·quota·감사·폐기가 필요하다.
- MSA(Microservices Architecture)의 내부망·VPN·service mesh 소속만으로 신뢰하지 않는다.
  service별 identity·수신 audience·허용 행위/자원을 매 요청 검증하고 network segmentation·egress 제한을 병행한다.
- mTLS는 transport peer를 인증한다. 최종 사용자·위임 권한·객체 인가는 별도다. 프록시가 전달하는
  identity header는 외부 값을 제거하고 검증한 경로에서만 신뢰한다. workload identity도 자동 인가는 아니다.
- Client Credentials·Token Exchange 등으로 대상에 맞는 짧은 자격을 선택한다. exchange 자체가
  원본 폐기·downscoping을 보장하지 않으므로 발급·검증·폐기 정책을 확인한다.
  bearer token 탈취 위험이 높으면 mTLS-bound token·DPoP 같은 sender constraint를 지원 범위에서 비교한다.
  TLS만 사용한 bearer token과 certificate-bound token을 같은 보장으로 설명하지 않는다.
- identity·인증서·키 회전과 폐기를 자동화하고 검증 장애 시 fail-closed 범위·서비스 피해를 정한다.
  침해 호스트는 외부 control plane에서 격리·자격 폐기할 수 있게 하고 감사 기록도 독립된 위치에 보관한다.
  신뢰한 이미지로 재구축하고 공격자가 남긴 세션·키·배포 권한도 재검토한다.

검증: 잘못된 서비스 identity·audience, 횡적 자원 접근, header 위조, 자격 폐기·회전,
인증 의존성 장애, host 격리와 잔존 연결·egress·감사 수집 중단을 가짜 자격으로 확인한다.
관련: [공통 인증·인가](identity-authorization.md), [메모리 비밀](memory-secrets.md), [용어](terminology.md).
근거: [NIST SP 800-207](https://www.nist.gov/publications/zero-trust-architecture),
[mTLS-bound token, RFC 8705](https://www.rfc-editor.org/rfc/rfc8705.html),
[DPoP, RFC 9449](https://www.rfc-editor.org/rfc/rfc9449.html). 공식 자료 확인: 2026-11-25.
