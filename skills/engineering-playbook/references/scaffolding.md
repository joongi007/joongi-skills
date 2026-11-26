# 새 프로젝트 구성과 실행 계약 (PLAYBOOK §8, §11)

새 프로젝트를 만드는 경우에만 적용한다. 기존 프로젝트는 지원 버전·lockfile·패키지·배포 계약을 유지한다.
WSL 설치 경계와 용량은 [WSL 가이드](wsl-development.md)를 확인한다.

## 생성 전 선택

목적·언어·지원 runtime·프로젝트 경로·패키지 관리자·배포 방식을 정한다.
호스트 설치와 컨테이너 초기화는 선택지이며 특정 Python/Node/Vite 버전을 이 가이드가 기본으로 강제하지 않는다.
생성기를 쓰면 선택 버전·실행 명령을 기록한다. 재현성이 필요하면 `latest` 대신 검증한 버전을 지정한다.
빈 경로·mount 대상·생성 파일 소유권을 확인하고 기존 파일을 덮어쓰지 않는다.

## 최소 구현부터 추가

1. 첫 실행·대표 요청과 종료를 확인하고 준비 조건·명령·성공 결과를 README에 적는다.
2. 필요한 의존성만 추가한다. DB·broker·JWT·상태관리 도구를 사용하지 않으면 설치하지 않는다.
3. lockfile·lint·type check·관련 테스트를 프로젝트 계약에 맞춰 구성한다.
   monorepo의 공유 lockfile도 가능하며 서비스마다 별도 lockfile을 강제하지 않는다.
4. 비밀 주입·로그·권한·자원 상한을 필요한 범위에서 설계한다.
5. 배포 산출물에는 필요한 runtime 의존성만 남기고 build/test 도구와 분리한다.

스택별 예시: [Python API](python-api.md), [프론트엔드](frontend.md), [린트](lint-naming.md).
공통 설정과 URL builder는 [설정](config-secrets.md), 개발·배포 Compose는 [Docker](docker.md)를 따른다.

## UI–API 계약 (§11.3)

API 경로·버전 정책·인증·오류·timeout·페이지 상한을 명시한다. `/api/v1`은 선택형 예시다.
health 경로도 `/healthz` 또는 `/api/v1/healthz` 중 실제 정의와 proxy/probe를 일치시킨다.
liveness·readiness의 의미는 [배포 계약](kubernetes-helm.md)을 따른다.
상대 API 경로와 단일 origin을 선택하면 proxy 경로·HMR을 확인한다.
origin을 나누면 정확한 CORS 허용 목록·쿠키·CSRF·TLS를 검증한다.
로컬의 HTTP smoke test가 운영 TLS·권한·네트워크 검증을 대신하지 않는다.

## 설치·중지·정리

준비 환경 → 설치 → 설정 → 실행 → 대표 동작 → 중지·재시작 → 업데이트·복구를 문서화한다.
`.env`·로컬 자격증명·cache·빌드 산출물의 Git 제외를 확인하고 비밀 없는 예제 설정을 제공한다.
IDE 설정은 팀 공유 필요성을 판단하며 `.vscode`·`.idea`를 무조건 제외하지 않는다.
사용자 데이터·volume 삭제는 중지·캐시 정리와 분리한다.
