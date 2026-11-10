# TCP·클라이언트 장애 감지 (PLAYBOOK §25.4)

노드가 전원 차단되거나 패킷이 버려지면 FIN/RST가 오지 않을 수 있다.
이는 Java 전용 문제가 아니다. 언어·OS·드라이버별 기본값을 확인하고,
서버 승격뿐 아니라 **클라이언트가 새 서버에 정상 요청을 완료할 때까지** 측정한다.

## 구분할 시간 제한

| 설정 | 제한 대상 | 대체할 수 없는 것 |
|---|---|---|
| connect timeout | 새 연결 수립 | 이미 만들어진 연결의 응답 대기 |
| read / socket timeout | 읽기 대기 | 여러 번 읽는 전체 요청의 총시간 |
| request deadline | 풀 대기·연결·재시도를 포함한 작업 예산 | OS 연결 생존 확인 |
| pool acquisition timeout | 풀에서 연결을 얻는 대기 | 실제 쿼리 시간 |
| TCP keepalive | 유휴 연결의 상대 생존 확인 | 짧은 요청 지연 보장 |
| TCP user timeout | 미확인 송신 데이터에 대한 제한, 지원 환경 한정 | 모든 유휴 연결 탐지 |

❌ `connectTimeout=2s` 하나를 지정하고 노드 장애를 2초 안에 감지한다고 문서화한다.

✅ 연결·읽기·풀 획득·전체 요청 예산을 각각 정하고 패킷 DROP으로 검증한다.

## Java 최소 예시

아래는 blocking `Socket` 예시다. JDBC·Lettuce·Jedis·HTTP 클라이언트에는
각 드라이버의 실제 설정명을 사용한다. 특정 라이브러리 설정으로 복사하지 않는다.

```java
// ❌ 기본 생성자로 연결하고 무기한 읽기
Socket socket = new Socket(host, port);
socket.getInputStream().read();

// ✅ 연결·읽기 제한을 따로 지정 (값은 예시)
Socket socket = new Socket();
socket.connect(new InetSocketAddress(host, port), 2000);
socket.setSoTimeout(3000);
socket.setKeepAlive(true);
```

`SO_TIMEOUT`은 읽기에 적용되며, timeout 예외만으로 소켓이 자동 폐기되지 않는다.
실제 구현에서는 try-with-resources 또는 풀의 invalidate/evict를 사용한다.
keepalive 활성화만으로 probe 간격이 짧아진다고 가정하지 않는다.
`TCP_KEEPIDLE` 등 지원 옵션은 OS/JDK/드라이버 조합별로 확인한다.

## 전환과 재시도

- DNS·Sentinel·로드밸런서의 주소 갱신과 기존 풀 연결 폐기를 함께 확인한다.
- 재시도 횟수·동시성을 제한하고 지수 백오프와 jitter를 적용한다.
- 결과를 못 받은 쓰기는 실패가 확정된 것이 아니다. 멱등 키나 조회로 결과를 확인한다.
- 총 요청 예산 안에서만 재시도한다. 모든 계층의 독립 재시도로 횟수가 곱해지지 않게 한다.
- K8s readiness는 새 트래픽 유입 제어다. 이미 열린 TCP 연결의 종료 보장은 아니다.

## 검증 기록

정상 지연, 노드 전원 차단, 패킷 DROP, DNS 갱신, 풀 고갈을 따로 재현한다.
각 경우 감지 시간, 요청 실패율, 정상화 시간, 중복 처리, 연결 수를 기록한다.
단순 프로세스 정상 종료만 테스트하면 FIN/RST 없는 장애를 검증하지 못한다.

근거: `refs/research/2026-11-05-infrastructure-quality.md`.
