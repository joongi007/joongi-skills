# 검증 기록

문서 ID: DEV-EVIDENCE · 기준일: 2026-11-05

이 파일은 실제 실행 증거다. 아래는 수용 시나리오이며 실제 결과·환경·한계를 이어 기록한다.

| 시나리오 | 검증할 결과 |
|---|---|
| clone 실행 | 추가 패키지 없이 Hub help·UI·health 확인 |
| 스킬 검색·조회 | 현재 스킬 검색, 본문·참조 읽기, 탈출 경로 거절 |
| upstream 연결 | stdio/HTTP fixture 등록·probe·검색·호출·오류 표시 |
| 버전 교차 | 2025/2026 client × 2025/2026 server |
| Apps 전달 | UI metadata와 ui resource 조회, 렌더러 요구 표시 |
| Tasks | 생성·진행·결과·취소·오류·재시작과 버전별 한계 |
| agent 설치 | 임시 HOME 감지·명시 agent·dry run·MCP 등록 |
| update | 새 agent 발견, 사용자 설정과 수정 스킬 보존 |
| uninstall | 관리한 등록만 제거, 사용자 파일 보존 |
| Pages 산출물 | 정적 파일 생성·상대 경로·install bootstrap |
| 보안 | Host/Origin·인증 정책·입력 상한·경로·명령 경계 |
| 문서 정합성 | local links·routing·CLI·지원 표와 테스트 연결 |

## 실제 실행 결과

- 2026-11-05: `./build.sh --check` 통과, 2개 스킬·참조 routing 경고 없음.
- 2026-11-05: `python3 scripts/check_docs.py` 통과, 로컬 링크·routing·REQ 참조 검사.
- 2026-11-05: `python3 -m unittest discover -s tests -p test_docs.py -v` 5개 통과.
  깨진 링크·저장소 탈출·중복 ID·미정의 요구사항·누락 routing을 검사한다.

- 2026-11-05: Linux/WSL, Python 3.10.12에서 전체 `python3 -m unittest discover -s tests -v`
  **65개 통과**. HTTP 검사는 loopback socket이 허용된 실행 환경에서 수행했다.
  2025-06-18/2025-11-25/2026-07-28 client × upstream 9조합, 실제 stdio subprocess와 HTTP,
  Skills manifest·원격 스킬 hash 확인, Apps resource·alias 충돌, Tasks·취소·PID 복구·stdio bridge,
  임시 홈 설치·새 agent 감지·설정 보존·롤백·제거, Pages 번들 생성을 포함한다.
- 2026-11-05: 마지막 잘못된 stdio 요청 처리·Windows liveness API 서명 보완 후 관련 회귀 테스트
  2개 재실행 통과. 실제 Windows의 API 실행을 검증한 것은 아니다.
- 2026-11-05: 전송 보안 8개 테스트 통과. 검증한 IP 직접 연결, IPv4-mapped metadata 차단,
  DNS/JSON/SSE deadline, redirect 거부, 응답 크기 제한, 막힌 subprocess stdin을 확인했다.
  TLS는 원래 hostname 유지 단위 검증이며 실제 외부 TLS 서버와의 접속 시험은 아니다.
- 2026-11-05: `python3 scripts/mutation_check.py`에서 선택한 보안 변이 **5/5 탐지**.
  owner 검사·취소 terminal 상태·경로 제한·metadata 주소 차단·Host 검사 제거를 기존 테스트가 탐지했다.
  임시 소스 복사본에서 수행하며, 범용 mutation engine이나 전체 코드 mutation coverage는 아니다.
- 2026-11-05: Ruff 0.16.6으로 `ruff check joongi_hub scripts tests`와
  `ruff format --check joongi_hub scripts tests` 통과.
- 2026-11-05: Node 22.13.0, Playwright 1.50.1, Chromium으로 `tests/browser_smoke.cjs` 통과.
  로컬·원격 스킬 읽기, MCP 등록·probe·echo 호출·백그라운드 작업·제거, 지원 범위,
  390px 모바일 가로 넘침 없음, 브라우저 JS·콘솔 오류 없음을 확인했다.
- 2026-11-05: Hub·Pages 데스크톱/모바일 스크린샷 직접 확인.
  Pages OS 탭·상대 경로 기반 다운로드 명령도 로컬 브라우저에서 확인했다.
