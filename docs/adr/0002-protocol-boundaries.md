# ADR-0002: 프로토콜 경계와 단계적 발견

상태: accepted · 날짜: 2026-11-05

도구 발견·노출 정책은 [ADR-0005](0005-native-tool-proxy.md)가 대체한다.
버전별 adapter와 기능 경계 결정은 유지한다.

## 맥락

Hub는 여러 MCP와 스킬을 한 접점에서 제공해야 한다. 2025와 2026 규격의 초기화,
기능 협상과 Tasks 계약이 달라 단순 프록시만으로 의미를 보존할 수 없다.

## 결정

downstream server와 upstream client 양쪽에 wire adapter 경계를 둔다.
검색용 설명을 먼저 제공하고 선택한 schema·본문·참조를 필요할 때 읽는다.
지원하는 확장만 광고하고, 해석할 수 없는 역방향 요청·변환은 명시적으로 제한한다.
Apps는 metadata·리소스 전달과 Host renderer를 구분한다.
resources/tools 기반 스킬 제공과 공식 Skills 확장 준수를 구분한다.

## 대안과 결과

모든 schema를 매번 노출하면 단순하지만 컨텍스트 비용과 이름 충돌이 커진다.
raw 메시지를 무조건 전달하면 빠르지만 버전 차이·소유권·URI·ID 매핑을 놓친다.
선택한 구성은 adapter 테스트가 필요하며 새로운 확장은 계약과 호환성 표를 함께 갱신한다.

## 검증

downstream 2종 × upstream 2종을 실제 stdio/HTTP fixture로 확인한다.
외부 Host별 실제 접속 결과는 fixture 결과와 별도로 기록한다.
