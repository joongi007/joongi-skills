# 로컬 실행과 장애 확인

문서 ID: OPS-LOCAL · 요구사항: REQ-UI, REQ-REGISTRY, REQ-TASKS

<!-- contract: cli.options = {"serve":["--help","--host","--port","--skills-dir","--state-dir"],"stdio":["--fallback","--help","--mode","--profile","--skills-dir","--state-dir","--url"],"configure":["--fallback","--help","--mode","--profile","--skills-dir","--state-dir","--url"],"start":["--help","--port","--skills-dir","--state-dir"],"stop":["--help","--skills-dir","--state-dir"],"restart":["--help","--port","--skills-dir","--state-dir"],"status":["--help","--skills-dir","--state-dir"],"open":["--help","--port","--skills-dir","--state-dir"],"state":["--help","--import-from","--restore-backup","--skills-dir","--state-dir"]} -->

설치는 [설치 안내](../installation/00-index.md), 기능 경계는
[호환성 계약](../architecture/02-compatibility.md)을 먼저 확인한다.
코드 분석 도구를 추가하려면 [코드 그래프 MCP 연결](01-code-graph.md)을 본다.
공식 SDK별 실제 접속 조합과 재실행은 [SDK 상호 운용 검증](02-sdk-interop.md)을 본다.
프로젝트 폴더에서 발견한 MCP·스킬을 모으려면 [로컬 수집](03-local-inventory.md)을 본다.
다언어 코드 분석의 선택 통합은 [Code Review Graph 연결](04-code-review-graph.md)을 본다.

인증·프로젝트별 분리·MCP 스킬 설치는 [인증과 스킬 관리](05-auth-project-skills.md)를 본다.

## clone에서 실행

Python 3.10 이상을 사용한다. 저장소 루트에서:

```bash
python3 -m joongi_hub serve --host 127.0.0.1 --port 8765
```

브라우저에서 `http://127.0.0.1:8765/`를 연다. health는 `/healthz`, MCP HTTP 접점은
`/mcp`, 관리 JSON API는 `/api/v1` 아래에 있다. UI와 API는 같은 origin을 사용한다.
이미 사용 중인 포트면 `--port`를 바꾼다. 외부 네트워크 공개를 위해 host를 바꾸지 않는다.

MCP stdio client에는 다음 명령을 등록할 수 있다. stdout은 protocol 메시지 전용이다.

```bash
python3 -m joongi_hub stdio
```

기본 `stdio`는 HTTP 서버를 탐색하지 않는다. 자동 공유를 원하면 `stdio --mode hybrid`를
사용하거나 웹의 연결 설정에서 혼합 모드를 저장한다. 혼합 모드는 실행 중인 같은 저장소의
HTTP Hub를 공유하고, 없으면 기본적으로 stdio로 실행한다. 연결 중 자동 전환은 하지 않는다.
자세한 설정·프로젝트 URL·시작과 중지는 [연결 방식과 웹 실행](06-connection-modes.md)을 본다.

사용 가능한 인자는 `python3 -m joongi_hub serve --help`와
`python3 -m joongi_hub stdio --help`에서 확인한다.

## 데이터 위치

기본 상태 디렉터리는 `~/.local/share/joongi-hub`, 스킬은 패키지와 함께 있는 `skills/`다.
설치된 런처의 기본 경로는 설치한 사용자 홈에 고정된다. 웹·stdio·업데이트가 같은 등록 정보를 쓴다.
다른 저장소는 명시적 `--state-dir`로 선택한다. 시험 환경은 별도 디렉터리로 격리한다.

```bash
# 실제 사용: 에이전트와 같은 영구 저장소로 웹 열기
joongi-hub open
joongi-hub state
```

임시 경로는 시험 전용이다. 예전 검토용 웹의 등록은 공용 설치에 자동으로 옮겨지지 않는다.
등록 경로 확인·가져오기·백업 복구는 [저장소 일관성과 복구](07-state-consistency.md)를 따른다.

registry JSON과 task SQLite를 백업할 때 해당 상태 디렉터리를 사용하는 프로세스를
중지해 일관된 복사본을 만든다.
sqlite 파일만 실행 중 복사하는 식의 불완전한 백업을 하지 않는다.
state에는 endpoint와 작업 결과가 포함될 수 있으므로 공개 저장소에 넣지 않는다.

## 장애 확인

| 증상 | 확인 |
|---|---|
| UI 접속 불가 | process 실행 여부, 포트 충돌, health 응답 |
| MCP 목록에 안 보임 | agent 재시작·설정 파일 위치·등록 명령·작업 디렉터리 |
| upstream probe 실패 | 명령 실행 가능 여부, endpoint, stderr, timeout |
| 도구는 보이나 호출 실패 | 실제 입력 schema, 인증, 서버 버전, upstream 오류 |
| 스킬 변경 미반영 | 설치본/원본 위치, 업데이트 충돌, catalog 새 조회 |
| 작업이 멈춤 | upstream 생존·timeout·취소 결과·재시작 정책 |

upstream stdio 명령은 사용자 권한으로 실행된다. 신뢰하는 명령만 등록한다.
비밀은 등록 예제에 직접 쓰지 않고 필요한 환경 변수로 주입한다.

## 제거와 복구

installer로 설치했다면 [제거 명령](../installation/00-index.md)을 사용한다.
clone에서 실행한 process는 Ctrl-C로 종료한다. 등록 파일·사용자 수정본·state 삭제는
다른 작업이므로 일괄 삭제하지 않는다. 복구 시험에는 별도 state 디렉터리를 사용한다.


## 작업과 프로세스 복구

작업에는 실행 PID를 기록한다. 다른 stdio/UI 프로세스가 같은 저장소를 열더라도
실행 PID가 살아 있는 작업은 유지한다. 실행 프로세스가 종료된 미완료 작업은 다음
초기화에서 실패로 정리한다. 자동 재실행은 외부 부작용 중복을 유발할 수 있어 보장하지 않는다.
UI에서 작업을 취소한 사실과 실제 upstream 실행 중지는 구분해서 확인한다.

2026 작업이 입력을 기다리면 UI에 표시된 요청 ID별 응답을 제출한다.
MCP client는 `tasks/get`의 `inputRequests`를 읽고 같은 task ID에
`tasks/update`의 `inputResponses`를 보낸다. 요청 ID는 원래 작업에 연결된 값만 사용한다.
Hub는 이미 응답한 입력 ID를 다시 대기 목록에 넣지 않고 원래 서버로 전달한다.

## 로컬 MCP App

Apps를 제공하는 도구를 실행하면 관리 UI에서 sandbox App view를 열 수 있다.
이 view는 resource CSP와 원래 MCP 서버에 묶인 callback을 사용한다.
view가 만료되면 App을 다시 열고, tool visibility가 app을 허용하지 않으면 호출이 거절된다.

## 스킬 supporting file 조회

native Skills manifest의 URI를 이용해 `resources/read`로 text·binary 파일을 읽는다.
`resources/directory/read`에는 `skill://<name>/references`처럼 디렉터리 URI를 보내고
반환된 바로 아래 항목에서 필요한 파일이나 `inode/directory` 항목만 이어서 선택한다.
manifest의 digest·size는 최종 읽은 바이트와 대조한다. 파일은 1 MiB, 스킬은 512개 파일·16 MiB 한도다.

도구·스킬 검색 옵션과 검색 범위는 [카탈로그 검색](08-catalog-search.md)을 따른다.
