# 파이프라인 비동기 패턴 (PLAYBOOK §23)

## 이벤트 루프 ↔ 워커 스레드 분리 (§23.1)

CPU/blocking I/O 작업(Parquet 쓰기, JPEG 인코딩 등)은 **이벤트 루프에서 직접 호출하지 않는다**:

```python
# ❌ 이벤트 루프 점유
def on_lidar(data):
    storage.write_parquet(data)  # blocking I/O

# ✅ asyncio.to_thread (단발 blocking 호출)
async def on_stop():
    await asyncio.to_thread(session.flush_all)

# ✅ producer-consumer (queue.Queue) — 지속적인 blocking 처리
class _SensorWorker:
    def __init__(self, storage):
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def put_lidar(self, ts, points, source, recv_ns):
        self._q.put_nowait(("lidar", ts, points, source, recv_ns))  # 즉시 반환

    def _run(self):
        while True:
            item = self._q.get(timeout=1.0)
            ...  # 스레드에서 blocking I/O
```

**규칙:**
- **이벤트 루프**: `put_nowait()` 호출만 (즉시 반환).
- **워커 스레드**: 큐 드레인 + 플러시 주기 관리.
- 종료 시 sentinel `("_stop", done_event, result)` 방식으로 깨끗하게 드레인.

## asyncio Task 수명 관리 (§23.2)

**태스크 참조를 보관하지 않으면 GC에 의해 조기 종료될 수 있다.**

```python
# 단기 태스크 — 집합으로 추적
encode_tasks: set[asyncio.Task] = set()
task = asyncio.create_task(...)
encode_tasks.add(task)
task.add_done_callback(encode_tasks.discard)

# 정리 시
await asyncio.gather(*encode_tasks, return_exceptions=True)
```

**규칙:**
- **장기 태스크**: `session.livekit_task` 등 **필드에 저장** → `on_stop()`에서 `await`.
- **단기 태스크**: **집합(`set`)으로 추적**, `add_done_callback(set.discard)` 패턴.
- **타임아웃이 있는 대기**: `asyncio.wait_for(asyncio.shield(task), timeout=N)` — `shield`로 원본 태스크 취소 방지.

## 타임스탬프 단위 변환 (§23.3)

로봇은 `time.monotonic()` 초(float) 단위로 전송:

```python
def _parse_ts_ns(raw) -> int:
    v = float(raw or 0)
    if v < 1e12:          # 초 단위 (≤ ~31년 uptime)
        return int(v * 1_000_000_000)
    return int(v)         # 이미 ns (≥ 11.5일 ns)
```

**규칙:**
- **저장 단위**: 내부 모든 타임스탬프는 **ns int64**.
- **판단 기준**: `1e12` (초 단위 최대 ~31년 << 1e12).
- 카메라 프레임: `timestamp_us * 1000` → ns (데이터 채널 경유 시).

## 자주 묻는 질문

**Q. `to_thread` vs `queue.Queue` 워커?**
- 단발/간헐적 blocking 호출 → `asyncio.to_thread`.
- 지속적/높은 빈도의 blocking 처리 → `queue.Queue` + 전용 스레드 (스레드 생성 비용 절감, 백프레셔 관리 가능).

**Q. 큐가 가득 찼을 때?**
- 의도적으로 `Queue(maxsize=N)`을 두고 `put_nowait()`이 `Full`을 던지면 **드롭 정책**(가장 오래된 것 제거 / 새 입력 거부)을 명시. 무한 큐는 메모리 폭발 위험.

**Q. 태스크 예외는 어떻게 잡나?**
- `add_done_callback`에서 `task.exception()` 확인하거나, `gather(..., return_exceptions=True)`로 수집 후 `logger.error("task_failed", exc_info=...)`.

자세한 동시성 선택 기준은 `concurrency.md` (§2) 참고.