- 2026-11-05: `bash build.sh`로 2개 `.skill` 번들 생성.
  `scripts/build_pages.py`로 `dist/pages-preview/`에 정적 페이지·설치 스크립트·소스 archive·SHA256 생성.
  이 미리보기의 download base는 예시 주소이며 실제 배포 시 Actions가 저장소 Pages 주소를 넣는다.

## 후속 구현과 실제 검증

앞의 65개·seed 변이 5개·Playwright 1.50.1 결과는 초기 구현의 이력이다. 아래가 후속 검증이다.

- 공식 TypeScript SDK 1.32.2의 2025 stdio·HTTP, Client 2.4.0의 2026 stdio·HTTP **네 조합 통과**.
  `npm run test:sdk`로 원본 SDK/schema의 검증을 우회하지 않고 실행했다. 도구·검색·resources·prompts와
  upstream 호출, 공식 SkillsClient의 YAML·binary·digest·디렉터리·원격 스킬을 확인했다.
  이 과정에서 누락된 caching 필드와 native Skills 경로 구조를 실제로 발견·수정했다.
- 공식 AppBridge/App SDK 2.0.4를 사용한 실제 브라우저에서 App 초기화, 원래 도구명의 callback,
  원래 리소스 URI 조회, 중첩 iframe relay, parent DOM 격리, Tasks 입력 제출·재개를 통과했다.
  View는 원본 HTML을 유지하고, 응답 CSP와 source-window 검증으로 원래 서버에 연결한다.
- Playwright 개발 의존성의 알려진 인증서 검증 취약점을 확인해 **1.64.1로 갱신**했다.
  해당 버전과 Chromium headless shell 156.0.8078.4에서 최종 브라우저 수용 테스트를 통과했다.
  `npm audit`은 **취약점 0건**을 보고했다.
- Windows PowerShell 5.1·Python 3.13에서 실제 clone bootstrap의 dry-run·설치·런처 실행·업데이트·
  신규 agent 탐지·제거를 통과했다. 별도 HTTPS test endpoint에서 다운로드·해시·압축 해제·설치·제거도
  실제 실행했다. 신뢰 인증서는 해당 test child에만 주입했으며 전역 인증서·실행 정책은 바꾸지 않았다.
- 6개 agent 모두 자동 MCP 등록·제거를 지원한다. Linux installer 29개 테스트와 Windows 29개 중
  27개 통과·POSIX 전용 2개 제외를 확인했다. OpenCode JSONC 주석·trailing comma·기존 값 보존 포함.
- 실제 **Codex CLI 0.166.0**이 설치된 설정·런처·인자를 인식했고,
  **Claude Code 2.1.233**은 실제 MCP 연결 `Connected`를 보고했다.
  `tests/agent_cli_smoke.py`는 임시 HOME과 state만 사용하며 인증·모델 API를 호출하지 않는다.
- 실제 GitNexus 1.6.12를 Node 22.18.0으로 실행해 프로젝트 100개 파일을 인덱싱하고 Hub에서 도구
  17개 발견·조회·호출 관계 확인을 통과했다. 당시 스냅샷의 1,286 nodes·2,377 edges·33 clusters·
  70 flows는 [증거 파일](../../examples/code-graph/verification.json)에 있다.
  PolyForm Noncommercial 라이선스 때문에 기본 설치에는 포함하지 않는다.
- 기본 제공 Python AST code graph MCP는 7개 분석 도구·SHA-256 freshness·재색인을 제공하고,
  실제 프로젝트·stdio Hub 연결과 코드 실행 금지·심볼·영향 분석 등 12개 테스트를 통과했다.
- 문서 검사는 실제 CLI·HTTP/RPC 분기·capability·버전·agent 경로와 문서 주장을 대조한다.
  11개 요구사항에서 실제 설계 문서와 수용 테스트로의 연결을 검사한다. 자연어 전체의 정합성을
  자동 증명하는 도구로 취급하지 않는다.
- 일반 AST mutation engine으로 storage의 비교·논리·분기·상수·부정 연산을 자동 변이했다.
  **48개 중 46개 탐지, 2개 동등 변이, invalid·timeout 0개**.
  SQLite 핸들 누수를 수정한 source hash로 [보고서](mutation-report.json)를 다시 생성했다.
- 실제 Windows 전체 테스트가 SQLite context manager의 연결 미종료를 발견했다.
  성공 commit·예외 rollback 후 항상 close하도록 수정했고, Windows Python 3.10/3.13의
  storage 회귀 테스트 8개와 파일 unlink를 통과했다.
