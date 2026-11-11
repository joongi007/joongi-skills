# 문서 안내

처음 사용한다면 아래에서 목적에 맞는 경로를 고르세요. 전체 문서를 순서대로 읽을 필요는 없습니다.

| 지금 필요한 일 | 시작점 |
|---|---|
| 내 에이전트에 설치 | [설치·업데이트·제거](installation/00-index.md) |
| 설치 후 첫 사용 | [README의 첫 사용 안내](../README.md#설치-후-첫-사용) |
| 웹을 켜고 끄거나 연결 문제 해결 | [연결 방식](operations/06-connection-modes.md) · [장애 확인](operations/00-index.md) |
| 지원 여부 확인 | [기능별 호환성](architecture/02-compatibility.md) · [검증 기록](development/03-verification.md) |
| 스킬을 직접 수정 | [작성 규칙](skill-authoring.md) · [패키징](development/04-skill-packaging.md) |

기여자: [제품 방향](01-vision.md) → [범위·수용 조건](02-scope.md) →
[구조](architecture/00-index.md) → [개발 절차](development/00-index.md).

| 문서 | 답하는 질문 |
|---|---|
| [vision](01-vision.md) | 누구의 어떤 문제를 해결하는가 |
| [scope](02-scope.md) | 무엇을 제공하고 무엇을 검증해야 하는가 |
| [architecture](architecture/00-index.md) | 경계·상태·버전 호환성·보안은 어떻게 동작하는가 |
| [ADRs](adr/00-index.md) | 왜 이 구조를 선택했는가 |
| [development](development/00-index.md) | 사람·에이전트가 어떤 단위로 나눠 검증하는가 |
| [operations](operations/00-index.md) | 실행·장애 확인·복구를 어떻게 하는가 |
| [installation](installation/00-index.md) | 배포·설치·업데이트·제거를 어떻게 하는가 |
| [skill-authoring](skill-authoring.md) | 스킬과 참조 자료를 어떻게 작성하는가 |
| [local-inventory](operations/03-local-inventory.md) | 로컬 프로젝트의 MCP·스킬 출처를 어떻게 모으는가 |

숫자는 해당 폴더의 읽는 순서다. 독립 주제가 되면 하위 폴더와 `00-index.md`를 만든다.
문서 ID·요구사항 ID·ADR ID는 경로 변경에도 유지한다. 현재 계약은 코드·테스트와 함께
갱신하고, 제안은 확정된 동작과 구분해 적는다.
