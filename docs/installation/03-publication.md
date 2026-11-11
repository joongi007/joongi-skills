# GitHub 공개 전 점검

이 저장소는 개인용 로컬 Hub의 초기 릴리스다. 소스를 공개하는 것과 다른 컴퓨터의
MCP 등록·인증·그래프 DB를 공유하는 것은 다르다. 설치하는 사람마다 자신의 에이전트와
MCP를 등록하고 인증한다. 개인 MCP 연결과 인증은 설치 번들에 포함하지 않는다.

## 공개 파일과 개인 설정

`.local/`, AWS·에이전트의 로컬 설정 디렉터리, `.env` 계열, 개인 키·인증서 파일,
Python·Node 캐시, 빌드 결과는 Git 제외 규칙으로 보호한다. `.env.example`은 예시만 넣는다.
이미 추적한 파일에는 `.gitignore`가 소급 적용되지 않으므로 실제 인덱스도 확인한다.

```bash
git status --short
git diff --cached --stat
git ls-files
```

`git add -f`, 전체 폴더 압축 업로드, `.local` 결과의 수동 첨부로 제외 규칙을 우회하지 않는다.
스크린샷·로그·이슈 첨부에도 실제 토큰·사용자 경로·프로젝트 목록이 있을 수 있다.
소스에 있는 Joongi라는 프로젝트명·공개 GitHub 출처와 예시 경로는 익명화하지 않는다.

Gitleaks를 설치한 환경에서는 첫 push 전에 다음을 실행한다. 탐지 값은 로그에 마스킹한다.

```bash
gitleaks dir . --redact=100 --no-banner
gitleaks git . --redact=100 --no-banner --log-opts="--all"
```

스캐너는 탐지 규칙에 맞는 비밀 값을 찾는 보조 검사다. 모든 개인정보나 새로운 형태의
인증 정보를 식별하지는 못한다. 공개 전에 스테이징한 파일을 직접 확인한다.
커밋 작성자 이름·이메일도 공개될 수 있으므로 Git 설정과 GitHub의 이메일 공개 설정을 확인한다.
이메일을 숨기려면 GitHub가 제공하는 본인 계정의 noreply 주소를 사용한다.
커밋에 들어간 실제 키를 발견하면 공개 전에 해당 키를 폐기하고 새로 발급한다.

## CI와 Pages

Check 워크플로는 다음을 검증한다.

- Linux·Windows × Python 3.10·3.14의 Python 테스트와 Windows PowerShell 설치 수명 주기
- 문서·런타임 계약, 스킬 번들, Ruff, JavaScript 문법, 핵심 로직의 뮤테이션 캠페인
- 공식 MCP SDK의 2025/2026 × stdio/HTTP 조합, Chromium 브라우저 시나리오
- Gitleaks 8.30.1로 현재 파일·전체 로컬 Git 이력·설치 번들 검사
- 추적된 파일에 개인 설정·환경 파일·키 파일이 포함되지 않는지 검사

공식 Actions는 검증한 commit SHA로 고정하고 Dependabot이 Actions·npm 업데이트 PR을 제안한다.
월별 일반 업데이트는 Actions와 npm을 각각 하나의 PR로 묶고 생태계별 열린 버전 업데이트 PR을
1개로 제한한다. 보안 업데이트는 별도 그룹으로 처리하며 일반 업데이트의 개수 제한을 적용하지 않는다.
업데이트를 자동 병합하지 않는다. PR에서 CI로 검증한 뒤 병합한다.
워크플로의 기본 토큰 권한은 읽기이며 Pages 배포 작업에만 배포 권한을 준다.
일반 Check는 main push와 PR에서 실행한다. 같은 PR의 이전 CI는 새 커밋이 올라오면 취소한다.
Pages는 전체 Check를 재사용하며 성공 후 정적 페이지와 설치 번들을 배포한다.
뮤테이션 캠페인은 살아남은 변이를 보고하며 CI는 미탐을 실패로 처리한다. 예외 허용 목록은 없다.
최신 범위와 미탐은 [검증 기록](../development/03-verification.md)을 확인한다.

첫 업로드 후 GitHub의 Actions 실행 결과를 확인하고, Settings → Pages에서 GitHub Actions를
선택한다. Pages 수동 배포 확인 후 `ENABLE_PAGES=true` 저장소 변수로 push 자동 배포를 켠다.
원격 Actions와 실제 Pages 주소의 다운로드·설치는 업로드 전 로컬 검사만으로
성공했다고 간주하지 않는다. 자세한 절차는 [Pages 배포](02-github-pages.md)를 따른다.

## 라이선스와 공개 범위

프로젝트 자체의 코드는 루트 [MIT License](../../LICENSE)를 따른다. 저작권 표기는
공개 GitHub 계정명 `joongi007`을 사용한다. 서드파티 파일에는 해당 파일의 원래
라이선스·NOTICE가 적용되며 그대로 유지한다.
디자인 토큰과 SDK 번들의 표시는 `joongi_hub/static/NOTICE*`, vendored YAML은
`joongi_hub/_vendor/yaml/LICENSE`와 `PROVENANCE.json`에서 확인한다.

MIT 선택은 2026-11-11 사용자 요청에 따라 반영했다. GitHub 저장소는
`https://github.com/joongi007/joongi-skills`를 사용한다. 원격 CI·Pages 상태는 해당 저장소의
Actions 실행 결과와 Pages 설정에서 확인한다.

설치·연동·로컬 실행은 [설치 안내](00-index.md)와
[연결 방식](../operations/06-connection-modes.md)을 따른다. 기본 stdio는 HTTP 서버를 요구하지 않는다.

## main 브랜치 보호

공용 저장소의 main은 강제 push·삭제를 금지하고 관리자에게도 보호 규칙을 적용한다.
변경은 별도 브랜치와 PR로 진행하며, 병합 전 최신 main 기준으로 다음 7개 검사를 통과해야 한다.

- `publication`, `windows-installer`, `browser`
- `test (ubuntu-latest, 3.10)`, `test (ubuntu-latest, 3.14)`
- `test (windows-latest, 3.10)`, `test (windows-latest, 3.14)`

검사 출처는 GitHub Actions로 고정한다. PR의 미해결 대화도 완료해야 한다.
개인 저장소이므로 다른 사람의 승인은 필수가 아니다. GitHub의 브랜치 보호는 저장소 설정이며
소스를 clone한 다른 저장소로 자동 복사되지는 않는다. 새 저장소에서는 설정을 다시 적용한다.
