# 카탈로그 검색 실험실

이 저장소의 검색 함수만 오프라인으로 비교한다. 공개 스킬과 합성 metadata를 사용하며 사용자 상태·등록·계정·인증은 읽지 않는다. 전체 Hub 지연이나 에이전트 성공률을 측정하는 도구는 아니다.

- [측정 보고서](../research/2026-11-19-search-first-evaluation.md)
- [2026-11-19 원자료](results-2026-11-19.json): 전체·질의별 p50/p95와 5,000개 후속 결과. 요약 통계이며 개별 시간 표본은 아니다.
- 출처: 이 저장소의 `scripts/benchmark_catalog_search.py` corpus/cases와 `joongi_hub/search.py`. 기준 구현은 [709cc5a](https://github.com/joongi007/joongi-skills/blob/709cc5ada82b8abfb8ca20c9f71506d3eee80ef5/joongi_hub/search.py). 확인일: 2026-11-19. 코드·자료는 저장소 루트 MIT 라이선스를 따른다. 외부 baseline 코드를 복제해 보관하지 않는다.

## 실행

Python 3.10+와 Git이 필요하다. `regex` 비교에는 ripgrep(`rg`)도 필요하며 없으면 해당 모드만 생략한다. 저장소 루트에서 실행한다. 별도 Python 의존성 설치나 실행 중 네트워크 연결은 필요하지 않다.

```sh
python refs/catalog-search-lab/compare.py --out dist/search-evaluation.json
python refs/catalog-search-lab/compare.py --followup --out dist/search-followup.json
```

기본값은 100/1,000/5,000개·23개 keyword 질의·각 5회다. `--followup`은 기본 5,000개에서 현재 no-cache와 캐시 객체 전달만 비교한다. `--sizes 100 --repeats 1`로 짧게 확인할 수 있다. seed 기본값은 20261119다. 출력 파일이 이미 존재하면 덮어쓰지 않는다.

기준 구현은 `git show 709cc5ada82b8abfb8ca20c9f71506d3eee80ef5:joongi_hub/search.py`로 읽어 메모리에서 실행한다. 신뢰하는 Git checkout에서 실행해야 한다. 해당 commit이 로컬 history에 있어야 하며 shallow clone·Pages 소스 번들·Git 없는 압축본에서는 없을 수 있다. 자동 fetch하지 않고 명확한 오류로 끝난다. `--baseline-revision`은 전체 40자리 commit SHA만 받는다.

## 비교 해석

기준·현재 구현에 같은 corpus와 `limit=5/detail=full`을 전달하고 반환 dictionary 전체의 동등성을 검사한다. mode별 점수·schema가 다르면 즉시 실패한다. keyword cold는 매번 새 캐시를 만들고 warm은 한 번 준비한 객체를 재사용한다. 5,000개는 2,000개 한도를 넘으므로 실제 캐시 hit가 없다. literal/regex는 keyword 캐시를 쓰지 않는다.

응답 크기는 넓은 질의 `project`의 이전 기본 100/full과 현재 기본 5/summary에 선택 상세 1건을 더한 compact JSON bytes다. 상세는 같은 corpus의 `Document.value`로 모사하며 실제 RPC 봉투·승인 schema wrapping·추가 왕복·토큰 수는 제외한다. 스키마와 기본값이 바뀌면 결과도 달라진다.

2026-11-19 초기 측정의 새 구현은 commit되지 않은 중간 상태였다. 현재 checkout은 한도 초과 시 JSON 직렬화 이전에 우회하며 그 변경 뒤 5,000개 후속 결과를 별도로 보존했다. 현재 스크립트는 현재 checkout과 고정 baseline을 비교한다. 초기 중간 구현이나 당시 호스트 부하를 복원하지 않는다. 다른 테스트·빌드가 동시에 실행됐고 CPU를 격리하지 않았으므로 절대 지연 차이를 특정 수정 하나의 효과로 단정하지 않는다. 실행 결과에는 날짜·CPU·Python·플랫폼·소스 해시를 기록한다.
