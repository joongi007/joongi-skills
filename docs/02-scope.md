# 범위와 수용 조건

문서 ID: DOC-SCOPE · 작성일: 2026-11-05

아래는 제품 요구사항이다. 구현 파일의 존재만으로 완료 처리하지 않는다.
정확한 프로토콜 경계는 [호환성](architecture/02-compatibility.md), 실제 검증 증거는
[검증 기록](development/03-verification.md)에 기록한다.

| ID | 이번 버전의 결과 | 수용 조건 |
|---|---|---|
| REQ-SKILL | 스킬 검색·단계적 조회 | 설명 검색 후 본문·참조 조회, 경로 이탈 차단 |
| REQ-REGISTRY | MCP 등록·인증·프로젝트 범위 | 영구 경로 고정·등록 백업·명시적 이관, 인증·토큰 갱신, 범위별 격리 |
| REQ-CALL | 연결한 MCP 도구 호출 | 실제 fixture 발견·호출, timeout·오류 격리 |
| REQ-PROTOCOL | 2025·2026 클라이언트와 서버 | 양쪽 버전 조합 테스트, unsupported 명시 |
| REQ-APPS | Apps 정보·리소스 전달 | UI metadata와 resource 출처·URI 유지/매핑 |
| REQ-TASKS | 장기 작업 상태·결과·취소 | 버전별 계약, 허용 상태 전이, 소유 작업 조회 |
| REQ-UI | 로컬 관리 UI | 실제 상태·검색·등록·실패·작업을 표시 |
| REQ-INSTALL | 감지·설치·갱신·제거 | 임시 HOME·프로젝트에서 계획 적용·고정·충돌 보호·롤백 |
| REQ-PAGES | 다운로드용 정적 사이트 | 설치 스크립트·배포 산출물 생성, 로컬 호출 불필요 |
| REQ-KNOWLEDGE | 인프라·문서·테스트 지침 | routing 가능, 원본 §와 일치, 출처 기록 |
| REQ-PROCESS | 병렬 가능한 개발 절차 | 소유 파일·계약·독립 테스트·통합 순서 정의 |

## 경계

Apps의 metadata 전달과 호스트 렌더러 구현을 구분한다. 로컬 관리 UI는 AppBridge 기반
sandbox iframe과 원래 서버에 묶인 callback을 제공한다. 외부 에이전트에서는 해당 호스트가
Apps를 지원해야 하며, 전역 callback 이름이 충돌하면 namespaced 이름을 사용한다.
2025·2026 사이에서 의미를 보존하지 못하는 서버 역방향 요청 등은 거절·제한을 명시한다.
로컬 App HTML에는 opaque origin과 리소스별 CSP·허용 method 정책을 적용한다.
Skills 확장은 안전한 YAML frontmatter와 텍스트·바이너리 supporting file manifest를 제공한다.
파싱 복잡도·파일 크기·경로·symlink·hash 검증 한도는 유지한다.
2026 Tasks의 입력 대기·응답 제출도 지원하며, 별도 sampling/elicitation 기능과 구분한다.

GitHub Pages는 정적 배포 표면이다. Python Hub는 사용자 컴퓨터에서 실행한다.
페이지를 열었다고 자동 설치하거나 개인 설정을 읽지 않는다.
실제 Pages 게시에는 GitHub 저장소와 배포 설정이 필요하다.

멀티 사용자 권한 관리·인터넷 공개·분산 Hub·자동 코드 편집·Kubernetes 운영 배포는
별도 요구사항과 검증 없이 이 버전의 지원 기능으로 광고하지 않는다.
