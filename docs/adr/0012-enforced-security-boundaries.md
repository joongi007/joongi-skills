# ADR-0012: 외부 실행 격리·서명된 배포·만료하는 로컬 세션

상태: accepted · 2026-11-14

## 맥락

환경변수 최소화와 OS 키링만으로 외부 MCP의 파일 접근을 제한할 수 없다.
같은 출처의 checksum은 배포 서버 변조를 탐지하지 못하고 만료 없는 Bearer는 유출 시 오래 남는다.

## 결정

외부 stdio는 Landlock+seccomp 또는 제한한 Docker에서만 실행한다. 미지원 시 fail closed한다.
WSL Windows mount와 subprocess 분석은 Docker-native로 실행한다.
공용 그래프의 신뢰한 adapter와 외부 분석 프로세스 경계를 분리한다.
배포본과 bootstrap은 npm·문서 빌드와 분리한 stdlib job에서 GitHub Sigstore로 서명한다.
실행 전 설치된 공식 gh로 workflow·main commit·저장소 ID·소유자 ID·digest를 검증한다.
로컬 세션은 1시간 토큰·15분 교체·60초 이전 토큰 유예·8시간 절대 한도를 사용한다.
관리되는 HTTP 연결에는 갱신 가능한 stdio broker를 사용한다.

## 대안과 결과

무제한 실행 fallback, 자기 검증만 하는 unsigned bootstrap, 영구 토큰은 거절했다.
격리를 제공할 수 없는 프로그램은 준비·등록을 변경해야 한다. 네트워크가 필요한 서비스는
원격 HTTPS MCP로 연결한다. 별도 로그인 서버·항시 실행 회전 데몬은 도입하지 않는다.
플랫폼·신뢰 경계·검사 방법은 [운영 계약](../operations/10-security-boundaries.md)을 따른다.
