# DB 설계·테넌트 격리·쿼리 성능 (PLAYBOOK §7, §12, §25)

DB 작업에서는 데이터 소유권·테넌트 경계·무결성·읽기/쓰기 부하·삭제와 복구 요구를 먼저 확인한다.
단일 사용자 로컬 DB와 다중 테넌트 서비스에 같은 격리 구조를 강제하지 않는다. 아래는 공통 판단 기준이며
RLS·인덱스·DDL의 실제 동작은 선택한 DB 엔진·버전에서 검증한다.

## 목차

- 격리 단위와 Row-Level Security
- 기본키와 물리 저장 특성
- 워크로드·인덱스·EXPLAIN
- 정규화·비정규화와 무결성
- ON DELETE·보존·복구
- 변경 전후 증거

## 격리 단위와 Row-Level Security

| 방식 | 적합한 조건 | 비용·남는 경계 |
|---|---|---|
| 전용 DB 인스턴스/클러스터 | 강한 운영·장애·규제 격리가 필요 | 비용·연결·migration·백업 관리 증가 |
| 테넌트별 database | 자격·스키마·복원 단위를 나눌 필요 | 같은 인스턴스의 CPU·I/O·관리자 권한은 공유 가능 |
| 테넌트별 schema/table | 논리 객체·보관 주기를 분리할 필요 | 객체 수·migration fan-out·동적 SQL·권한 관리 |
| 공유 table + tenant key | 많은 테넌트와 공통 스키마, 운영 효율 | 모든 접근 경로의 행 격리·noisy neighbor 제어 필요 |

테이블 이름이나 schema만 나눴다고 보안 격리가 완성되지는 않는다. 실제 DB role·접속 자격·GRANT와
관리/백업 경계를 확인하고 식별자·`search_path`를 사용자 입력으로 임의 선택하게 하지 않는다.
공유 table에는 tenant key를 명시하고, RLS(Row-Level Security)를 지원하면 DB 차원의 방어층으로 우선 검토한다.
RLS가 없는 엔진은 검증한 애플리케이션 정책·DB 자격 분리 또는 더 강한 격리 구조를 선택하고 한계를 기록한다.

PostgreSQL RLS를 선택할 때:

- 대상 table에서 RLS를 활성화하고 명령별 정책을 적용한다. 활성화 후 해당 정책이 없으면 기본 거부다.
  `TRUNCATE` 같은 table 전체 명령은 RLS 대상이 아니므로 app role의 해당 권한도 별도로 제한한다.
- 실제 app role은 superuser·`BYPASSRLS`·table owner와 분리한다. owner는 통상 우회하므로
  필요하면 `FORCE ROW LEVEL SECURITY`를 검토한다. FORCE도 superuser/BYPASSRLS를 제한하지는 않는다.
- `USING`으로 읽기/변경 대상, `WITH CHECK`로 삽입·변경 후 행의 허용 범위를 검증한다.
  정책별 role·명령·허용 합성 방식을 확인하고 tenant key가 다른 INSERT/UPDATE도 거부한다.
- tenant context는 인증·소속 검증 뒤 서버가 설정한다. connection pool에서는 transaction-local 설정 등으로
  수명을 한정하고 반환·오류·취소·다음 요청에서 누출되지 않는지 확인한다. background job에도 같은 경계를 적용한다.
  클라이언트가 임의 tenant를 세션 변수에 넣을 수 있는 경로를 열지 않는다. 사용자 지정 GUC에 의존한 RLS가
  SQL injection이나 직접 SQL 권한까지 방어한다고 가정하지 않는다.
- 참조도 tenant 경계를 포함한다. 예: 자식의 `(tenant_id, parent_id)`가 부모의
  `UNIQUE (tenant_id, id)`를 참조하게 해 다른 테넌트의 부모와 연결되지 않게 한다.
  전역 유일 ID를 쓴다는 것만으로 이 무결성이 보장되지는 않는다.
- FK·UNIQUE 등 참조 무결성 검사는 RLS를 우회한다. 오류를 통한 존재 여부 노출과
  관리자·migration·백업·복원 경로의 우회를 따로 검토한다. RLS는 API의 객체·행위 인가를 대신하지 않는다.
