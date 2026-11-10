# 카탈로그 검색 개선 평가

날짜: 2026-11-11

## 근거와 선택

어휘 검색을 쓰려면 반드시 임베딩이 필요한 것은 아니다. Anthropic의 공식
[Tool Search 문서](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)는
정규식·BM25 검색을 제공하며 도구 이름·설명과 인자 이름·설명을 검색 대상으로 설명한다.
[advanced tool use 자료](https://www.anthropic.com/research/advanced-tool-use)는 별도 임베딩 검색도
가능한 선택지로 다룬다. 이는 Hub에서 어휘 검색을 먼저 개선할 근거이며 모델 성능 향상의 증명은 아니다.

정규식에는 [ripgrep](https://github.com/BurntSushi/ripgrep)의 Rust 기본 엔진을 사용한다.
[Rust regex](https://github.com/rust-lang/regex)의 엔진 특성과 제한을 따르며, 사용자 패턴을
Python `re`로 실행하거나 PCRE2로 자동 전환하지 않는다.

## 재현

```bash
python3 -B scripts/benchmark_catalog_search.py --size 1000 --repeats 3 --output /tmp/catalog-search.json
python3 -B -m unittest tests.test_search -q
```

WSL Python 3.10에서 스킬 3개와 그래프 도구 9개의 실제 메타데이터, 소수의 가상 도구,
대부분의 잡음 도구를 합쳐 1,000항목을 만들었다. 식별자·인자·CamelCase·한국어·대체 영어 검색
22개를 수동 선정했다. 각 검색을 3회 실행해 메타데이터 처리와 순위화 시간을 포함했다.
두 엔진은 동일한 새 설명과 카탈로그로 비교했다. 비교 기준은 이전 이름·설명 부분 문자열 점수다.

| 측정 | 이전 검색 | 새 어휘 검색 |
|---|---:|---:|
| 정답이 첫 번째 | 7/22 | 19/22 |
| 정답이 상위 5개에 포함 | 11/22 | 20/22 |
| MRR@5 | 0.4091 | 0.8788 |
| 검색 시간 중앙값 | 0.267ms | 25.041ms |

새 검색은 이 평가셋에서 더 잘 찾았지만 더 느렸다. `문서 변환`, `정규식 취약점`처럼
영어 메타데이터와 직접 겹치지 않는 두 질의는 여전히 실패했다. 영어 대체 질의는 찾았다.
정규식 subprocess 성능은 이 keyword 비교에 포함하지 않았다.

평가셋은 구현에 맞춰 선정한 smoke test다. held-out 검색 성능, 실제 프로젝트의 검색 분포,
LLM 작업 성공률·전체 지연·토큰 절감·임베딩 대비 우위를 입증하지 않는다.
원본 결과는 로컬 `.local/integrations/lexical-search-evaluation.json`에 보관한다.

클라이언트가 어떤 도구 정의를 모델에 보내는지는
[별도 실측](2026-11-11-client-tool-loading-evaluation.md) 범위다. 이 검색 결과와 합쳐 해석하지 않는다.
