# Joongi Skills & Hub

AI 에이전트에 공통 작업 지침을 설치하고, 여러 MCP 서버를 한 곳에서 연결·검색하는 로컬 도구입니다.
**0.1.0 · 초기 릴리스**입니다. 개인 컴퓨터에서 사용하는 단일 사용자 도구이며, 인터넷 공개 서버로 제공하지 않습니다.

[소개와 제공 기능](https://joongi007.github.io/joongi-skills/guide.html) · [설치 사이트](https://joongi007.github.io/joongi-skills/) · [처음 사용하기](docs/getting-started/00-index.md) · [전체 문서](docs/00-index.md)

- **스킬**은 에이전트가 필요한 작업에서 읽는 Markdown 지침입니다.
- **MCP**는 에이전트와 외부 도구를 연결하는 프로토콜입니다. **Hub**가 연결·검색·호출을 중계합니다.
- **Prompts**는 MCP 서버가 제공하는 대화 템플릿입니다. 공용 번들은 없으며, 연결 서버의 목록·내용을 중계합니다.
- 기본 **stdio** 방식은 에이전트가 Hub 프로세스를 실행합니다. 웹 서버를 미리 켤 필요가 없습니다.

브라우저 조작은 선택 설치입니다. [격리 Playwright](docs/operations/16-browser-automation.md)와
기존 로그인을 공유하는 [개인 Windows Edge 백그라운드 연결](docs/operations/17-personal-edge.md)을 구분해 선택합니다.
개인 Edge 모드는 공식 확장과 사용자 연결 승인이 필요하며 OS 샌드박스가 아닙니다.

## 설치

Python 3.10 이상과 [GitHub CLI](https://cli.github.com/)를 먼저 준비하세요.
관리자 권한은 필요하지 않습니다. 설치기는 기존 에이전트 설정 폴더를 감지해 스킬 5개와
`joongi-hub` MCP 연결을 등록합니다. 에이전트 앱 자체와 외부 MCP 서버는 설치하지 않습니다.

### macOS · Linux · WSL

Bash 터미널에서 실행하세요.

```bash
curl -fsSL 'https://joongi007.github.io/joongi-skills/install.sh' | bash -s -- install
```

### Windows PowerShell

```powershell
& ([scriptblock]::Create((Invoke-RestMethod 'https://joongi007.github.io/joongi-skills/install.ps1'))) install
```

위 간편 명령은 HTTPS로 받은 설치 스크립트를 바로 실행합니다. 스크립트가 설치 번들의
서명·출처·현재 main 커밋을 검증한 뒤 설치합니다. **최초 스크립트까지 실행 전에 검증하려면
[보안 설치](docs/installation/04-verified-install.md)를 사용하세요.** 검증을 생략하는 옵션은 없습니다.

소스를 직접 관리하려면 [클론 설치](docs/installation/00-index.md#클론에서-설치)를 선택하세요.
변경 경로를 확인하는 `--dry-run`, 에이전트를 지정하는 `--agent codex`, 설치 경로와 충돌 복구는
[설치 상세](docs/installation/00-index.md)에 있습니다.

## 설치 후 첫 사용

1. 에이전트에서 `joongi-hub` MCP 연결을 다시 엽니다. MCP만 재연결할 수 없다면 새 세션을 엽니다.
2. “Hub에서 usual-korean 스킬을 찾아 읽어줘”라고 요청해 검색·읽기가 되는지 확인합니다.
3. 외부 도구가 필요하면 “Hub 설정 화면 열어줘”라고 요청해 MCP 서버를 등록합니다.
4. 서버의 **연결 확인**을 누르고 필요한 서비스에 로그인합니다. 등록·연결·로그인은 서로 다른 단계입니다.

**처음 설치한 Hub의 외부 MCP 목록은 비어 있습니다.** 개발자의 MCP 등록·인증은 배포하지 않습니다.
Notion 등의 서비스는 사용할 사람이 자신의 연결과 권한을 설정해야 합니다.
[첫 사용 안내](docs/getting-started/00-index.md) · [인증과 호출 승인](docs/operations/05-auth-project-skills.md).

## 함께 설치되는 스킬

| 스킬 | 사용할 때 |
|---|---|
| [engineering-playbook](skills/engineering-playbook/SKILL.md) | 개발 전반의 판단 기준과 Codex Security CLI 검수 절차 |
| [usual-korean](skills/usual-korean/SKILL.md) | 자연스러운 한국어와 기술 용어 선택 |
| [applying-design-systems](skills/applying-design-systems/SKILL.md) | 기존 토큰 활용·디자인 명세 선택·UX 검토 |
| [creating-diagrams](skills/creating-diagrams/SKILL.md) | Mermaid·Excalidraw·SVG 다이어그램, 아이콘·캡처 선택 |
| [building-procedural-3d](skills/building-procedural-3d/SKILL.md) | 이미지 기반 Three.js 제작과 단계별 렌더 비교 |

스킬은 제작·검토 지침입니다. Excalidraw·snapdom·img2threejs 같은 외부 엔진 전체를 설치하는 것은 아닙니다.
자동 선택과 같은 이름의 스킬 우선순위는 에이전트마다 다릅니다. [시각 자료 제작 예시](docs/operations/13-visual-workflows.md).

Codex Security는 별도 스캔 MCP가 아니라 `engineering-playbook`의 검수 가이드로 제공합니다.
`codex`·`security`로 스킬을 검색해 읽은 뒤 에이전트의 shell 도구로 공식 CLI를 실행합니다.
CLI 설치·로그인·서비스 접근 권한은 별도이며 Hub 설치만으로 자동 검수되지는 않습니다.
[검수 가이드와 실행 조건](docs/operations/15-codex-security.md).

브라우저가 필요하면 선택형 [격리 Playwright MCP](docs/operations/16-browser-automation.md)를 준비할 수 있습니다.
Linux/WSL·Docker에서 전용 브라우저로 화면 확인·클릭·입력을 처리하며, 개인 Chrome 프로필은 공유하지 않습니다.
허용 HTTPS 사이트와 호출 승인을 사용합니다. 기본 설치에는 이미지 다운로드나 서버 등록을 포함하지 않습니다.

## 관리·업데이트·제거

macOS·Linux·WSL에서는 다음 전체 경로 명령을 사용합니다. `~/.local/bin`이 PATH에 있다면 경로를 생략해도 됩니다.

```bash
~/.local/bin/joongi-hub open
~/.local/bin/joongi-skills status
~/.local/bin/joongi-skills update
~/.local/bin/joongi-hub stop
~/.local/bin/joongi-skills uninstall --dry-run
~/.local/bin/joongi-skills uninstall
```

Windows에서는 다음 형식입니다. [OS별 전체 명령](docs/installation/00-index.md#windows).

```powershell
& "$HOME/.local/bin/joongi-hub.cmd" open
& "$HOME/.local/bin/joongi-skills.cmd" update
```

원격 설치는 같은 배포 주소에서 갱신하고, 클론 설치는 저장소에서 `git pull --ff-only` 후 업데이트합니다.
업데이트할 때 새로 발견한 에이전트도 등록합니다. 제거는 관리 중인 설치 파일을 대상으로 하며
사용자 수정본·다른 설정·Hub의 서버 등록·작업·인증은 보존합니다.
임시 설정 화면은 창을 닫으면 정리되고, `open`으로 연 관리 웹은 `stop`으로 중지합니다.
[stdio·HTTP와 웹 실행](docs/operations/06-connection-modes.md).

## 지원 범위와 준비 사항

Claude Code·Codex·Cursor·Copilot CLI·Gemini CLI·OpenCode를 지원합니다.
Hub는 클라이언트와 외부 서버의 MCP 버전을 각각 협상합니다. Apps·Tasks 등은
[기능별 호환성 표](docs/architecture/02-compatibility.md)에서 확인하세요.

외부 stdio MCP에는 Linux/WSL 격리 또는 Docker 등 [실행 환경 준비](docs/operations/10-security-boundaries.md)가 필요합니다.
격리할 수 없으면 연결을 거절합니다. 서비스 토큰은 OS 보안 저장소로 보호하며,
Linux에서 토큰을 저장하려면 Secret Service와 열린 로그인 키링이 필요합니다.
[환경별 인증 준비](docs/operations/05-auth-project-skills.md).

기본은 stdio·HTTP 공통의 검색 중심 모드입니다. 일반 도구는 **상위 5개 한 줄 검색 → 정확한 상세·schema 조회 → 호출**로 사용합니다.
App·명시적 Task 지원 외부 도구는 native 목록에 남겨 원래 호스트 계약을 유지합니다.
[검색 범위와 예외](docs/operations/08-catalog-search.md).

회사·개인 스킬 출처와 개발·문서·디자인·도구 묶음은 [검색 설정](docs/operations/14-catalog-preferences.md)에서 선택합니다.
Hub 선택과 에이전트의 native 설치는 별개입니다. native 기본 디자인 지침도 제외하려면 설치 명령에
`--exclude-category design`을 추가하세요. 제외는 업데이트에도 유지하며 `--reset-skill-selection`으로 복원합니다.
사용 통계는 기본 꺼짐이며 선택한 경우에만 로컬 집계를 저장합니다.

## 기여와 배포

[개발 절차](docs/development/00-index.md) · [테스트 준비와 검증](docs/development/02-quality.md) ·
[스킬 작성](docs/skill-authoring.md) · [Pages 배포](docs/installation/02-github-pages.md).

현재 CI 결과는 [GitHub Actions](https://github.com/joongi007/joongi-skills/actions)에서 확인합니다.
[검증 기록](docs/development/03-verification.md)은 날짜별 실행 이력이며, 과거의 테스트 수는 최신 상태를 뜻하지 않습니다.
프로젝트는 [MIT License](LICENSE)를 따릅니다. 서드파티 라이선스와 NOTICE는 각각 유지합니다.