- 최종 Linux Python 3.14.0 전체 **116개 통과**, Windows Python 3.13 전체 **116개 중 플랫폼 전용 4개 제외**를
  확인했다. MRTR 재요청·URI round-trip·manifest가 보호하는 HTML 원본 바이트 유지도 포함한다.
- 최종 검토 Hub에는 내장 `code-graph`와 명확히 이름 붙인 `검토용 Apps·Tasks 예제`를 연결했다.
  각 7개 도구가 실제 probe로 발견됐으며 개인 agent 설정이 아닌 `/tmp/joongi-hub-review` 상태만 사용한다.

## 외부 조건과 지원 경계

2026-11-07 디자인·탐색 개선:

- GTMUX의 공통 UX 원칙을 디자인 스킬 참조로 추가하고, 긴 토큰 계약을 별도 참조로 옮겼다.
  진입 `SKILL.md`는 39줄이며 프로젝트 전용 CLI·컴포넌트는 도입하지 않았다.
- 스킬의 짧은 표시 이름·요약, 접힌 frontmatter, MCP 설정·도구 목록 펼침,
  도구 검색과 세션 내 펼침 상태 보존을 브라우저로 확인했다.
- 로컬 skill URI를 원격으로 잘못 구분하던 화면 로직과 참조 선택 시 SKILL.md만
  다시 읽던 문제를 수정하고 실제 참조 문서 선택을 브라우저 검증에 추가했다.
- 키보드 펼침·기존 Apps/Tasks 동작·모바일 가로 넘침·콘솔 오류 검사를 통과했다.
  실제 검토 Hub의 데스크톱 스킬·MCP와 모바일 MCP 화면도 캡처해 확인했다.
- 문서·Pages 테스트 7개와 문서 계약·스킬 구조·번들 검증을 통과했다.
  영어/한국어 스킬의 모델 성능 A/B 실험은 수행하지 않았다.

2026-11-06 추가 검증:

- Linux Python 3.14.0 전체 132개 테스트 통과. native 도구 schema·버전별 Task 실행 조건,
  App view별 Task 생성·조회·결과·취소와 소유권, 이전 App metadata, graph bootstrap을 포함한다.
  upstream Task capability 검사도 관련 회귀 테스트와 함께 확인했다.
- 공식 SDK 2025/2026 × stdio/HTTP 네 조합 재검증 통과.
- 실제 브라우저에서 App 내부 Task 생성→조회→결과, 기존 App callback·opaque iframe 격리 통과.
- Code Review Graph 2.3.9를 선택 통합했다. 분석 도구 7개 발견·통계·파일 요약 호출을 확인했고
  [증거](../../examples/code-graph/review-graph-verification.json)를 남겼다. 내부 Apps 리소스나
  native Tasks를 제공하는 서버라고 취급하지 않는다.
- 남은 확장 범위: App 내부 2026 Task 입력 재개, 목록 변경 푸시, 10분 view 만료를 넘는 작업 제어.

GitHub 원격 저장소·CLI 인증·token이 제공되지 않아 **GitHub 업로드·Pages 공개 배포는 미실행**이다.
게시할 저장소 주소를 사용자에게 요청한 상태이며, workflow와 검증된 배포 산출물은 준비돼 있다.
연결 가능한 GitHub 통합을 확인해 연결을 요청했으며 아직 연결 확인을 받지 않았다.
Cursor/Gemini/Copilot/OpenCode의 GUI 전체 실사용과 외부 OAuth 계정 연결은 자동 설정·fixture 검증과
구분한다. 전체 MCP 규격 적합성 인증을 주장하지 않으며 정확한 기능 범위는 호환성 문서를 따른다.

## 2026-11-07: upstream 인증·프로젝트·스킬 관리

- Linux Python 3.10: 전체 **163개**, 플랫폼 조건 2개 제외·실패 없음.
  Python 3.14.0: 전체 **163개**, Windows DPAPI 1개 제외·실패 없음.
- 새 기능 31개 테스트는 독립 OAuth HTTP provider, 임시 프로젝트와 HOME을 사용했다.
  Windows Python 3.13에서도 **31개 중 30개 통과·symlink 권한 조건 1개 제외**를 확인했다.
  DPAPI의 실제 암호화 파일과 새 manager의 복호화·헤더 생성도 포함한다.
