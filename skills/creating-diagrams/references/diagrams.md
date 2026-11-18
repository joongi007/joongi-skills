# 형식 선택과 편집 가능한 산출물

| 요구 | 우선 검토 | 원본과 출력 |
|---|---|---|
| Git에서 관리하는 구조·흐름·시퀀스·상태 | Mermaid | `.mmd` + 검증한 SVG/PNG 또는 Markdown |
| 화이트보드 재배치·손그림 느낌·공동 편집 | Excalidraw | `.excalidraw` scene + SVG/PNG |
| 발표·문서용 정밀 배치·브랜드 스타일 | SVG / HTML+SVG | 독립 원본 + SVG/PNG |

Mermaid를 선택했다면 노드 ID·레이블·분기·방향을 구분하고 렌더러 버전으로 구문을 확인한다.
긴 문장은 줄이되 조건과 예외를 지우지 않는다. 그림이 복잡하면 시점이나 책임 경계로 나눈다.
이 저장소의 문서 빌드는 `scripts/render_mermaid.mjs`로 정적 SVG를 만든다.
이 스크립트는 사이트 빌드용이며 일반 `.mmd` 변환 CLI가 아니다. 다른 프로젝트는 그 프로젝트의
기존 렌더러나 버전 고정된 Mermaid CLI를 사용한다.

## Excalidraw

[Excalidraw](https://github.com/excalidraw/excalidraw)는 편집기이며 그 저장소 URL 자체가 MCP endpoint는 아니다.
사용 가능한 로컬 편집기·SDK·검토한 MCP가 있으면 재사용한다. 없으면 도구 준비 여부를 밝히고,
사용자가 Excalidraw를 지정했다면 임의로 Mermaid 결과만 내지 않는다.

- scene 요소는 현재 SDK의 `convertToExcalidrawElements` 등 공식 생성 API로 구성한다.
  컨테이너·텍스트·화살표 binding, files와 appState를 보존한다. 수작업 JSON은 실제 편집기로 열어 검증한다.
- 편집기에서 JSON scene을 저장하거나 SDK의 직렬화 API로 `.excalidraw` 원본을 만든다.
- [공식 export API](https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/utils/export)의
  `exportToSvg` 또는 `exportToBlob`을 사용한다. 브라우저·폰트·이미지 files가 준비된 상태에서 실행한다.
- 출력 폭·높이·배율을 제한하고 PNG 생성 전 총 픽셀을 확인한다. JSON 원본 저장은 PNG 렌더 성공을 뜻하지 않는다.
- 원본 재열기, 연결된 도형 이동 시 화살표·레이블 유지, 이미지 누락, 목표 크기의 글자 가독성을 확인한다.
- 외부 웹 편집기로 올리는 동작은 로컬 파일 생성과 별개다. 공유 링크·클라우드 저장은 요청한 경우에만 한다.

## SVG/HTML과 diagram-design 참고

[diagram-design](https://github.com/cathrynlavery/diagram-design)은 HTML+SVG 중심의 에이전트 스킬이다.
그대로 설치하지 않고 여기서는 설명의 초점·레이아웃·브랜드 일관성 접근을 선택적으로 사용한다.
원본의 전체 유형 라이브러리·검사 도구가 필요하면 해당 버전·라이선스·스크립트를 별도로 검토해 도입한다.

- 제목·읽는 순서·중요 관계를 먼저 배치하고 색상 외에 레이블·선 형태로도 구분한다.
- 독립 SVG는 `viewBox`, 의미 있는 title/desc, 필요한 로컬 글꼴 대체를 제공한다.
- 문서에 넣을 SVG는 script·이벤트 handler·외부 리소스·불필요한 foreignObject를 제거한다.
  HTML을 SVG로 감쌌다고 모든 문서 도구에서 벡터로 편집되는 것은 아니다.
- 원본과 PNG의 배경·테마·font·출력 크기를 기록한다. 실제 이미지를 열어 렌더 결과를 확인한다.
