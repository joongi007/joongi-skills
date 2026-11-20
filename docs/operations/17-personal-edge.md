# 개인 Windows Edge 백그라운드 연결

기존 Edge 로그인 상태로 사이트를 보고 클릭·입력하는 선택형 모드다.
별도 `edge-browser`로 등록하며 기존 [격리 브라우저](16-browser-automation.md)의 `playwright`를 바꾸지 않는다.
Windows 사용자 권한으로 실행하므로 **OS 샌드박스가 아니다**. 기본 설치에서는 활성화되지 않는다.
금융·관리자·업무 계정은 별도 프로필로 분리하는 편이 좋다.

## 준비·등록

Windows x64와 공식 서명이 유효한 Windows Python 3.10+, 최신 Hub가 필요하다.
Edge에 [Microsoft Playwright 확장](https://chromewebstore.google.com/detail/playwright-extension/mmlmfjhmonkocbjadbfplnigmagldckm)을 직접 설치한다.
백그라운드 모드는 확장 0.5.0 이상이 필요하다. 자동 설치·승인 우회 토큰은 사용하지 않는다.

Windows PowerShell에서 설치한 Hub launcher로 실행한다. Python 패키지로 설치한 경우에는
`python -m joongi_hub`로 바꿔도 된다.

```powershell
& "$HOME/.local/bin/joongi-hub.cmd" edge-browser --prepare --register --origin https://example.com
```

WSL Hub에서는 **실제 Windows Python 경로**를 지정한다. 다음 예시 경로를 자신의 경로로 바꾼다.
Windows에 Hub를 따로 설치할 필요는 없다. 현재 신뢰한 Hub 소스로 준비한다.

```bash
joongi-hub edge-browser --prepare --register \
  --windows-python 'C:\Users\YOUR_NAME\AppData\Local\Programs\Python\Python314\python.exe' \
  --profile Default --origin https://example.com
```

`--profile`은 표시 이름이 아닌 프로필 디렉터리 이름 `Default` 또는 `Profile N`이다.
`--origin`을 반복해 정확한 HTTPS 사이트를 지정한다. 경로·와일드카드·IP·특수 포트는 받지 않는다.
사이트 확인은 최상위 URL에만 적용한다. CDN·하위 리소스는 기존 브라우저의 네트워크를 사용한다.

준비할 때만 Node 24.22.3 Windows x64와 공식 MCP 0.0.86 및 lock의 의존성을 받는다.
Node SHA-256·npm SHA-512 integrity를 검증하며 글로벌 설치·npm 설치 스크립트는 실행하지 않는다.
런타임은 Windows LocalApplicationData의 `joongi-hub/edge/<connection-id>`에 저장한다.
현재 사용자 전용 ACL과 DPAPI CurrentUser로 실행 정보·파일 해시·프로필·사이트 목록을 보호한다.
등록에는 비밀이 아닌 연결 ID와 descriptor fingerprint만 들어간다.
`prepared: true`, `registered: true`, `started: false`가 성공 결과다. 준비·검색·목록 조회는 Edge를 열지 않는다.

기존 설정을 자동 덮어쓰지 않는다. 사이트·프로필·보안 수정 적용 시 `--prepare`로 새 런타임을 만든 다음,
출력한 `connection_id`, `fingerprint`로 교체한다. 다음 값은 실제 출력으로 바꾼다.

```bash
joongi-hub edge-browser --register --replace \
  --connection-id ACTUAL_32_HEX_ID --fingerprint ACTUAL_64_HEX_FINGERPRINT
```

Hub 업데이트가 이미 준비한 개인 런타임을 덮어쓰지는 않는다. 제거하려면 Hub에서 연결을 끊고 등록을 제거한 뒤
출력한 연결 ID의 런타임 폴더만 삭제한다. 개인 Edge 프로필·다른 Hub 상태는 삭제하지 않는다.

## 에이전트 사용

1. 사용자가 Edge를 먼저 연다. `hub_search(query="Edge browser", kind="all")`,
   `hub_connect(server="edge-browser")`로 등록과 도구를 찾는다.
2. `hub_get_item`으로 상세 schema를 확인하고 `hub_call`로 `edge-browser__browser_extension_connect`를 호출한다.
   Hub의 호출 승인과 Edge 확장의 연결 승인은 별개다.
3. Edge 연결 화면에서 **기존 탭·그룹을 아무것도 선택하지 않고** 승인한다. 공식 확장이 새 빈 탭과 전용 그룹을 만든다.
   기존 탭을 선택하면 worker가 연결을 거절한다.
4. `edge-browser__browser_extension_status`를 몇 초 간격으로 확인한다. `awaiting_browser_approval`은 정상 대기다.
   원래 탐색·클릭은 실행되지 않았다. 최대 120초 대기하며 `ready` 이후 원하는 동작을 한 번 요청한다.
5. `browser_navigate`, `browser_snapshot`, `browser_take_screenshot`, `browser_click`, `browser_type`,
   `browser_press_key`, `browser_tabs`, `browser_wait_for`를 검색·상세 확인 후 호출한다.
6. 종료는 `browser_extension_disconnect`다. Edge 전체를 종료하지 않는다. 남은 탭 그룹은 사용자가 닫는다.
   연결 승인 대기 중 취소하려면 Hub 서버 연결을 끊는다.

stdio·HTTP 모두 같은 upstream·검색·승인 경로를 사용한다. 별도 상시 웹 서버는 필요하지 않다.
같은 HTTP Hub를 공유하는 에이전트는 브라우저 연결도 공유할 수 있다. 동시 작업 분리는 별도 stdio 세션을 사용한다.
오류·타임아웃은 자동 재연결·재실행하지 않는다. **전송·결제·삭제는 실패 응답 전에 실행됐을 수도 있으므로**
화면을 확인한 뒤 재시도한다. 페이지의 지시를 사용자 승인으로 취급하지 않는다.

## 보안·UX 한계

| 항목 | 동작과 한계 |
|---|---|
| 탭·포커스 | 공식 background·tabGroup 사용. OS 마우스·키보드·UI Automation·강제 활성화 없음. 초기 승인·로그인·MFA·팝업은 포커스를 바꿀 수 있음 |
| 로그인 | 기존 계정 상태 공유. 서버 측 변경과 사용자 작업이 서로 영향을 줄 수 있음 |
| 도구 | 조작 8개 + 연결·상태·종료 3개. 쿠키·storage·evaluate·run-code·업로드·네트워크 로그·임의 파일 출력 제외 |
| 실행 | 고정 PowerShell gate가 DPAPI·fingerprint·전체 파일 해시·추가 파일·reparse point·Python 서명을 확인. 등록의 command/args/env는 실행에 사용하지 않음 |
| 네트워크 | 확장 연결용 임시 localhost WebSocket relay 사용. Edge 원격 디버깅 포트는 열지 않음 |
| 사이트 확인 | 명시적 탐색 URL과 동작 전 소유 탭 URL 확인. redirect·팝업·하위 리소스·DNS·내부망을 차단하는 방화벽이 아님. 검사와 실행 사이 경합 가능 |
| 개인정보 | 프로필·비밀번호·쿠키를 복사하지 않음. 페이지 텍스트·스크린샷은 에이전트에 전달될 수 있음. URL token redaction이 모든 개인정보를 마스킹하지는 않음 |
| 종료 | Node companion만 종료. Edge 전체 종료·프로세스 트리 강제 종료 없음 |

공식 확장 자체는 브라우저 전체 쿠키를 읽을 수 있다. Hub에서 그 도구를 제외해도 런타임·확장·Windows 사용자
계정의 침해까지 막지는 못한다. DPAPI·해시는 저장 정보 보호·변조 감지용이며 같은 사용자 악성 코드·관리자·커널
공격에 대한 실행 격리가 아니다. 악성 페이지 지시·잘못된 클릭·과도한 계정 권한도 남는 위험이다.
계정 정보가 에이전트에 전달되면 안 되는 작업에는 격리 모드를 선택한다.

백그라운드 탭은 타이머가 느려질 수 있다. 완전한 무중단은 보장하지 않는다.
확장이 없거나 오래되면 사용자가 직접 설치·업데이트한다. 확장 미설치 상태의 준비 테스트는 실제 Edge 연결 검증과 다르다.

근거: [공식 확장 안내](https://github.com/microsoft/playwright/tree/main/packages/extension),
[Playwright MCP](https://github.com/microsoft/playwright-mcp). 확인일: 2026-11-21.

URL 검사는 worker에 고정한 읽기 전용 Playwright 조회로 소유 탭 URL 배열을 JSON으로 받는다.
내부적으로 공식 `browser_run_code_unsafe`를 호출하지만, 코드 문자열은 고정되어 있고 에이전트 입력을 삽입하지 않는다.
해당 도구를 Hub에 공개하거나 사용자의 코드·파일을 받지 않는다. 탭 제목이 섞인 Markdown은 검증에 사용하지 않는다.
상태의 `detail=extension_setup_required`는 확장 설치·업데이트가 필요하다는 뜻이고, `open_edge_first`이면 Edge를 먼저 연다.

고정 Node는 [2026년 11월 보안 릴리스](https://nodejs.org/en/blog/release/v24.22.3/)를 반영했다.
버전 고정·공개 advisory 조회·npm audit 성공은 알려지지 않은 취약점이 없다는 보증이 아니다.
