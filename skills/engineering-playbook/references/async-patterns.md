# Python asyncio의 수명·취소·시간 계약 (PLAYBOOK §23)

Python/asyncio를 쓰는 경우에 적용한다. 실행기 선택은 [동시성](concurrency.md),
요청 종료·프로세스 재시작 후에도 보존할 작업은 [내구성 작업 계약](background-jobs.md)을 따른다.

## 블로킹 호출과 큐 (§23.1)

단발 블로킹 I/O는 `await asyncio.to_thread(call, ...)`로 옮길 수 있다.
지속적인 작업은 제한된 thread pool·consumer를 비교한다. 기존 풀을 쓰는 `to_thread`가 매번 새 thread를
만든다고 가정하지 않는다. CPU 병렬성은 GIL·native code·실행 환경을 확인한다.

인프로세스 producer-consumer를 선택했다면 `queue.Queue(maxsize=N)` 또는 `asyncio.Queue(maxsize=N)`로
상한을 정한다. 큐 종류에 맞는 thread-safety를 지키고, 이벤트 루프에서 동기 `put()`·`join()`으로 대기하지 않는다.
`put_nowait()`의 `Full`/`QueueFull`에 대해 거절·드롭·재시도 정책을 명시한다. 빈 큐의 timeout도 처리한다.
종료는 수신 중지 → 처리 drain 또는 명시적 취소 → flush → worker join 순서와 시간 예산을 정한다.
daemon thread 종료에 데이터 보존을 맡기지 않는다. 버퍼와 영속 접수는 서로 다른 보장이다.

## Task 소유권과 예외 (§23.2)

관련 task를 함께 기다릴 수 있으면 `TaskGroup` 등 structured concurrency를 검토한다.
분리 task는 강한 참조·소유자·완료 처리·예외 수집·종료 예산을 둔다.
완료 callback에서 집합에서 제거하기 전에 오류를 수집한다. 완료 task를 먼저 제거한 뒤 종료 시
`gather()`만 하면 이미 제거된 task의 예외를 놓칠 수 있다.

```python
# spawn 인자는 신뢰한 애플리케이션의 coroutine이며 이 집합은 같은 이벤트 루프에서만 사용한다.
tasks: set[asyncio.Task] = set()

def completed(task: asyncio.Task) -> None:
    try:
        task.result()  # 완료된 예외를 관찰한다
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("background_task_failed")  # 로그 수집의 비밀 마스킹도 적용
    finally:
        tasks.discard(task)

def spawn(coro):
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(completed)
    return task
```

소유자는 종료 시 새 task 생성을 막고 남은 task를 기다리거나 취소·정리한다.
`CancelledError`는 cleanup 뒤 전파하는 것을 기본으로 하며 의도적 취소 억제는 이유를 남긴다.
`wait_for(shield(task), timeout)`는 대기 timeout에서 원본 task 취소를 막지만 직접 취소·프로세스 종료를
막지 않는다. 남은 task의 소유자·완료 관측을 유지한다. 실행 중 thread·외부 부작용의 중단도 별도로 확인한다.

## Clock domain과 타임스탬프 (§23.3)

프로토콜에 시간 원점(epoch 또는 monotonic), 단위(s/ms/us/ns), 정밀도·범위·시간대를 명시한다.
값의 크기만 보고 초·나노초를 추측하지 않는다. 작은 ns와 큰 s의 범위는 겹친다.
monotonic clock은 경과 시간 측정용이며 다른 호스트·재부팅 사이의 절대 시각으로 비교하지 않는다.
절대 시각은 합의한 UTC/epoch 계약을 사용하고 clock skew를 고려한다.
정수·실수 변환의 정밀도 손실·overflow·음수·잘못된 단위를 검증한다. ns int64도 선택형 저장 형식이다.

근거(2026-11-27): [asyncio task·취소·thread 실행](https://docs.python.org/3/library/asyncio-task.html).
