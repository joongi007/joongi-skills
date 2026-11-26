# 엔지니어링 용어와 의미 경계 (PLAYBOOK §1, §26)

첫 등장에는 통용되는 CS 명칭과 필요한 영어 원어·약어를 함께 쓰고 이후 표기를 일치시킨다.
영어로만 쓰거나 모든 단어에 괄호를 붙이는 것이 목적은 아니다. 설명은 자연스러운 한국어로 쓰되
다른 개념을 같은 이름으로 부르지 않는다. 프로젝트의 domain glossary·프로토콜 계약을 우선한다.

| 용어 | 이 가이드에서의 의미·구분 |
|---|---|
| Authentication / Authorization | 인증은 주체 확인, 인가는 주체가 행위·자원에 접근 가능한지 판단 |
| Principal / Workload identity | 사용자·서비스 등의 주체 / 실행 중 서비스·작업의 신원 |
| Trust boundary / Threat model | 신뢰·권한 가정이 바뀌는 경계 / 자산·공격자·가정·피해를 정의한 위협 모델 |
| Zero Trust / Defense in depth | 위치만으로 신뢰하지 않는 접근 전략 / 독립적인 여러 방어층 |
| Bearer credential / Sender-constrained token | 소지만으로 사용 가능한 자격 / 특정 키·인증서의 소유 증명을 요구하는 토큰 |
| API key / Access Token / Refresh Token | 서비스 계약의 키 / API 접근 자격 / 새 Access Token 발급 자격. 서로 대체하지 않기 |
| Hash / KDF / Encryption | digest 계산 / 비용을 조정한 키 유도·password verifier / 키로 복호화 가능한 암호화 |
| HMAC / Signature | 공유 비밀의 message authentication / 비대칭 서명 문맥에서는 개인키 서명·공개 키 검증 |
| JWT / JWK / JWKS | 토큰 형식 / 키 표현 / 키 집합. 자세한 규칙은 [JWKS](jwt-jwks.md) |
| Rotation / Expiration / Revocation | 새 자격으로 교체 / 정해진 시각 후 효력 종료 / 기한 전 강제 폐기 |
| BFF / TMB | frontend 전용 backend / token-mediating backend. [배치·위협 차이](browser-backends.md) |
| API aggregation / Orchestration | 여러 응답을 묶기 / 여러 작업의 순서·상태·실패 흐름 조정 |
| Hexagonal Architecture | Ports & Adapters로 업무와 외부 입출력의 경계를 분리 |
| Clean Architecture | 안쪽 업무 정책으로 향하는 source-code dependency rule |
| Modular Monolith / Microservices | 한 배포 단위 안의 업무 모듈 / 독립 배포·운영하는 서비스 구조 |
| Dependency Injection / Dependency Inversion | 의존 객체 제공 방식 / 정책과 구체 구현의 의존 방향 원칙 |
| Durable job / Async runtime task | 영속 상태·작업 ID·복구 계약을 가진 작업 / 코루틴·future 등 실행 객체. application task라는 이름만으로 내구성이 생기지는 않음 |
| Concurrency / Parallelism / Asynchrony | 진행을 겹침 / 실제 동시 실행 / 완료를 동기 대기로만 처리하지 않는 실행·통신 방식. 서로 동의어가 아님 |
| Backpressure / Rate limit / Concurrency limit | 소비 능력에 맞춘 생산 제어 / 시간당 호출량 제한 / 동시 실행 수 제한 |
| Deadline / Timeout / Cancellation | 전체 완료 시한 / 특정 대기의 제한 / 중단 요청. timeout·취소가 부작용 중단을 보장하지 않음 |
| Atomicity / Consistency / Durability | 묶음의 전부 또는 전무 / 명시한 제약·일관성 모델 충족 / 보장한 실패 범위에서 확정 상태 보존 |
| Transaction / Unit of Work | DB 등의 원자적 작업 경계 / 유스케이스 변경을 추적·확정하는 패턴. DI 주입 자체가 commit은 아님 |
| Primary key / Foreign key / Index | 행 식별 제약 / 참조 무결성 제약 / 접근 경로. FK·정규화·인덱스는 서로 다른 결정 |
| RLS / Tenant isolation | 행 단위 접근 정책 / tenant 사이의 데이터·권한 경계. RLS 하나로 전체 격리가 완성되지는 않음 |
| RPO / RTO | 허용 데이터 손실의 시간 목표 / 허용 복구 시간 목표. 실측 손실·복구 시간과 구분 |
| Quorum / Majority / Fencing | 프로토콜이 요구하는 동의 수 / 전체의 과반수 / 이전 쓰기 주체의 접근 차단. 제품별 의미 확인 |
| Image tag / Digest | 변경 가능한 이미지 이름 / 내용 식별 hash. 버전 태그 선택이 불변 배포를 보장하지 않음 |
| Wall clock / Monotonic clock | 절대 시각 표현 / 경과 시간 측정용 시계. 서로 다른 원점·호스트 값을 임의 비교하지 않음 |
| Idempotency / Exactly-once | 재시도해도 의도한 효과가 중복되지 않음 / 정의한 범위에서 한 번의 효과·처리 보장. ID 발급만으로 성립하지 않음 |
| Source of truth / Projection | 기준 데이터 / 그 데이터에서 만든 조회·계산용 사본 |
| Cache-aside / Refresh / Bypass | cache miss 시 원천 조회 / cache 읽기 우회 후 갱신 / 읽기·쓰기 모두 우회. [계약](external-cache.md) |
| Fail-closed / Fail-open | 판단 불가 시 접근 중단 / 판단 불가 시 허용. 적용 범위·가용성 비용 명시 |

모호한 문장을 구체화한다. 예를 들어 “토큰 교체”는 signing key rotation인지 Refresh Token rotation인지,
“캐시 갱신”은 원천 재조회인지 invalidation인지, “비동기”는 nonblocking I/O인지 durable job인지 적는다.
TASK ID 같은 식별자는 프로젝트 필드명(task_id/job_id 등)과 mapping을 명시하고 임의로 이름을 바꾸지 않는다.
처음 쓰는 약어는 풀어 쓰고 기존 glossary와 다르면 의미·선택 이유를 기록한다. 새 내용을 쓸 때와 관련 문서를
수정할 때 적용하며, 용어 통일만을 목적으로 무관한 API 식별자·문서 전체를 재작성하지 않는다.