- 실제 app role로 조회·목록·집계·수정·삭제·export·직접 SQL을 검사한다. tenant 변경·pool 재사용·
  다른 tenant의 FK 참조·정책 누락·복원 후 정책/role까지 검증한다. 관리자 접속 테스트만으로 통과 처리하지 않는다.

## 기본키와 물리 저장 특성

기본키(Primary Key, PK)는 행 식별·유일성 계약과 물리 저장 비용을 함께 고려해 선택한다.

| 후보 | 검토할 이점 | 검토할 비용 |
|---|---|---|
| 정수 surrogate key (예: BIGINT identity) | 작은 키·비교 비용·인덱스 locality | 중앙 생성·분산 병합, 증가 패턴·규모 노출, hot page 경합 |
| UUID (random/time-ordered) | 분산 생성·병합·외부 식별 | 키 폭·인덱스 크기, random 삽입 locality, time-ordered 값의 시각 노출 |
| tenant를 포함한 composite key | tenant-local 유일성·참조 경계 표현 | FK·인덱스 폭·ORM·pagination 계약 복잡도 |

자연키는 불변성·폭·변경 전파를 검토하고 필요하면 surrogate PK와 업무 UNIQUE를 분리한다.
UUIDv7 등 시간 순서가 있는 키도 항상 더 빠르지는 않다. 생성 방식·동시성·실제 엔진으로 비교한다.
InnoDB는 clustered PK를 사용하며 secondary index에도 PK가 들어가 넓은 PK의 비용이 커질 수 있다.
PostgreSQL의 일반 heap table에 같은 물리 특성을 그대로 적용하지 않는다. 순차 ID·UUID는 인가 수단이 아니다.

## 워크로드·인덱스·EXPLAIN

읽기/쓰기 비율, QPS(queries/s)·TPS(transactions/s)·동시 연결, 행 수·폭·증가율, tenant별 편중, point lookup·range scan·
정렬·join·집계·batch 쓰기·삭제를 먼저 기록한다. 읽기 최적화가 쓰기 지연·용량을 얼마나 늘리는지도 측정한다.

- 인덱스는 실제 WHERE·JOIN·ORDER BY·pagination과 selectivity에 맞춘다. 예를 들어 tenant별 최신 목록에는
  `(tenant_id, created_at, id)`가 후보지만 모든 쿼리에 tenant-first를 강제하지 않는다. 복합 키의 순서·
  범위 조건·정렬 방향·partial/covering index의 지원과 비용을 실행 계획으로 확인한다.
- 불필요한/중복 인덱스는 쓰기·WAL/redo·복제·저장 비용을 늘린다. PostgreSQL의 FK 선언은 참조하는
  자식 열의 인덱스를 자동 생성하지 않으므로 join·부모 삭제 검사와 쓰기 비용을 보고 추가 여부를 결정한다.
  사용 통계의 관측 기간·재시작·정기 업무를 확인하지 않고 인덱스를 삭제하지 않는다.
- N+1·과다 열/행 조회·반복 round trip·불필요한 sort·큰 OFFSET·컬럼 변환/암시적 cast·오래된 통계를 점검한다.
  적절한 batching·projection·keyset pagination 등을 비교하되 의미·정렬 안정성·동시 변경 계약을 유지한다.
- `EXPLAIN`으로 예상 계획을 보고, 대표 데이터의 격리 환경에서 PostgreSQL의
  `EXPLAIN (ANALYZE, BUFFERS)` 등으로 estimated/actual rows·loops·join·filter·sort spill·I/O를 비교한다.
  sequential scan은 작은 테이블이나 큰 비율 조회에서 합리적일 수 있다. 무조건 index scan으로 바꾸지 않는다.
- **EXPLAIN ANALYZE는 실제로 쿼리를 실행한다.** 쓰기·트리거·함수의 외부 부작용·lock을 고려한다.
  transaction rollback도 sequence 증가·외부 호출 등을 전부 되돌리지 않는다. 운영에서 임의 쓰기 쿼리를
  시험하지 말고 승인된 범위·timeout·부하 상한과 안전한 사본을 사용한다.

