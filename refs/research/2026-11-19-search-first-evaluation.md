# 카탈로그 검색 오프라인 성능 측정

측정 시각(UTC): 2026-11-19T14:30:37.669856+00:00 → 2026-11-19T14:32:00.353203+00:00
Python: 3.10.12 (main, Aug 31 2026, 10:18:17) [GCC 11.4.0]
CPU: AMD Ryzen 7 9700X 8-Core Processor · 논리 CPU 16개
환경: Linux-6.18.58.1-microsoft-standard-WSL2-x86_64-with-glibc2.35

## 목차

- [측정 범위와 방법](#측정-범위와-방법)
- [Keyword 지연](#keyword-지연)
- [Literal·regex 지연](#literalregex-지연)
- [응답 크기](#넓은-질의의-응답-크기)
- [판단과 한계](#판단과-한계)
- [5,000개 후속 측정](#후속-측정-5000개에서-직렬화-전-항목-수-검사)

## 측정 범위와 방법

`scripts/benchmark_catalog_search.py`의 공개 스킬·합성 메타데이터 corpus와 기존 질의 22개에 넓은 질의 `project`를 추가했다. 실제 사용자 상태·등록·인증은 읽지 않았다. 이전 구현은 Git commit `709cc5ada82b8abfb8ca20c9f71506d3eee80ef5`의 `joongi_hub/search.py`에 있는 rank, 새 구현은 측정 시작 시의 `joongi_hub.search.rank`다. 단순 substring 카운터와 비교한 수치가 아니다.

각 질의는 5회, 각 크기·구현당 115표본이다. 같은 코퍼스·질의·`limit=5/detail=full`을 사용하고 seed 20261119로 질의와 구현 순서를 섞었다. 반환 항목 전체를 비교해 이름·점수·스키마가 동일함을 확인했다. p50은 중앙값, p95는 nearest-rank다. 전체 p95는 서로 다른 질의의 표본을 합친 값이며 질의별 통계는 JSON에 있다.

CPU 격리·governor 고정은 하지 않았고 다른 에이전트의 빌드·테스트가 동시에 실행될 수 있다. 아래 변동폭을 포함해 해석해야 한다. 이 측정은 `rank()` 호출만 포함하며 Hub의 파일 탐색·카탈로그 생성·전송·연결·브라우저·LLM 작업은 제외한다.

## Keyword 지연

| 항목 수 | 구현 | p50 ms | p95 ms | 최소 ms | 최대 ms |
|---|---|---:|---:|---:|---:|
| 100 | old_rank | 2.145 | 2.973 | 2.023 | 5.753 |
| 100 | current_no_cache | 2.153 | 2.446 | 2.039 | 3.335 |
| 100 | current_cold_cache | 2.271 | 2.862 | 2.142 | 6.392 |
| 100 | current_warm_cache | 0.599 | 0.794 | 0.509 | 0.983 |
| 1000 | old_rank | 21.025 | 28.378 | 17.665 | 41.700 |
| 1000 | current_no_cache | 21.001 | 30.056 | 17.742 | 33.000 |
| 1000 | current_cold_cache | 21.697 | 29.674 | 19.071 | 32.166 |
| 1000 | current_warm_cache | 6.156 | 11.222 | 4.972 | 14.663 |
| 5000 | old_rank | 139.948 | 194.510 | 104.042 | 290.181 |
| 5000 | current_no_cache | 140.667 | 184.841 | 110.907 | 211.650 |
| 5000 | current_cold_cache | 149.011 | 205.989 | 117.331 | 227.701 |
| 5000 | current_warm_cache | 153.524 | 194.342 | 120.531 | 217.614 |

warm은 사전 준비 한 번 후 같은 메타데이터를 재사용한다. cold는 요청마다 새 캐시를 만들며 직렬화·해시·전처리 비용을 포함한다. no-cache도 전처리 이후 같은 랭킹 알고리즘을 쓴다.

캐시는 프로세스·프로필 안에서 최대 2개 전처리 결과, 2,000개 항목·2 MiB 메타데이터까지만 보관한다. 5,000개 코퍼스는 의도적으로 캐시를 우회하며 warm 이름의 측정에도 실제 hit가 없다.

| 항목 수 | warm 캐시 상태 |
|---|---|
| 100 | `{"entries": 1, "hits": 115, "misses": 1, "max_entries": 2, "max_documents": 2000, "max_metadata_bytes": 2097152}` |
| 1000 | `{"entries": 1, "hits": 115, "misses": 1, "max_entries": 2, "max_documents": 2000, "max_metadata_bytes": 2097152}` |
| 5000 | `{"entries": 0, "hits": 0, "misses": 0, "max_entries": 2, "max_documents": 2000, "max_metadata_bytes": 2097152}` |

## Literal·regex 지연

각 대표 질의는 9회 반복했다. 이 모드는 keyword 전처리 캐시를 쓰지 않는다. regex는 실제 ripgrep 프로세스 생성·매칭 비용을 포함한다.

| 항목 수 | 모드·질의 | 구현 | p50 ms | p95 ms |
|---|---|---|---:|---:|
| 100 | literal: `project` | old_rank | 2.083 | 2.219 |
| 100 | literal: `project` | current_no_cache | 0.384 | 0.537 |
| 100 | literal: `project` | current_warm_cache | 0.373 | 0.441 |
| 100 | regex: `project|review` | old_rank | 4.524 | 4.973 |
| 100 | regex: `project|review` | current_no_cache | 2.431 | 3.776 |
| 100 | regex: `project|review` | current_warm_cache | 2.518 | 4.905 |
| 1000 | literal: `project` | old_rank | 19.314 | 24.448 |
| 1000 | literal: `project` | current_no_cache | 3.428 | 4.061 |
| 1000 | literal: `project` | current_warm_cache | 3.388 | 3.894 |
| 1000 | regex: `project|review` | old_rank | 23.615 | 29.209 |
| 1000 | regex: `project|review` | current_no_cache | 6.295 | 8.043 |
| 1000 | regex: `project|review` | current_warm_cache | 6.395 | 7.569 |
| 5000 | literal: `project` | old_rank | 159.850 | 203.999 |
| 5000 | literal: `project` | current_no_cache | 31.633 | 58.664 |
| 5000 | literal: `project` | current_warm_cache | 33.925 | 47.332 |
| 5000 | regex: `project|review` | old_rank | 149.704 | 188.855 |
| 5000 | regex: `project|review` | current_no_cache | 35.306 | 54.863 |
| 5000 | regex: `project|review` | current_warm_cache | 33.008 | 49.768 |

## 넓은 질의의 응답 크기

질의는 `project`다. 공백 없는 UTF-8 JSON payload를 비교했고 JSON-RPC/content 봉투와 실제 서비스의 승인 스키마 wrapping은 제외했다. 선택한 상세 1건은 같은 corpus의 `Document.value`로 모사했다. 실제 MCP 왕복·토큰 수를 측정한 값은 아니다.

| 항목 수 | 이전 결과 수 | 새 결과 수 | 이전 100/full bytes | 새 5/summary bytes | 선택 상세 bytes | 새 합계 bytes | 감소 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100 | 88 | 5 | 25506 | 848 | 377 | 1225 | 95.20% |
| 1000 | 100 | 5 | 22618 | 848 | 377 | 1225 | 94.58% |
| 5000 | 100 | 5 | 22618 | 848 | 377 | 1225 | 94.58% |

## 판단과 한계

- 100/1,000개 항목의 warm keyword 전처리 재사용에는 이 코퍼스에서 이점이 있었다. 캐시 없는 keyword는 이전 구현과 비슷했고 cold는 직렬화·해시 비용 때문에 오히려 느릴 수 있다.
- 5,000개에서는 캐시가 적용되지 않아 개선을 관측하지 못했다. warm 객체를 전달한 p50이 no-cache보다 나빴으며 min/max 변동도 컸다. 이를 전체 Hub의 속도 향상으로 설명하면 안 된다.
- literal·regex의 개선은 사용하지 않는 keyword 전처리를 생략한 효과다. warm/no-cache 차이를 해당 모드의 캐시 효과라고 해석하지 않는다.
- 초기 측정 당시 구현은 캐시 한도를 넘긴 요청에서도 메타데이터 JSON을 만든 뒤 우회했다. 항목 수 검사를 먼저 하면 불필요한 직렬화는 피할 수 있지만 이번 측정에서는 소스를 수정하지 않았다.
- 요약 5개와 상세 1개의 payload 합계는 작은 편이었다. 여러 상세·큰 스키마를 읽으면 합계가 커지고, 상세 조회의 추가 왕복 지연도 있다.
- 결과 동등성은 이 smoke set에서 관측한 사실이며 모든 질의의 정확도·다국어 의미 검색·모델 선택 성공률을 증명하지 않는다.
- 사용자의 실제 상태나 계정, 네트워크 MCP, 전체 stdio/HTTP 요청, 파일 탐색·원본 변경 감지 비용은 측정하지 않았다.

원자료: [JSON](../catalog-search-lab/results-2026-11-19.json) · 재현 방법: [검색 실험실](../catalog-search-lab/README.md).

## 후속 측정: 5,000개에서 직렬화 전 항목 수 검사

측정(UTC): 2026-11-19T14:35:11.806580+00:00 → 2026-11-19T14:35:43.399085+00:00
환경: 3.10.12 (main, Aug 31 2026, 10:18:17) [GCC 11.4.0] · Linux-6.18.58.1-microsoft-standard-WSL2-x86_64-with-glibc2.35 · 논리 CPU 16개
측정한 search.py SHA-256: `8a42c8514fab0a3ae64f65fd628abfe3e559158d01fe01fee1d9984368772239`

`len(selected)>2000` 검사를 메타데이터 JSON 직렬화보다 먼저 수행하는 메인 수정을 대상으로, 같은 5,000개 corpus·23개 질의·각 5회·limit=5/detail=full을 재측정했다. 구현 순서는 seed 20261119로 섞었다. 반환 항목·점수·스키마는 모두 동등했다. 이전 표와 원자료는 변경하지 않았다.

| 구현 | 표본 | p50 ms | p95 ms | 최소 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| current_no_cache | 115 | 145.130 | 179.142 | 109.302 | 193.877 |
| current_warm_cache | 115 | 148.321 | 177.740 | 113.788 | 198.920 |

캐시 상태: `{"entries": 0, "hits": 0, "misses": 0, "max_entries": 2, "max_documents": 2000, "max_metadata_bytes": 2097152}`

이 크기에서는 캐시가 실제로 적용되지 않는다. 수정은 우회 대상의 불필요한 JSON 작업을 제거하며, 전체 Hub나 5,000개 코퍼스의 캐시 hit를 제공하는 변경이 아니다. 다른 에이전트의 테스트가 동시에 실행 중이고 CPU를 격리하지 않았으므로 이전 실행과의 절대 수치 차이를 이 수정 하나의 효과로 단정할 수 없다. literal/regex 전처리 생략 결과와 응답 크기 결과는 앞선 측정 그대로다.

후속 측정 재현: [검색 실험실](../catalog-search-lab/README.md)의 `--followup` 명령을 사용한다.

초기 측정의 새 구현은 작업 중인 checkout이었다. 이후 항목 수 검사 순서가 바뀌었으므로 현재 checkout으로 재실행한 값은 초기 구현의 정확한 재현이 아니다. 후속 측정은 해당 수정 이후의 별도 실행이며, 원자료에 소스 해시를 보존했다. 실행 시점의 코드·공개 스킬·호스트 부하가 달라지면 수치와 응답 크기도 달라질 수 있다.
