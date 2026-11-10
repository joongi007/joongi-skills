# 연결 방식과 웹 UI 실행

문서 ID: OPS-CONNECTION-MODES · 요구사항: REQ-REGISTRY, REQ-PROTOCOL, REQ-INSTALL, REQ-UI

기본값은 순수 stdio다. 에이전트가 MCP 연결 시 Hub를 실행하므로 사용자가 먼저 서버를 켤 필요는 없다.
웹 UI는 연결·인증·스킬을 관리할 때 선택적으로 실행한다. 현재 Docker·Compose·k3s 배포는 제공하지 않는다.

## 세 가지 방식

| 설정 | 에이전트 연결 | HTTP Hub가 없을 때 |
|---|---|---|
| stdio | 자체 Hub 프로세스. HTTP 탐색도 하지 않음 | 정상 실행 |
| stdio + HTTP (`hybrid`) | stdio 접점을 통해 같은 저장소의 HTTP Hub 공유 | 기본은 stdio 자체 실행, 오류로 중단하도록 선택 가능 |
| HTTP (`http`) | 에이전트의 native Streamable HTTP 연결 | 오류. HTTP Hub를 별도로 시작해야 함 |

혼합 모드의 결정은 연결 시작 시 한 번만 한다. 초기 health 검사로 같은 상태 저장소·실행 인스턴스를
확인한다. 연결된 HTTP Hub가 나중에 종료돼도 요청을 stdio에서 다시 실행하지 않는다.
이미 실행 중인 stdio가 나중에 켠 HTTP Hub로 옮겨가지도 않는다. MCP 연결 또는 에이전트 세션을 다시 연다.
에이전트가 연결을 유지하는 동안 stdio 프로세스도 대기한다. 정상 EOF와 WSL/POSIX의 SIGTERM은
Hub가 실행한 MCP 프로세스도 정리한다. Windows의 강제 TerminateProcess나 전원 종료는
정상 종료와 같지 않으므로 에이전트의 정상 연결 종료 또는 stop을 사용한다. 사용하지 않는 upstream의 자동 유휴 종료는
현재 구현하지 않았다. 여러 에이전트에서 MCP 프로세스를 공유하려면 혼합 또는 HTTP 모드를 사용한다.

## 설정하기

웹의 **연결 설정**에서 방식을 저장한다. 공용 설정은 기본값이고, 프로젝트 범위는 이를 상속하거나
별도 방식으로 바꿀 수 있다. 방식 변경은 연결 설정만 바꾸며 스킬·인증·Tasks 저장소를 이동하지 않는다.
독립 stdio 프로세스들의 자격증명 갱신은 재진입 가능한 OS 파일 잠금으로 직렬화한다.

CLI에서도 같은 설정을 쓴다. `joongi-hub state` 또는 MCP의 `hub_status`에서 현재
저장 경로·등록 수·백업 위치를 확인한다. [저장소 일관성과 복구](07-state-consistency.md)를 참고한다.

```bash
joongi-hub configure --mode stdio
joongi-hub configure --mode hybrid --fallback stdio
joongi-hub configure --profile my-project --mode http --url http://127.0.0.1:8765
```

`--state-dir`을 지정했다면 모든 명령과 에이전트 연결에서 동일하게 지정한다. 연결 설정 파일은
공용 `connection.json`, 프로젝트는 해당 프로젝트의 Hub 상태 폴더 아래 `connection.json`이다.
웹의 **공용 기본 설정 따르기**는 프로젝트 재정의를 제거한다.

일회성 실행에서는 저장값보다 CLI 인자가 우선한다.

```bash
joongi-hub stdio --mode stdio
joongi-hub stdio --mode hybrid --fallback error
joongi-hub stdio --mode http --url http://127.0.0.1:8765
```

마지막 명령은 stdio 접점을 통한 HTTP 전용 bridge다. native HTTP 연결을 지원하는 에이전트에는
아래의 HTTP URL을 직접 등록하는 것을 우선한다. Hub 주소는 loopback HTTP만 허용하며,
localhost 입력은 127.0.0.1로 정규화한다. HTTP 전용 bridge는 지정한 URL을 그대로 우선하며
혼합 모드만 같은 저장소의 실행 중인 endpoint를 우선 탐색한다.
현재 원격 서버·다중 사용자 인증·TLS 역방향 프록시 배포를 제공하는 기능은 아니다.

## 에이전트에 반영하기

설정 저장 후 **내 에이전트에 등록** 또는 **이 프로젝트에 등록**에서 에이전트를 고른다.
**에이전트 등록 계획 보기 → 에이전트 등록 적용** 순서로 대상 파일을 검토한다.
다른 설정과 스킬은 유지하고, 다른 도구 소유이거나 직접 수정한 `joongi-hub` 항목은 덮어쓰지 않는다.
계획의 설정·manifest·대상 파일이 바뀌거나 15분이 지나면 다시 계획해야 한다.
현재 에이전트의 MCP 연결·세션은 다시 열어야 한다. 신뢰할 프로젝트의 설정을 로드하는 절차는
각 에이전트의 기능이며 Hub가 대신 승인하지 않는다.

