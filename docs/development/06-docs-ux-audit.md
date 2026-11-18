# 문서·설치·웹 UX 점검 기록

점검일: 2026-11-19. 대상 독자는 이 프로젝트의 대화 기록과 개발자의 컴퓨터 설정을 모르는 사람이다.
이 문서는 제품 설명과 검사 이력을 구분하기 위한 유지보수 기록이며, 사용자 시작점은 [처음 사용하기](../getting-started/00-index.md)다.

## 조사 범위와 방법

README와 `docs/`의 모든 Markdown을 목록화하고 제목·독자·명령 예시·대화 의존 표현·현재/과거 상태 설명을 점검했다.
공개 `skills/`·`refs/`도 경로·routing·링크·대화 의존 표현 검색 대상에 포함했다.
그 중 설치·첫 사용·인증·승인·상태·검색·배포·웹 안내의 사용자 경로는 구현과 함께 대조해 수정했다.
아래 목록이 문서별 점검 범위다. 날짜별 실험·ADR의 과거 결정을 현재 구현으로 덮어쓰지는 않았다.

자동 링크·앵커·명시적 계약 검사는 전체 공개 문서에 적용한다. 이런 검사는 모든 문장의 사실성,
모든 외부 링크의 가용성, 제3자 서비스의 최신 기능을 증명하지 않는다. 새 외부 제품 기능 조사는 이번 범위가 아니다.

## 발견한 문제와 반영

| 문제 | 사용자가 겪는 혼란 | 수정 |
|---|---|---|
| 긴 서명 검증 코드가 기본 화면을 차지 | 첫 설치에 필요한 행동을 찾기 어려움 | OS별 한 줄 명령을 기본, 기존 보안 설치를 펼침 메뉴·별도 문서로 제공 |
| 설치 방식별 신뢰 차이가 불명확 | 간편 실행도 최초 스크립트까지 사전 검증한다고 오해 | 최초 bootstrap과 archive의 검증 시점을 README·설치·보안·ADR에 일치시킴 |
| 설치 전제와 다음 행동이 흩어짐 | Python/gh 준비·연결 재열기·빈 MCP 목록에서 막힘 | 준비 표·첫 사용 안내·설치 후 검색 확인 제공 |
| 대화에서 쓰던 가계부·개인 경로 | 예시가 특정 사용자 설정에 의존하는 것처럼 보임 | 일반 문서·교체 가능한 경로로 변경, 환경 차이 명시 |
| 과거 결과에 현재 상태라는 제목 사용 | 예전 테스트 수·개인 연결을 새 설치의 기본값으로 오해 | 날짜별 스냅샷과 최신 CI 확인 경로 구분 |
| HTTP 등록·앱 내 승인 설명 불일치 | 토큰을 수동 복사하거나 브라우저가 반드시 필요하다고 오해 | 관리되는 credential bridge와 수동 native 설정, 협상한 form 승인 조건 구분 |
| 추가 스킬이 공개 소개와 관리 화면에 빠짐 | 설치된 다이어그램 지침을 찾기 어려움 | 5개 스킬 목록·사람용 이름·실제 제작 예시 연결 |
| ADR·작업 단위 표 중간의 빈 줄 | 표 일부가 일반 문장처럼 렌더됨 | 연속된 Markdown 표로 정리 |
| Windows inline 설치가 호출한 터미널까지 종료 | 설치 후 계속 작업하기 어려움 | 성공 시 caller로 반환, 실패는 오류로 전달. 수정 전 실패·수정 후 성공 확인 |
| 짧은 실행 명령이 파일 경로를 갖지 않음 | 작업 폴더/상위 스크립트의 설치기를 잘못 선택할 위험 | Bash 파이프·PowerShell scriptblock은 원격 경로만 사용, 회귀 검사 추가 |

## UI와 실제 검증

