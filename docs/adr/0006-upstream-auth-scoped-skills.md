# ADR-0006: upstream 인증과 프로젝트별 스킬 관리

상태: accepted · 날짜: 2026-11-07

## 맥락

개인 Hub 하나에서 인증이 필요한 여러 MCP를 연결하고, 공용 스킬과 프로젝트 스킬을
분리하며 에이전트용 복사본을 설치·업데이트해야 한다. 기존 개인 설정과 수정한 파일은 보존해야 한다.

## 선택

Hub 로그인 대신 loopback 경계와 기존 관리 API 보호를 유지하고 upstream별 인증을 추가한다.
OAuth discovery·PKCE·브라우저 callback·Device Code·Client Credentials와 수동 헤더 인증을 지원한다.
토큰은 서버 설정과 분리하고 서버 URL·인증 설정 fingerprint 및 프로젝트 상태 경로에 결합한다.
Windows는 DPAPI, POSIX는 소유자 전용 파일을 사용한다. provider별 모든 인증 확장을 광고하지 않는다.

명시적으로 등록한 프로젝트의 선택된 공용 항목과 로컬 스킬을 합성한다. 로컬 스킬이 우선하며
읽기·검색·native Skills URI에 동일한 카탈로그를 적용한다. stdio 연결은 profile을 고정한다.
인증·Tasks·연결 설정은 범위별 상태를 쓰고 에이전트가 스스로 읽는 전역 스킬과 구분한다.

설치는 기존 installer의 소유권·잠금·복구를 재사용한다. 변경 계획의 스냅샷과 대상 hash를 검증한 뒤
계획 ID로 적용한다. 프로젝트 복사본은 기본 고정하고 lockfile도 같은 설치 트랜잭션에서 기록한다.
임의 MCP 요청으로 다른 출처를 신뢰하거나 프로젝트 자체 스킬을 공용으로 승격하지 않는다.

## 대안·결과

Keycloak·다중 사용자 권한은 개인 로컬 범위에 과해 제외한다. 에이전트마다 OAuth를 중복 구현하거나
비밀을 server JSON에 넣는 방식도 제외한다. POSIX 파일은 OS 계정 탈취를 방어하지 않는다.
회사별 SSO·mTLS 등은 별도 adapter가 필요하다. 네이티브 에이전트의 전역 스킬 우선순위는 Hub가 제어하지 않는다.

## 검증

`tests/test_auth.py`는 독립 HTTP provider로 PKCE·discovery·갱신·회전·철회·device polling과
관리 API 보호를 검증한다. `tests/test_projects.py`는 경로·카탈로그·인증 저장소·RPC 범위를,
`tests/test_skill_management.py`는 고정·수정 보호·스냅샷·재사용 차단·롤백을 검증한다.
`tests/browser_management.cjs`는 실제 Chromium으로 OAuth 팝업과 callback, 사용자·프로젝트 설치,
프로젝트 선택과 연결 제외를 확인한다. 실제 상용 제공자 전체를 검증했다는 의미는 아니다.
