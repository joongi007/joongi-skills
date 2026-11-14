# GitHub Pages 배포와 원격 설치

GitHub Pages는 정적 안내 페이지, HTML 문서, 설치 스크립트, 소스 번들을 배포한다.
로컬 Hub나 MCP 서버 프로세스를 호스팅하지 않는다. 브라우저로 페이지를 여는 것만으로
컴퓨터에 설치하지 않으며, 사용자가 내려받은 스크립트를 터미널에서 실행한다.

## 배포 준비

1. 저장소를 GitHub에 올린다.
2. Settings → Pages → Build and deployment에서 GitHub Actions를 선택한다.
3. Actions에서 `Publish installer and guide` 워크플로를 수동 실행한다.
4. Actions가 표시하는 실제 Pages 주소에서 안내 페이지와 `install.sh`를 확인한다.

이후 `main` push마다 배포하려면 Settings → Secrets and variables → Actions → Variables에
`ENABLE_PAGES`를 `true`로 추가한다. 설정 전에는 자동 Pages 작업을 건너뛰고 일반 Check만 실행한다.
비공개 저장소는 계정의 Pages 사용 가능 여부도 확인한다.

워크플로는 재사용하는 Check 워크플로의 비밀 값 검사·Python·Windows 설치·문서·SDK·브라우저·
스킬·뮤테이션 검증이 모두 통과한 후 사이트를 만든다. 실제 Pages 주소는
`actions/configure-pages`의 출력으로 문서 사이트에 주입한다. 배포 서명의 신뢰 정책은
공식 저장소 ID·소유자 ID·workflow와 공개 설치 주소를 의도적으로 고정한다.
fork는 이 신뢰 정책과 배포 주소를 검토해 변경해야 한다.
실제 배포 성공 여부는 원격 Actions 실행 결과에서 확인한다.

## 사용자가 실행하는 명령