- 인증: 실제 HTTP authorization callback·PKCE S256, WWW-Authenticate·PRM·OAuth/OIDC discovery,
  DCR, CIMD 문서 ID·redirect 검증, client_secret_basic/post, Client Credentials,
  Device Code polling, 토큰 만료·refresh rotation·401 한 번 재시도·철회를 확인했다.
  CIMD의 HTTPS 문서 응답만 fixture로 주입하고 실제 token 교환은 독립 HTTP provider로 수행했다.
- 프로젝트: 공용 선택·프로젝트 override·비선택 URI 거부·경로 이탈·자격증명 경로 분리,
  실제 stdio 독립 실행과 HTTP 공유 연결에서 profile 고정·초기화 유지·범위 변경 거부를 확인했다.
- 스킬: 사용자·프로젝트 설치, 기본 pin·unpin·업데이트·제거, 배포 목록에서 사라진 관리 스킬 제거,
  수정·다른 소유 파일 보호, 계획 스냅샷·재사용 거부, installer 실패 복구와 lockfile 보호를 확인했다.
- Chromium/Playwright: 기존 Apps·Tasks 수용 흐름과 새 OAuth popup/callback·연결,
  사용자 설치·프로젝트 등록·선택·선택하지 않은 MCP 제외·고정 설치를 실제로 수행했다.
  펼친 인증·설치 계획과 390px 화면의 가로 넘침도 검사한다.
- 공식 SDK 1.32.2/Client 2.4.0의 2025/2026 × stdio/HTTP 네 조합이 다시 통과했다.
  wheel을 별도 venv에 설치하고 저장소 경로 없이 Hub와 설치 엔진의 import를 확인했다.
- Ruff check·format, 문서 링크·실행 계약, 스킬 bundle·AGENTS·Pages 소스 bundle 생성을 확인했다.
  검증 중 실제 개인 에이전트 설정이나 다른 프로젝트를 설치 대상으로 사용하지 않았다.
- 상용 제공자의 실제 계정·MFA·회사별 SSO 전체, private_key_jwt·mTLS·DPoP는 검증·지원 범위가 아니다.
  POSIX 자격증명 파일은 암호화 저장소가 아니며 owner-only 권한으로 보호한다.
  상세 사용법은 [인증·프로젝트·스킬 관리](../operations/05-auth-project-skills.md)를 본다.

## 웹 UI/UX 점검 후 회귀 검증

`tests/browser_ux.cjs`는 독립된 임시 Hub·HOME·프로젝트에서 다음을 실제 Chromium으로 확인한다.

- 설치 계획 생성 후 선택·작업 변경 시 적용 불가, 요청 중 선택 변경 시 늦은 계획 응답 무시.
- 프로젝트 전환 실패 뒤 메뉴를 이동해도 이전 카탈로그를 표시하지 않음, 재시도 복구.
- 초기 프로젝트 조회 실패 시 로딩 표시를 종료하고 키보드로 재시도 가능.
- 인증·새 MCP·프로젝트 폼과 설치 선택의 새로고침·탐색 간 보존, 비밀 값의 브라우저 저장소 미사용.
- 선택한 인증 방식과 행동 일치, 설정 저장 전 비밀 저장 차단·저장 후 허용.
- Markdown 읽기·원문 전환, 표·참조 링크, HTML/script·javascript 링크 실행 차단.
- 기존 연결이 있는 작업 공간의 소개 패널 생략, 390px 넘침 없음·주요 버튼 높이 44px 이상.

기존 `browser_smoke.cjs`와 `browser_management.cjs`의 Apps·Tasks·OAuth·설치 흐름도 함께 검증한다.

## 2026-11-08: 명시적 연결 방식과 실행 관리

- Python 3.10: 전체 **185개**, 플랫폼 조건 2개 제외·실패 없음.
  Python 3.14.0: 전체 **185개**, Windows DPAPI 1개 제외·실패 없음.
- `tests/test_connections.py`는 순수 stdio의 HTTP 탐색 금지, 혼합 모드의 저장소 확인·대체 실행,
  HTTP 전용 실패, 연결 뒤 오류 시 자체 실행으로 전환하지 않음, 설정 상속·재정의·절대 경로,
  2025 session·2026 요청의 프로젝트 URL 고정과 충돌 거절을 확인했다.
