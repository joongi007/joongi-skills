# 스킬·MCP 검색과 상세 조회

<!-- contract: catalog.defaults = {"limit":5,"detail":"summary","summary_chars":160,"exposure":"search-first","usage_enabled":false} -->

문서 ID: OPS-SEARCH · 요구사항: REQ-REGISTRY, REQ-CALL

검색은 현재 작업 범위에서 **사용하도록 선택한 스킬·등록된 MCP 서버·연결된 도구**를 함께 찾습니다.
인터넷의 새 서버를 찾는 마켓플레이스가 아닙니다. 등록 서버는 연결 전에도 이름·상태로 찾을 수 있지만,
그 서버의 도구와 원격 스킬은 `hub_connect`로 실제 연결한 뒤 검색할 수 있습니다.
검색·상세 조회만으로 서버를 시작하거나 도구를 실행하지 않습니다.

## 1. 이름과 한 줄 설명으로 찾기

에이전트의 `hub_search` 기본값은 **`limit: 5`, `detail: "summary"`, `kind: "all"`**입니다.
stdio·HTTP MCP·관리 화면 검색은 같은 기본 계약을 사용합니다. 결과의 이름·종류·출처와
한 줄 설명을 보고 후보를 고릅니다. 검색 응답의 설명은 공백을 정리한 160자까지 제공하며 더 길면
`description_truncated: true`를 붙입니다. 요약에는 입력 schema나 스킬 파일 목록을 넣지 않습니다.

```json
{"query":"repo_root","kind":"tool"}
```

짧은 키워드·정확한 도구 식별자를 사용하세요. 결과가 없으면 영어 식별자·동의어로 다시 찾고,
너무 많으면 `match: "all"`, `kind`, 정확한 서버 ID로 좁힙니다. 한국어를 영어 의미로 번역하는 검색은 아닙니다.

## 2. 고른 항목의 정확한 상세 보기

`hub_get_item`에 결과의 `kind`와 `name`을 그대로 전달합니다. 재검색이나 순위 선택이 아니라
**현재 범위에서 그 항목 하나만 정확히 조회**합니다. 꺼졌거나 더 이상 없는 항목은 오류입니다.
도구는 전체 설명·원본 schema·Apps/Tasks metadata와 승인 대기 대안을 확인할 수 있습니다.

```text
hub_get_item(kind="tool", name="code-review-graph__get_impact_radius_tool")
```

스킬은 상세에서 참조 파일을 확인하고 `hub_read_skill`로 필요한 본문만 읽습니다.
다른 출처의 동명 스킬은 `company__design-guide`처럼 출처가 붙은 이름으로 구별합니다.
관리 화면에서는 결과의 **상세**를 누른 뒤 전체 설명·schema를 보고 다음 행동으로 이동합니다.

## 3. 읽거나 실행하기

도구의 schema에 맞춰 `hub_call`합니다. 서버 항목은 연결 관리로 이동해 먼저 연결하고,
스킬 항목은 `hub_read_skill`로 읽습니다. 상세를 보는 행위는 실행 승인이나 OAuth 동의를 대신하지 않습니다.

```text
hub_call(name="code-review-graph__get_impact_radius_tool", arguments={...})
hub_read_skill(name="company__design-guide")
```

이 흐름은 출력의 크기를 줄이는 단계적 조회입니다. grep/ripgrep의 정규식 평가를 세 번 수행하는 방식이 아닙니다.
상세 조회와 실제 실행은 각각 정확한 식별자를 사용합니다.

## 옵션과 API

| 옵션 | 기본값 | 동작 |
|---|---|---|
| `mode` | `keyword` | 단어별 순위화. `literal`은 고정 문자열, `regex`는 Rust 정규식 |
| `match` | `any` | keyword에서 한 단어 이상 일치. `all`은 모든 단어 일치 |
| `limit` | `5` | 1~100개. 더 많은 후보가 필요할 때 명시적으로 늘림 |
| `detail` | `summary` | 한 줄 설명. 기존 전체 결과가 필요하면 `full`을 명시 |
| `kind` | `all` | `skill`, `server`, `tool`로 제한 |
| `server` | 없음 | 정확한 서버 ID로 제한 |

