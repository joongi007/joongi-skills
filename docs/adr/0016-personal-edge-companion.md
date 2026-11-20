# ADR-0016: 개인 Edge를 별도 준비한 공식 확장 모드로 연결

상태: 채택 · 2026-11-21

## 문제

격리 Chromium에는 기존 Windows Edge 로그인 상태가 없다.
UI Automation으로 기존 창을 조작하면 활성 탭·포커스·선택자에 의존해 사용자 작업을 방해할 수 있다.

## 결정

기존 Docker 모드를 유지하고 `edge-browser`를 선택형으로 추가한다.
공식 Playwright 확장의 background·tabGroup·소유 탭 모델을 사용한다.
사용자가 연결 승인 때 기존 탭을 선택하지 않으면 새 빈 탭을 받는다.
worker는 첫 탭 목록이 빈 탭 하나가 아니면 연결을 거절한다.
Hub 호출 승인과 확장 연결 승인은 각각 유지하며 승인 우회 토큰을 저장하지 않는다.

Windows/WSL 모두 등록의 임의 명령 대신 고정 PowerShell gate를 실행한다.
명시적인 owner CLI 준비 단계에서만 해시 고정 Node·integrity 고정 npm 패키지를 받는다.
현재 사용자 ACL·DPAPI descriptor·공개 fingerprint·전체 파일 해시·추가 파일·reparse point·Python 서명을 검사한다.
등록에는 경로·코드·토큰 없이 연결 ID와 fingerprint만 받는다. 일반 stdio 샌드박스를 완화하지 않는다.

목록·상태 조회는 브라우저를 열지 않는다. 연결 시작은 즉시 정상 대기를 반환한다.
준비 전 원래 도구 호출은 실행하지 않으며 실패는 자동 재실행하지 않는다.
쿠키·코드 실행·업로드·임의 파일 도구를 제외한다. 종료할 때 Node만 종료하고 Edge나 후손 트리를 종료하지 않는다.

## 한계와 대안

companion은 Windows 사용자 권한이며 OS 실행 격리가 아니다.
공식 확장 자체의 브라우저 전체 쿠키 읽기 권한은 남는다. 탭 URL 검사는 원자적인 네트워크 보안 경계가 아니다.
redirect·하위 리소스·팝업과 페이지/계정의 의미적 부작용을 차단하지 않는다.
같은 사용자 악성 코드·관리자·침해된 의존성까지 방어한다고 주장하지 않는다.

UI Automation은 포커스 의존성 때문에 채택하지 않는다. 기존 프로필 CDP 포트 개방·쿠키 복사·비공개 bridge 역공학도 하지 않는다.
개인 계정 접근이 필요 없는 경우 Docker 격리 모드를 사용한다.
초기 승인·로그인·팝업과 공유 계정 동시 변경 때문에 완전한 사용자 무중단은 보장하지 않는다.

검증은 [운영 안내](../operations/17-personal-edge.md)와 `tests/test_edge_runtime.py`를 따른다.
확장 미설치 상태의 준비/변조 테스트를 실제 브라우저 연결 검증으로 표시하지 않는다.

URL은 고정된 내부 Playwright probe의 JSON 배열로 확인한다. 표시용 탭 제목을 URL로 해석하지 않는다.
probe는 공식 `browser_run_code_unsafe`의 고정 읽기 코드만 호출하며, 에이전트 코드·파일은 절대 받지 않는다.
