# TASK ID 기반 비동기 처리와 실행 역할 (PLAYBOOK §2, §4, §23)

언어와 무관하게 요청 시간 예산을 넘기거나 재시도·복구가 필요한 작업에 적용한다.
짧은 I/O 호출의 `async/await`와, 요청 종료 후에도 남는 내구성 있는 작업은 구분한다.
메모리의 future·task ID만 반환하는 것으로 프로세스 재시작을 견디지는 못한다.

## API·worker·scheduler 경계

| 역할 | 책임 | 분리할 때 확인할 점 |
|---|---|---|
| API | 입력·권한 검증, 작업 접수, 상태·결과 조회 | 접수량·큐 크기 상한, 사용자별 quota |
| worker | 큐 소비, 업무 실행, 결과·진행 상태 저장 | CPU/메모리별 동시성, timeout, 재시도·종료 |
| scheduler | 예정 시각에 실행할 작업 등록 | 시간대·누락 실행·중복 등록·겹친 실행 정책 |

같은 저장소·이미지에서 `api`, `worker`, `scheduler` 진입점만 나누어 시작할 수 있다.
별도 프로세스라고 별도 마이크로서비스·DB가 필요한 것은 아니다. Java에서도 같은 분리를 쓸 수 있다.
초기에는 단일 프로세스를 택할 수 있지만, API 복제본마다 scheduler를 시작해 중복 실행시키지 않는다.
여러 scheduler가 필요하면 리더 선출·lease 또는 공유 저장소의 원자적 등록을 사용하고,
`작업 종류 + 대상 + 예정 시각` 등으로 중복 키를 정한다. lease 만료·리더 교체 시 중복도 처리한다.
Kubernetes CronJob도 정확히 한 번 실행을 보장하지 않으며 `concurrencyPolicy`는 그 CronJob의 Job에만 적용된다.

## 최소 HTTP 계약 예시

1. `POST /tasks`에서 입력·소유권·멱등 키를 검증한다. 같은 사용자·같은 키의 요청 내용이
   달라지면 충돌로 처리한다. 작업과 enqueue 의도를 내구성 있게 기록한 뒤 `202 Accepted`,
   `Location: /tasks/{task_id}`, 적절한 `Retry-After`와 `task_id`를 반환한다.
2. worker는 등록된 작업을 받아 상태를 원자적으로 전이한다.
   예시: `queued → running → succeeded | failed | cancelled`; 재시도는 횟수·다음 시각을 기록해
   `running → queued`로 되돌릴 수 있게 한다. 허용 전이와 결과 저장의 원자성을 정한다.
3. `GET /tasks/{task_id}`는 상태·결과 또는 안전한 오류를 반환한다. task ID가 추측하기
   어려워도 매번 사용자·tenant 소유권을 검사한다. 상태 조회도 rate limit을 두고 polling은 백오프한다.
4. 취소 API는 협력적 취소 의도를 기록한다. 이미 끝난 작업·취소와 완료의 경합을 정의하고,
   외부에 완료된 부작용까지 되돌렸다고 표시하지 않는다. 결과·실패 기록의 보관 기간도 정한다.

DB commit 뒤 enqueue 전에 죽는 유실 구간은 transactional outbox 또는 검증한 DB 큐로 닫는다.
worker는 결과를 내구성 있게 저장한 뒤 ack한다. 큐 제품의 전달 보장을 확인하고 중복 전달을 전제로 한다.
결제·메일 등 부작용은 업무 멱등 키·외부 제공자의 멱등 계약으로 보호한다. TASK ID만으로 exactly-once가 되지 않는다.
재시도는 일시 오류에만 상한·백오프·jitter를 적용하고 소진 작업은 격리·수동 재처리 경로를 둔다.

## 멀티프로세스·장애 검증

- CPU 작업은 프로세스 풀이나 별도 worker를 후보로 삼고 I/O 작업은 런타임에 맞는 제한된 동시성을 쓴다.
  프로세스 간 메모리·DB 연결은 공유된다고 가정하지 않는다. 자식 프로세스에서 연결 풀을 초기화하고,
  API·worker 복제본 수를 곱한 전체 DB 연결·메모리·외부 호출량을 산정한다.
- 큐에는 필요한 작업 데이터·식별자만 넣는다. 임의 명령·pickle 등 비신뢰 실행 payload를 받지 않고
  producer/consumer 권한을 나눈다. 비밀·인증 컨텍스트를 그대로 직렬화하지 않는다.
- 종료 시 신규 수신을 멈추고 drain한다. 처리 중 worker 강제 종료·lease 만료·재전달에서 복구하는지 확인한다.
- 접수 직후 API 종료, DB commit 후 publish 실패, 중복 배달, 부작용 후 ack 전 종료,
  scheduler 두 개 동시 실행, 취소·완료 경합, 다른 사용자의 상태 조회를 검증한다.
- 큐 대기 시간·최고 작업 나이·실행 시간·재시도·실패·고립된 running 상태를 관측한다.
  단순 프로세스 생존 확인으로 작업 진행을 판단하지 않는다.

관련: [동시성](concurrency.md), [DB 소유권](architecture.md), [outbox 등 패턴](patterns-scale.md).
근거: [Asynchronous Request-Reply](https://learn.microsoft.com/en-us/azure/architecture/patterns/asynchronous-request-reply),
[Background jobs의 역할·복구 설계](https://learn.microsoft.com/en-us/azure/architecture/best-practices/background-jobs),
[CronJob의 중복·동시성 제한](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/).
