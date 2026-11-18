# 다이어그램·아이콘과 시각 자료 제작

기본 스킬 `creating-diagrams`는 도구 선택·제작·실제 렌더 검토를 안내합니다.
`applying-design-systems`는 제품 디자인 정책과 토큰 선택을 담당합니다.
외부 스킬 원문·Excalidraw 편집기·snapdom 패키지·새 MCP 서버는 포함하지 않습니다.

## 이렇게 요청하세요

| 요청 예시 | 선택 경로 | 완료 시 확인 |
|---|---|---|
| “이 서비스 구조를 Git 문서에 넣어줘” | Mermaid 우선 검토 | 원본, 관계와 실제 렌더 |
| “내가 도형을 옮길 수 있게 Excalidraw로 줘” | 사용 가능한 Excalidraw 편집기/SDK | 재열리는 scene + SVG/PNG |
| “발표용으로 보기 좋은 다이어그램을 만들어줘” | 토큰을 적용한 SVG/HTML | 원본, 목표 크기의 이미지 |
| “이 장치의 부품 구조를 입체적으로 설명해줘” | anatomy를 참고한 등각투영 SVG | 투영·부품·연결과 범례 |
| “웹 앱용 아이콘을 만들어줘” | 기존 icon set 또는 일관된 SVG | 실제 작은 크기, 원본·export |
| “앱의 이 카드만 PNG로 저장하게 해줘” | 기존 캡처 또는 snapdom 도입 검토 | 개인정보 제거, CORS, 치수·출력 검증 |

Hub에서는 `hub_search(query="Excalidraw", kind="skill")`로 찾은 뒤
`hub_read_skill(name="creating-diagrams")`으로 읽습니다. 참조 경로는 반환된 routing에 따라 읽습니다.
순수 stdio에서도 스킬 검색·읽기가 가능하며 이를 위해 HTTP 관리 화면을 켤 필요가 없습니다.
이 스킬 자체가 도형을 렌더하는 MCP 도구는 아닙니다. 에이전트가 현재 환경의 도구로 제작합니다.
도구가 없으면 준비가 필요한 부분을 알리고 렌더를 했다고 주장하지 않습니다.

## 디자인 자료는 여러 개, 프로젝트의 기준은 하나

기존 DESIGN.md·컴포넌트·토큰을 먼저 사용합니다. 새 프로젝트라면 open-design과
awesome-design-md 같은 자료에서 후보를 좁혀 비교합니다. 선택한 기준·출처·버전·예외를 남기고
다이어그램과 아이콘도 같은 토큰에 맞춥니다. 모든 정책의 팔레트와 폰트를 한꺼번에 섞지 않습니다.
[디자인 정책 선택](../../skills/applying-design-systems/references/design-policies.md).

## 등록 개수와 비용

Hub 검색은 모든 외부 도구 schema를 항상 주입하는 비용을 줄입니다. 하지만 검색 결과·선택 후 본문,
native 스킬의 이름·설명, 검색 모호성·유지보수 비용은 남습니다. MCP 연결은 실행 자원과 권한도 필요합니다.
`creating-diagrams`는 제작 지침과 선택형 참조를 제공하며 외부 MCP 프로세스나 렌더 의존성을 포함하지 않습니다.
새 도구가 필요해지면 실행 위치·정확한 패키지/버전·권한·파일 접근·업로드 여부를 검토해 선택합니다.

이미지 입력의 자원 제한은 [web-security §4.2](../../skills/engineering-playbook/references/web-security.md#42-이미지-압축-폭탄-메타데이터)를 확인하세요.
