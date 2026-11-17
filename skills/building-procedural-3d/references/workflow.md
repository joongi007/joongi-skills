# 단계별 작업과 검사 입력

구성요소·식별 특징·렌더 증거를 연결한다. 이 형식은 Hub의 자체 manifest이며 upstream의
ObjectSculptSpec과 호환된다고 주장하지 않는다. 원본의 전체 forge 기능은 포함하지 않는다.

| 단계 | 확인할 결과 |
|---|---|
| blockout | 동일 카메라에서 전체 크기·실루엣·비율 |
| structure | 구성요소 계층·연결·좌우 방향·피벗 |
| form | 곡면·모서리·작은 형상과 특징의 구현 |
| material | 재질 구분·roughness·금속성·색 공간 |
| surface | 표면 디테일과 실제 형상의 구분 |
| lighting | 같은 노출·조명에서 참조와 비교 |
| interaction | 회전·애니메이션·재시작·자원 및 이벤트 정리 |
| optimization | 정한 기기·해상도에서 draw calls·삼각형·프레임 시간 |

각 단계는 `{stage, evidence, accepted, notes}`로 기록한다. `evidence`는 실제 캡처·측정 파일의
경로나 식별자 1~8개, `accepted`는 검토 결과 boolean이다. 검사 도구가 파일을 열거나 실행하지는
않으므로 파일 존재·해시·카메라 조건·실제 이미지 비교는 에이전트와 리뷰어가 별도 확인한다.
상호작용이 없으면 그 이유와 정적 표시·dispose 검사를 interaction 단계에 기록한다.

## 첫 단계 입력 예시

아래는 **입력 형식 예시**다. 경로를 실제로 만든 증거로 바꾸고 검토 후에만 accepted를 true로 둔다.

```json
{
  "target_stage": "blockout",
  "report": {
    "references": ["reference/chair-front.png"],
    "components": [{"id": "seat", "purpose": "좌석의 전체 형상"}],
    "details": [{"id": "rounded-edge", "component_id": "seat", "evidence": ["reference/chair-front.png"], "confidence": 0.8}],
    "passes": [{"stage": "blockout", "evidence": ["review/blockout-front.png"], "accepted": false, "notes": "실제 렌더 비교 후 검토 결과를 기록할 것"}],
    "limitations": ["뒷면 형상은 참조에 보이지 않음"]
  }
}
```

`target_stage` 이전 단계가 없거나 순서가 다르면 blocked다. components의 고유 id에 모든
detail.component_id가 연결되어야 한다. confidence는 0~1이며 bool을 수치로 받지 않는다.
components는 1~256개, details는 1~1024개, 전체 report는 128 KB 이하다.
마지막 단계에서는 `budget`과 `measurements` 모두에 양수 예산과 측정값을 기록한다.

```json
{"budget": {"draw_calls": 80, "triangles": 100000, "frame_ms": 20}, "measurements": {"draw_calls": 32, "triangles": 24000, "frame_ms": 12}}
```

수치는 예시이며 제품 요구사항에 맞춰 정한다. 실측하지 못하면 optimization 통과를 선언하지 않는다.
목표 기기·해상도·브라우저·측정 방식은 해당 pass.notes와 실제 측정 파일에 함께 기록한다.
`status: passed`와 `verification: manifest_only`는 기록의 구조 검사 통과이며 완성품 인증이 아니다.

## 원본 도구를 추가로 사용할 때

img2threejs는 별도의 skill·Python 스크립트·선택형 플러그인을 제공한다. 실제로 그 기능이
필요하면 공식 설치 문서와 라이선스·버전·프로젝트 변경 범위를 검토해 별도로 설치한다.
이 스킬을 읽었다고 원본 도구를 실행했거나 생성 서비스를 이용했다고 표현하지 않는다.