- 여섯 에이전트의 native stdio/HTTP 등록을 공용·프로젝트 범위에서 확인했다.
  소유권·설정 수정·계획 재사용·설정 변경 후 적용 거절, 기존 설정 유지도 검증했다.
- 실제 daemon 시작·중복 시작 방지·상태·재시작·종료와 기록 유지, CLI 설치의 HTTP 등록을 확인했다.
  다운로드 임시 소스를 삭제한 뒤에도 설치된 런타임의 웹 UI가 유지되고, WSL/POSIX의 stdio
  SIGTERM 종료가 Hub가 실행한 MCP 프로세스를 정리하는 것도 확인했다.
  OS 잠금은 독립 프로세스의 동시 자격증명 업데이트와 프로세스 종료 후 해제를 확인했다.
- Windows Python 3.13에서 새 연결·잠금·실제 DPAPI 테스트 **23개 중 21개 통과**,
  Linux에서 생성하는 WSL 설정과 POSIX SIGTERM 테스트 2개 제외. Windows daemon 수명주기도 포함한다.
- **Codex CLI 0.167.0**이 stdio·혼합·native HTTP 등록을 인식했고,
  **Claude Code 2.1.233**은 세 방식 모두 실제 MCP 연결 `Connected`를 보고했다.
  임시 HOME·state만 사용하며 로그인·모델 API를 호출하지 않았다.
- Windows Python에서 생성된 `wsl.exe -d Ubuntu-22.04 --exec …` 인자를 그대로 실행해
  Linux Hub의 초기화·스킬 3개 조회를 실제로 통과했다. Windows용 에이전트 제품 UI 자체를
  모두 실행했다는 의미는 아니다.
- 브라우저 수용 테스트 네 개가 통과했다. 새 설정 화면의 mode·fallback 저장,
  공용/프로젝트 에이전트 계획·적용, native 형식 표시, WSL 생성, 390px 화면을 포함한다.
  기존 OAuth·스킬 설치·Apps·Tasks·입력 보존 회귀 흐름도 유지됐다.
- 공식 SDK 1.32.2/Client 2.4.0의 2025/2026 × stdio/HTTP 네 조합이 다시 통과했다.
- wheel을 별도 Python 3.14 venv에 설치하고 새 stdio 모드 CLI 실행을 확인했다.
- Docker·Compose·k3s 배포, 실행 중 자동 전환·재시도, 자동 유휴 종료는 이번 구현 범위가 아니다.
  [연결 방식과 실행 안내](../operations/06-connection-modes.md)에 현재 동작을 정리했다.

## 사용자가 확인할 항목

로컬 UI의 정보 밀도·검색 흐름·등록 오류 안내, 설치 대상 agent 선택,
스킬 기본값, 문서 구조와 인프라 지침의 강도를 검토한다.
취향에 대한 피드백과 protocol correctness 수정은 별도 변경으로 추적한다.


## 2026-11-10: 영구 등록 저장소와 복구

- Python 3.10: 전체 **194개**, 플랫폼 전용 2개 skip, 실패 없음.
- Windows Python 3.13: 저장소·설치 관련 **46개**, 플랫폼 전용 2개 skip, 실패 없음.
- 브라우저 smoke·관리·UX·연결 설정 4개 시나리오 통과. 임시 저장소 경고와 빈 목록 경로 안내 포함.
- 공식 SDK: 2025/2026 × stdio/HTTP 4조합 통과.
- WSL·Windows 실제 공용 설치본 업데이트 후 stdio 초기화·도구 목록·`hub_status`의 영구 경로와
  등록 수·Code Review Graph 실제 연결과 통계 호출 통과. 기존 프로젝트 MCP 설정은 변경하지 않음.
- Code Review Graph 2.3.9를 WSL 영구 도구 환경에 복구하고 기존 프로젝트 색인을 갱신함.
  Windows에서는 검증한 WSL stdio 실행 경로로 동일 도구에 연결함. 테스트 fixture MCP는 공용 등록하지 않음.
- 웹은 선택 사항으로 유지하며 검증용 임시 웹 프로세스는 테스트 종료 때 정리함.
- 임시 경로의 기존 servers.json은 소실돼 파일에서 자동 이관할 수 없었음. 검증 기록이 있는 실제
  그래프 MCP를 재검증해 등록했으며 알 수 없는 과거 연결을 추정해 추가하지 않음.