- 기존 open-design GitHub 토큰·시스템 글꼴을 유지하고 설치를 앞에 배치했다.
- 명령 원문은 가로 스크롤로 보존한다. 보안 설치·클론 설치는 접고, 위험 차이는 항상 보이게 둔다.
- 복사 성공·클립보드 실패 시 선택과 다음 행동, 탭 방향키·Home/End·펼침 키보드를 검사했다.
- 주요 복사 버튼은 44px 이상이다. 320/390/768/1440px에서 페이지 전체 가로 넘침이 없는지 검사했다.
- 모바일 제목의 한국어 단어 잘림을 수정하고 반복된 박스 대신 순서 목록으로 예시를 정돈했다.
- 실제 데스크톱·모바일 캡처를 열어 확인했다. 로컬 한글 폰트를 쓴 미리보기는 검증용이며 배포 자산이 아니다.
- 문서는 JavaScript 없이 탐색·목차·표·Mermaid 이미지를 읽는 기존 경계를 유지한다.

| 실행 | 결과·범위 |
|---|---|
| Linux Python | 설치·bootstrap·Pages·문서·서명·공개 제외 규칙 46개 실행, 1개 플랫폼 제외, 실패 없음 |
| native Windows Python | bootstrap·설치·서명 39개 실행, 3개 플랫폼 제외, 실패 없음 |
| 브라우저 | `browser_install.cjs`, `browser_docs.cjs`, `browser_smoke.cjs` 통과 |
| 정적 검사 | 스킬 구조·문서 링크·실행 계약·JavaScript 문법·수정 Python Ruff 검사 |
| 실제 공개 설치 | Pages workflow의 배포 후 검사에서 inline bootstrap과 검증한 파일 경로를 각각 확인하도록 확장 |

마지막 행은 배포 후 수행할 검사 계약이다. 로컬 검증만으로 원격 배포가 성공했다고 판정하지 않는다.
외부 접근성 인증·모든 스크린리더·모든 OS/브라우저를 검증한 결과는 아니다.

## 문서별 점검 목록

`docs/` 51개와 README를 사용자 안내·기여자 안내·검증 이력으로 구분했다.

