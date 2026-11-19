# 설계 결정

| ID | 상태 | 결정 |
|---|---|---|
| [ADR-0001](0001-local-runtime.md) | accepted | 의존성 없는 단일 사용자 로컬 실행 |
| [ADR-0002](0002-protocol-boundaries.md) | accepted | wire 버전·확장과 core 경계 분리 |
| [ADR-0003](0003-managed-installation.md) | accepted | manifest 기반 agent 설치·보존 |
| [ADR-0004](0004-bundled-extensions.md) | accepted | vendored YAML과 공식 SDK 기반 Apps 호스트 |
| [ADR-0005](0005-native-tool-proxy.md) | 부분 대체 | native 도구 발견과 버전별 Tasks·App view 소유권 |
| [ADR-0006](0006-upstream-auth-scoped-skills.md) | accepted | upstream 인증·프로젝트 범위·검토한 스킬 설치 계획 |
| [ADR-0007](0007-explicit-connection-modes.md) | accepted | 명시적 연결 방식·선택적 웹 실행·범위 고정 |
| [ADR-0008](0008-persistent-state-identity.md) | accepted | 연결 방식과 독립된 영구 등록·경로 진단·백업 복구 |
| [ADR-0009](0009-project-selecting-graph.md) | accepted | 공용 코드 그래프의 명시적 프로젝트 선택·DB 분리 |
| [ADR-0010](0010-lexical-catalog-search.md) | 부분 대체 | 메타데이터 어휘 검색·선택적 정규식·검색 범위 안내 |
| [ADR-0011](0011-local-credential-boundaries.md) | accepted | OS 인증 저장소·로컬 HTTP 자격증명·호출 승인 |
| [ADR-0012](0012-enforced-security-boundaries.md) | accepted | 외부 MCP 실행 격리·배포 provenance·로컬 세션 자동 교체 |
| [ADR-0013](0013-owner-host-consent.md) | accepted | 모델 호출 도구와 분리된 호스트 form 입력 승인 |
| [ADR-0014](0014-installation-trust-and-onboarding.md) | accepted | 간편 설치·실행 전 서명 확인의 신뢰 차이와 첫 사용 안내 |
| [ADR-0015](0015-search-first-catalog.md) | accepted | 전송 공통 검색 중심 노출·정확한 상세·선택형 출처·분류·통계 |

새 결정은 맥락·선택·대안·결과·검증을 포함한다. 상태가 바뀌면 대체 ADR을 연결한다.