운영·제한은 [저장소 일관성과 복구](../operations/07-state-consistency.md), 결정은
[ADR-0008](../adr/0008-persistent-state-identity.md)에 기록한다.


## 2026-11-10: 공용 그래프의 프로젝트 선택

- 기존 공용 연결의 고정 DB에 다른 저장소 경로를 전달하면 출처 불일치로 거절됨을 실제로 재현함.
- 프로젝트 선택 어댑터와 회귀 테스트 추가 후 전체 Python **201개**, 2개 skip, 실패 없음.
  Windows의 어댑터·설정 관련 **9개**, 플랫폼 전용 2개 skip, 실패 없음.
- 실제 Code Review Graph 2.3.9로 별도 Python·TypeScript 저장소를 각각 색인하고 A→B→A 통계
  조회 통과. 프로젝트별 파일 1개씩 확인하고 서로 다른 DB에 저장함.
- WSL·Windows 공용 등록을 백업 후 어댑터로 교체. 실제 설치본에서 9개 도구 발견과 필수
  repo_root 확인. Windows 드라이브 경로→WSL 변환을 포함한 실제 그래프 통계 조회 통과.
- 이전 `.local/code-review-graph/data/graph.db`의 SHA-256 보존을 확인함.
- wheel에 어댑터 모듈과 2.3.9 입력 스키마 JSON이 포함됨을 확인함.
- 기존 에이전트의 MCP 연결을 다시 열어 새 도구 목록과 필수 경로 입력을 반영해야 함.

설계: [ADR-0009](../adr/0009-project-selecting-graph.md),
운영: [Code Review Graph](../operations/04-code-review-graph.md).

## 2026-11-11: 메타데이터 검색 개선

- 전체 Python 211개 테스트, 플랫폼 전용 2개 skip, 실패 없음.
- Windows Python 3.13에서 검색·그래프 관련 19개 테스트, 3개 skip, 실패 없음.
  Windows에 rg가 없어 실제 정규식 엔진 테스트 1개는 skip했고, 누락 시 오류 동작은 검증함.
- Ruff check·format 통과. CLI·문서·런타임 계약 검사 통과.
- 공식 MCP SDK의 2025/2026 × stdio/HTTP 4개 조합 통과.
  첫 sandbox 실행의 HTTP 포트 바인딩 제한은 권한을 적용한 재실행에서 해소됨.
- WSL·Windows 공용 설치본을 업데이트하고 실제 stdio로 Code Review Graph에 연결함.
  `repo_root` 인자 검색, 상위 5개 요약, 정확한 이름의 전체 schema 조회,
  스킬 검색과 검색 도구의 새 schema·readOnlyHint를 양쪽 설치본에서 확인함.
- 웹 관리 서버는 실행하지 않았으며 기존 stdio 연결 방식을 유지함.

검색 smoke 평가의 범위와 수치는 [검색 평가](../../refs/research/2026-11-11-catalog-search.md),
사용법은 [카탈로그 검색](../operations/08-catalog-search.md)에 기록함.

### 한영 키워드 보강

- 코드 그래프 도구 9개의 영어 설명에 짧은 한국어 검색어를 추가하고, 검색 안내에
  필요한 경우 한국어 요청을 영어 키워드로 바꾸도록 명시함. 자동 번역 서비스는 추가하지 않음.
- WSL 검색·그래프 테스트 20개 통과. Windows 검색 테스트 11개 중 rg 전용 1개 skip, 실패 없음.
- WSL·Windows 설치본에서 `변경 영향`, `호출 관계`, `긴 함수` 검색이 의도한 도구를
  첫 번째로 반환함을 실제 stdio로 확인. 같은 연결에서 실제 그래프 통계 조회도 통과함.
- 양쪽 `joongi-hub status`가 `mode: stdio`, `running: false`, `url: null`임을 확인함.
  이는 관리 웹이 꺼져 있다는 뜻이며 stdio 사용에 웹 실행이 필요하지 않음.

## 2026-11-11: GitHub 공개 전 점검

- `.local`에 더해 AWS·에이전트 로컬 설정, 환경·키 파일과 `_site`를 Git 제외 규칙에 추가함.
  설치 번들과 정적 사이트도 개인 설정·환경·키 파일을 제외하고 tar의 계정·그룹·수정 시각을 제거함.
  별도 임시 소스에 민감 파일을 주입한 회귀 테스트에서 비공개 파일 제외와 헤더 초기화를 확인함.