공용 등록은 기존 installer manifest를 재사용하고, 프로젝트 등록은 `.joongi/private/mcp-installation.json`에
소유권을 기록한다. 프로젝트 연결 파일 경로는 다음과 같다.

| 에이전트 | 프로젝트 설정 파일 |
|---|---|
| Claude Code | `.mcp.json` |
| Codex | `.codex/config.toml` |
| Cursor | `.cursor/mcp.json` |
| Copilot CLI | `.github/mcp.json` |
| Gemini CLI | `.gemini/settings.json` |
| OpenCode | `opencode.json` 또는 기존 `opencode.jsonc` |

공용 MCP URL은 `/mcp`, 프로젝트 URL은 `/mcp/projects/프로젝트ID`다. URL로 고정된 프로젝트와
header·metadata·legacy session의 범위가 다르면 요청을 거절한다.
프로젝트 연결이 공용 연결을 대체하는 우선순위는 에이전트마다 확인해야 한다. 에이전트가 직접 읽는
전역 스킬이나 다른 이름의 MCP를 Hub가 숨기지는 않는다.

**수동 연결 설정**에는 선택한 에이전트 형식의 서버 항목을 표시한다.
Windows 에이전트에서 WSL을 사용한다면 WSL 안에서 **Windows용 WSL 연결 생성**을 사용한다.
배포판 이름과 현재 Linux Python·소스·상태 경로를 `wsl.exe -d 배포판 --exec …`의 인자 배열로 만든다.
이 결과는 Windows 쪽 설정에 복사한다. 현재 환경의 자동 등록 버튼이 Windows 설정을 자동 수정하지는 않는다.
HTTP 방식은 WSL 안에서 HTTP Hub를 실행하고 Windows에서 해당 localhost 주소에 접근할 수 있어야 한다.
Windows↔WSL localhost 전달은 사용자 WSL 네트워크 설정에 따라 달라진다.

## 설치와 함께 고르기

```bash
bash install.sh install --mode stdio
bash install.sh install --mode hybrid --start
bash install.sh update --mode http --url http://127.0.0.1:8765 --start
```

Windows PowerShell에서는 동일한 인자를 `install.ps1`에 전달한다. `--dry-run`은 설정·런타임을
쓰거나 서버를 시작하지 않는다. `--start --port 8766`으로 포트를 바꿀 때 HTTP 등록 주소도
`--url http://127.0.0.1:8766`으로 맞춘다. 시작 실패가 이미 완료한 설치를 제거하지는 않는다.
다운로드 설치의 `--start`도 임시 다운로드 폴더가 아닌 설치된 런타임에서 실행한다.
설치 후 `joongi-skills update`는 저장한 연결 방식을 읽어 에이전트 등록도 갱신한다.

## 필요할 때 켜고 끄기

```bash
joongi-hub start                 # 백그라운드 실행. 이미 실행 중이면 중복 실행하지 않음
joongi-hub status
joongi-hub open                  # 필요하면 시작하고 브라우저 열기
joongi-hub stop
joongi-hub restart
joongi-hub serve                 # 터미널에서 직접 실행, Ctrl+C로 종료
```

브라우저 탭을 닫는 것과 HTTP Hub를 종료하는 것은 다르다. 웹에서도 **웹 UI 실행·종료**를 펼쳐
확인 후 중지할 수 있다. HTTP 연결과 진행 중인 작업은 종료의 영향을 받는다.
Hub가 시작한 stdio upstream은 정리하지만 외부 HTTP 서버까지 종료하지 않는다.
정상 종료·재시작은 설정·인증·기록을 보존하며 진행 중 작업을 자동 재개하지 않는다.
stdout은 stdio 모드에서 JSON-RPC 전용이다. daemon의 시작 오류는 상태 폴더의 `runtime.log`에 기록한다.

## 공식 에이전트 형식 근거

조회: 2026-11-08. 설정 형식 확인과 각 제품 전체의 실제 UI 검증은 구분한다.

- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli): native HTTP `url`.
- [Claude Code MCP](https://code.claude.com/docs/en/mcp): `type: http`, `url`.
- [Cursor MCP](https://prod.cursor.com/docs/mcp): `url`.
- [Gemini CLI MCP](https://geminicli.com/docs/tools/mcp-server/): Streamable HTTP `httpUrl`.
- [Copilot CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference): `type: http`, `url`, tools 및 프로젝트 `.github/mcp.json`.
- [OpenCode MCP](https://opencode.ai/docs/mcp-servers/): `type: remote`, `url`.
