# Joongi Skills & Hub

내 개발 지침과 디자인 규칙을 재사용하고, 여러 MCP 서버의 스킬·도구를 한 접점에서
찾아 쓰는 로컬 작업 공간. **0.1.0, 검토용 초기 릴리스**다.

Python 3.10 이상이면 실행한다. 런타임 외부 의존성·프론트엔드 빌드·별도 DB 서버는 없다.
개인용 loopback 서비스이며 원격 공개·다중 사용자 운영은 별도 설계가 필요하다.

프로젝트는 [MIT License](LICENSE)를 따른다. 포함된 서드파티 파일의 기존 라이선스·NOTICE는 유지한다.

## 로컬에서 바로 실행

에이전트가 stdio로 실행하게 하려면 다음 절의 설치 명령을 사용한다.
설치 없이 선택적 웹 관리 화면을 먼저 확인하려면 저장소 루트에서:

```bash
python3 -m joongi_hub serve
```

[http://127.0.0.1:8765](http://127.0.0.1:8765)에서 스킬을 읽고 MCP를 등록한다.
등록한 서버는 **연결 확인**을 눌러야 실행·연결하고 도구를 가져온다.

## 에이전트에 설치

```bash
git clone https://github.com/joongi007/joongi-skills.git
cd joongi-skills
bash install.sh install --dry-run
bash install.sh install
~/.local/bin/joongi-skills status
```

Windows에서는 `./install.ps1 install`을 사용한다. Claude, Codex, Cursor, Copilot,
Gemini, OpenCode를 자동 탐지한다. 발견한 에이전트에 스킬과 Hub MCP 연결을 함께 등록한다.
OpenCode의 JSONC 주석·trailing comma와 기존 설정도 보존한다.

기본은 에이전트가 실행하는 순수 stdio다. 웹 UI를 먼저 켤 필요가 없다.
설치 후 에이전트의 MCP 연결을 다시 연다. 관리 화면이 필요할 때만 `joongi-hub open`을 실행한다.
여러 에이전트에서 서버를 공유하려면 연결 설정에서 stdio + HTTP 또는 HTTP를 선택한다.
[연결 방식·에이전트 등록·WSL·시작과 중지](docs/operations/06-connection-modes.md).

```bash
~/.local/bin/joongi-skills update      # 갱신하고 새 에이전트 재탐지
~/.local/bin/joongi-skills status
~/.local/bin/joongi-skills uninstall   # 소유한 변경만 제거
```

클론 설치는 `git pull --ff-only` 후 업데이트한다. Pages 설치는 원래 다운로드 주소를 기억한다.
기존 설정·수정한 스킬은 보호한다. 경로·수동 등록·충돌 복구는
[설치 문서](docs/installation/00-index.md)를 본다.

## Hub 기능과 범위

- **스킬**: 로컬·연결된 MCP 스킬 검색, 본문·참조 조회, 출처와 SHA-256 manifest 유지.
- **MCP**: stdio·Streamable HTTP upstream 등록·발견·호출, tools/resources/prompts 프록시.
- **도구 발견**: 연결된 도구를 `서버ID__도구명`으로 직접 노출하고 schema·Apps·Tasks 계약 보존.
- **버전**: `2025-06-18`, `2025-11-25`, `2026-07-28`의 초기화·요청별 기능 협상을 구분.
- **Tasks**: 백그라운드 실행·결과·취소, 입력 대기·제출·재개, 2025/2026 task 형태 변환.
- **Apps**: 공식 AppBridge를 사용한 샌드박스 렌더링, 원래 도구명·리소스 요청의 출처별 라우팅.
- **코드 그래프**: 내장 Python AST MCP의 심볼·호출 관계·영향 분석, 변경 감지·재색인.
- **선택 통합**: Code Review Graph 2.3.9의 분석 7개·색인 관리 2개 도구. 프로젝트마다 경로를 명시하고 DB를 분리.
- **인증**: Bearer·API key·Basic, OAuth PKCE·Device Code·Client Credentials, 갱신·철회.
- **프로젝트**: 선택한 공용 스킬·MCP와 프로젝트 스킬 합성, 범위별 인증·작업 분리.
- **스킬 관리**: UI·MCP에서 설치 계획 검토·적용, 프로젝트 버전 고정·수정 파일 보호.
- **UI**: 통합 검색, 스킬 문서, MCP 연결, 도구 실행, 작업 결과, 기능별 호환성.
- **설치**: 자동 감지·선택 설치·미리보기·업데이트·제거·실패 롤백·수정 파일 보호.

로컬 UI에서 Apps를 열어 직접 조작할 수 있다. 외부 클라이언트에는 해당 호스트의 Apps 지원이 필요하다.
App 안에서도 Task 생성·조회·결과·취소를 처리하고 view별 소유권을 검사한다.
App 내부 2026 Task 입력 재개와 목록 변경 푸시는 아직 지원하지 않는다.
native Skills는 안전한 YAML 메타데이터, 텍스트·바이너리 참조, SHA-256 검증과 디렉터리 조회를 지원한다.
독립적인 sampling/elicitation callback, subscriptions, 구형 HTTP+SSE 전송은 지원하지 않는다.
공식 2025·2026 SDK 네 조합, 실제 Claude Code 연결과 Codex CLI 설정 인식을 검증했다.
각 외부 에이전트 제품 전체의 기능을 같은 범위로 검증했다는 뜻은 아니다.
[인증·프로젝트·스킬 관리](docs/operations/05-auth-project-skills.md),
[호환성 계약](docs/architecture/02-compatibility.md), [검증 기록](docs/development/03-verification.md).

## GitHub Pages 설치 안내

[설치 안내 사이트](https://joongi007.github.io/joongi-skills/)에서 OS별 설치 명령과 스크립트를 확인한다.

`.github/workflows/pages.yml`이 정적 안내 페이지·OS별 설치 스크립트·소스 번들·SHA256을 만든다.
GitHub 저장소에서 **Settings → Pages → GitHub Actions**를 선택하면 배포 시 실제 주소가 반영된다.
설정 후 워크플로를 수동 실행한다. 자동 배포는 저장소 변수 `ENABLE_PAGES=true`로 켠다.
사이트는 설치 파일과 안내를 제공하며 사용자의 로컬 Hub 서버를 호스팅하지 않는다.
Pages 배포는 비밀 값 검사·Python·Windows 설치·문서·SDK·브라우저 등 전체 Check 통과 후 진행한다.

Pages에서 명령을 복사해 터미널에서 설치한다. 브라우저 CORS가 터미널 다운로드를 막지는 않는다.
Pages가 로컬 Hub에 접근할 필요도 없다. [배포 안내](docs/installation/02-github-pages.md).
공개 파일·개인 설정 제외·라이선스·첫 업로드 확인은 [공개 전 점검](docs/installation/03-publication.md)을 본다.

## 개발과 검증

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_docs.py
python3 scripts/mutation_check.py   # AST 연산자로 변이를 생성하고 독립 테스트 실행
./build.sh --check
node --check joongi_hub/static/app.js
node --check site/install.js
```

HTTP 테스트는 localhost 포트를 열 수 있는 환경에서 실행한다. SDK·브라우저 개발 검증은:

```bash
npm ci
npm run build:apps
npx playwright install chromium --only-shell
npm run test:sdk
npm run test:browser
```

문서 검사는 링크뿐 아니라 실제 CLI·HTTP/RPC 경로·기능·에이전트 경로와 문서 주장의 일치를 검사한다.
AST 변이 캠페인의 범위·최신 결과·살아남은 변이의 한계는 [검증 기록](docs/development/03-verification.md)에 남긴다.
런타임 사용자에게 Playwright나 Ruff는 필요하지 않다.

[문서 안내](docs/00-index.md) → [개발 절차](docs/development/00-index.md) →
[독립 작업 단위](docs/development/01-work-packages.md) 순으로 읽는다.
각 작업은 담당 파일·선행 계약·검증·완료 조건을 포함하므로 사람이나 여러 에이전트에게
나누어 맡길 수 있다. 디자인 토큰의 출처·라이선스는 [NOTICE](joongi_hub/static/NOTICE.txt)에 있다.

## 스킬 소스 관리

개인 자료를 일관되게 읽을 수 있도록 스킬의 설명·지침·제목은 한국어를 기본으로 한다.
기술명·코드·명령어·파일명은 원문을 유지한다. [작성 언어 기준](docs/skill-authoring.md#작성-언어).

`usual-korean`은 한국어 답변·문서·UI 문구를 자연스럽게 쓰는 개인 스킬이다.
“SNS에 팔로우 버튼”처럼 익숙한 표현을 쓰고, 기술 용어는 원어·음역·번역어 중 문맥에 맞게 고른다.
애매한 용어는 공식 문서와 실제 용례를 찾아 확인한다. [스킬 지침](skills/usual-korean/SKILL.md).

로컬 프로젝트의 MCP·스킬 출처도 모을 수 있다.
`python3 scripts/collect_local_integrations.py --root /mnt/d/Project`를 실행하면
개인 목록을 `.local/integrations/`에 저장한다. [수집 범위와 재사용](docs/operations/03-local-inventory.md).

`skills/` 아래 소스를 고치고 `build.sh`로 `.skill` 번들을 만든다.
엔지니어링 플레이북은 인프라·HA·TCP·DB 복구·Kubernetes/Helm·문서 정합성·뮤테이션 테스트·
규모별 패턴·병렬 개발 지침까지 포함한다. 아래는 기존 스킬 패키징 도구의 사용법이다.

```
skills/                       # 스킬 소스 (여기를 편집)
  engineering-playbook/       # 코딩 규약 — 백엔드·프론트·인프라·보안
    SKILL.md                  #   frontmatter(name, description) + 라우팅 인덱스
    PLAYBOOK.md               #   원본 문서 (§1~§24)
    references/*.md           #   주제별 참조 파일
  applying-design-systems/    # 비주얼 디자인 — open-design 토큰 카탈로그
    SKILL.md
    references/*.md
  usual-korean/              # 자연스러운 한국어·기술 용어·의미 보존
    SKILL.md
    references/*.md
refs/                         # 근거 자료 — 번들에 안 들어감 (규약: refs/INDEX.md)
  INDEX.md                    #   색인. 여기에 없으면 없는 자료다
  research/                   #   C. 조사 종합 노트 (YYYY-MM-DD-주제.md)
  concepts/                   #   B. 개념 시각 설명 (HTML, NN- 순번)
  <주제>/                      #   A. 참고 자료 (README.md + 최소 실행 예제)
docs/                         # 이 저장소를 쓰는 방법 (작성 규칙 등)
prompts/                      # 재사용 프롬프트 조각
dist/                         # 빌드 산출물 (.skill, git 추적 안 함)
AGENTS.md                     # 다른 에이전트 도구용 진입점 (--agents 로 생성)
build.sh                      # 패키징/검증/링크 스크립트
```

## 사용법

```bash
./build.sh                       # skills/* 전부 dist/*.skill 로 패키징
./build.sh engineering-playbook  # 특정 스킬만
./build.sh --check               # 검증만 (커밋 전 / CI)
./build.sh --link                # ~/.claude/skills 에 심볼릭 링크
./build.sh --clean               # dist/ 삭제
./build.sh --agents              # AGENTS.md 재생성
./build.sh --install DIR         # DIR/.claude/skills 에 복사 (팀 공유용, 커밋할 것)
./build.sh --out /some/dir       # 출력 경로 변경
```

bash + coreutils + find/awk 만 쓴다. zip 압축은 `zip` 이 있으면 그걸 쓰고,
없으면 `python3` 의 zipfile 로 폴백한다 (둘 다 없으면 에러).

## 개발 흐름

1. `./build.sh --link` 을 한 번 실행하면 `~/.claude/skills/<name>` 이
   이 저장소를 가리키는 심볼릭 링크가 된다. 이후 `skills/` 를 고치면 즉시 반영되고,
   매번 다시 빌드할 필요가 없다.
2. 배포하거나 다른 곳에 설치할 때만 `./build.sh` 로 `.skill` 을 만든다.
   `.skill` 은 스킬 이름을 최상위 디렉터리로 갖는 zip 파일이다.
3. `dist/` 는 `.gitignore` 에 있다. 빌드 산출물은 커밋하지 말고,
   배포가 필요하면 GitHub Release 에 첨부한다.

## 프로젝트에 적용하기

Claude Code가 스킬을 찾는 곳은 두 군데다. **어느 쪽인지부터 정한다.**

| 스코프 | 경로 | 범위 | git 공유 |
|---|---|---|---|
| Personal | `~/.claude/skills/<name>/` | 이 기기의 **모든 프로젝트** | 안 됨 (기기 로컬) |
| Project | `<repo>/.claude/skills/<name>/` | 그 저장소에서만 | **됨 (커밋)** |

우선순위는 `Enterprise > Personal > Project`. 같은 이름이 양쪽에 있으면 **Personal이 이긴다.**

### 나 혼자 쓴다 → Personal, 한 번만

```bash
git clone <이 저장소> ~/joongi-skills
cd ~/joongi-skills && ./build.sh --link
```

`~/.claude/skills/<name>` 이 이 저장소를 가리키는 심볼릭 링크가 된다.
**사본이 하나도 없다.** 저장소에서 고치면 모든 프로젝트에 즉시 반영되고,
Claude Code가 변경을 실시간 감지하므로 재시작도 필요 없다.

프로젝트마다 복사해 넣을 이유가 없다 — 사본이 늘어난 만큼 갈라진다.

### 팀·CI도 받아야 한다 → Project, 커밋

그 저장소에서 일하는 **모든 사람**이 규약을 받아야 할 때만.

```bash
cd ~/joongi-skills
./build.sh --install /path/to/그-프로젝트
```

`<프로젝트>/.claude/skills/` 에 실제 파일로 복사된다(심볼릭 링크는 클론에서 살아남지 못한다).
**이건 커밋한다.** `.gitignore` 에 넣으면 팀도 CI도 못 받으므로 프로젝트에 둘 이유 자체가 없어진다.

갱신은 같은 명령을 다시 실행하면 된다 — 대상 디렉터리를 통째로 교체하므로
원본에서 지운 파일이 사본에 남지 않는다.

> 주의: Personal이 Project를 이긴다. 양쪽에 같은 스킬이 있으면 네가 보는 것은 Personal 쪽이다.
> 팀에 배포한 버전을 확인하려면 `~/.claude/skills/<name>` 링크를 잠시 치우고 본다.

### 어느 쪽도 아니면

`.skill` 번들(`./build.sh`)은 배포·백업용이다. GitHub Release에 첨부하거나
스킬을 지원하는 다른 도구에 넣을 때 쓴다.

## 다른 에이전트 도구에서 쓰기

스킬 내용은 전부 순수 markdown이라 Claude 전용 기능에 의존하지 않는다.

`./build.sh --agents` 가 저장소 루트에 `AGENTS.md` 를 만든다. Codex, Cursor, Zed 처럼
AGENTS.md 규약을 읽는 도구가 여기서 스킬을 찾아 `SKILL.md` → 라우팅 표 → 참조 파일 순으로
따라간다. 스킬을 추가하거나 description을 고치면 다시 실행한다.

지침 자체는 `skills/` 한 곳에만 있고 `AGENTS.md` 는 포인터일 뿐이라, 사본이 갈라질 일이 없다.
도구별 전용 포맷(`.cursor/rules/*.mdc`, `.github/copilot-instructions.md`)은 만들지 않는다.

## 새 스킬 추가

`skills/<kebab-case-name>/SKILL.md` 를 만들고 frontmatter 를 채운다.

```markdown
---
name: my-skill
description: 언제 이 스킬을 써야 하는지 구체적으로. 이 문장만 보고 라우팅되므로 트리거 키워드를 넣는다.
---

# My Skill
...
```

`build.sh` 가 검증하는 것:

- `SKILL.md` 존재, frontmatter 파싱 가능
- `name` 이 디렉터리 이름과 일치하고 kebab-case (≤64자)
- `description` 존재 (≤1024자, 너무 짧으면 경고)
- `__pycache__`, `.DS_Store`, `node_modules` 등은 번들에서 제외

작성 규칙은 [docs/skill-authoring.md](docs/skill-authoring.md), 그 근거가 된 Anthropic 공식 지침
요약은 [refs/research/](refs/research/) 에 있다.

## refs/ — 근거 자료

스킬의 규칙에는 근거가 있어야 하고, 그 근거는 어딘가에 남아야 한다.
`refs/` 가 그 자리다. 세 종류를 구분한다 — **A. 참고 자료**(주제 폴더 + 돌려볼 수 있는 최소 예제),
**B. concepts**(개념 시각 설명 HTML), **C. research**(외부 문서·표준 조사 노트).

규칙은 [refs/INDEX.md](refs/INDEX.md) 에 있다. 요약하면: 출처와 조회 날짜를 반드시 적고,
원문이 아니라 요약이면 그렇게 밝히고, 측정값은 측정 환경을 같이 적고, 새 자료를 넣으면
INDEX 표에 한 줄 추가한다.

`refs/` 는 `.skill` 번들에 들어가지 않는다. 스킬을 쓰는 사람이 아니라 **만드는 사람**을 위한 자료다.
