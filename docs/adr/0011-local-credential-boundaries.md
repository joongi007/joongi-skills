# ADR-0011: 로컬 자격증명과 실행 승인

상태: accepted · 날짜: 2026-11-14

## 맥락

loopback에서도 다른 로컬 프로세스나 브라우저 요청이 MCP에 접근할 수 있다.
upstream에 위임한 OAuth 권한은 도구 설명의 신뢰와 별개로 통제해야 한다.
POSIX 파일 권한만으로는 인증 비밀의 저장 시 암호화가 되지 않았다.

## 결정

관리 API·범위별 HTTP MCP 자격증명을 분리하고 stdio HTTP bridge에도 동일하게 적용한다.
OS DPAPI·Keychain·Secret Service를 사용하고 잠금·부재 시 평문 fallback 없이 실패한다.
credentialed 연결에는 정확한 호출 한 번 승인 또는 명시한 도구 허용 목록을 사용한다.
Task 승인에는 동일한 작업의 검증한 입력 응답을 포함한다. 동기 continuation은 새 호출로 승인한다.
알고 있는 비밀이 upstream 응답·오류에 반사되면 결과 전체를 거절한다.

## 대안과 결과

인접 파일의 자체 AES key는 같은 파일 접근자에게 추가 보호가 약하고 암호 구현 부담을 늘린다.
매 요청 OS 인증 팝업은 백그라운드 stdio 사용과 맞지 않는다. 열린 로그인 키링을 사용한다.
Hub 자체와 같은 사용자 악성 프로세스는 별도의 OS 격리 없이는 여전히 신뢰 경계 안에 있다.
업데이트의 same-origin checksum은 독립된 배포 서명이 아니며 검토한 commit 고정은 clone에서 사용한다.

## 검증

`tests/test_security_boundaries.py`, `tests/test_credential_store.py`, `tests/test_auth.py`,
`tests/test_credential_lock.py`와 3개 OS의 native-vault CI를 사용한다.
