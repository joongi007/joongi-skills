# 린트·포맷·명명 규칙 (PLAYBOOK §22)

저장소의 지원 runtime·도구 버전·명명 규약을 우선한다. 도구 교체나 전체 포맷은 별도 변경으로 판단한다.
린트 통과는 동작·보안·아키텍처 검증을 대체하지 않는다.

## Python·Ruff (§22.1)

Ruff는 lint·format·import 정리에 사용할 수 있다. Black·isort가 이미 있으면 기능 중복·CI 계약을
확인하고 변경 필요성을 판단한다. 함께 쓰는 도구의 충돌만 줄이며 일괄 금지하지 않는다.
`target-version`은 실제 최소 지원 Python에 맞추고 line length·규칙·예외는 프로젝트에 고정한다.
자동 수정은 diff를 확인한다. 모든 warning이 `--fix`로 해결된다고 가정하지 않는다.

## TypeScript·ESLint (§22.2)

선택한 ESLint·TypeScript·plugin 버전이 지원하는 설정 형식을 사용한다.
flat config 예시를 기존 구버전에 그대로 복사하지 않는다. 신규 설정은 해당 버전의 공식 권장 구성을 확인한다.
TypeScript strict 검사를 우선 검토하되 기존 코드 전환에는 단계·호환성·회귀 검증을 둔다.

## 이름과 공개 계약 (§22.3)

Python의 `snake_case` 함수·`PascalCase` 클래스·`UPPER_SNAKE_CASE` 상수 등 생태계 관례를 따르되
공개 필드·메시지·기존 식별자를 문체 통일 때문에 바꾸지 않는다.
`__all__`, 명시적 re-export, 한정된 lint 예외 중 공개 API와 도구에 맞는 방식을 선택한다.
`# ruff: noqa: F401`을 모든 모듈에 적용해 미사용 import 검사를 끄지 않는다.

TS의 `PascalCase.tsx`, `useXxx.ts`, `<name>Store.ts`는 팀 선택형 예시다.
WebSocket event·NATS subject·로그 event 이름은 서로 다른 계약이다. 하나의 문법으로 강제하지 않는다.
예: `v1/orders/created`는 WS event, `orders.status.created`는 NATS subject,
`order_created`는 로그 event로 선택할 수 있다. 기존 schema·producer·consumer와 함께 변경한다.
용어·약어는 [용어](terminology.md), 로그 필드는 [로그](logging.md)를 따른다.
