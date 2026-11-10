# 인증·프로젝트 범위·스킬 관리

문서 ID: OPS-AUTH-PROJECTS · 요구사항: REQ-REGISTRY, REQ-SKILL, REQ-INSTALL

## 연결한 MCP에 로그인하기

Hub는 단일 사용자 loopback 서비스다. Hub 자체에 Keycloak이나 사용자 로그인을 추가하지 않았다.
관리 API는 기존 Host·Origin 검사와 세션 토큰을 사용한다. 이 토큰과 upstream 서비스의 토큰은 별개다.
로컬 프로세스와 OS 계정을 신뢰하는 모델이며, 다른 사용자에게 원격 공개하는 서버가 아니다.

MCP 연결 → 해당 서버의 **인증**을 펼쳐 방식을 저장한 뒤 로그인한다.
인증 방식을 바꾸면 **인증 설정 저장**을 먼저 누른다. 저장 전에는 로그인·비밀 값 저장을 막고,
선택한 인증 방식에 해당하는 입력과 행동만 보여준다.
OAuth는 **로그인 시작 → 브라우저에서 계속**을 누르고 서비스에서 동의한 뒤 Hub로 돌아와
**연결 확인**을 누른다. 동의·서비스 계정 가입·MFA를 에이전트가 대신 승인하지 않는다.

| 방식 | 설정·행동 |
|---|---|
| none | 인증 없는 서버 |
| bearer | token_env로 환경변수 이름 지정 또는 로컬 비밀 값 저장 |
| api_key | token_env, header, 선택적 prefix. 기존 headers 환경변수 매핑도 지원 |
| basic | username_env·password_env 또는 로컬 사용자 이름·비밀번호 저장 |
| oauth | 브라우저 Authorization Code + PKCE S256, state·issuer·resource 검사 |
| device_code | 서비스가 지원하면 코드 입력 후 로그인 완료 확인. poll 간격 준수 |
| client_credentials | client_id·client_secret_env 필수. 사용자 동의 없는 서비스 계정 grant |
| external | stdio 서버 자체 CLI 로그인·자격증명 저장소·env 매핑 사용 |

HTTP OAuth는 WWW-Authenticate의 Protected Resource Metadata, RFC 8414와 OIDC discovery,
사전 등록 client ID, 서버가 지원하는 CIMD 또는 Dynamic Client Registration을 처리한다.
client secret은 환경변수로 주고 client_secret_basic 또는 client_secret_post를 지정할 수 있다.
토큰 갱신·refresh token rotation, 401 이후 한 번의 갱신·재시도, 선택적 provider revocation을 지원한다.
권한 확대는 자동 동의하지 않는다. 서버가 요청한 scope를 확인하고 다시 로그인한다.

고급 설정에는 `issuer`, `resource_metadata_url`, `client_auth_method`, `client_metadata_url`,
개별 `*_endpoint`를 넣는다. CIMD는 실제 HTTPS client metadata 문서와 현재 callback 등록이
필요하다. 로컬 Hub가 외부에서 접근 가능한 CIMD 문서를 자동 발행하지는 않는다.
브라우저 OAuth 서버는 metadata에 S256 지원을 명시해야 한다. 고정 callback 포트가 필요한
제공자는 Hub의 포트를 고정하고 UI에서 사용하는 `http://127.0.0.1:포트/oauth/callback`을 등록한다.

```json
{"type":"oauth","client_id":"registered-id","issuer":"https://identity.example.com","scopes":["read"],"client_secret_env":"EXAMPLE_CLIENT_SECRET","client_auth_method":"client_secret_basic"}
```

인증 URL은 HTTPS 또는 loopback HTTP만 허용하고, metadata·token 요청의 redirect는 따르지 않는다.
토큰과 비밀번호는 서버 등록 JSON·도구 결과·화면 상태·요청 로그에 내보내지 않는다.
Linux/macOS에서는 `auth/credentials.json`을 소유자 전용 파일 권한으로 저장한다. 이 파일은
평문이며 OS 계정이나 관리자에게서 비밀을 숨기는 암호화 저장소는 아니다. Windows에서는
같은 사용자 DPAPI로 내용을 보호한다. 환경변수 값은 파일로 복사하지 않는다.
인증 해제는 로컬 저장 값을 지우고 가능한 경우 서비스 토큰을 철회한다. 환경변수·서버 CLI의
로그인 상태나 서비스의 모든 세션을 삭제하지는 않는다.

private_key_jwt, mTLS, DPoP, SAML 직접 로그인, 토큰 교환·회사별 비표준 SSO는 전용 구현이 필요하다.
모든 제공자의 실제 계정으로 검증한 것은 아니다. Device Code·Client Credentials도 서비스가
해당 grant를 지원해야 한다. stdio는 HTTP OAuth를 강제로 적용하지 않고 해당 서버의 인증 방식을 쓴다.

## 프로젝트마다 사용할 것만 선택하기

**프로젝트 범위 → 프로젝트 등록**에서 현재 컴퓨터의 절대 경로와 가져올 공용 스킬·MCP를 선택한다.
기본은 공용 항목을 가져오지 않는다. 상단 작업 범위를 바꾸면 선택한 카탈로그·연결·Tasks·인증을 사용한다.
공용 서버를 가져와도 인증 토큰은 프로젝트마다 따로 저장한다. 공용 서버 설정 변경은 상속에 반영되고,
같은 ID의 프로젝트 연결을 저장하면 그 프로젝트 설정이 우선한다. 상속 연결 자체를 제외하려면
프로젝트의 공용 MCP 선택을 해제한다.

