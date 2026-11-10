# ADR-0001: 의존성 없는 로컬 실행

상태: accepted · 날짜: 2026-11-05

## 맥락

사용자는 clone·다운로드 후 쉽게 설치하고 검토할 수 있는 로컬 Hub를 원한다.
기존 플레이북의 서비스 기본은 Python 3.14/FastAPI이지만 배포 대상에 Python 3.10도
존재하며 개인용 설치에서 DB·패키지 설치를 선행시키면 진입 비용이 커진다.

## 결정

이 제품은 Python 3.10 이상 표준 라이브러리로 시작한다. loopback HTTP UI/API와 MCP
stdio를 제공한다. registry는 JSON, task 상태는 SQLite에 저장한다.
이 결정은 이 제품의 로컬 runtime 예외이며 다른 프로젝트의 FastAPI 기본을 변경하지 않는다.

YAML·Apps 확장 구현은 [ADR-0004](0004-bundled-extensions.md)가 보완한다. vendored 파서와
번들 SDK를 포함하며, 설치 시 외부 패키지를 요구하지 않는 목표는 유지한다.

## 대안과 결과

FastAPI + React/Vite는 입력 schema·생태계 도구가 강하지만 build·의존성 배포가 필요하다.
Node 단일 runtime은 MCP 생태계 연계가 좋지만 기존 환경에 추가 설치가 필요할 수 있다.
선택한 구성은 배포가 단순한 대신 HTTP 입력 검증·보안·동시성·프로토콜 계약을 직접
검증해야 한다. 다중 사용자·원격 공개는 추가 인증과 운영 설계 후 별도 결정한다.

## 검증

지원 Python에서 추가 패키지 없이 CLI·HTTP·stdio·SQLite 테스트를 실행한다.
runtime 예외가 설치 문서와 CI의 최소 버전에 일치해야 한다.
