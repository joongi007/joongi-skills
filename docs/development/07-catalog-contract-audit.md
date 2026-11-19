# 검색·카탈로그 계약 독립 감사와 검증 계획

문서 ID: DEV-CATALOG-AUDIT · 기준일: 2026-11-19

## 독립 감사의 범위

별도 에이전트가 수정 전 main `709cc5ada82b8abfb8ca20c9f71506d3eee80ef5`의 README와
maintained docs 51개를 목록화하고 검색·노출·기본값·스킬 범위 관련 진술을 구현·테스트와 대조했다.
site의 검색/설치 설명, stdio·HTTP 진입점, source·프로필·native 설치 경계도 조사했다.
이 단계에서는 소스·문서를 수정하지 않았고 외부 실제 계정·MCP·사용자 홈은 호출하지 않았다.
과거 ADR과 날짜별 시험 기록은 현재 계약과 구분했다. 모든 외부 제품의 최신 기능이나 모든 코드의 무결성을 증명한 감사는 아니다.

감사 결과를 전달한 뒤 해당 에이전트가 설치기와 문서 구현도 맡았다.
이후 설치기·문서의 자체 수정과 검사는 위 read-only 독립 감사와 구분한다.
전체 변경의 수용 검증은 통합 테스트·문서 계약·브라우저·CI에서 다시 확인해야 한다.

## 확인한 사실과 불일치 유형

| 초기 발견 | 분류 | 후속 계약 |
|---|---|---|
| 추적 소스의 stdio·HTTP는 동일한 Hub.tools를 사용해 연결 도구를 모두 노출 | 사용자 관측과 추적 소스의 차이. stdio만 완료됐다고 단정할 수 없음 | 공통 서비스에서 search-first 기본/App·명시적 Task 예외 |
| rank·service·MCP schema·HTTP 기본은100/full, 설명은5/summary 권장, UI는20/summary | 당시 표는 코드와 일치하나 흐름별 기본/권장이 혼재 | 공통5/summary, 명시적 full 호환 옵션 |
| 전체 schema를 얻으려면 정확한 이름을 fuzzy 검색에 다시 전달 | 독립 상세 API 미구현 | kind/name exact hub_get_item |
| 프로젝트만 common allowlist/로컬 override, 공용 source·분류 선택 없음 | 기능 누락 | 범위별 출처·묶음·개별 on/off와 일관된 카탈로그 읽기 |
| 기존 native 설치는 모든 기본 스킬을 매 update에 다시 복사 | Hub off와 에이전트 사본의 역할 차이 | 저장되는 exclude-category와 명시적 reset, 소유권/수정 보호 |
| source/skills는 한 단계만 탐색하고 설치 snapshot도 같은 경로를 가정 | 중첩 폴더만 추가하면 읽기/설치가 함께 깨질 위험 | 독립 로컬 source roots와 namespace, 자동 native 복사와 구분 |
| 매 검색에서 정규화·토큰 빈도 재계산 | 비용 개선 후보 | 제한된 metadata 준비 LRU; 실제 지연은 별도 측정 |
| 사용 집계 없음 | 선택 기능 누락 | 기본off·지역 집계·비밀 미기록·한도/초기화 |
| 문서 계약은 버전·CLI·route 중심 | 기본값/노출 drift를 자동 검출하지 못함 | 검색·노출 실행 계약과 negative 회귀 검사 |

초기 근거는 `joongi_hub/service.py`의 당시742–755/1344–1363줄, `search.py`의 당시134–167줄,
`server.py`의 당시370–384줄, `profiles.py`의 당시157–201줄, `scripts/install_manager.py`의 당시609–616줄이다.
줄 번호는 위 기준 커밋의 위치다. 수정 후 현재 파일의 같은 줄을 뜻하지 않는다.

## 문서 동기화

현재 동작은 [검색](../operations/08-catalog-search.md), [선호·출처·통계](../operations/14-catalog-preferences.md),
[설치](../installation/00-index.md), [호환성](../architecture/02-compatibility.md), [ADR-0015](../adr/0015-search-first-catalog.md)에 정리한다.
README·첫 사용·사이트 문구도 같은 세 단계와 선택/설치의 차이를 안내한다.
ADR-0005의 전체 native, ADR-0010의 full 기본값은 당시 결정으로 남기고 대체 ADR을 연결한다.
이전 검색/토큰 측정값을 새 캐시·새 노출 정책의 성능 증거로 재사용하지 않는다.

