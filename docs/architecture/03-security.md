# 신뢰 경계와 보안

문서 ID: ARCH-SECURITY · 요구사항: REQ-REGISTRY, REQ-CALL, REQ-INSTALL

## 로컬 접근

Hub는 loopback에 바인딩한다. 로컬 서비스라도 외부 웹페이지가 브라우저를 통해
설정 변경을 요청할 수 있으므로 Host·Origin 검증과 변경 요청 보호가 필요하다.
와일드카드 CORS를 추가해 설치 페이지에서 로컬 설정을 직접 조작하지 않는다.
관리 API의 조회·변경에는 관리 토큰, HTTP MCP에는 범위별 Bearer 토큰이 필요하다.
두 자격증명을 서로 대체할 수 없고 URL·헤더·메타데이터로 연결 범위를 바꿀 수 없다.
`joongi-hub open`은 관리 토큰을 URL fragment로 브라우저에 넘긴다. fragment는 HTTP 요청에
전송되지 않으며 UI가 즉시 주소에서 지우고 해당 탭의 sessionStorage에 보관한다.
이 로컬 관리 토큰과 에이전트 연결 설정의 HTTP 토큰도 비밀이므로 공유하지 않는다.
외부 서비스의 OAuth 토큰·환경 변수 값·비밀번호는 관리 API에서 반환하지 않는다.

## 등록과 실행

등록한 stdio 명령은 사용자 권한으로 실행되는 프로그램이다. 자동 발견을 위해
프로세스를 실행하는 시점도 실행 경계로 다룬다. 명령·인자는 배열로 전달하고 shell을 쓰지 않는다.
외부 MCP 서버가 반환한 지침은 untrusted content이며 사용자 권한이나 설치 승인을 대체하지 않는다.
stdio 자식에는 PATH·홈·임시 경로·OS 실행·locale 등 기본 허용 목록만 전달한다.
API key·proxy·인증 agent socket·인터프리터 주입 변수 등은 자동 상속하지 않는다.
추가 변수가 필요하면 서버별 env 매핑을 명시한다. 이는 파일·네트워크 접근 격리는 아니다.

HTTP upstream 주소는 로컬 MCP를 연결할 필요가 있어 일반 웹 fetch와 정책이 다르다.
사용자가 명시적으로 등록한 endpoint에 한정하고, cloud metadata·redirect·URL 자격증명 등은
코드 정책으로 제한한다. 외부 MCP에는 HTTPS를 요구하고 평문 HTTP는 검증한 모든 목적지가
loopback일 때만 허용한다. 요청·응답 크기·동시성·시간 예산을 제한한다.

## 파일과 상태

스킬 조회는 catalog 내 허용 파일만 열고 `..`, 절대 경로, symlink 이탈을 막는다.
등록 JSON 변경은 원자적 교체, tasks는 transaction을 사용한다.
사용자 에이전트 설정은 installer가 소유한 항목만 수정하고 충돌한 파일을 덮어쓰지 않는다.
제거 시 설치 이후 수정된 파일·다른 MCP 등록·다른 스킬을 보존한다.

## Apps

Apps metadata 전달은 HTML 안전성의 보증이 아니다. 로컬 렌더러는 `allow-scripts`만 있는
sandbox iframe을 사용하여 외부 HTML을 opaque origin으로 실행한다. 응답 CSP는 해당 resource가
선언한 origin으로 한정하고 object·base·form 권한은 열지 않는다.
view token은 만료 시간이 있으며 원래 MCP 서버와 도구에 묶인다. App callback의 도구·resource·prompt는
해당 서버 안에서만 전달하고 허용하지 않은 method는 거절한다. App에 로컬 관리 API token을 넘기지 않는다.
외부 에이전트에서의 렌더링은 그 Host의 sandbox·CSP 계약을 따른다.

## 배포

GitHub Pages는 공개 정적 파일만 제공한다. 개인 config·state·토큰은 산출물에서 제외한다.
터미널 다운로드에는 브라우저 CORS가 적용되지 않는다. 설치 스크립트를 검토한 다음 실행하며,
릴리스·commit 고정과 checksum 검증을 제공할 때 공급망의 변동 범위를 줄일 수 있다.

## Upstream 인증과 프로젝트

인증 비밀은 server 설정과 분리하며 서버 URL·auth fingerprint·프로젝트 상태에 결합한다.
OAuth callback만 외부 로그인 페이지에서 돌아오는 탐색을 허용하고 state·PKCE·issuer를 검사한다.
Windows는 사용자 DPAPI, WSL은 Windows DPAPI bridge, macOS는 로그인 Keychain,
Linux는 Secret Service를 쓴다. 파일에 평문으로 저장하는 fallback은 없다.
잠긴 저장소를 Hub가 반복해서 열도록 요구하지 않고 명시적인 복구 오류를 반환한다. 프로젝트 범위는 명시적
카탈로그·연결·상태 분리이며 로컬 사용자 간 권한 경계는 아니다. 에이전트의 자체 전역 스킬은
별도다. 상세 방식과 제한은 [인증·프로젝트·스킬 관리](../operations/05-auth-project-skills.md)를 본다.

## 호출 승인과 응답 유출 방어

OAuth·bearer·API key·basic·환경 변수나 header를 사용하는 연결은 기본적으로 도구 호출 승인을
요구한다. 도구의 readOnlyHint·설명·MRTR inputResponses는 사용자의 보안 승인을 대신하지 않는다.
관리 UI에서 서버·도구·인수를 검토한 한 번의 승인은 5분 안에 동일한 요청에 한 번만 사용한다.
서버 설정·도구 정의·인수·동기 MRTR continuation이 달라지면 새 승인이 필요하다.
명시적으로 허용한 도구는 계속 호출할 수 있고 차단 목록이 우선한다.
인증 없는 연결에 정책이 없으면 기존 동작대로 실행한다. 정책을 저장하면 그 연결에도 승인 규칙을 적용한다.
Task 시작 승인은 동일한 작업 안에서 검증한 input request에 답하고 계속 진행하는 것을 포함한다.

upstream의 정상 응답과 RPC 오류에 현재 알고 있는 비밀 값이 그대로·URL encoding·Base64로
반사되면 결과 전체를 일반 오류로 바꾼다. 6자 미만 비밀·임의 변형·분할 유출까지 막는 DLP는 아니다.
Hub 자체나 같은 OS 사용자 권한의 악성 프로세스는 실행 중 복호화한 토큰을 읽거나 사용할 수 있다.
OS 키링은 저장 시 보호이며 프로세스 샌드박스가 아니다. 최소 권한·신뢰한 코드·토큰 철회를 함께 사용한다.

## 정적 Markdown과 Mermaid

Markdown의 raw HTML 실행은 끈다. 공개 문서의 Mermaid는 격리한 빌드 브라우저에서만 실행하고
안전 검사한 SVG 이미지로 배포한다. 설정 재정의·상호작용·외부 리소스는 허용하지 않는다.
[문서 빌드와 안전 설정](../installation/02-github-pages.md#markdown-문서를-사이트에서-읽기)을 따른다.
