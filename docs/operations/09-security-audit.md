# 보안 점검 기록: 로컬 MCP의 신뢰 경계

문서 ID: OPS-SECURITY-AUDIT · 점검일: 2026-11-14

## 범위와 방법

참고한 [ARTEX Global](https://github.com/jiwoochris/artex-global)은 LLM 기반 자율 침투 테스트 시스템이다.
그 저장소의 [방어·탐지 가이드](https://github.com/jiwoochris/artex-global/blob/main/docs/defense-ko.md)를
참고해 진입점 → 인증·권한 → 실행·네트워크 → 비밀 유출 경로를 확인했다.
ARTEX 엔진을 설치하거나 실행한 결과가 아니며 그 코드·프롬프트를 Hub에 포함하지 않았다.

시험 대상은 임시 상태 디렉터리의 우리 Hub, 로컬 가짜 MCP·OAuth 제공자, 임시 자식 프로세스다.
가짜 토큰만 사용했고 외부 서비스에 스캔·익스플로잇을 보내거나 실제 계정 권한을 사용하지 않았다.
의존성 advisory 조회는 별도 읽기 작업이다. 이 기록은 독립적인 외부 보안 인증이 아니다.

## 확인한 위험과 수정

| ID | 확인한 조건·영향 | 수정 | 재현·회귀 검사 |
|---|---|---|---|
| AUDIT-01 | 원격 주소를 HTTP로 등록하면 인증 헤더를 암호화하지 않는 연결을 시도할 수 있음. 네트워크 경로 공격자가 토큰·내용을 관찰·변조할 위험 | 외부 MCP는 HTTPS 필수. HTTP는 DNS로 확인한 목적지가 모두 loopback일 때만 허용하고 실제 연결에도 확인한 sockaddr 사용 | `tests.test_final_security_audit.FinalSecurityAudit.test_plain_http_outside_loopback_is_rejected_before_credentials_are_sent` |
| AUDIT-02 | stdio 서버가 부모의 모든 환경변수를 받아, 명시하지 않은 비밀이나 interpreter 설정까지 우발적으로 노출 | 실행 필수 환경변수만 기본 전달. 추가 값은 서버별 env 매핑으로 지정 | `tests.test_final_security_audit.FinalSecurityAudit.test_stdio_does_not_inherit_ambient_secrets_but_explicit_mapping_works` |

두 항목은 수정 전 테스트 실패로 재현하고 수정 후 통과를 확인했다.
AUDIT-02는 같은 사용자 프로세스를 격리하는 조치가 아니며 임의의 악성 프로그램을 안전하게 만들지 않는다.
HTTPS 연결과 로컬 HTTP 연결의 호환성, loopback·외부 IP가 섞인 DNS 응답의 거절도 확인한다.
세부 테스트는 외부 네트워크로 패킷을 보내지 않고 DNS 응답과 연결 생성 지점을 대체한다.

## 함께 확인하는 방어

| 경로 | 검사·근거 | 판정의 범위 |
|---|---|---|
| 무인증 접근·범위 변경·승인 재사용 | `tests/test_security_boundaries.py` | 관리 토큰과 범위별 MCP 토큰 분리, 정확한 호출 한 번 승인, MRTR 입력의 승인 우회 거절 |
| 로그인·갱신·토큰 회전 | `tests/test_auth.py`, `tests/test_credential_lock.py` | 가짜 제공자의 PKCE·issuer·state·refresh·revocation과 프로세스 잠금 |
| OS 인증 저장소 | `tests/test_credential_store.py`, native-vault CI | Windows DPAPI·macOS Keychain·Linux Secret Service, 잠금 시 평문 fallback 없음 |
| SSRF·DNS·시간·크기 한계 | `tests/test_transport_limits.py` | metadata/link-local 차단·DNS pinning·redirect 거절·bounded I/O |
| Markdown·Mermaid·Apps | 문서·브라우저·Mermaid 보안 검사 | HTML 비실행·정적 SVG 정리·App iframe 범위와 소유권 |
| 의존성·배포 | npm advisory 조회, publication CI | 알려진 advisory와 비밀 값 검사. 무취약점·공급망 무결성의 증명은 아님 |

## 추가 구현 후의 신뢰와 제한

- 외부 stdio MCP는 OS 샌드박스에서 실행한다. Hub 본체는 신뢰 프로그램이다.
- OS 키링은 저장 시 보호다. 정상적인 요청을 수행하는 Hub에는 복호화한 토큰을 사용할 권한이 있다.
- 프롬프트 인젝션을 완전히 제거하지 않는다. 응답의 알려진 비밀 반사 검사는 임의 변형·분할 유출까지 보장하지 않는다.
- 도구 승인은 모든 데이터 읽기·관리 동작에 대한 OS 권한 통제가 아니다. 명시적 허용 목록·인증 없는 연결의 기본 허용·Task 계속 진행의 범위를 검토해야 한다.
- 로컬 HTTP·관리 토큰은 자동 만료·교체하며 이전 영구 토큰을 폐기한다.
- 인증 실패 제한과 크기 제한 보안 이벤트를 제공한다. 동일 OS 사용자가 바꿀 수 없는 외부 감사 저장소·행동 상관분석은 제공하지 않는다.
- 원격 설치·업데이트는 실행 전에 Sigstore 서명·출처·현재 main commit을 확인한다.
- 모든 서비스의 실제 계정, 모든 브라우저·OS 설정이나 ARTEX 전체 공격을 검증한 것이 아니다.

## 실행한 검증

- WSL/Python 3.10: 전체 246개 테스트 실행, 통과(플랫폼·native 저장소 전용 3개 제외).
- native Windows: 이번 수정과 코드 그래프 관련 12개 테스트 실행, 통과(POSIX 전용 1개 제외).
- 공식 SDK: 2025·2026 × stdio·HTTP 네 조합 통과.
- 브라우저: 관리 인증·OAuth·도구 승인·프로젝트·연결 방식·Apps·정적 문서·Mermaid 검사 통과.
- Node advisory 조회: 조회 시점 알려진 취약점 0개. 모든 취약점 부재를 뜻하지 않는다.
- 수정 전 재현 테스트 3개 실패 → 수정 후 통과. 실제 비밀 값은 사용하지 않았다.

## 재현

```bash
python3 -B -m unittest tests.test_final_security_audit tests.test_security_boundaries tests.test_transport_limits -v
python3 -B -m unittest discover -s tests -q
npm run test:sdk
npm run test:browser
npm audit
```

브라우저·문서 검사의 준비는 [테스트 안내](../development/02-quality.md)를 따른다.
점검 후 변경도 검증해야 한다. “마지막 점검”은 이후의 코드·의존성 변경까지 안전하다는 보증이 아니다.

후속 구현의 동작과 플랫폼별 준비: [보안 경계 운영](10-security-boundaries.md). 위 실행 수치는 최초 점검 기록이다.
