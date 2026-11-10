# ADR-0004: 번들형 YAML 파서와 Apps 호스트

상태: accepted · 날짜: 2026-11-05

## 맥락

단순 name/description 파싱과 Apps metadata 전달만으로는 사용자가 요청한 스킬 배포·App
상호작용을 충분히 지원하지 못한다. 설치 시 Python·Node 패키지 다운로드를 요구하지 않으면서
표준 YAML과 공식 Apps SDK의 동작을 제공해야 한다.

## 결정

Python 런타임에는 MIT PyYAML 6.0.3의 순수 Python 파일을 vendoring한다. 공식 PyPI sdist의
SHA-256과 라이선스를 보존한다. SafeLoader 기반으로 구조·깊이·JSON 호환성을 제한하고
실행 태그·재귀 alias·merge 키를 거절한다. metadata 필드는 Agent Skills의 string map 계약을 따른다.
supporting file은 text/blob과 원본 바이트 기반 digest로 전달한다.

브라우저는 공식 MCP Apps AppBridge 2.0.4와 Client/Core 2.4.0을 개발 시 번들링한 파일로 사용한다.
원본 App HTML을 고치지 않고 opaque-origin 하위 iframe에 넣는다. relay는 message의 source
window를 확인하며 도구·리소스 요청을 원래 서버 namespace로 전달한다.
리소스 URI의 복원은 protocol 필드에만 적용하고 business payload는 바꾸지 않는다.
native Skills manifest가 보장한 파일 바이트는 App wrapper로 변경하지 않는다.

## 결과

사용자의 설치에는 추가 package manager가 필요 없다. 개발 빌드와 검증에는 package-lock으로
고정한 Node 의존성이 필요하다. SDK 라이선스는 static NOTICE에, PyYAML provenance는 vendor
디렉터리에 보관한다. ADR-0001의 배포 목표는 유지하며 표준 라이브러리만 사용한다는 구현 제약은
이 결정으로 대체한다. 독립적인 sampling callback·subscription 등은 선언하지 않는다.

## 검증

공식 SDK로 두 protocol era와 두 transport를 확인한다. 공식 App SDK가 실행되는 브라우저에서
원래 도구명·리소스 URI의 왕복과 parent DOM 차단을 검사한다. YAML·binary·manifest·directory
조회, callback 출처 격리, CSP 주입 거부를 회귀 테스트로 확인한다.
