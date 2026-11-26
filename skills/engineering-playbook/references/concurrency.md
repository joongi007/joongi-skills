# 동시성·병렬성·처리량 (PLAYBOOK §2)

Concurrency(동시성)는 여러 작업의 진행을 겹치는 것, Parallelism(병렬성)은 실제 동시 실행이다.
`async/await`는 실행 모델이며 작업의 영속성·재시작 복구를 보장하지 않는다.
긴 작업의 접수·상태·재시도·멱등성은 [백그라운드 작업](background-jobs.md)을 따른다.

## 실행 모델 선택

먼저 I/O 대기·CPU 시간·p95/p99 지연·처리량·메모리·외부 의존성 상한을 측정한다.
아래는 Python/asyncio의 선택지다. Java virtual thread 등 다른 런타임의 모델에 그대로 적용하지 않는다.

| 작업 | 선택 후보 | 확인할 비용 |
|---|---|---|
| 비동기 드라이버의 I/O 대기 | coroutine + 제한된 동시 실행 | 이벤트 루프 지연·연결 풀·취소 |
| 블로킹 I/O SDK | `asyncio.to_thread` 또는 제한된 thread pool | SDK thread safety·풀 포화·취소 후 실행 지속 |
| 긴 CPU 연산 | process pool·별도 worker; GIL 해제 native code라면 thread도 비교 | 직렬화·프로세스 기동·메모리·실측 병렬성 |
| 요청보다 오래 살아야 하는 작업 | 영속 작업 저장소·queue + worker | 전달·복구·중복·상태 조회 계약 |

한 이벤트 루프의 callback/task는 협력적으로 실행된다. 긴 CPU 연산이나 동기 I/O를 루프에서
실행하면 다른 요청·타이머 진행을 막는다. `async def`로 선언하는 것만으로 nonblocking이 되지 않는다.
스레드가 늘면 항상 느려지거나 async가 항상 빠르다고 가정하지 않는다.

## GIL의 적용 범위

GIL이 활성화된 CPython의 순수 Python CPU 연산은 thread 추가만으로 CPU 병렬성을 얻기 어렵다.
GIL을 해제하는 native library·free-threaded build는 다르다. 실제 interpreter·GIL 상태·확장 호환성을 확인한다.
free-threaded 환경도 thread safety·락 경합·공유 상태의 원자성을 별도로 검증한다.
`to_thread`가 이벤트 루프에서 호출을 옮겨도 CPU 병렬성이나 timeout 시 실행 중단까지 보장하지 않는다.

## 상한과 Backpressure

동시 실행·대기열·메모리·외부 호출량에 상한을 두고, 포화 시 대기·거절·드롭 정책을 정한다.
인프로세스 큐와 프로세스 간 내구성 큐의 보장은 다르다. 수신·영속 접수·처리 완료를 로그에서 구분한다.
producer가 consumer보다 계속 빠르면 큐만 늘리지 말고 처리량·접수 정책을 조정한다.
설정 주입 방식은 [설정](config-secrets.md), Python 수명 관리는 [async 패턴](async-patterns.md)을 본다.

## 수평 확장과 상태

단일 인스턴스도 요구를 만족하는 유효한 선택이다. 확장 시 제약·전환 조건을 기록한다.
복제본에 걸쳐 일관돼야 하는 세션·멱등 키·전역 quota는 공유 저장소 등으로 조정한다.
제한된 프로세스별 캐시·임시 상태까지 일괄 금지하지 않는다. 손실·stale·정합성 범위를 정한다.
worker 간 중복은 업무 멱등성으로 처리하고 scheduler 중복 실행은 [작업 계약](background-jobs.md)을 따른다.
전체 복제본·프로세스의 연결 풀·메모리·외부 호출 상한을 합산해 부하·장애·포화를 검사한다.

근거(2026-11-27): [asyncio·to_thread](https://docs.python.org/3/library/asyncio-task.html),
[CPython free threading](https://docs.python.org/3/howto/free-threading-python.html).
