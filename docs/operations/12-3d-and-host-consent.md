# 3D 작업과 GUI 호스트 승인 사용 예시

문서 ID: OPS-3D-HOST-CONSENT · 작성일: 2026-11-18

## 이미지에서 Three.js 모델 만들기

사용자 요청 예시: “이 의자 사진으로 회전해서 볼 수 있는 Three.js 모델을 만들어줘.”

1. 에이전트가 `hub_search(query="building-procedural-3d", kind="skill")`로 찾고
   `hub_read_skill(name="building-procedural-3d")`와 선택된 참조를 읽는다.
2. 실제 이미지를 보고 구성요소·특징·불확실한 면·카메라·성능 예산을 기록한다.
3. blockout부터 한 단계씩 구현하고 프로젝트 preview에서 실제로 렌더·캡처·비교한다.
4. `hub_3d_review(target_stage="blockout", report=...)`로 manifest를 검사한다.
   이전 단계 누락·연결되지 않은 detail·증거 누락·거절된 review가 있으면 `status: blocked`다.
5. 최적화까지 통과하면 모델 factory·preview·증거·측정·알려진 근사를 함께 전달한다.

입력 예시는 [스킬의 workflow](../../skills/building-procedural-3d/references/workflow.md)에 있다.
도구 결과의 `verification: manifest_only`는 **제출 기록 검사**를 뜻한다. 파일 존재·이미지 유사도·
실제 성능 측정의 진위까지 인증하지 않는다. 숫자만 바꿔 통과시키지 말고 실제 실패를 고친다.
스킬이 모델의 모든 행동을 강제하지도 않는다. 중요한 정확도는 사용자 수용 검사를 포함한다.

[img2threejs](https://github.com/img2threejs/img2threejs)는 원본 skill·forge·플러그인을 제공한다.
이 저장소는 그 방법을 참고한 독립 스킬과 작은 manifest 검사를 제공하며, upstream 엔진을
vendoring하거나 원본 스크립트를 실행하지 않는다. 전체 원본 파이프라인이 필요하면 별도 설치를 검토한다.

## GUI 앱 안에서 호출 선택

일반 MCP Apps iframe의 버튼만으로 승인 도구를 만들면 모델도 같은 도구를 호출할 수 있다.
`visibility: app`만으로 사용자 조작이 서버에 증명되지는 않으므로 관리 토큰·브라우저 capability나
범용 `approve` 도구를 앱에 전달하지 않는다.

대신 Hub가 직접 관리하는 승인에는 공식 **form elicitation**의 호스트 사용자 입력 채널을 사용한다.

| 연결 | 동작 |
|---|---|
| stdio·2025-11-25·`elicitation.form` 또는 legacy `elicitation: {}` | 호스트가 앱 안에 선택 폼을 표시. 체크한 요청을 한 번만 승인하고 현재 호출은 같은 wire 요청으로 재개 |
| 2026-07-28·form 미지원·URL만 지원 | 기존 로컬 브라우저 승인함 사용 |
| HTTP 직접 연결·Tasks 승인 | 기존 승인 흐름 유지. 호스트 폼으로 지원을 확대했다고 주장하지 않음 |
| 폼 오류·45초 대기·너무 큰 검토 자료 | 호출을 실행하지 않고 정상 승인 대기로 반환. 사용자 요청 시 브라우저 승인함을 명시적으로 열 수 있음 |

예를 들어 Notion 페이지 조회가 막히면 앱은 “notion · notion-fetch”와 인수·연결 주소를 보여준다.
기본 체크는 모두 꺼져 있다. 현재 범위에서 최대 8개 요청의 snapshot을 고를 수 있고,
나중에 들어온 요청은 포함하지 않는다. 폼은 한 번 허용만 지원하며 1시간·항상 허용은 브라우저에서 선택한다.
사용자가 거절·취소하면 해당 호출을 실행하지 않는다. 모델이 승인됐다고 텍스트를 보내거나
일반 도구 인수에 `approve: true`를 넣어도 승인되지 않는다.

호스트가 실제 사람에게 폼을 보여주는 것은 클라이언트의 신뢰 경계다. 악성 호스트나 동일 OS 사용자
권한의 임의 코드까지 사용자 입력 채널이 방어하는 것은 아니다. 로그인 비밀번호·API key·OAuth 토큰은
이 폼으로 받지 않고 기존 OS 저장소·OAuth 브라우저 흐름을 유지한다.

이 기능은 Apps 렌더러와 별개다. GUI 앱이라고 반드시 form을 지원하는 것은 아니며, 지원하지 않는
클라이언트에 UI를 주입할 수 없다. 외부 MCP의 일반 elicitation/sampling 프록시까지 구현한 기능도 아니다.

## 검증 범위

- `tests/test_sculpt_review.py`: 단계 누락·순서·구성요소 연결·잘못된 수치·예산 초과·실제 Hub 검색/호출.
- `tests/test_native_consent.py`: 협상된 form·현재 snapshot·입력 위조·거절·상태 변경·request ID·취소·메시지 보존.
- `tests/sdk_native_consent.cjs`: 공식 SDK stdio에서 수락 후 정확히 한 번 실행, 거절·취소 후 실행 0회,
  브라우저 자동 실행 0회. 특정 GUI 제품 UI를 직접 자동화한 결과는 아니다.

공식 근거: [MCP form elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation),
[MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview).
