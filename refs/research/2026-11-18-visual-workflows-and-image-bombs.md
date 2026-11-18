# 이미지 자원 제한과 시각 제작 자료 조사

확인일: 2026-11-18. 원문 복사가 아닌 요약·채택 판단이다. 원격 저장소의 main은 변경될 수 있다.
기존 스킬 2개를 보완하고 `creating-diagrams` 독립 지침을 추가했다. 외부 스킬 원문·코드·에셋은 번들에 복제하지 않았다.

| 1차 자료 | 확인한 기능·한계 | 채택 |
|---|---|---|
| [Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html) | lazy open·픽셀 경고/오류, 실제 load와 구분 | web-security §4.2의 치수 사전 검사·격리·누적 자원 제한 |
| [OWASP Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | 형식·크기·권한·저장·서비스 거부 방어의 다층 검사 | 바이트 검사를 디코딩 제한의 대체로 보지 않음 |
| [awesome-shelf](https://github.com/joongi007/awesome-shelf) | open-design·awesome-design-md·Excalidraw·diagram-design 후보 발견 | 후보를 실제 원본 자료와 대조 |
| [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) | 웹사이트 분석 기반 DESIGN.md 모음 | 여러 후보 비교 후 프로젝트 정책 하나 선택 |
| [diagram-design](https://github.com/cathrynlavery/diagram-design/tree/main/skills/diagram-design) | MIT, HTML/SVG 다이어그램 스킬; 글꼴·배치 등 고유 취향 포함 | 다이어그램 방법론 참고; 전체 유형·스크립트·원본 자동 설치 안 함 |
| [anatomy](https://github.com/wheresryan22/anatomy) | MIT, 등각 SVG 기술 설명·선택 WebGL·상호작용 | 투영·깊이·모델 일치 참고; 모든 그림에 입체 표현 강제 안 함 |
| [Excalidraw](https://github.com/excalidraw/excalidraw) / [export API](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/utils/export) | 편집기·scene·SVG/PNG export; repo URL은 MCP 주소 아님 | 원본과 렌더를 함께 제공하는 선택형 workflow |
| [snapdom](https://github.com/zumerlab/snapdom) | MIT DOM 캡처, browser 필요·CORS·foreignObject·민감 필드 주의 | capture 참조; 상시 MCP나 런타임 의존성 추가 안 함 |

## 등록 비용 판단

Hub의 지연 검색은 외부 도구 목록 전체를 시작 시 주입하는 비용을 줄인다.
그러나 native 스킬은 클라이언트가 이름·설명을 먼저 로드할 수 있고 검색 결과·선택 후 본문은 토큰을 쓴다.
후보 증가에 따라 검색 모호성·인덱스 작업·유지보수·권한·공급망 비용도 남는다.
연결한 MCP의 실행 비용과 단순 스킬 파일 등록 비용은 다르다.
이번에는 상시 MCP 없이 구분되는 제작 스킬 하나와 선택형 참조를 추가했다.
검색 성능 향상 수치는 측정하지 않았으며, 등록 개수만으로 속도·정확도 향상을 주장하지 않는다.
