# 실행 격리·배포 검증·로컬 토큰 수명

문서 ID: OPS-SECURITY-BOUNDARIES · 2026-11-14

## stdio MCP 실행 격리

등록된 외부 프로그램은 OS 경계 안에서만 실행한다. `sandbox.backend`의 기본값은 `auto`다.
지원 환경이 없으면 연결을 거절한다. 제한 없는 실행으로 되돌아가는 설정은 없다.
원격 HTTPS MCP는 로컬 실행 대상이 아니며 기존 인증·호출 승인 정책을 따른다.

| 프로필 | 준비 | 허용 범위 |
|---|---|---|
| `landlock` | Linux Landlock ABI 6 이상·libseccomp | 런타임·진입 스크립트·명시한 경로. 네트워크·자식 프로세스 생성 차단, 스레드 허용 |
| `docker-native` | Linux/WSL·Docker Engine·고정 이미지 | 호스트 Linux 런타임과 명시한 경로만 컨테이너에 공유. 네트워크 차단, 자식 프로세스 허용 |
| `docker` | Docker Engine·검토한 digest의 Linux 이미지 | `/workspace/` 아래에 명시한 mount만 공유. 네트워크 차단 |

WSL의 `/mnt/c`, `/mnt/d` 같은 Windows 경로는 Docker 격리를 선택한다.
일반 Linux 경로의 `auto`는 지원되면 Landlock, 지원되지 않으면 Docker-native를 사용한다. subprocess가 필요한 MCP는 `docker-native`를 지정한다.
Docker의 기본 seccomp, 메모리·PID·CPU 제한이 꺼져 있으면 실행을 거절한다.
공식 Docker seccomp 기본 정책을 고정해 사용하고 socket 생성·연결을 추가로 차단한다.
공유 프로젝트 안의 Unix socket에도 연결할 수 없다.
컨테이너는 non-root·read-only rootfs·capability 제거·no-new-privileges를 사용한다.

```bash
joongi-hub sandbox
joongi-hub sandbox --prepare
```

두 번째 명령은 코드에 digest로 고정한 Debian 이미지만 준비한다.
자동 image pull, 임의 이미지 태그, Docker socket·OS 서비스 socket 공유는 허용하지 않는다.
Windows/macOS의 네이티브 프로그램을 Linux 프로필로 실행하지 않는다.
Windows에서는 WSL에 Hub를 먼저 설치한 뒤 Windows 설치기에 `--wsl-distribution Ubuntu`를 지정하면
에이전트와 `joongi-hub.cmd`가 같은 WSL Hub·등록·인증 상태를 사용한다. 배포판 이름은 실제 이름으로 바꾼다.
Windows 쪽 기존 상태는 삭제하지 않는다. 이 선택은 업데이트에도 유지된다.
macOS/Windows의 로컬 프로그램은 검토한 Docker 이미지로 등록하거나 Linux/WSL Hub를 사용한다.

서버 JSON 예시:

```json
{"id":"local-review","transport":"stdio","command":"/usr/bin/python3",
 "args":["/opt/review/server.py"],"sandbox":{"backend":"docker-native",
 "read":["/work/project"],"write":["/work/review-cache"]}}
```

`read`는 읽기 전용, `write`는 읽고 쓰기 허용이다. 경로는 절대 경로로 지정한다.
홈 전체·OS 상태·Hub 자격증명·신뢰한 실행 코드 쓰기는 거절한다.
환경변수는 필요한 값만 전달하며 loader 변수가 격리 helper에 먼저 적용되지 않는다.
명시적으로 공유한 프로젝트나 환경변수 값은 해당 MCP가 읽을 수 있으므로 범위를 좁힌다.

공용 Code Review Graph는 신뢰한 Hub adapter가 프로젝트를 선택하고 외부 분석 프로그램을 격리한다.
등록 시 `read_roots`로 허용한 저장소 안에서만 선택한다. 모델이 임의의 홈 경로를 승인할 수 없다.
프로젝트마다 DB를 분리하고 외부 프로그램에는 해당 프로젝트와 전용 cache만 공유한다.
빌드 계획·상태 제어 파일은 외부 분석 프로그램의 쓰기 범위에서 제외한다.

## 다운로드 실행 전 서명 검증

