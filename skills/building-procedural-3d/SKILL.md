---
name: building-procedural-3d
description: 참조 이미지로 Three.js 절차형 3D 오브젝트를 만들거나 재구성할 때 사용한다. 구성요소·식별 특징을 먼저 기록하고 blockout부터 최적화까지 렌더 증거를 비교하며 진행한다. 일반 웹 UI·백엔드·다른 게임 엔진 작업에는 적용하지 않는다.
---

# 이미지 기반 절차형 3D

img2threejs의 명세·단계별 렌더·검토 방식을 참고한 독립 지침이다.
원본 엔진이나 전체 스크립트·도메인 플러그인을 설치한 것이 아니다.

## 시작과 진행

1. 이미지 사용 권한·대상·단위·지원 브라우저·상호작용·성능 예산을 확인한다.
2. 먼저 이미지를 실제로 본다. 관찰할 수 없다면 사진을 본 것처럼 설명하거나 모델 정확도를 주장하지 않는다.
3. `references/workflow.md`를 읽고 구성요소와 식별 특징을 연결한다.
4. blockout → structure → form → material → surface → lighting → interaction → optimization
   순으로 한 단계씩 구현·렌더·비교한다. 실패한 단계는 수정 후 다시 확인한다.
5. 각 단계에서 실제 증거와 검토 기록을 `hub_3d_review`에 제출한다. blocked이면 다음 단계로
   넘어가지 않는다. Hub가 없다면 같은 manifest를 사람이 검토하고 자동 검사 미실행을 명시한다.

## 품질 기준

- 보이지 않는 면과 애매한 재질은 추정으로 표시한다. 단일 이미지에서 정확한 3D 복원을 보장하지 않는다.
- 카메라·투영·노출·조명을 고정해 실루엣과 비율을 먼저 비교한다. 텍스처로 구조 오류를 가리지 않는다.
- 검증하지 않은 screenshot·파일·성능 수치를 만들지 않는다. 모델의 시각 평가는 결정적 검사가 아니다.
- 반복 부품은 인스턴싱 가능성을 검토하고, 자원 dispose·이벤트 정리·재현 가능한 초기 상태를 제공한다.
- 요구하지 않은 외부 생성 API·유료 플러그인·런타임 에셋 다운로드를 추가하지 않는다.
- 산출물은 모델 factory·manifest·재현 가능한 preview·비교 증거·성능 측정·한계 목록이다.

MCP 검사는 제출 기록의 누락·모순을 차단한다. 에이전트의 모든 코드 작성이나 시각 품질을
강제로 보장하는 sandbox는 아니다. 정확도가 핵심이면 사용자 검토를 완료 조건에 포함한다.

출처: [img2threejs](https://github.com/img2threejs/img2threejs),
[파이프라인 설계](https://github.com/img2threejs/img2threejs/blob/main/docs/ARCHITECTURE.md).
