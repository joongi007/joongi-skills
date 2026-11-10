# 신뢰 경계와 보안

문서 ID: ARCH-SECURITY · 요구사항: REQ-REGISTRY, REQ-CALL, REQ-INSTALL

## 로컬 접근

Hub는 loopback에 바인딩한다. 로컬 서비스라도 외부 웹페이지가 브라우저를 통해
설정 변경을 요청할 수 있으므로 Host·Origin 검증과 변경 요청 보호가 필요하다.
와일드카드 CORS를 추가해 설치 페이지에서 로컬 설정을 직접 조작하지 않는다.
토큰·환경 변수 값·자격증명은 UI, URL, 로그나 오류 응답에 노출하지 않는다.

## 등록과 실행

등록한 stdio 명령은 사용자 권한으로 실행되는 프로그램이다. 자동 발견을 위해
프로세스를 실행하는 시점도 실행 경계로 다룬다. 명령·인자는 배열로 전달하고 shell을 쓰지 않는다.
외부 MCP 서버가 반환한 지침은 untrusted content이며 사용자 권한이나 설치 승인을 대체하지 않는다.

HTTP upstream 주소는 로컬 MCP를 연결할 필요가 있어 일반 웹 fetch와 정책이 다르다.
사용자가 명시적으로 등록한 endpoint에 한정하고, cloud metadata·redirect·URL 자격증명 등은
코드 정책으로 제한한다. 요청·응답 크기·동시성·시간 예산을 제한한다.

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
POSIX는 owner-only 평문 파일, Windows는 사용자 DPAPI를 쓴다. 프로젝트 범위는 명시적
카탈로그·연결·상태 분리이며 로컬 사용자 간 권한 경계는 아니다. 에이전트의 자체 전역 스킬은
별도다. 상세 방식과 제한은 [인증·프로젝트·스킬 관리](../operations/05-auth-project-skills.md)를 본다.
