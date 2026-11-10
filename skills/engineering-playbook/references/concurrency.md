# 동시성과 성능 (PLAYBOOK §2)

## 핵심 요약

| 작업 성격 | 1순위 | 피해야 할 것 |
|---|---|---|
| **I/O 대기** (DB·HTTP·소켓) | `asyncio` 단일 스레드 + 다수 코루틴 | 스레드 수만 늘리는 단순 확장 (문맥 전환·락 경합) |
| **CPU 바운드** | `ProcessPoolExecutor` 또는 배치 워커 | 코루틴 안에서 그대로 돌리기 (이벤트 루프 굶음) |
| **블로킹 SDK가 섞였을 때** | `asyncio.to_thread()` 또는 제한된 스레드 풀 | 무한정 스레드 늘리기 |

핵심 원칙: **이벤트 루프는 한 번에 하나의 코루틴만 실행한다.** 그래서 무거운 CPU/blocking 호출이 코루틴 안에 있으면 모든 요청·타이머·하트비트가 굶는다.

## 선택 절차

1. 이 코드가 **대기(I/O)가 대부분**인가 → async 파이프라인 우선.
2. **CPU가 오래** 걸리는가 → 루프 밖으로(스레드/프로세스/배치).
3. **외부 시스템 보호**(rate limit) 필요한가 → 동시성 수·간격·타임아웃을 **환경 변수**로 노출.

## Python 한정 주의 (GIL)

- 순수 Python CPU 연산은 **한 시점에 한 스레드만** 실행. 스레드 늘려도 CPU 병렬 안 나옴.
- 네이티브 코드 구간(NumPy·암호화 일부)은 GIL 풀려서 병렬 가능.
- **순수 CPU 병렬이 필요하면 프로세스로** 가야 한다.

## 수평 확장 (§2.6)

- "지금은 단일 인스턴스로 충분"만으로 설계를 닫지 않는다. **단일이 정말 충분하다는 근거가 있을 때만** 단일화.
- API 복제본 N개 띄울 수 있게:
  - 세션·rate limit 카운터 등 **로컬 메모리 금지** → Redis/DB로.
  - 헬스·리더 선출 필요 시 **분산 락·오케스트레이션 규약**을 문서에.
- 워커가 동일 입력을 나눠 받을 때 **멱등 키·파티션·락** 설계.
- "당분간 단일 Pod"를 택해도 **replica 수만 늘리면 되는지** 검토 후 "의도적 단일"이라고 명시.

## 수신부 ↔ 처리부 분리 (§2.7) — 생산자-소비자

데이터 **수신**과 **처리**를 한 흐름에 몰지 않고 사이에 **버퍼(큐)** 를 둔다.

- **프로세스/Pod 간**: Redis Stream, RabbitMQ, Kafka, 파일 스풀, DB 큐 등 — 프로젝트에 맞게.
- **스레드 간**(한 프로세스 안): `queue.Queue` 로 같은 패턴 축소 적용. 단, 무거운 CPU는 **프로세스 분리**와 함께 봐야 안전 (GIL).
- "수신 완료"와 "처리 완료"의 **경계를 코드·로그·메트릭에서 구분 가능**하게 둔다.

## CPU 작업이 코루틴에 들어왔을 때 해결 방향

```python
# ❌ 이벤트 루프 점유
async def handle():
    result = heavy_parse(big_json)  # CPU bound

# ✅ asyncio.to_thread (I/O와 섞일 때 타협)
result = await asyncio.to_thread(heavy_parse, big_json)

# ✅ ProcessPoolExecutor (대량·장시간 CPU)
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(process_pool, heavy_parse, big_json)

# ✅ 배치 워커 + 큐 (API는 작업 ID만 반환)
job_id = await queue.enqueue(big_json)
return {"job_id": job_id}
```

자세한 코드 패턴은 `async-patterns.md` (§23) 참고.
