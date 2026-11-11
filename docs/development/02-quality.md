# 테스트와 문서 정합성

문서 ID: DEV-QUALITY · 요구사항: REQ-PROCESS, REQ-KNOWLEDGE

## 검사 수준

| 수준 | 증명할 것 | 대표 실패 |
|---|---|---|
| 단위 | 독립 함수·상태 전이 | 경계값·잘못된 입력·허용하지 않은 전이 |
| 계약 | 버전별 요청·응답·오류 | metadata 누락·다른 schema·ID 충돌 |
| 통합 | 실제 transport와 저장소 연결 | 세션·재연결·파일 갱신·timeout |
| 수용 | 사용자의 처음부터 끝까지 흐름 | 설치 후 새 프로세스 실행 불가·제거 시 손상 |
| 문서 | 설명과 실제 계약 일치 | CLI 인자·경로·지원 표가 코드와 다름 |

## 이 저장소의 기본 검증

```bash
./build.sh --check
python3 scripts/check_docs.py
python3 scripts/check_contracts.py
python3 -m unittest discover -s tests -v
python3 -m joongi_hub --help
python3 scripts/mutation_check.py
```

lint·문서 검사·mutation 결과는 [검증 기록](03-verification.md)에 실제 명령과 함께 적는다.
실행하지 않은 검사는 통과했다고 쓰지 않는다.

## 테스트 설계

기대값은 명세의 독립 값으로 정한다. 같은 구현 helper로 actual과 expected를 만들지 않는다.
정상 호출과 함께 timeout, broken JSON, 비정상 subprocess 종료, 잘못된 경로,
취소·중복 요청, 서버명·도구명 충돌, 기존 설정 변경을 검증한다.
fixture는 실제 JSON-RPC를 읽고 응답해야 하며 실제 client adapter가 이를 호출해야 한다.
외부 계정 인증 없이 재현 가능한 fixture와 외부 제품의 실접속 결과를 구분한다.

## AST 뮤테이션 테스트

`scripts/mutation_check.py`는 Python AST에서 비교 연산자 반전, and/or 교체, not 제거,
if 분기 고정, boolean 반전·정수 경계 변경을 자동 열거한다. 각 변이는 임시 소스에서
독립 실행되며 원본 파일을 수정하지 않는다. 기본 캠페인은 소유권과 지속성 경계인
`storage.py` 전체를 `tests.test_storage_contracts`로 검증한다.

```bash
python3 scripts/mutation_check.py --report dist/mutation-report.json
python3 scripts/mutation_check.py --fail-on-survivor
python3 scripts/mutation_check.py --target joongi_hub/storage.py --tests tests.test_storage_contracts --operators comparison,boolean,branch
```

baseline 통과를 먼저 확인하고 killed·survived·timeout·invalid를 별도 기록한다.
구문 오류를 테스트가 잡아낸 결함으로 세지 않는다. 기본 명령은 살아남은 변이도 모두 보고하며,
모든 변이를 검토한 대상에서만 `--fail-on-survivor`를 사용한다. 특정 모듈의 탐지율을 전체
코드의 mutation coverage로 부르지 않는다. 재현 결과와 동등 변이 판단은
[mutation 보고서](mutation-report.json)를 본다.

CI는 `--fail-on-survivor`로 미탐·invalid·timeout·baseline 실패를 차단한다. 예외 허용 목록은 없다.
JSON 표현만 바꾸는 변이도 Registry의 4 MiB 제한과 결합하면 재조회 실패를 일으킬 수 있다.
ASCII·한국어 대용량 레코드의 실제 저장·재조회를 포함해 검사한다.
현재 storage 캠페인은 70개 변이를 모두 탐지했고 미탐·invalid·timeout은 0개다.

1. 초기 대상: 경로 허용 판단, 설치 소유권·hash 판단, 버전 분기, task 전이.
2. 분기 반전·경계 변경·반환 변경·검사 제거 후 기존 테스트가 실패하는지 확인한다.
3. 살아남은 변이는 테스트 누락·동등 변이·의도한 지원 범위 밖으로 분류한다.
4. 중요한 변이만 기준으로 삼고 생성 UI 코드나 외부 schema 전체에 점수 목표를 강제하지 않는다.

뮤테이션을 구현했다는 사실과 실행 결과는 다르다. 도구·대상·변이 수·kill/survive·시간을 기록한다.
수동 seed 결함 테스트와 AST 자동 생성 캠페인의 결과를 구분한다.

## 문서 정합성 절차

변경한 REQ-ID에서 설계·ADR·테스트·운영 예제로 이동하여 같은 동작을 설명하는지 확인한다.
로컬 링크, routing의 참조 파일, 중복 ID, 폐기 용어와 설정 키를 검사한다.
문법·링크 검사는 의미의 일치까지 증명하지 않으므로 별도 검토한다.
오래된 ADR은 삭제보다 `superseded` 상태와 대체 ADR 연결을 남긴다.

명시적 인터페이스·버전·capability·경로 주장은 [실행 가능한 계약](../architecture/04-contracts.md)으로
관리한다. `check_docs.py`는 contracts.json이 있는 저장소에서 이 검사도 함께 실행하므로,
링크만 맞고 실제 API나 CLI·설치 경로가 달라진 변경을 통과시키지 않는다.
