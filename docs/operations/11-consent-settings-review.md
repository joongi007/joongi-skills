# 반복 허용·임시 설정 화면 보안 검수

문서 ID: OPS-CONSENT-SETTINGS-REVIEW · 점검일: 2026-11-15

## 범위와 검수 방법

검수 대상은 호출 한 번·1시간·항상 허용, 철회, 임시 설정 웹, 승인 화면의 자동 닫기다.
우리 코드의 정적 검토와 임시 상태 저장소·가짜 OAuth/MCP 제공자·Chromium을 이용한 동적 검증을 수행했다.
실제 Notion 데이터를 읽거나 승인하지 않았고 외부 서비스에 침투 요청을 보내지 않았다.
이 기록은 외부 기관의 보안 인증이 아니다.

[ARTEX Global 방어 가이드](https://github.com/jiwoochris/artex-global/blob/133f3cf97f2d153227a1a95d3c4b7cd5b72020a6/docs/defense-ko.md)를
참고해 관리 진입점 → 권한 확대 → 자격증명 변경 → 비밀 유출·실행 경계를 검토했다.
확인한 ARTEX 커밋은 `133f3cf97f2d153227a1a95d3c4b7cd5b72020a6`이다.
`mcphttp/client.go`와 `server/mcpdiscover.go`는 외부 MCP 연결·발견을 위한 클라이언트 코드다.
이번 검수에서 ARTEX 엔진이나 ARTEX가 제공하는 보안 검사 MCP를 실행한 것은 아니다.
그 코드·프롬프트·탐지 규칙을 MIT인 이 저장소에 복사하지 않았다.

## 확인한 경로와 결과

| 경로 | 검토·수정 | 재현·회귀 검사 |
|---|---|---|
| 반복 허용 후 연결·도구·환경변수 변경 | 연결·도구 정의·실제 매핑 값의 digest에 묶고 변경이 확인되면 허용 및 이전 승인 대기를 제거 | `tests/test_scoped_consent.py` |
| 허용 철회 후 이미 승인된 대기로 우회 | 철회한 binding의 남아 있는 대기도 함께 제거 | `tests/test_scoped_consent.py` |
| 다른 프로젝트로 허용 복사·철회 | 프로젝트별 SQLite 저장소를 유지하고 다른 저장소의 ID는 권한을 주지 않음 | `tests/test_scoped_consent.py` |
| 승인 후 실제 전송 전 로그인 교체 | 인증 변경 식별자를 승인에 묶고 HTTP 자격증명을 만들 때 재확인. 다른 계정으로 보내기 전에 거절 | `tests/test_agent_approval.py` |
| 정상 token refresh로 매번 재승인 | 로그인 교체와 refresh를 구분. 정상 refresh에서는 변경 식별자 유지 | `tests/test_auth.py` |
| 에이전트가 스스로 넓은 범위 승인 | MCP에 decide·관리 자격증명을 노출하지 않음. scope는 nonce가 필요한 브라우저 POST 또는 관리 인증 API에서만 선택 | `tests/test_security_boundaries.py`, `tests/test_agent_panel.py` |
| 임시 관리 토큰과 MCP·상시 관리 토큰 혼용 | 임시 인스턴스는 메모리의 독립 관리 토큰 사용. 다른 토큰과 HTTP MCP 접속 거절 | `tests/test_agent_panel.py` |
| CSRF·Host 변경·도구 인수의 HTML 주입 | 기존 Host·Origin·CSP 경계 유지. 인수를 text로 렌더링 | `tests/test_agent_panel.py`, `tests/browser_approval.cjs` |
| 탭 닫기로 stdio 또는 다른 탭 종료 | 문서별 lease와 닫기 유예. 임시 웹만 종료, 다른 탭과 stdio 유지. 새로고침·동시 재개 검증 | `tests/test_agent_panel.py`, `tests/browser_settings.cjs` |
| 저장 응답 유실·자동 닫기의 성공 오인 | 읽기 전용 결과 확인 후에만 완료 처리·자동 닫기. 재승인 POST 반복 없음 | `tests/browser_approval.cjs`, `tests/browser_settings.cjs` |

설정·환경변수 변경 후 남아 있던 승인으로 우회하는 경로와 로그인 교체 시점의 경쟁 조건은
검수 중 수정하고 회귀 테스트를 추가했다. 임시 웹을 다시 여는 동안 이전 창의 OAuth callback
정리가 겹쳐도 죽은 포트를 복구하지 않도록 정리 순서를 보완했다.

## 남는 신뢰 경계

- 1시간·항상 허용은 선택한 도구의 다른 인수·페이지까지 포함한다. 특정 가계부 페이지만 허용하는 리소스 정책은 아니다.
- 도구 정의 변경은 Hub가 갱신된 정의를 확인한 뒤 판정한다. 서버가 같은 정의로 내부 동작만 바꾸는 경우는 감지하지 못한다.
- 기존 `allowed_tools`는 사용자가 직접 설정한 별도의 허용 목록이다. 새 반복 허용의 변경 감지 규칙을 소급 적용하지 않는다.
- 브라우저 자동 닫기는 브라우저 정책에 따라 거절될 수 있다. 완료 상태는 유지하고 수동 탭 닫기를 안내한다.
- 탭 닫기 신호가 오면 약 5초, 누락되면 마지막 heartbeat 후 120초 이내 임시 웹을 정리한다. 열린 창을 즉시 감지하는 OS 창 감시 방식은 아니다.
- 같은 OS 사용자 권한으로 임의 코드를 실행할 수 있는 에이전트에 대해, 브라우저 승인만으로 완전한 격리를 보장하지 않는다.
  기존 stdio sandbox·OS 자격증명 저장소·서명 검증 경계는 [실행 보안](10-security-boundaries.md)과 함께 적용한다.