| 문서 | 독자·역할 | 처리 |
|---|---|---|
| [README](../../README.md) | 처음 방문한 사용자 | 목적·간편 설치·보안 선택·5개 스킬·첫 사용 재작성 |
| [00-index.md](../00-index.md) | 사용자 또는 기여자의 문서 진입점 | 읽는 순서·요구사항·용어·참조 확인 |
| [01-vision.md](../01-vision.md) | 사용자 또는 기여자의 문서 진입점 | 읽는 순서·요구사항·용어·참조 확인 |
| [02-scope.md](../02-scope.md) | 사용자 또는 기여자의 문서 진입점 | 읽는 순서·요구사항·용어·참조 확인 |
| [adr/00-index.md](../adr/00-index.md) | 설계 결정의 배경·이력 | 대체·보완 관계 확인; 설치 UX ADR 추가 |
| [adr/0001-local-runtime.md](../adr/0001-local-runtime.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0002-protocol-boundaries.md](../adr/0002-protocol-boundaries.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0003-managed-installation.md](../adr/0003-managed-installation.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0004-bundled-extensions.md](../adr/0004-bundled-extensions.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0005-native-tool-proxy.md](../adr/0005-native-tool-proxy.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0006-upstream-auth-scoped-skills.md](../adr/0006-upstream-auth-scoped-skills.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0007-explicit-connection-modes.md](../adr/0007-explicit-connection-modes.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0008-persistent-state-identity.md](../adr/0008-persistent-state-identity.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0009-project-selecting-graph.md](../adr/0009-project-selecting-graph.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0010-lexical-catalog-search.md](../adr/0010-lexical-catalog-search.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0011-local-credential-boundaries.md](../adr/0011-local-credential-boundaries.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0012-enforced-security-boundaries.md](../adr/0012-enforced-security-boundaries.md) | 설계 결정의 배경·이력 | 대체·보완 관계 확인; 설치 UX ADR 추가 |
| [adr/0013-owner-host-consent.md](../adr/0013-owner-host-consent.md) | 설계 결정의 배경·이력 | 용어·목적·링크 확인; 과거 결정은 날짜와 함께 유지 |
| [adr/0014-installation-trust-and-onboarding.md](../adr/0014-installation-trust-and-onboarding.md) | 설계 결정의 배경·이력 | 대체·보완 관계 확인; 설치 UX ADR 추가 |
| [architecture/00-index.md](../architecture/00-index.md) | 개발자·지원 범위 검토자 | 용어·명시적 구현 계약·설치 신뢰 설명 대조 |
| [architecture/01-components.md](../architecture/01-components.md) | 개발자·지원 범위 검토자 | 용어·명시적 구현 계약·설치 신뢰 설명 대조 |
| [architecture/02-compatibility.md](../architecture/02-compatibility.md) | 개발자·지원 범위 검토자 | 용어·명시적 구현 계약·설치 신뢰 설명 대조 |
| [architecture/03-security.md](../architecture/03-security.md) | 개발자·지원 범위 검토자 | 용어·명시적 구현 계약·설치 신뢰 설명 대조 |
| [architecture/04-contracts.md](../architecture/04-contracts.md) | 개발자·지원 범위 검토자 | 용어·명시적 구현 계약·설치 신뢰 설명 대조 |
| [development/00-index.md](../development/00-index.md) | 기여자·검증 담당자 | 실행 전제·날짜별 증거·현재 상태 구분 확인 |
| [development/01-work-packages.md](../development/01-work-packages.md) | 기여자·검증 담당자 | 실행 전제·날짜별 증거·현재 상태 구분 확인 |
| [development/02-quality.md](../development/02-quality.md) | 기여자·검증 담당자 | 실행 전제·날짜별 증거·현재 상태 구분 확인 |
| [development/03-verification.md](../development/03-verification.md) | 기여자·검증 담당자 | 실행 전제·날짜별 증거·현재 상태 구분 확인 |
| [development/04-skill-packaging.md](../development/04-skill-packaging.md) | 기여자·검증 담당자 | 실행 전제·날짜별 증거·현재 상태 구분 확인 |
| [development/05-backlog.md](../development/05-backlog.md) | 기여자·검증 담당자 | 실행 전제·날짜별 증거·현재 상태 구분 확인 |
| [development/06-docs-ux-audit.md](../development/06-docs-ux-audit.md) | 기여자·검증 담당자 | 실행 전제·날짜별 증거·현재 상태 구분 확인 |
| [getting-started/00-index.md](../getting-started/00-index.md) | 처음 설치한 사용자 | 설치·재연결·빈 목록·외부 등록·인증 순서 신설 |
| [installation/00-index.md](../installation/00-index.md) | 사용자 설치 또는 저장소 배포 담당자 | 준비·실행 위치·신뢰 경계·독자 구분 확인 및 보완 |
| [installation/01-agent-paths.md](../installation/01-agent-paths.md) | 사용자 설치 또는 저장소 배포 담당자 | 준비·실행 위치·신뢰 경계·독자 구분 확인 및 보완 |
| [installation/02-github-pages.md](../installation/02-github-pages.md) | 사용자 설치 또는 저장소 배포 담당자 | 준비·실행 위치·신뢰 경계·독자 구분 확인 및 보완 |
| [installation/03-publication.md](../installation/03-publication.md) | 사용자 설치 또는 저장소 배포 담당자 | 준비·실행 위치·신뢰 경계·독자 구분 확인 및 보완 |
| [installation/04-verified-install.md](../installation/04-verified-install.md) | 사용자 설치 또는 저장소 배포 담당자 | 준비·실행 위치·신뢰 경계·독자 구분 확인 및 보완 |
| [operations/00-index.md](../operations/00-index.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/01-code-graph.md](../operations/01-code-graph.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/02-sdk-interop.md](../operations/02-sdk-interop.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/03-local-inventory.md](../operations/03-local-inventory.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/04-code-review-graph.md](../operations/04-code-review-graph.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/05-auth-project-skills.md](../operations/05-auth-project-skills.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/06-connection-modes.md](../operations/06-connection-modes.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/07-state-consistency.md](../operations/07-state-consistency.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/08-catalog-search.md](../operations/08-catalog-search.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/09-security-audit.md](../operations/09-security-audit.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/10-security-boundaries.md](../operations/10-security-boundaries.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/11-consent-settings-review.md](../operations/11-consent-settings-review.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/12-3d-and-host-consent.md](../operations/12-3d-and-host-consent.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [operations/13-visual-workflows.md](../operations/13-visual-workflows.md) | 설치 후 사용자 또는 운영 검증 담당자 | 명령 전제·환경·현재 동작과 이력 구분 확인 및 관련 흐름 보완 |
| [skill-authoring.md](../skill-authoring.md) | 사용자 또는 기여자의 문서 진입점 | 읽는 순서·요구사항·용어·참조 확인 |
