# 설치·업데이트·제거

AI 에이전트용 스킬과 `joongi-hub` MCP 연결을 사용자 홈에 설치합니다.
관리자 권한은 필요하지 않습니다. 에이전트 앱과 외부 MCP 서버는 별도로 준비합니다.
처음 사용하는 분은 [설치 후 첫 사용](../getting-started/00-index.md)도 함께 읽으세요.

## 준비 사항

| 항목 | 필요한 경우 |
|---|---|
| Python 3.10 이상 | 모든 설치와 Hub 실행. Windows는 `py -3`, POSIX는 `python3` 확인 |
| GitHub CLI (`gh attestation verify`) | 다운로드 설치와 원격 업데이트의 서명 검증 |
| Bash·curl 또는 PowerShell | 해당 OS의 다운로드 명령 |
| 에이전트 설정 폴더 | 자동 등록 대상 감지. 없으면 Hub만 설치 |
| OS 보안 저장소 | 서비스 인증 저장. Linux는 Secret Service·열린 키링과 `secret-tool`·`gdbus` 필요 |
| Linux/WSL 격리 또는 Docker | 외부 stdio MCP 실행. 단순 스킬 검색·원격 HTTPS MCP와는 구분 |

[환경별 보안 준비](../operations/10-security-boundaries.md) · [인증 저장소](../operations/05-auth-project-skills.md).
기본은 순수 stdio로, 에이전트가 필요할 때 Hub를 실행합니다. 관리 웹을 미리 켤 필요는 없습니다.

## 클론 없이 설치

macOS·Linux·WSL의 Bash에서 실행합니다.

```bash
curl -fsSL 'https://joongi007.github.io/joongi-skills/install.sh' | bash -s -- install
```