read/write latency p50/p95/p99·처리량과 함께 table/index/전체 저장량·증가율·WAL/redo·
buffer hit·실제 read/write I/O·lock wait·deadlock·복제 지연·vacuum/bloat를 관측한다.
동일한 데이터 분포·하드웨어·부하·기간에서 cold/warm cache와 혼합 부하를 구분해 변경 전후를 비교한다.
빈 테이블·단일 요청의 평균 시간만으로 운영 성능을 단정하지 않는다. 계획·통계에도 민감 값이 남지 않게 한다.

## 정규화·비정규화와 무결성

정규화(normalization)는 함수 종속과 데이터 중복·갱신 이상을 줄이는 설계다.
FK(foreign key)는 참조 무결성을 집행하는 제약이며 FK를 추가하는 것 자체가 정규화는 아니다.
업무 불변식·변경 빈도·join 비용·운영 편의로 정규화 수준을 선택한다.

반복 join·집계가 실제 병목이라면 비정규화(denormalization), materialized view·read model을 비교한다.
중복 데이터의 source of truth·갱신 경로·허용 지연·재구성·대조/수정 절차를 함께 설계한다.
이를 정하지 않고 읽기를 빠르게 하는 복사본만 추가하지 않는다. 리팩토링 시 분리·통합 양쪽을 검토하고
dual-write 실패·backfill·이전/신규 스키마 호환·검증·rollback 비용을 측정한다.
FK 제거는 별도 결정이다. 대체 검증·동시 쓰기의 무결성·고아 데이터 탐지/복구 없이 성능만 보고 제거하지 않는다.

## ON DELETE·보존·복구

| 정책 | 적합한 의미 | 주의할 점 |
|---|---|---|
| `RESTRICT` / `NO ACTION` | 참조가 남은 부모의 삭제를 막음 | PostgreSQL에서 NO ACTION의 지연 검사 가능 여부 등 차이 확인 |
| `CASCADE` | 부모와 수명을 공유하는 종속 행도 삭제 | 연쇄 fan-out·lock·WAL·실수의 피해 범위·감사·복구 |
| `SET NULL` | 부모가 사라져도 자식 기록이 의미를 유지 | nullable·업무 의미·다른 제약과의 호환 |
| 명시적 삭제 workflow / soft delete | 승인·보존·단계적 정리 필요 | 참조·가시성·UNIQUE·실제 purge·재시도·복구 설계 |

한 행의 삭제가 다른 업무 기록까지 연쇄 삭제하지 않아야 하면 RESTRICT와 명시적 삭제 순서 등을 우선 비교한다.
RESTRICT는 자식을 남긴 채 부모 한 행만 지우는 옵션이 아니다. 보존하려는 자식과 참조 관계를 먼저 결정한다.
CASCADE도 소유 관계가 명확하면 유효하다. 모든 FK에 일괄 적용하거나 일괄 금지하지 않는다.
삭제 전 영향 행 수·권한·보관 의무를 확인하고 대규모 삭제는 batch·상한·중단/재개를 설계한다.
soft delete도 백업이나 법적 파기를 대신하지 않는다. 잘못된 삭제·부분 완료·PITR 복원을 검증한다.

## 변경 전후 증거

ADR/PR에는 격리 방식·실행 role·PK/UNIQUE/FK·인덱스·ON DELETE의 선택 이유, 대표 쿼리의 계획,
부하/용량 측정 조건과 전후 수치, 테넌트 누출·동시성·삭제/복구 검증, migration·rollback을 남긴다.
보안·무결성·읽기/쓰기 SLO·운영 비용 중 어떤 trade-off를 수용했는지 명시한다.

관련: [DB 소유권](architecture.md), [백업·복구](database-recovery.md), [공통 인가](identity-authorization.md).
공식 자료 확인: 2026-11-27. PostgreSQL 18·MySQL 8.4 자료는 엔진별 예시이며 도입 버전을 강제하지 않는다.
[RLS](https://www.postgresql.org/docs/18/ddl-rowsecurity.html),
[무결성·ON DELETE](https://www.postgresql.org/docs/18/ddl-constraints.html),
[EXPLAIN](https://www.postgresql.org/docs/18/using-explain.html),
[복합 인덱스](https://www.postgresql.org/docs/18/indexes-multicolumn.html),
[성능 관측](https://www.postgresql.org/docs/18/monitoring-stats.html),
[InnoDB PK·secondary index](https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html).
