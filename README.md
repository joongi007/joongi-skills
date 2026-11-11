# Joongi Skills & Hub

여러 AI 에이전트에서 같은 개발 지침을 사용하고, MCP 서버를 한 곳에서 연결·검색하는 로컬 도구입니다.
**0.1.0 · 초기 릴리스**이며, Python 3.10 이상이 필요합니다.

[설치 안내 사이트](https://joongi007.github.io/joongi-skills/) · [문서 안내](docs/00-index.md) · [지원 범위](docs/architecture/02-compatibility.md)

## 먼저 알아두기

- **기본은 stdio**입니다. 에이전트가 필요할 때 Hub를 실행하므로 웹 서버를 미리 켤 필요가 없습니다.
- 설치기는 Claude, Codex, Cursor, Copilot, Gemini, OpenCode의 기존 설정 디렉터리를 감지합니다.
  발견한 에이전트에 공용 스킬 3개와 Hub MCP 연결을 등록합니다.
- 외부 MCP는 사용자가 별도로 등록합니다. 설치만으로 외부 서비스가 자동 연결되지는 않습니다.
- 개인 컴퓨터에서 사용하는 도구입니다. 런타임에 별도 패키지 설치·프론트엔드 빌드·DB 서버가 필요하지 않습니다.

## 설치

클론 없이 설치하려면 [설치 안내 사이트](https://joongi007.github.io/joongi-skills/)에서
사용하는 OS의 명령을 복사해 터미널에서 실행하세요.

소스를 직접 관리하려면 다음과 같이 설치합니다.

### macOS · Linux · WSL

```bash
git clone https://github.com/joongi007/joongi-skills.git
cd joongi-skills
bash install.sh install --dry-run
bash install.sh install
~/.local/bin/joongi-skills status
```

### Windows PowerShell

```powershell
git clone https://github.com/joongi007/joongi-skills.git
cd joongi-skills
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 install --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 install
& "$HOME/.local/bin/joongi-skills.cmd" status
```

`--dry-run`은 실제로 설치하지 않고 변경할 경로를 보여줍니다.
특정 에이전트만 선택하려면 설치 명령에 `--agent codex`처럼 덧붙이세요.
기존 설정과 직접 수정한 파일은 보호하며, 충돌하면 덮어쓰지 않고 중단합니다.
[설치 경로·충돌 복구·WSL 설정](docs/installation/00-index.md).

## 설치 후 첫 사용

1. 사용하는 에이전트의 MCP 연결을 다시 열거나 새 세션을 시작합니다.
2. “Hub에서 usual-korean 스킬을 찾아 읽어줘”라고 요청해 연결을 확인합니다.
3. 외부 MCP를 추가하려면 `joongi-hub open`으로 관리 화면을 열고, 서버를 등록한 뒤 **연결 확인**을 누릅니다.
4. 관리 화면이 필요 없으면 `joongi-hub stop`으로 웹 서버를 끕니다. 기본 stdio 연결은 계속 사용할 수 있습니다.

`joongi-hub`와 `joongi-skills`는 `~/.local/bin`에 설치됩니다.
PATH에 없다면 `~/.local/bin/joongi-hub open`처럼 전체 경로를 쓰세요.
Windows에서는 `& "$HOME/.local/bin/joongi-hub.cmd" open` 형식입니다.

stdio·stdio + HTTP·HTTP 중 선택하는 방법은 [연결 방식과 웹 실행](docs/operations/06-connection-modes.md)에 있습니다.

## 업데이트와 제거

```bash
~/.local/bin/joongi-skills update
~/.local/bin/joongi-skills status
~/.local/bin/joongi-skills uninstall --dry-run
~/.local/bin/joongi-skills uninstall
```

Windows에서는 `& "$HOME/.local/bin/joongi-skills.cmd" update`처럼 실행합니다.

| 설치 방식 | 최신 버전으로 갱신 |
|---|---|
| 설치 안내 사이트에서 설치 | `joongi-skills update`가 원래 다운로드 주소에서 최신 배포본을 받습니다. |
| Git 클론에서 설치 | 저장소에서 `git pull --ff-only` 후 `joongi-skills update`를 실행합니다. |

업데이트할 때 새로 발견한 에이전트도 등록합니다. 제거할 때는 이 도구가 관리하는 변경만 되돌리고,
다른 설정·수정한 파일·Hub의 서버 등록과 작업·인증 정보는 남깁니다.
[업데이트·제거·복구 상세](docs/installation/00-index.md).

## 무엇을 할 수 있나요?

| 기능 | 내용 |
|---|---|
| 공용 스킬 | 한국어 표현(`usual-korean`), 개발·테스트·운영 규칙(`engineering-playbook`), 디자인·UX 원칙(`applying-design-systems`) |
| MCP 연결 | stdio·Streamable HTTP 서버 등록, 도구·리소스·프롬프트 검색과 호출 |
| 코드 분석 | 내장 Python 코드 그래프, 선택 설치하는 Code Review Graph 연동과 프로젝트별 DB 분리 |
| 인증·프로젝트 | API key·Bearer·Basic·OAuth, 프로젝트별 MCP·스킬·인증 범위 관리 |
| Apps·Tasks | 로컬 UI의 MCP App 실행, 백그라운드 작업·결과·취소·입력 대기 처리 |
| 관리 화면 | 스킬 읽기, MCP 등록·연결 확인, 도구 실행과 결과·지원 범위 확인 |

클라이언트와 연결할 MCP 서버의 버전·기능은 각각 협상합니다.
`2025-06-18`, `2025-11-25`, `2026-07-28`을 다루며, 기능별 제한은
[호환성 표](docs/architecture/02-compatibility.md)에 정리했습니다.
외부 에이전트에서 Apps를 사용하려면 해당 에이전트도 Apps를 지원해야 합니다.
구형 HTTP+SSE, 독립적인 sampling/elicitation callback, subscriptions 등은 지원하지 않습니다.

Hub 검색과 함께 연결된 도구의 직접 노출도 제공합니다. 에이전트가 모든 도구 설명을 읽는지,
검색한 도구만 읽는지는 클라이언트 동작에 따라 다릅니다.
[검색 방식과 범위](docs/operations/08-catalog-search.md) · [실제 검증 범위](docs/development/03-verification.md).

## 문서와 개발

| 하고 싶은 일 | 읽을 문서 |
|---|---|
| 설치·업데이트·제거 | [설치 안내](docs/installation/00-index.md) |
| 웹 켜기·끄기, 연결 문제 해결 | [로컬 운영](docs/operations/00-index.md) |
| 인증·프로젝트별 스킬 관리 | [인증과 스킬 관리](docs/operations/05-auth-project-skills.md) |
| 구조와 설계 결정 이해 | [아키텍처](docs/architecture/00-index.md) · [ADR](docs/adr/00-index.md) |
| 개발·테스트 작업 나누기 | [개발 절차](docs/development/00-index.md) |
| 스킬 작성·패키징 | [작성 규칙](docs/skill-authoring.md) · [패키징 도구](docs/development/04-skill-packaging.md) |
| Pages를 직접 배포하기 | [배포 안내](docs/installation/02-github-pages.md) |

개발 검증의 시작점은 다음과 같습니다. SDK·브라우저·뮤테이션 검증에 필요한 환경과 명령은
[테스트 안내](docs/development/02-quality.md)를 따릅니다.

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/check_docs.py
bash build.sh --check
```

개인 설정·인증 정보·로컬 수집 결과는 공개 파일에 포함하지 않습니다.
공개 검사 범위는 [배포 점검](docs/installation/03-publication.md)을 확인하세요.
프로젝트는 [MIT License](LICENSE)를 따르며, 서드파티 파일의 기존 라이선스와 NOTICE를 유지합니다.
