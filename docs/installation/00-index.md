# 설치·업데이트·제거

Python 3.10 이상이면 추가 패키지 없이 실행한다. 개발 기준은 Python 3.14이며,
설치 가능한 환경을 넓히려고 런타임의 최소 버전은 3.10으로 둔다.
설치에는 관리자 권한이 필요 없다. 기본 연결은 순수 stdio이며, 설치와 함께
`--mode hybrid --start`로 공유 서버를 켤 수도 있다.
세부 사용은 [연결 방식과 웹 실행](../operations/06-connection-modes.md)을 본다. 실제 설치 전 `--dry-run`으로 경로를 확인할 수 있다.

원격 설치·업데이트에는 [GitHub CLI](https://cli.github.com/)의 서명 검증 기능이 필요합니다.
외부 stdio MCP에는 Linux/WSL 격리 또는 Docker가 필요하며, 준비되지 않으면 연결을 거절합니다.
[보안 경계·플랫폼 준비](../operations/10-security-boundaries.md).

## 클론 없이 설치

[설치 안내 사이트](https://joongi007.github.io/joongi-skills/)에서 OS별 명령을 복사해 터미널에서 실행한다.
사이트는 설치 파일을 제공하고, Hub는 사용자의 컴퓨터에서 실행된다.
설치 후에는 에이전트의 MCP 연결을 다시 열고 스킬 검색을 확인한다.
[설치 후 첫 사용 순서](../../README.md#설치-후-첫-사용).

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
~/.local/bin/joongi-skills update --download-base https://OWNER.github.io/REPOSITORY
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

클론에서 PowerShell로 실행한다.

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

## 테스트용 경로

```bash
python3 -B scripts/install_manager.py install --home /tmp/joongi-test-home --agent claude
python3 -B scripts/install_manager.py uninstall --home /tmp/joongi-test-home
```

`--home`을 지정하면 탐지·설치·상태 기록 모두 해당 경로 아래에만 생성한다.
테스트는 임시 홈에서만 수행한다.
