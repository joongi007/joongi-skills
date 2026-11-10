# 도구·스킬 검색

문서 ID: OPS-SEARCH · 요구사항: REQ-REGISTRY, REQ-CALL

`hub_search`는 현재 프로필의 스킬과 연결된 MCP의 도구·스킬 메타데이터를 검색한다.
연결하지 않은 MCP를 검색 때문에 실행하지 않는다. 프로젝트 파일을 grep하거나 스킬의
참조 문서 전체를 읽는 기능은 아니다. MCP가 먼저 필요하면 `hub_connect`로 연결한다.

## 검색 순서

1. 도구 이름이나 짧은 키워드로 `limit: 5`, `detail: "summary"` 검색한다.
2. 결과가 없거나 너무 많으면 대체 용어·영어 식별자, `match: "all"`, 서버 필터로 좁힌다.
3. 선택한 정확한 이름으로 다시 검색해 전체 `inputSchema`를 확인한 뒤 `hub_call`한다.
   스킬은 선택한 항목을 `hub_read_skill`로 읽는다.

```json
{"query":"repo_root","kind":"tool","limit":5,"detail":"summary"}
```

```json
{"query":"code-review-graph__get_impact_radius_tool","mode":"literal","detail":"full"}
```

```json
{"query":"impact|review","mode":"regex","server":"code-review-graph","limit":5,"detail":"summary"}
```

| 옵션 | 기본값 | 동작 |
|---|---|---|
| `mode` | `keyword` | `keyword`: 단어별 순위화, `literal`: 고정 문자열, `regex`: Rust 정규식 |
| `match` | `any` | keyword에서 하나 이상 일치. `all`은 모든 단어 일치 |
| `limit` | `100` | 1~100개 |
| `detail` | `full` | 기존 전체 결과 유지. `summary`는 schema·파일 목록을 제외 |
| `kind` | `all` | `skill` 또는 `tool`로 제한 |
| `server` | 없음 | 정확한 서버 ID로 제한 |

요약 설명은 300자 이후 잘라 `description_truncated: true`를 표시한다. 실행 조건과 인자는
전체 정의에서 확인한다. 빈 검색어는 필터에 맞는 카탈로그를 반환한다.
웹의 기존 검색 API는 기본 옵션을 사용한다.

## 순위와 범위

이름·서버·설명·인자 이름과 설명을 검색한다. 정확한 이름을 우선하고, 이름의 단어와
드문 단어에 가중치를 주는 BM25 계열 점수로 정렬한다. CamelCase와 snake_case도 나눈다.
기본 검색은 대소문자를 구분하지 않고 Unicode NFKC를 정규화한다. 형태소 분석이나
의미 번역은 하지 않는다. `문서 변환`으로 영어 도구를 못 찾으면 `convert markdown`으로 재검색한다.

공용 Code Review Graph 도구에는 `변경 영향`, `호출 관계`, `코드 리뷰`, `긴 함수`,
`색인 상태` 같은 짧은 한국어 키워드도 설명에 포함한다. 원래 영어 설명·식별자는 유지한다.
등록한 외부 MCP 설명을 일괄 번역하지 않으며, 임의의 한국어 문장을 이해하는 기능은 아니다.
이 검색과 재검색 안내는 HTTP 서버 없이 순수 stdio에서도 동일하게 제공된다.

비밀 값, schema 기본값·예제, 프로젝트 파일과 참조 문서 본문은 색인하지 않는다.
검색어는 1,000자, 필드는 8,192자, 필터 이후 카탈로그는 10,000항목·UTF-8 8 MiB로 제한한다.
매 검색에서 현재 메타데이터를 순위화하므로 별도 DB·임베딩 서버·오래된 검색 캐시가 없다.

`regex`만 선택적으로 로컬 `rg`가 필요하다. stdin으로 메타데이터만 전달하며 파일을 탐색하지 않는다.
Rust 기본 엔진을 강제하고 PCRE2·lookaround·backreference를 허용하지 않는다.
정규식 크기·DFA 크기를 각각 1 MiB로 제한하고 2초에 중단한다. `rg`가 없거나 패턴을
지원하지 않으면 오류를 반환한다. Python backtracking 정규식으로 대체하지 않는다.
keyword·literal은 추가 설치 없이 동작한다.

## 클라이언트 검색과의 구분

이 구현은 Hub의 `hub_search` 순위를 바꾼다. Codex·Claude 등의 자체 ToolSearch 순위는
해당 클라이언트가 정한다. 구체적인 도구 설명은 양쪽 검색에 도움이 될 수 있지만,
Hub가 클라이언트의 선택·토큰 사용량·성공률을 보장하지 않는다. native 도구와 Apps 노출은 유지한다.

비교 측정은 [검색 평가](../../refs/research/2026-11-11-catalog-search.md),
클라이언트 로딩 측정은 [별도 보고서](../../refs/research/2026-11-11-client-tool-loading-evaluation.md)를 본다.