빈 검색어는 현재 선택된 카탈로그에서 상위 항목을 반환하며 전체 목록을 뜻하지 않습니다.
관리 검색 API는 `GET /api/v1/search?q=...&kind=tool`이고 `detail`·`limit`도 받을 수 있습니다.
이 API가 제공하는 필터는 q/kind/detail/limit이며 MCP의 mode/match/server와 구분합니다.
상세는 `GET /api/v1/catalog/item?kind=tool&name=서버ID__도구명`으로 조회합니다.
관리 API에는 관리 인증이 필요하며, HTTP MCP와 관리 API는 다른 접점입니다.

## 모델에게 보이는 도구 목록

기본 `search-first`는 허브 기본 도구와 함께, 원본에 App 리소스가 있거나
`execution.taskSupport`가 명시적으로 `optional`/`required`인 외부 도구만 native `tools/list`에 제공합니다.
일반 외부 도구는 검색·상세 조회 후 `hub_call`로 사용합니다. App 내부 callback은 별도 app-only alias로 보존합니다.
이 판정은 stdio·HTTP의 공통 서비스에서 수행하며, Hub가 legacy 응답에 덧붙이는 Task 정보로
일반 도구를 Task로 오인하지 않습니다. 고급 `all-native`는 선택된 서버의 모든 도구를 직접 노출합니다.

노출 정책을 바꿨다면 에이전트가 `tools/list`를 다시 읽도록 MCP 연결을 다시 여세요.
목록 변경 알림 푸시는 제공하지 않습니다. Apps 지원 여부와 실제 실행 승인은 기존 호환성·인증 계약을 따릅니다.
[검색 범위·출처·묶음 설정](14-catalog-preferences.md).

## 어휘 검색과 캐시

이름·별칭·서버·설명·인자 이름/설명을 순위화합니다. 정확한 이름을 우선하고 드문 단어에 가중치를 줍니다.
CamelCase·snake_case 분리, 대소문자 무시, Unicode NFKC 정규화를 사용합니다.
스킬 참조 본문·프로젝트 파일·schema 기본값/예제·비밀 값은 색인하지 않습니다.
미연결 서버의 명령 인수·환경변수·인증·비밀 URL도 검색 문서에 넣지 않습니다.

각 Hub 프로세스는 정규화한 검색 metadata의 토큰 빈도 준비 결과를 **LRU 최대 2개** 보관합니다.
준비 결과마다 최대 2,000항목·2 MiB metadata까지만 캐시하고 큰 목록은 캐시 없이 계산합니다.
metadata 내용이 달라지면 새 키를 사용하고 설정 변경 시 캐시를 비웁니다. 결과·도구 응답·인증은 캐시하지 않습니다.
프로필마다 Hub가 분리되며 다른 프로세스와 캐시를 공유하지 않습니다. 원본 목록 스캔·metadata 확인 비용은 남습니다.
캐시가 실제 작업 성공률이나 모든 규모의 지연을 개선한다고 보장하지 않습니다.

전체 검색 입력은 1,000자, 필드는 8,192자, 필터 후 10,000항목·UTF-8 8 MiB 상한을 유지합니다.
`regex`만 선택적으로 `rg`가 필요합니다. stdin metadata만 전달하고 Rust 기본 엔진·1 MiB regex/DFA·2초 제한을 사용합니다.
PCRE2·lookaround·backreference는 지원하지 않으며 `rg` 부재 시 Python backtracking으로 우회하지 않습니다.
keyword/literal은 추가 실행 도구 없이 동작합니다.

## 측정과 과거 기록

[2026-11-11 검색 평가](../../refs/research/2026-11-11-catalog-search.md)와
[클라이언트 로딩 평가](../../refs/research/2026-11-11-client-tool-loading-evaluation.md)는
당시 전체 native 노출·기본 full·이전 카탈로그를 측정한 기록입니다. 새 기본값·캐시·정책의 성능 수치가 아닙니다.
[2026-11-19 오프라인 실측](../../refs/research/2026-11-19-search-first-evaluation.md)은 같은 합성 metadata와 반환값으로 keyword cold/warm·literal/regex 및 요약+상세 payload 크기를 비교했습니다. 100/1,000개 warm 전처리에 이점이 있었지만 5,000개는 캐시를 우회했고 개선을 관측하지 못했습니다. 전체 Hub I/O·실제 MCP 왕복·에이전트 성공률은 측정하지 않았습니다. [스크립트와 원자료](../../refs/catalog-search-lab/README.md)에서 환경과 후속 측정 한계를 확인하세요.