- 전체 Python **213개**, 플랫폼 전용 2개 skip, 실패 없음. 전체 Ruff check·format,
  문서·실행 계약·스킬 3개 검증 통과.
- 공식 SDK의 2025/2026 × stdio/HTTP 4개 조합과 브라우저 4개 수용 시나리오 통과.
- 실제 Windows PowerShell의 격리한 홈에서 설치·업데이트·새 에이전트 탐지·MCP 등록·제거 통과.
- Gitleaks 8.30.1의 공식 바이너리 체크섬을 확인하고 Git 제외 규칙을 적용한 공개 후보 소스를 검사함.
  최종 공개 후보 소스 214개·설치 번들 213개에서 탐지 0건. 별도 임시 폴더의 가짜 GitHub 토큰은
  실제로 탐지하는 양성 대조도 통과함. 소스와 배포 번들 검사 기록은 로컬
  `/tmp/joongi-publication-audit/`에 보관함. 탐지 0건은 모든 개인정보 부재의 증명은 아님.
- 공식 actionlint 1.7.12의 체크섬 확인 후 두 workflow의 문법·의존성 검사 통과.
  공식 Actions를 commit SHA로 고정하고 Pages가 전체 Check 결과를 기다리도록 연결함.
- Windows에서도 새 공개 파일 제외 테스트와 기존 Pages 빌드·설치 테스트 통과.
- 현재 기본 storage 뮤테이션 캠페인은 **70개 중 54개 탐지, 16개 미탐**, invalid·timeout 0개.
  이전 48개 대상 이후 Registry 복구·검증 분기가 늘었으나 기본 캠페인의 테스트 범위는
  `tests.test_storage_contracts`다. 이번 16개를 모두 동등 변이로 분류하지 않았으며 추가 검토·테스트가 필요함.
  기본 CI는 미탐을 보고하고 invalid·timeout·baseline 실패를 차단한다.
- 현재 작업 폴더의 `.git`은 유효한 저장소가 아니어서 과거 이력·커밋 작성자 정보는 점검할 수 없었음.
  GitHub Actions·Pages 실제 원격 실행은 아직 수행하지 않았고 루트 LICENSE는 선택하지 않음.

업로드 순서와 남은 선택은 [공개 전 점검](../installation/03-publication.md)을 따른다.

### MIT 라이선스 선택 반영

- 이후 사용자 요청으로 루트 MIT LICENSE를 추가하고 저작권 표기에 공개 계정명 joongi007을 사용함.
- README·공개 안내·Python 패키지 메타데이터를 함께 갱신하고 서드파티 라이선스는 유지함.
- 문서 검사와 Pages 번들·Python wheel 빌드 통과. 두 배포 파일에서 루트 LICENSE 포함을 확인함.
- GitHub 저장소 연결·업로드·원격 Actions와 Pages 배포는 아직 실행하지 않음.

### GitHub 첫 연결과 Windows CI 보완

- 사용자 요청으로 비공개 `joongi007/joongi-skills`의 main에 첫 커밋을 push함.
  커밋 작성자는 공개 계정명과 GitHub noreply 이메일을 사용함. 생성한 실제 Git 이력도
  Gitleaks 검사에서 탐지 0건이며 개인 설정·인증·DB는 추적하지 않음.
- Pages는 설정 전 자동 배포하지 않음. 설정 후 수동 실행하거나 `ENABLE_PAGES=true`로 켠다.
- 첫 원격 CI에서 publication·Windows 설치·브라우저·Linux Python 3.10은 통과했으나,
  영문 Windows Python 3.14에서 인코딩·짧은 경로 표기·작업 로그 정리 문제가 드러남.
- 설치 CLI 출력을 UTF-8로 고정하고 stdio 테스트도 UTF-8로 읽도록 수정함.
  테스트의 임시 경로를 정규화하고, 그래프는 worker 종료·로그 핸들 해제 후 ready로 보고함.
- 레거시 cp1252 출력 환경과 worker 종료 전 상태를 회귀 테스트로 재현해 수정 전 실패·수정 후 통과 확인.
  Windows 관련 테스트 68개 통과, 플랫폼 전용 5개 skip. 전체 환경의 최종 결과는 원격 Actions를 확인한다.
- CI matrix의 fail-fast를 해제해 한 환경이 실패해도 다른 환경의 검증 결과를 남긴다.
