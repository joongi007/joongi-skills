# ADR-0015: 전송 공통 검색 중심 카탈로그와 선택형 지침

상태: accepted · 날짜: 2026-11-19

## 맥락

일반 도구까지 native 목록에 모두 노출하면 검색 중심으로 사용하려는 요구와 컨텍스트 비용이 충돌한다.
이전 구현의 기본 100개/full, 권장 예시 5개/summary, UI의 20개/summary가 나뉘어 사용 흐름도 불분명했다.
회사·개인 스킬을 기본 제공 지침과 구분하고 필요 없는 디자인 등은 선택적으로 제외할 필요가 있다.

## 결정

[ADR-0005](0005-native-tool-proxy.md)의 전체 native 노출 결정을 기본 search-first로 대체한다.
stdio·HTTP 모두 동일한 Hub 서비스에서 허브 기본 도구와 원본 App·명시적 Task 지원 도구만 직접 노출한다.
App 내부 callback의 원래 이름/namespace와 app-only visibility는 유지한다.
고급 all-native는 선택된 외부 서버의 전체 노출을 명시적으로 요청한 경우에만 사용한다.

검색 기본값은 limit5/summary이며 설명은 한 줄 160자로 제한한다. 전체 schema는
`hub_get_item(kind,name)`의 정확한 상세에서 확인하고 `hub_call`로 실행한다. full 검색은 명시적 호환 옵션으로 남긴다.
검색·상세 조회는 서버를 시작하거나 승인 권한을 주지 않는다. 검색했다는 사실 자체를 실행 인가로 쓰지 않는다.

카탈로그 선택은 범위별 출처·스킬·서버·분류 설정으로 적용한다. 외부 로컬 스킬 폴더는
source ID namespace를 사용해 같은 이름을 구별한다. 비활성 항목은 지원하는 카탈로그 조회 경로에서도 제외한다.
MCP 변경은 local stdio/credential bridge owner에 제한하고 직접 HTTP MCP에는 조회만 허용한다. 로컬 관리 화면은 기존 관리 인증을 사용한다.

metadata 준비 결과는 크기 제한이 있는 프로세스별 2-entry LRU로 재사용한다. 결과·인증·도구 응답은 캐시하지 않는다.
사용 통계는 기본 꺼짐이며 local aggregate만 저장한다. rawquery/args/payload/token/path는 기록하지 않는다.

native 에이전트 설치는 별도 선택이다. 반복 exclude-category를 설치 manifest에 저장해 업데이트에도 유지하며,
reset-skill-selection으로 명시적으로 복원한다. 기존 소유권·수정 보호를 우회하지 않는다.

## 대안과 결과

전체 문서·schema를 처음부터 내보내는 방식과 새 embedding 서버의 상시 도입은 선택하지 않는다.
원본 metadata 준비 캐시는 어휘 검색의 결과 의미를 유지하며, 원본 파일 스캔과 정의 갱신 비용은 남는다.
하나의 소유 파일 집합으로만 출처를 나누거나 Hub에서 숨겼다고 native 사본을 지우는 방식도 선택하지 않는다.
끄기 선택은 discovery/스킬 조회 정책이다. 이미 알고 있는 도구의 직접 호출 인가를 대체하지 않으며 기존 승인·격리를 유지한다.
이 기능은 단일 OS 사용자의 선호이며 회사용 다중 사용자 권한 정책을 강제하는 서비스가 아니다.

## 검증과 갱신

전송·프로토콜별 노출과 기본값, exact 상세, 프로필/출처/분류의 일관성, owner 변경 경계,
캐시 불변성·metadata 변경, 통계 비밀 비기록·한도, 설치 제외의 지속·복원을 검증한다.
[독립 계약 감사와 검증 계획](../development/07-catalog-contract-audit.md),
[검색 안내](../operations/08-catalog-search.md), [선호와 통계](../operations/14-catalog-preferences.md)를 함께 갱신한다.
