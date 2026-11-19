# 문서 안내

Joongi Skills & Hub는 AI 에이전트에 공통 지침을 설치하고 여러 MCP 연결을 관리하는 로컬 도구입니다.
처음 방문했다면 **[처음 사용하기](getting-started/00-index.md)**에서 준비·설치·연결 확인 순서로 시작하세요.
개발자의 대화 기록이나 개인 MCP 설정은 필요하지 않습니다.

## 사용자를 위한 안내

| 필요한 일 | 읽을 문서 |
|---|---|
| 간편 설치·업데이트·제거 | [설치 안내](installation/00-index.md) |
| 최초 스크립트도 실행 전에 검증 | [보안 설치](installation/04-verified-install.md) |
| 어떤 스킬이 설치되는지 확인 | [README의 스킬 목록](../README.md#함께-설치되는-스킬) |
| 관리 화면 열기·끄기·stdio/HTTP 선택 | [연결 방식과 웹 UI](operations/06-connection-modes.md) |
| MCP 등록·연결·로그인·호출 승인 | [첫 연결 순서](getting-started/00-index.md#4-외부-mcp-등록연결로그인하기) · [인증 상세](operations/05-auth-project-skills.md) |
| 스킬·등록 MCP·연결 도구 검색 | [검색 → 상세 → 호출](operations/08-catalog-search.md) |
| 회사·개인 스킬, 묶음 on/off, 사용 통계 | [검색 설정과 출처](operations/14-catalog-preferences.md) |
| 다이어그램·아이콘·3D 제작 | [시각 자료 제작](operations/13-visual-workflows.md) · [3D와 호스트 승인](operations/12-3d-and-host-consent.md) |
| 연결이 안 되거나 목록이 다름 | [장애 확인](operations/00-index.md#장애-확인) · [상태 저장소](operations/07-state-consistency.md) |
| 지원 기능과 보안 한계 확인 | [호환성](architecture/02-compatibility.md) · [보안 경계](operations/10-security-boundaries.md) |

설치된다는 것과 외부 서비스에 연결·로그인된다는 것은 다릅니다. 최초 설치의 외부 MCP 목록은 비어 있습니다.
이 프로젝트의 스킬 5개는 작업 지침이며 외부 편집기·엔진 전체를 자동 설치하지 않습니다.

## 기여자와 운영자를 위한 안내

| 목적 | 읽을 문서 |
|---|---|
| 제품 목적·요구사항 | [제품 방향](01-vision.md) · [범위와 수용 조건](02-scope.md) |
| 구조·프로토콜 계약·설계 이유 | [아키텍처](architecture/00-index.md) · [설계 결정](adr/00-index.md) |
| 코드 변경·작업 분할·검증 | [개발 절차](development/00-index.md) · [테스트 준비](development/02-quality.md) |
| 스킬 수정·패키징 | [작성 규칙](skill-authoring.md) · [패키징](development/04-skill-packaging.md) |
| 직접 Pages 배포·공개 점검 | [배포 절차](installation/02-github-pages.md) · [공개 전 점검](installation/03-publication.md) |
| 과거 시험과 검수 결과 | [날짜별 검증 기록](development/03-verification.md) · [보안 검수](operations/09-security-audit.md) |
| 제안과 미구현 기능 | [백로그](development/05-backlog.md) |

문서의 명령은 별도 표시가 없으면 저장소 루트 또는 설치한 사용자의 터미널에서 실행합니다.
`/path/to/...`, `/절대/...`는 사용자의 실제 경로로 바꿔야 하는 예시입니다.
날짜가 있는 검증·조사 기록은 그 시점의 증거이며 현재 실행 상태나 테스트 수를 뜻하지 않습니다.
최신 원격 결과는 [GitHub Actions](https://github.com/joongi007/joongi-skills/actions)에서 확인하세요.
폴더의 숫자는 읽는 순서이고, 하위 주제는 각 폴더의 `00-index.md`에서 안내합니다.
