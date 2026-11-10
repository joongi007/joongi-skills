# 코드 그래프 MCP 연결과 검증

문서 ID: OPS-CODEGRAPH · 요구사항: REQ-REGISTRY, REQ-CALL

Python 프로젝트는 추가 설치 없이 포함된 읽기 전용 AST 그래프 MCP를 바로 연결한다.
함수·클래스·모듈 검색, 소스 문맥, 호출자·호출 대상, 역방향 영향 분석을 제공한다.
대상 코드를 import하거나 실행하지 않으며 AST로 파싱한다.

실제 [GitNexus](https://github.com/abhigyanpatwari/GitNexus) 1.6.12도 이 저장소를 색인하고
Hub를 통해 심볼·호출 관계를 조회했다. [Serena](https://github.com/oraios/serena)는 추가 후보이며
이 작업에서 실행한 도구는 아니다. 내장 Python 분석기와 외부 GitNexus는 서로 다른 제품이다.

`code-review-graph` 2.3.9도 실제 색인·Hub 연결·통계·파일 요약 조회를 검증했다.
선택 설치 방법은 [Code Review Graph 연결](04-code-review-graph.md)을 본다.

## 내장 Python 그래프 바로 사용

```bash
# 임시 Hub에서 실제 프로젝트 파싱·MCP 연결·도구 호출까지 검증. 설정을 남기지 않는다.
python3 scripts/check_code_graph.py --target /path/to/project

# 지정한 Hub에 등록하고 실접속 검증한다. UI를 새로고침하고 연결 확인을 누른다.
python3 scripts/check_code_graph.py --target /path/to/project --state-dir ~/.local/share/joongi-hub --register

# UI에 직접 입력할 command/args/id JSON을 생성한다.
python3 scripts/check_code_graph.py --target /path/to/project --print-config
```

같은 ID의 다른 등록을 덮어쓰지 않는다. 대상을 바꾸려면 `--id`로 새 ID를 쓰거나
의도적으로 `--replace`를 지정한다. command/args는 소스·설치 런타임 위치를 절대 경로로
고정하므로 에이전트의 작업 디렉터리가 달라도 실행된다.

설치된 Hub 명령에서도 실행할 수 있다.

```bash
python3 -m joongi_hub.code_graph --project /path/to/project --summary
python3 -m joongi_hub.code_graph --project /path/to/project
```

두 번째 명령은 stdio MCP 서버이므로 대화형 메뉴가 아니라 JSON-RPC를 기다린다.
설치 런타임이 Python site-packages에 있지 않다면 복제 저장소에서 실행하거나
설치기의 런타임 경로를 사용하는 등록 JSON을 쓴다.

| 도구 | 용도 |
|---|---|
| `graph_status` | 파일 SHA-256 기반 freshness·파싱 오류·규모 확인 |
| `graph_index` | 변경된 프로젝트 다시 파싱 |
| `graph_symbols` | 함수·클래스·모듈 이름 검색 |
| `graph_context` | 정확한 심볼의 제한된 소스 문맥 조회 |
| `graph_callers` / `graph_callees` | 정적 호출·import 관계 조회 |
| `graph_impact` | 역방향 의존성의 변경 영향 범위 탐색 |

Hub에서는 `hub_search`로 도구를 찾은 뒤 `hub_call`로
`code-graph__graph_callers`, `{"symbol":"package.module.function"}`를 호출한다.
동명 심볼은 후보 목록을 반환하므로 정확한 qualified name 또는 ID로 다시 조회한다.

파일 추가·삭제·내용 변경 후에는 기존 그래프 조회를 거절하고 `graph_index`를 요구한다.
심볼과 변경 영향은 정적 후보이며 동적 dispatch·monkey patch·reflection·상속을 모두 해석하지 않는다.
`unresolved_calls`와 `parse_errors`를 함께 확인한다. Python 문법 지원은 실행하는 Python 버전에 따른다.
기본 제외 대상은 `.git`, 가상환경, node_modules, dist/build, vendor/_vendor와 숨김 경로다.
프로젝트 전체 10000개·32MiB, 개별 Python 파일 2MiB, 결과 200개·영향 깊이 10을 상한으로 둔다.

## 실제 GitNexus 검증

2026-11-05에 npm GitNexus 1.6.12를 `/tmp/joongi-codegraph-tools`에 설치했다.
지원 런타임인 Node 22.18.0도 `/tmp/joongi-codegraph-node`에 설치하여 MCP 재접속·심볼 조회를 검증했다.
임시 전용 home·storage root를 사용하고 다음처럼 실제 저장소를 색인했다.

```bash
GITNEXUS_HOME=/tmp/joongi-codegraph-state \
GITNEXUS_STORAGE_ROOT=/tmp/joongi-codegraph-index \
gitnexus analyze /path/to/joongi-skills --skip-git --index-only \
  --skip-agents-md --skip-skills --skip-fts --workers 1
```

측정 당시 100개 파일, 1286개 노드, 2377개 edge, 33개 cluster, 70개 flow를 보고했다.
Hub는 `2025-11-25`로 연결했고 17개 실제 도구를 발견했다. `list_repos` 결과의 프로젝트를 확인하고,
`cypher`에서 `validate_server`와 소스 경로를 조회했다. `context`는 호출자로
`Hub.register`, `HubTest.test_registry_validation`, 호출 대상으로 `validate_url`을 반환했다.
증거 요약은 [실접속 기록](../../examples/code-graph/verification.json)에 있다.

이 색인은 Git 저장소가 아니어서 freshness는 `unknown`이고, FTS·embedding을 켜지 않았다.
일부 flow 탐색 예산이 잘려 있어 없는 edge·flow를 미사용의 증거로 판단하지 않는다.
GitNexus가 기본으로 생성하는 에이전트 문서·스킬 설치는 위 옵션으로 억제했다.
검증용 외부 패키지와 인덱스는 배포 번들에 포함하지 않는다.

GitNexus 1.6.12의 라이선스는 **PolyForm Noncommercial 1.0.0**이다.
상용 프로젝트의 기본 도구로 자동 설치하지 않는다. 외부 도구 선택 시 현재 버전의
라이선스·런타임 요구·외부 전송 여부를 확인한다. 내장 AST 분석기는 외부 GitNexus 코드에 의존하지 않는다.

## 선택과 준비

1. 대상 프로젝트의 언어·규모와 필요한 분석(호출자·영향 범위·참조)을 정한다.
2. 공식 안내에서 설치할 버전·라이선스·로컬 인덱스 위치·MCP 시작 명령을 확인한다.
3. 해당 명령이 agent 설정이나 소스 파일을 자동 수정하는지 확인한다.
4. 프로젝트를 색인하고 커밋·dirty 상태·색인 시각을 기록한다.
5. 처음에는 읽기 중심으로 검토하고 rename/edit 도구는 별도 실행 범위로 다룬다.

## Hub 등록 형식

로컬 관리 UI에 MCP 서버를 등록한다. 명령 경로·인자는 실제로 설치한 서버의 안내에 맞춘다.
`command`에는 전체 셸 문자열 대신 실행 파일 하나를, `args`에는 인자 배열을 넣는다.

```json
{
  "id": "code-graph",
  "name": "Project code graph",
  "transport": "stdio",
  "command": "/absolute/path/to/installed-mcp-executable",
  "args": ["mcp"],
  "protocol_version": "auto",
  "enabled": true
}
```

이는 Hub 입력 schema 예시이며 위 경로는 실행 가능한 기본값이 아니다.
Hub는 임의 shell이나 프로젝트 경로를 추론하지 않는다. 서버가 프로젝트 인자를 지원하면
공식 명령에 맞춰 전달하고, 별도 프로세스로 실행되는 agent에서도 같은 프로젝트를 보게 한다.

HTTP 서버라면 `transport: "http"`, `url`에 실제 MCP endpoint를 등록한다.
비밀 header가 필요하면 `headers`의 값은 비밀 그 자체가 아니라 환경 변수명이다.
예: `{"Authorization": "CODE_GRAPH_AUTHORIZATION"}`.
환경 변수에는 서버가 기대하는 전체 header 값을 넣고 Hub를 시작한다.

## 수용 테스트

등록 → 연결/probe → 실제 도구 목록 확인 → 알려진 함수의 호출자 조회 →
직접 코드 검색과 비교 → 수정 후 재색인 → 영향 분석 결과 재확인을 수행한다.
그래프가 누락한 동적 호출·생성 코드·런타임 구성은 테스트와 직접 확인으로 보완한다.
서버 중지 시 Hub에 오류가 표시되고 다른 스킬 조회가 정상 동작하는지도 확인한다.

외부 도구 버전과 실접속 결과는 [검증 기록](../development/03-verification.md)에 추가한다.