Windows는 아래 [Windows](#windows)의 PowerShell 명령을 사용합니다.
이 간편 방식은 HTTPS로 받은 설치 스크립트를 바로 실행합니다. 스크립트 내부의 설치 번들
서명·출처 검증은 필수입니다. 최초 스크립트도 실행 전에 검증하려면 [보안 설치](04-verified-install.md)를 선택하세요.

설치 계획만 확인하거나 특정 에이전트를 선택할 수 있습니다. 다음 예시는 Bash입니다.

```bash
curl -fsSL 'https://joongi007.github.io/joongi-skills/install.sh' | bash -s -- install --dry-run
curl -fsSL 'https://joongi007.github.io/joongi-skills/install.sh' | bash -s -- install --agent codex
```

`--dry-run`은 변경 계획만 출력하며 설치하지 않습니다. 계획을 확인했다면 `--dry-run` 없이 다시 실행하세요.
설치 후 에이전트에서 `joongi-hub` 연결을 다시 열고 “Hub에서 usual-korean 스킬을 찾아 읽어줘”라고 요청합니다.
외부 MCP 목록이 비어 있는 것은 정상입니다. 사용할 서비스는 [직접 등록·로그인](../getting-started/00-index.md#4-외부-mcp-등록연결로그인하기)합니다.

## 클론에서 설치

```bash
git clone https://github.com/joongi007/joongi-skills.git
cd joongi-skills
bash install.sh install --dry-run
bash install.sh install
~/.local/bin/joongi-skills status
```

설치 후 에이전트의 MCP 연결을 다시 연다. 에이전트가 stdio 프로세스를 실행하므로 웹을 켤 필요가 없다.
선택적으로 `~/.local/bin/joongi-hub open`을 실행하면 관리 화면을 연다.
`~/.local/bin`이 PATH에 있으면 명령에서 해당 경로를 생략할 수 있다. Hub의 상태·서버 등록 정보는
`~/.local/share/joongi-hub`에 별도로 보관한다.

설치기는 기존 에이전트 설정 디렉터리를 탐지하고, 해당 에이전트의 스킬과 MCP 등록을
추가한다. 6개 지원 에이전트 모두 MCP 등록도 자동 적용한다. 에이전트가 없으면 Hub만 설치하며,
나중에 설치를 다시 실행하면 된다.

```bash
bash install.sh install --agent claude --agent codex
bash install.sh install --all       # 미설치 에이전트 경로도 만들겠다는 명시적 선택
bash install.sh status
```

기본 묶음의 native 설치를 제외할 수 있다. `--exclude-category`는 반복 가능하며 제외를 설치 manifest에 저장한다.
이후 업데이트·새 에이전트 설치에도 적용하고, `--reset-skill-selection`은 기존 제외를 비운 뒤 새 제외를 적용한다.
여러 분류에 속한 스킬은 하나의 제외에만 해당해도 설치하지 않는다. 예를 들어 문서 제외는 engineering-playbook도 제외한다.

```bash
bash install.sh install --exclude-category design
bash install.sh update --exclude-category documentation --exclude-category tools
bash install.sh update --reset-skill-selection
```

위 옵션은 Windows PowerShell 명령에도 전달한다. 기존 관리된 제외 사본은 수정되지 않았을 때만 제거하고
회사·다른 도구 소유 사본과 수정본은 보호한다. Hub 원본과 카탈로그 선호는 바꾸지 않는다.
[카탈로그 선택과 native 설치 차이](../operations/14-catalog-preferences.md#회사-기본값과-native-설치-구분).

지원 에이전트와 정확한 설치 경로는 [01-agent-paths.md](01-agent-paths.md)를 본다.
에이전트의 현재 세션에서는 새 스킬·MCP가 즉시 보이지 않을 수 있으므로 새 세션을 연다.

## 업데이트

클론에서 최신 소스를 받은 뒤 다시 설치한다. `install`과 `update`는 같은 멱등 작업이다.

```bash
git pull --ff-only
bash install.sh update
```

설치된 관리 명령으로도 가능하다.

```bash
~/.local/bin/joongi-skills update --source /path/to/joongi-skills
~/.local/bin/joongi-skills update --download-base https://joongi007.github.io/joongi-skills
~/.local/bin/joongi-skills update    # 원래 설치 출처에서 갱신하고 새 에이전트 재탐지
```

업데이트할 때 기존 에이전트와 새로 발견된 에이전트에 현재 스킬을 설치한다.
스킬 디렉터리는 교체하므로 소스에서 삭제한 참조 파일이 설치본에 남지 않는다.
Pages 설치는 다운로드 주소를 기억하므로 이후 `joongi-skills update`만 실행하면 된다.
클론 설치는 원래 클론의 현재 파일을 사용한다. Git pull은 사용자가 실행하며,
원래 클론이 사라지면 설치된 스냅샷으로 새 에이전트를 탐지한다.
`--source`를 명시하면 기억한 원격 다운로드 주소를 해제하고 로컬 소스로 전환한다.

## 제거

```bash
~/.local/bin/joongi-skills uninstall --dry-run
~/.local/bin/joongi-skills uninstall
# 클론이 있다면 bash install.sh uninstall 도 동일
```

이 도구가 설치한 변경되지 않은 스킬·실행 파일·런타임과 관리 중인 MCP 등록만 제거한다.
다른 스킬·MCP·설정은 남긴다. 사용자가 설치 후 수정한 파일이나 MCP 등록은 보존하고
경로를 알려준다. Hub 서버 등록·작업·인증 정보도 자동 삭제하지 않는다.

설치 상태 기록인 `~/.local/share/joongi-skills/installation.json`은 남겨서 보존된 파일을
추적한다. 모든 잔여 파일을 확인한 후 이 작은 기록을 수동 삭제할 수 있다.

## 충돌과 복구

- 기존 이름의 스킬·MCP가 다른 도구 소유이면 덮어쓰지 않고 전체 설치를 중단한다.
- 설치 후 수정한 파일이 있으면 업데이트도 중단한다. 원본 저장소에 변경을 옮기거나
  해당 설치본을 다른 경로로 이동한 뒤 다시 실행한다.
- 심볼릭 링크 대상에는 쓰지 않는다. 기존 `build.sh --link` 설치를 사용했다면 링크를
  다른 곳에 보관하거나 제거한 후 새 설치기를 사용한다.
- 설치 중 파일 쓰기가 실패하면 이미 교체한 파일은 되돌린다. 프로세스 강제 종료나
  전원 장애까지 아우르는 파일시스템 트랜잭션은 아니다.
- 동시 설치를 막는 `install.lock`이 남았다면 다른 설치 프로세스가 없는지 확인한 후
  해당 파일만 제거한다. 실행 중인 설치기의 잠금은 지우지 않는다.

## Windows

PowerShell에서 간편 설치합니다. 전역 실행 정책은 바꾸지 않습니다.

```powershell
& ([scriptblock]::Create((Invoke-RestMethod 'https://joongi007.github.io/joongi-skills/install.ps1'))) install
```

계획만 확인하려면 같은 명령 끝에 `--dry-run`을 추가하고, 설치할 때는 제거합니다.
실행 전 최초 스크립트 서명까지 확인하려면 [보안 설치](04-verified-install.md#windows-powershell)를 사용합니다.

클론에서 설치하는 경우에는 저장소 루트에서 다음을 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 install --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 install
& "$HOME/.local/bin/joongi-skills.cmd" update
& "$HOME/.local/bin/joongi-skills.cmd" uninstall
```

자식 PowerShell의 실행 정책만 지정하며 사용자 전역 정책은 바꾸지 않는다.
세부 옵션은 Python 진입점을 직접 호출하면 셸별 인수 해석 차이가 없다.

```powershell
py -3 -B scripts/install_manager.py install --agent codex --dry-run
& "$HOME/.local/bin/joongi-skills.cmd" status
```

PowerShell은 `py -3`, `python3`, `python` 순으로 Python 3.10 이상을 찾는다.
PATH의 `python.exe`가 오래된 버전이어도 지원 버전이 `py`에 등록돼 있으면 사용할 수 있다.
특정 실행 파일은 `JOONGI_PYTHON`으로 지정한다.

Windows PowerShell 설치와 실제 공개 URL의 설치·업데이트·제거는 CI와 로컬 Windows에서 검증했다.
사용한 환경·명령·제한은 [검증 기록](../development/03-verification.md)을 본다.

## WSL에서 사용하기

WSL 안에서 실행하는 에이전트는 WSL 터미널에서 설치합니다. Windows 앱은 Windows PowerShell에서 설치합니다.
두 환경은 홈과 MCP 등록·인증 상태가 기본적으로 다르므로, 같은 PC라고 자동 공유하지는 않습니다.

Windows 에이전트도 이미 설치된 WSL Hub 하나를 사용하려면 Windows 설치 명령에
`--wsl-distribution 배포판이름`을 명시합니다. 설치된 배포판 이름은 `wsl.exe --list --quiet`로 확인합니다.
또는 WSL 관리 화면의 **Windows용 WSL 연결 생성**을 사용해 검토한 설정을 Windows 에이전트에 복사합니다.
[상태 경로와 공유](../operations/07-state-consistency.md) · [연결 설정](../operations/06-connection-modes.md).

## 설치가 안 될 때

| 증상 | 다음 행동 |
|---|---|
| Python 또는 gh를 찾을 수 없음 | 필요한 도구를 설치하고 터미널을 다시 엽니다. Python은 `JOONGI_PYTHON`으로 지정 가능 |
| 서명·main 커밋 불일치 | 설치하지 않습니다. GitHub Actions의 최신 배포가 완료됐는지 확인하고 다시 받습니다 |
| 같은 이름의 스킬·MCP 충돌 | 표시된 경로의 소유권을 확인합니다. 수정 내용을 보관하고 출처를 정리한 뒤 다시 실행합니다 |
| 에이전트가 감지되지 않음 | 에이전트를 한 번 실행해 설정 폴더를 만들거나 `--agent codex`처럼 명시합니다 |
| 설치 후 명령을 찾을 수 없음 | 이 문서의 전체 경로 명령을 쓰거나 `~/.local/bin`을 PATH에 추가합니다 |
| 설치 후 Hub가 보이지 않음 | 에이전트의 MCP 연결을 다시 엽니다. 새 스킬 목록은 새 세션이 필요할 수 있습니다 |
| 원격 설치를 오프라인에서 실행 | 다운로드·검증은 네트워크가 필요합니다. 신뢰한 로컬 클론의 설치는 원격 설치와 구분합니다 |

## 테스트용 경로

```bash
python3 -B scripts/install_manager.py install --home /tmp/joongi-test-home --agent claude
python3 -B scripts/install_manager.py uninstall --home /tmp/joongi-test-home
```

`--home`을 지정하면 탐지·설치·상태 기록 모두 해당 경로 아래에만 생성한다.
테스트는 임시 홈에서만 수행한다.