## 검사 계획과 판정 기준

| 검사 경로 | 확인할 독립 기대값 |
|---|---|
| stdio·HTTP × 2025·2026 | 일반 동기 도구 숨김, 원본 App/explicit Task 유지, all-native 복원 |
| App callback | app-only alias·namespace·다른 서버 동명·미협상 UI·원본 metadata 보존 |
| 함수·schema·MCP·관리 API·UI | 생략한 limit/detail이5/summary, 한 줄160자, 상한100·invalid 거절 |
| 정확한 상세 | kind/name 하나만 조회, 끈 항목/동명 모호성 거절, 상세만으로 실행하지 않음 |
| 검색→상세→호출 | 원본 schema 유지, 일반 도구도 hub_call 가능, 검색 기록으로 승인 우회 불가 |
| 범위·source·묶음 | 변경 후 검색·스킬 읽기·resource·native Skills·목록 일관성, 다른 프로필 누출 없음 |
| owner 변경 | local stdio/credential bridge만 MCP 변경, 직접 HTTP/App/외부 서버는 변경 불가 |
| metadata 캐시 | uncached 기대 결과와 일치, 입력/결과 변조로 cache 오염 불가, 정의 변경/정책 변경 후 stale 결과 없음 |
| 사용 통계 | 기본off·opt-in·동시 집계·30일/1,000키·초기화, rawquery/args/payload/token/path 미기록 |
| native 설치 | category 제외 누적/보존·새 에이전트·reset 우선순위·회사 파일/수정본 보호 |
| 문서 검사 | 잘못된 기본값·노출 주장 fixture가 검사를 실패시킴. 링크 성공만으로 의미 일치를 대신하지 않음 |
| 실제 UI | 상위 목록→상세→읽기/실행, 설정 저장·전환·오류·늦은 응답·모바일·키보드 |

현재 관련 코드는 `tests/test_search.py`, `tests/test_catalog_preferences.py`, `tests/test_usage_stats.py`,
`tests/test_installer.py`, `tests/browser_catalog.cjs`, `tests/browser_catalog_preferences.cjs`와 MCP/HTTP 통합 fixture다.
위 표는 요구되는 수용 조건이며 파일이 있다는 사실만으로 전부 통과했다고 판정하지 않는다.
추가 통합 테스트와 최종 CI 실행 결과를 [검증 기록](03-verification.md)에 이어 기록한다.

## 먼저 실행한 설치기 검증

- Linux Python: `python -B -m unittest tests.test_installer` 40개 통과.
- native Windows: 같은40개 실행, 플랫폼 전용2개 제외, 실패 없음.
- 실제 임시 홈에 설치한 runtime에 category helper가 포함되고 재실행 update가 제외를 유지함을 확인했다.
- installer 두 파일의 Ruff 검사 통과. 사용자 실제 설치 상태를 이 검사의 대상으로 사용하지 않았다.

이는 해당 구성요소의 자체 검사다. 전체 CI·공개 Pages 배포 검증이 완료됐다는 뜻은 아니다. 성능의 별도 측정 범위는 아래 기록을 따른다.

## 오프라인 검색 측정 근거

[2026-11-19 실측](../../refs/research/2026-11-19-search-first-evaluation.md)은 고정 Git baseline과 현재 구현을 같은 공개 스킬·합성 metadata·23개 질의·명시적 5/full로 비교했다. 이름·점수·schema가 동등한지 확인하고 cold/warm 지연과 기본 100/full 대 5/summary+상세 1건의 JSON bytes를 별도로 기록했다. [재현 스크립트와 원자료](../../refs/catalog-search-lab/README.md)를 함께 보관한다.

5,000개는 캐시 한도를 넘어 hit가 없고, 직렬화 전 항목 수 검사 후속 실행에서도 속도 개선을 단정하지 않았다. 동시 테스트 부하·CPU 미격리 한계와 중간 구현/후속 구현 차이를 보고서에 보존했다. 이 기록은 전체 stdio/HTTP I/O·네트워크 MCP·LLM 선택 성공률이나 전체 수용 조건 통과를 증명하지 않는다.