원격 설치·업데이트는 GitHub CLI의 Sigstore 검증을 필수로 사용한다.
먼저 [공식 GitHub CLI](https://cli.github.com/)를 설치한다. 검증기를 찾지 못하거나
서명·인증서·출처가 맞지 않으면 압축 해제와 실행을 하지 않는다. checksum-only 우회는 없다.

1. 사이트의 명령은 임시 디렉터리에 bootstrap과 attestation을 받는다.
2. 설치된 `gh attestation verify`가 bootstrap을 검증한 뒤에만 실행한다.
3. 검증된 bootstrap은 archive도 검증한 뒤 압축을 푼다.
4. 업데이트에는 설치된 신뢰 정책·검증기를 사용한다. 다운로드한 코드가 자기 신뢰 정책을 결정하지 않는다.

검증 대상은 archive digest, GitHub OIDC issuer, 정확한 Pages workflow·main ref·source commit,
고정한 저장소 ID와 소유자 ID, GitHub-hosted runner다.
현재 보호된 main commit과 다르면 거절하므로 이전 정상 서명으로 되돌리는 공격도 거절한다.
main 변경 직후 Pages 배포가 완료되기 전에는 설치가 잠시 실패할 수 있다. 배포 완료 후 다시 시도한다.
GitHub 계정·workflow·GitHub/Sigstore 자체는 신뢰 기반이다. 처음 복사하는 명령은
[공식 저장소](https://github.com/joongi007/joongi-skills)와 대조한다.

서명 job은 stdlib만으로 검토한 checkout의 배포본을 만들며 npm·문서 빌드 코드를 실행하지 않는다.
사이트 build job에는 OIDC 서명 권한이 없다. 서명 job의 immutable artifact ID로 파일을 전달한다.
클론한 checkout을 직접 설치하는 것은 사용자가 로컬 소스를 신뢰하는 별도 경로다.

## 로컬 토큰 자동 교체

| 항목 | 동작 |
|---|---|
| 대상 | 관리 UI와 범위별 로컬 HTTP MCP 토큰. 외부 OAuth refresh와 별개 |
| 토큰 유효 기간 | 1시간, 최초 세션의 8시간 한도 이내 |
| 자동 교체 | 유효한 요청 또는 로컬 broker 접근 시 발급 후 15분이 지나면 교체 |
| 이전 토큰 | 교체 후 최대 60초만 인정 |
| 네트워크 요청 | 만료된 토큰으로 갱신·8시간 세션 연장 불가 |
| 로컬 소유자 | 상태 디렉터리에 접근할 수 있는 broker가 새 세션 발급 가능 |
| 강제 폐기 | `joongi-hub credentials --rotate-local`, 이전 토큰 즉시 무효화 |

사용 중 요청 시 교체하므로 타이머·항시 실행 서버가 필요 없다.
관리 화면은 응답의 새 토큰을 반영한다. 8시간 뒤에는 `joongi-hub open`으로 다시 연다.
설치기가 관리하는 HTTP 연결은 stdio credential bridge가 매 요청마다 현재 토큰을 읽는다.
직접 HTTP 설정을 복사하는 사용자 정의 클라이언트는 만료·교체 시 다시 발급받아야 한다.
표시된 만료 시각은 상한이며 같은 범위의 다른 broker가 먼저 교체하면 이전 토큰은 60초 뒤 무효화된다.
이전 버전의 만료 없는 로컬 토큰은 업그레이드할 때 폐기한다.

## 이벤트와 보호 범위

인증 실패는 종류별 1분 20회 이후 429로 응답하며 정상 토큰의 요청은 차단하지 않는다.
`security-events.jsonl`에는 시각·고정 이벤트 이름·고정 분류만 기록한다.
토큰·요청 본문·도구 인수·URL은 기록하지 않고 1 MiB씩 두 파일로 제한한다.
같은 OS 사용자에게서 로그를 변조 불가능하게 보관하는 시스템은 아니다.

격리는 외부 stdio 프로세스의 권한을 줄인다. Hub 본체는 인증 정보를 사용해야 하는 신뢰 프로그램이다.
OS 관리자·동일 사용자에 의한 Hub 코드 변조·커널 취약점·공유하기로 한 데이터의 악용까지 제거하지 않는다.
공급망 검증과 도구 승인은 이 경계를 함께 보완한다.

검사: `tests/test_sandbox_boundaries.py`, `tests/test_release_verification.py`,
`tests/test_local_token_rotation.py`, `tests/test_security_events.py`.
