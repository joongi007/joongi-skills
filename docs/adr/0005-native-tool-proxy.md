# ADR-0005: 도구 원형을 보존하는 발견과 Apps·Tasks 라우팅

상태: accepted · 날짜: 2026-11-06

## 맥락

범용 `hub_call`은 여러 도구를 작은 인터페이스로 검색·호출하기 편하지만,
외부 호스트가 개별 도구의 schema·Apps resource·Tasks 실행 조건을 발견하기 어렵다.
예제 App 렌더링과 독립 Task 실행에 성공한 것만으로 App 내부 Task 왕복까지 검증한 것은 아니다.

## 결정

연결된 모든 upstream 도구를 namespace와 원래 schema·metadata를 유지해 native 도구로 노출한다.
`hub_search`·`hub_call`은 편의 경로로 유지한다. ADR-0002의 검색 중심 발견 정책은 이 결정으로
대체하며 버전별 wire adapter 경계는 유지한다.

2025 `execution.taskSupport`와 2026 요청별 Tasks 협상을 구분한다.
App 리소스의 현재·이전 metadata 표기를 함께 인식한다. App 내부 Task 요청은 view에 묶인
requester로 core에 전달해 Task ID 소유권을 검사한다. 출처별 도구·리소스 라우팅은 유지한다.

## 대안과 결과

Apps·Tasks 도구만 예외로 직접 노출하면 upstream 기능과 버전별 예외가 늘어난다.
전체 native 노출은 schema 비용을 늘리지만 호스트가 원래 도구 계약을 이해할 수 있다.
외부 서버가 수십 개의 도구를 제공하면 서버의 도구 필터를 활용한다.

외부 MCP가 보통 tools만 제공한다면 Hub 등록만으로 native Apps·Tasks 기능이 생기지는 않는다.
Hub가 동기 호출을 자체 Task로 감싸는 기능과 upstream의 native Task 지원은 구분한다.
코드 그래프 UI를 별도로 제공하려면 `ui://` 리소스와 App 도구를 구현해야 한다.

## 검증과 경계

일반 도구의 직접 발견·원래 schema, 2025 Task 실행 조건·2026 metadata 변환,
이전 App metadata, App별 Task 조회·취소 격리를 회귀 테스트한다.
공식 App SDK가 실행되는 브라우저에서 Task 생성→조회→결과를 확인한다.
Task 내부 입력 재개와 live 목록 변경 푸시, 만료된 App의 장기 작업 제어는 별도 과제다.
