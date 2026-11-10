# Code Review Graph 선택 연결

문서 ID: OPS-REVIEWGRAPH · 요구사항: REQ-REGISTRY, REQ-CALL, REQ-APPS, REQ-TASKS

[code-review-graph](https://github.com/tirth8205/code-review-graph) 2.3.9는 MIT 라이선스의
외부 코드 분석 MCP다. 여러 프로젝트에 사용할 수 있어 선택 통합으로 추가했다.
Hub의 필수 의존성이나 기본 자동 설치 패키지는 아니다.

## 실제 확인한 범위

Linux/WSL, Python 3.14.0, FastMCP 3.4.11, mcp 1.30.0으로 이 저장소를 분석하고
2025-11-25 stdio로 Hub에 연결했다. 분석 도구 7개를 발견하고
`list_graph_stats_tool`과 `query_graph_tool(file_summary)`을 호출했다.
[검증 기록](../../examples/code-graph/review-graph-verification.json).

해당 스냅샷의 통계 조회 결과는 파일 50개, 노드 518개, edge 6,774개이며
Python·JavaScript·Bash·PowerShell을 포함했다. edge는 정적 분석 후보를 포함하며
호출 관계 중 직접 해석한 것과 unresolved를 구분한다. 숫자는 품질이나 최신성의 보장이 아니다.
Git 이력이 없는 이 환경에서는 PR diff·커밋별 변경 탐색을 검증하지 않았다.

## 공용 연결 설치

공용 연결은 한 저장소에 고정하지 않는다. Hub의 프로젝트 선택 어댑터가 도구마다 필수인
`repo_root`로 대상을 정하고, `<Hub 상태>/review-graphs/<프로젝트 식별자>/data/graph.db`에
서로 다른 그래프를 저장한다. 실행 디렉터리나 이전 호출의 프로젝트를 기본값으로 쓰지 않는다.
Windows 경로를 WSL 연결에 전달하면 `D:\Project\game`을 `/mnt/d/Project/game`으로 해석한다.
같은 폴더의 symlink·대소문자 별칭은 파일 식별자와 저장된 원본 경로를 대조한다.

```bash
uv venv "$HOME/.local/share/joongi-hub/tools/code-review-graph" --python 3.14
uv pip install --python "$HOME/.local/share/joongi-hub/tools/code-review-graph/bin/python" 'code-review-graph==2.3.9'

# 기본은 프로젝트 선택 방식. 공용 영구 저장소에 등록한다.
python3 scripts/check_review_graph.py \
  --python "$HOME/.local/share/joongi-hub/tools/code-review-graph/bin/python" \
  --register
```

이미 같은 ID가 등록돼 있으면 설정을 검토하고 `--replace`로 명시적으로 교체한다.
`--print-config`는 UI에 넣을 JSON을 만든다. 외부 Python 환경은 자동 설치하지 않는다.
프로젝트에 고정한 연결이 필요한 경우에만 `--fixed-project --target /절대/프로젝트경로`를 쓴다.
이 경우의 `--data-dir`은 원래 단일 프로젝트의 상태 폴더다. 공용 기본값으로 쓰지 않는다.

## 에이전트 사용 순서

1. `graph_project_status`에 **현재 작업 중인 프로젝트의 절대 경로**를 `repo_root`로 전달한다.
2. `not_indexed`이면 같은 경로로 `graph_build`를 호출한다. 다른 저장소의 그래프를 대체 사용하지 않는다.
3. `graph_project_status`를 조회해 `ready`를 확인한다.
4. 기존 분석 도구에도 매번 같은 `repo_root`를 전달한다. 코드 수정 후 `graph_build`의
   `refresh: true`로 해당 프로젝트만 갱신한다.

Hub 경유 도구 이름에는 `code-review-graph__` 접두사가 붙는다.

```json
{"repo_root":"/mnt/d/Project/my-game"}
```

색인은 요청받았을 때만 만들며 동시에 최대 2개, 각 빌드는 최대 5분이다.
빌드는 MCP 연결 종료와 독립된 로컬 작업으로 완료 상태를 기록한다. 분석용 upstream은 어댑터
프로세스당 최근 사용한 최대 2개만 유지한다. 자동 전체 프로젝트 스캔·auto-watch는 하지 않는다.
Git/SVN이 없는 프로젝트는 `graph_build`의 `initialize_project: true`를 명시해야 빈
`.code-review-graph` 표지를 만든다. 그 외에는 프로젝트에 파일을 쓰지 않고 캐시만 갱신한다.
기존 `.local/code-review-graph` 등 다른 그래프 DB를 덮어쓰거나 자동 이전하지 않는다.
이동·삭제된 프로젝트와 기존 캐시의 식별 관계가 달라지면 자동으로 다른 프로젝트를 연결하지 않는다.

외부 도구는 자체 ignore 파일을 쓰므로 `.gitignore`만으로 제외됐다고 가정하지 않는다.
이 저장소의 `.code-review-graphignore`는 `.local`·vendored YAML·생성된 SDK 번들을 제외한다.

## 제공 도구와 확장 경계

| 도구 | 용도 |
|---|---|
| `graph_project_status` | 선택한 프로젝트의 색인 준비·진행·실패 상태 |
| `graph_build` | 해당 프로젝트만 비동기 색인·갱신 |
| `list_graph_stats_tool` | 색인 규모·언어·갱신 시각 |
| `query_graph_tool` | 호출·참조·파일 요약 |
| `get_impact_radius_tool` | 변경 영향 범위 |
| `get_review_context_tool` | 리뷰에 필요한 코드 문맥 |
| `get_minimal_context_tool` | 필요한 문맥 선별 |
| `find_large_functions_tool` | 큰 함수·클래스 탐색 |
| `get_docs_section_tool` | 도구 사용 문서 |

외부 서버에는 분석 도구 7개만 허용하고, 어댑터가 관리 도구 2개를 추가해 총 9개를 노출한다.
모든 도구는 `repo_root`를 필수로 받는다. 입력 스키마는 검증한 2.3.9 형식을 보존한다. 모든 도구의 모든 인자를
실행 검증한 것은 아니며, refactor 적용·wiki 생성·embedding 도구는 노출하지 않는다.

이 구성에는 `ui://` App 리소스를 선언한 도구가 없고 upstream native Tasks도 광고하지 않는다. `graph_build`의 자체 진행 조회는 MCP Tasks가 아니다.
그래프 도구를 Hub의 백그라운드 Task로 실행할 수는 있지만, 이것이 원본 서버의 native Task
지원이나 그래프 시각화 App을 뜻하지는 않는다. 별도 그래프 App 구현은 이번 범위에 넣지 않았다.
Hub의 일반 Apps·Tasks 전달 경계는 [호환성 계약](../architecture/02-compatibility.md)을 따른다.


## 프로젝트 격리 검증

`tests/test_review_graph_gateway.py`는 두 저장소 교차 호출·별도 DB·필수 경로·미색인 안내·
독립 연결의 상태 공유·symlink 별칭·명시적 비 Git 표지 생성을 검증한다.
실제 2.3.9에서도 서로 다른 Python·TypeScript 저장소를 색인한 뒤 A→B→A 통계를 조회해
파일이 각각 해당 저장소에만 속함을 확인했다. 기존 joongi-skills 그래프는 보존했다.