먼저 [공식 GitHub CLI](https://cli.github.com/)와 Python 3.10 이상을 준비한다.
[설치 안내 사이트](https://joongi007.github.io/joongi-skills/)의 OS별 명령은 bootstrap·attestation을
임시 디렉터리에 받고 `gh attestation verify`가 성공한 뒤에만 bootstrap을 실행한다.
처음 복사하는 명령은 공식 저장소의 `site/install.js`와 대조한다.

검증하지 않은 다운로드 파일을 바로 실행하는 예전 설치 명령은 사용하지 않는다.
PowerShell 명령은 자식 프로세스에만 실행 정책 예외를 적용하며 전역 정책을 바꾸지 않는다.
로컬 checkout을 신뢰하고 설치하는 방법은 [클론에서 설치](00-index.md#클론에서-설치)를 따른다.

## CORS와 다운로드 검증

터미널의 `curl`·Python 다운로드에는 브라우저 CORS가 적용되지 않는다.
브라우저 안내 페이지가 localhost의 설치 API를 호출하는 기능은 제공하지 않으므로,
원격 사이트에 로컬 제어 권한을 열 필요가 없다. 로컬 관리 UI는 Hub와 같은 출처에서 제공한다.

부트스트랩은 `bundle-manifest.json`과 고정 파일명 `joongi-skills.tar.gz`를 HTTPS로 받고,
SHA256·다운로드 크기·압축 해제 크기·파일 개수·경로·링크를 검사한 뒤 설치기를 실행한다.
체크섬 외에 Sigstore 서명·인증서·출처·현재 main commit 검증이 필수다.
서명이 없거나 검증기가 없으면 실행·압축 해제를 하지 않는다.
원격 업데이트도 설치된 검증기로 같은 정책을 적용한다. [세부 신뢰 정책](../operations/10-security-boundaries.md#다운로드-실행-전-서명-검증).

## 배포 산출물 로컬 확인

```bash
python3 -m pip install --require-hashes --only-binary=:all: -r requirements-docs.txt
npm ci
npx playwright install chromium --only-shell
python3 scripts/build_pages.py --out /tmp/joongi-pages-preview --base-url https://example.invalid/joongi-skills
node scripts/render_mermaid.mjs /tmp/joongi-pages-preview
python3 -m http.server 8080 --directory /tmp/joongi-pages-preview
```

페이지를 열어 레이아웃과 상대 링크를 확인한다. HTTP 미리보기에서는 클론 설치 명령을 보여준다.
생성한 bootstrap의 다운로드 주소는 예시이므로 원격 설치 검증에는 실제 HTTPS 배포 주소가 필요하다.
출력 디렉터리가 이미 존재하면 실수로 덮어쓰지 않고 중단한다.

개인 설정·환경 파일·키 파일은 공개 번들과 정적 사이트에서 제외한다. 소스 tar의 사용자·그룹·
수정 시각 헤더도 초기화한다. GitHub CI는 현재 파일·커밋 이력·압축 해제한 설치 번들을
Gitleaks로 검사하며 로그의 탐지 값은 마스킹한다. 탐지되지 않았다고 모든 개인정보 부재를 보장하지는 않는다.
업로드 전 [공개 전 점검](03-publication.md)을 따른다.

## 배포한 설치 파일 검증

Pages workflow는 배포 후 Linux·Windows에서 실제 공개 URL을 다시 내려받아 검증한다.
공백·한글이 포함된 임시 홈에 설치하고 stdio 검색, 원격 업데이트와 새 에이전트 감지,
설치된 관리 명령의 자기 제거, 사용자 파일·Hub 상태 보존까지 확인한다. 실제 사용자 설정은 사용하지 않는다.

배포한 커밋의 checkout에서 수동으로도 재현할 수 있다.

```bash
python3 -B tests/pages_live_smoke.py --base-url https://joongi007.github.io/joongi-skills
```

Windows에서는 같은 명령의 `python3` 대신 `py -3`을 사용한다.
bootstrap과 설치 런타임이 검토한 소스와 일치해야 통과한다.

출처: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), 조회 2026-11-05.

## Markdown 문서를 사이트에서 읽기

설치 페이지의 **문서** 메뉴는 같은 사이트의 `read/docs/00-index.html`로 이동한다.
README와 `docs/`, `skills/`, `refs/`의 공개 Markdown을 빌드 시 HTML로 변환한다.
문서 목록·접을 수 있는 본문 목차·제목 앵커·표·코드를 제공하며 JavaScript 없이 읽고 이동할 수 있다.
문서 사이의 상대 링크와 앵커는 HTML 경로로 바꾸고, 원문·JSON·라이선스 등은 GitHub 링크로 유지한다.

원본 `.md`만 수정해 main에 병합하면 기존 Pages CI가 검사 → HTML·설치 번들 생성 → 배포를 수행한다.
`requirements-docs.txt`의 Markdown 변환 패키지는 빌드·개발 검사 전용이며 버전과 wheel 해시를 고정한다.
Hub 실행과 사용자 설치에는 추가 Python 패키지가 필요하지 않다. 생성 HTML은 Git에 커밋하지 않는다.

HTML 태그 실행은 끄고, 계약 검사 주석과 스킬의 frontmatter는 읽기 화면에서 생략한다.
일반 코드 블록은 원문을 표시한다. `mermaid` 코드 블록은 빌드 시 SVG로 변환해 이미지로 보여주고,
접힌 **도표 원문**도 제공한다. 읽는 브라우저에는 Mermaid JavaScript를 배포하지 않는다.
Node 22·Playwright Chromium·Mermaid·DOMPurify는 빌드·검사 전용이며 Hub 실행에는 필요하지 않다.

Mermaid는 `securityLevel: strict`, HTML label 비활성화, 외부 통신 차단 상태에서 실행한다.
원문의 init directive·YAML 설정·click 기능을 거절하고, 생성 SVG를 DOMPurify로 정리한 뒤
script·이벤트·foreignObject·링크·외부 이미지·외부 CSS 참조를 제거하거나 거절한다.
완성 문서는 SVG를 `<img>`로 읽으며 CSP에서 스크립트 실행을 허용하지 않는다.
원문 16,000자·간선 256개·빌드당 도표 128개·도표당 15초 제한을 둔다.
지원하지 않거나 안전 검사에 실패한 도표는 CI를 실패시키므로 원문을 수정해야 한다.
이 설정은 공개 Pages 문서에 적용하며 로컬 Hub의 동적 Markdown 읽기에는 Mermaid를 추가하지 않는다.
문서 전체의 HTML 링크·제목 앵커, 사설 경로 제외와 JavaScript 없는 브라우저 탐색을 CI에서 검증한다.

변환 설정 근거: [markdown-it-py의 HTML 비활성화 지침](https://markdown-it-py.readthedocs.io/en/latest/security.html).

Mermaid 설정 근거: [공식 보안 수준 설명](https://mermaid.js.org/config/usage),
[secure 설정](https://mermaid.js.org/config/schema-docs/config.html).