프로젝트 스킬은 `.agents/skills`, `.claude/skills`, `.cursor/skills`, `.github/skills`,
`.gemini/skills`, `.opencode/skills` 순서로 찾는다. 같은 이름이면 먼저 발견한 프로젝트 스킬이
공용 스킬보다 우선한다. `skill_paths`로 이 목록을 줄이거나 순서를 바꿀 수 있다. 등록되지 않은
스킬은 URI를 직접 입력해도 읽을 수 없다. 프로젝트 밖 경로와 symlink는 허용하지 않는다.
프로젝트 등록을 해제해도 소스 파일이나 설치된 스킬을 삭제하지 않는다.

에이전트에는 프로젝트 카드의 **에이전트 연결 설정**을 등록한다. 핵심 인자는 다음과 같다.

```bash
python3 -m joongi_hub stdio --state-dir /path/to/hub-state --profile project-id
```

기본은 지정한 범위의 독립 stdio다. 혼합 모드는 같은 state의 실행 중인 HTTP Hub를 공유한다.
세 가지 연결 방식과 웹에서의 에이전트 등록은 [연결 설정](06-connection-modes.md)을 본다.
한 연결의 profile을 다른 profile로 바꾸는 요청은 거절한다. 이는 Hub 내 작업 분리이며,
악의적인 로컬 사용자에 대한 접근 제어·샌드박스는 아니다.
에이전트가 자체적으로 읽는 전역 스킬이나 별도로 등록한 MCP까지 숨기지는 않는다.
완전한 분리가 필요하면 해당 에이전트의 전역 설정도 확인하고 프로젝트 전용 연결을 사용한다.
다른 프로젝트나 기존 에이전트 설정을 자동으로 삭제하지 않는다.

## 스킬 설치·업데이트·제거

스킬 라이브러리의 **설치 관리**에서 작업·스킬·에이전트를 고르고 **변경 계획 보기**를 누른다.
대상 경로와 보호할 파일을 확인한 다음 **이 계획 적용**을 누른다. MCP에서도
`hub_skills_status`, `hub_skills_plan`, `hub_skills_apply`로 같은 기능을 사용한다.
`hub_auth_status`는 비밀 값 없이 현재 범위의 인증 상태를 반환한다. 로그인·비밀 입력은 로컬 UI에서 한다.

공용 범위는 사용자 스킬 폴더에, 프로젝트 범위는 프로젝트 스킬 폴더에 복사한다.
Claude·Codex·Cursor·Copilot·Gemini·OpenCode 중 대상을 고를 수 있다. 이 관리 기능은 스킬만
변경하며 에이전트 실행 파일이나 MCP 설정은 수정하지 않는다. 기존 설치 스크립트의 소유권 manifest를
재사용한다. 새 에이전트에도 **설치** 계획을 만들거나 기존 설치 명령을 다시 실행한다.

작업·스킬·에이전트·배포 출처 갱신 선택을 바꾸면 기존 계획을 무효화한다.
요청 중 선택을 바꾼 경우 늦게 도착한 계획도 표시하지 않는다.
계획은 15분간 유효하고 원본 스냅샷·대상 파일·manifest가 바뀌면 재계획해야 한다.
다른 도구가 설치했거나 직접 수정한 파일을 덮어쓰지 않는다. 적용 실패 시 installer가 복구한다.
프로젝트 복사본은 기본 버전 고정이며, 업데이트하려면 **고정 해제**를 먼저 적용한다.
`joongi-skills.lock.json`은 버전·digest·고정을 기록하고, 기기별 관리 정보는 `.joongi/private/`에 둔다.
프로젝트의 자체 스킬을 공용으로 복사하거나 설치 출처의 스킬을 자동 수정하지 않는다.

업데이트의 **등록된 배포 출처 갱신**은 설치 때 기록한 다운로드 주소가 있을 때 사용한다.
클론 출처는 사용자가 `git pull --ff-only`로 갱신한 뒤 적용한다. 임의 URL이나 프로젝트 소스가
MCP 인자만으로 공용 배포 출처가 되지 않는다. 에이전트의 스킬 재탐지는 새 세션이 필요할 수 있다.

검증은 [검증 기록](../development/03-verification.md)을 본다.
공식 근거: [MCP 2025 인증](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization),
[MCP 2026 인증 보안](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations).

## 웹 화면의 새로고침과 읽기

같은 범위에서 새로고침하거나 메뉴를 옮겨도 작성 중인 인증·MCP·프로젝트 폼과 스킬 관리
선택을 유지한다. 비밀 값도 현재 탭의 DOM 메모리에만 남으며 localStorage·sessionStorage에
저장하지 않는다. 범위를 바꾸거나 탭을 닫으면 편집 값은 비운다. 프로젝트 전환 실패 시
오류 화면에서 **다시 연결**로 복구하며, 이전 범위의 목록을 현재 범위처럼 표시하지 않는다.

스킬 문서는 기본 Markdown 읽기 보기로 표시하고 **원문 보기**로 전환할 수 있다.
제목·표·목록·코드·HTTP(S) 링크와 스킬 내부 참조를 지원한다. HTML은 텍스트로 보여주고
실행하지 않는다. 전체 CommonMark·중첩 목록·이미지 렌더러를 제공한다는 의미는 아니다.
