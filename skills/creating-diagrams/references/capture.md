# DOM 캡처와 이미지 내보내기

[SnapDOM](https://github.com/zumerlab/snapdom)은 브라우저 DOM을 이미지 등으로 내보내는 라이브러리다.
MCP 서버나 디자인 정책이 아니며, 순수 Node.js 프로세스만으로 DOM을 렌더하지 않는다.
상시 서버를 추가하지 말고 현재 프로젝트의 브라우저·캡처 도구를 우선 사용한다.

| 목적 | 선택 기준 |
|---|---|
| 앱 내 특정 요소를 사용자가 이미지로 저장 | snapdom 도입을 검토; 버전 고정·라이선스·번들 영향 확인 |
| 에이전트가 실제 화면을 검사·스크린샷 생성 | 기존 Playwright/브라우저의 screenshot 우선 |
| 편집 가능한 도형·벡터가 필요 | 원본 SVG/Excalidraw export 우선; DOM 캡처와 구분 |

프로젝트에 설치되어 있을 때 사용하는 예시이며, 설치되었다는 뜻은 아니다.

```javascript
import { snapdom } from '@zumer/snapdom';
// 비밀 정보 제거와 폰트·이미지 준비 후 실행한다.
const node = document.querySelector('#diagram');
const image = await snapdom.toPng(node);
// 앱에서 미리보기/다운로드 경로로 전달한다. 실제 출력 치수도 검사한다.
```

- 캡처 전 비밀번호·토큰·개인정보를 DOM과 픽셀에서 가린다. 텍스트 export의 마스킹이 이미지까지
  가린다고 가정하지 않는다. 원본 HTML export에도 숨은 데이터·속성·불필요한 상태를 포함하지 않는다.
- 폰트·이미지 로딩을 기다리고 애니메이션은 재현 가능한 시점에 멈춘다. 원본 화면과 결과를 비교한다.
- CORS는 그대로 적용된다. 외부 이미지·폰트·스타일을 읽지 못하면 로컬 자산이나 허용된 제공 경로를 쓴다.
  우회용 무제한 URL proxy를 만들지 않는다. cross-origin iframe 내부는 캡처할 수 있다고 가정하지 않는다.
- SVG export의 foreignObject는 도구별 지원이 다르다. 출판용 벡터라면 실제 대상 도구에서 확인한다.
- 입력 DOM 크기·출력 폭/높이·DPR/scale·총 픽셀·캡처 시간·동시성을 제한한다.
  긴 페이지를 무제한 canvas로 만들지 말고 분할·페이지화한다.
- 캡처는 sandbox가 아니다. 임의 HTML을 렌더할 때는 별도 브라우저 환경·외부 연결 제한·자격증명 없는
  프로필을 사용하고 사용자의 로그인된 브라우저를 재사용하지 않는다.
