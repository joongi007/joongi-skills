# 인프라·품질·MCP 호환성 조사

조회일: 2026-11-05. 아래는 공식 자료의 **요약과 이 저장소의 적용 판단**이다.
원문 인용·외부 코드 복사·실측 성능 결과가 아니다. 라이브러리·규격 변경 시 재확인한다.

## 출처

| 공식 자료 | 확인한 사실 | 적용 위치 |
|---|---|---|
| [Redis licenses](https://redis.io/legal/licenses/) | Redis 라이선스는 버전별로 다름 | §25.2 |
| [Valkey COPYING](https://github.com/valkey-io/valkey/blob/unstable/COPYING) | BSD 계열 라이선스, 배포 버전의 파일 확인 필요 | §25.2 |
| [Valkey Sentinel](https://valkey.io/topics/sentinel/) | 감시·승격·서비스 발견, quorum과 과반수 승인 | §25.3 |
| [Java Socket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/Socket.html) | connect/read 제한과 keepalive는 별도 | §25.4 |
| [PostgreSQL standby](https://www.postgresql.org/docs/current/warm-standby.html) | 비동기 복제는 손실 구간 가능, 동기 복제와 다른 비용 | §25.5 |
| [K3s embedded etcd HA](https://docs.k3s.io/datastore/ha-embedded) | 3개 이상 server, quorum·디스크 성능·복구 계획 | §25.6 |
| [Kubernetes topology spread](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) | 노드·존 배치 분산 | §25.6 |
| [Helm charts](https://helm.sh/docs/topics/charts/) | Chart.yaml·values·templates와 chart 검증 | §25.6 |
| [PIT concepts](https://pitest.org/quickstart/basic_concepts/) | seeded mutation으로 테스트 탐지력 확인, equivalent mutation 존재 | §26.3 |
| [MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) | 연결·초기화 기반 모델 | Hub compatibility |
| [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) | self-contained 요청과 요청별 capability | Hub compatibility |
| [Tasks extension](https://modelcontextprotocol.github.io/ext-tasks/specification/2026-07-28/tasks.html) | 별도 opt-in 확장과 task handle·poll·cancel | Hub Tasks 경계 |
| [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview) | tool UI metadata와 UI resource, Host 렌더링 | Hub Apps 경계 |
| [Skills WG](https://modelcontextprotocol.io/community/working-groups/skills-over-mcp) | 공식 Skills extension 작업·상태 | 공식 확장과 자체 조회 구분 |
| [GitNexus](https://github.com/nxpatterns/gitnexus) | 코드 그래프와 MCP/CLI 제공 | §27 도구 선택 예시 |
| [Serena](https://github.com/oraios/serena) | 심볼 기반 코드 탐색·편집 MCP | §27 도구 선택 예시 |

## 해석과 저장소 적용

Sentinel 개수의 홀수는 효율·장애 허용을 위한 통상 선택이다. 짝수 자체가 금지인 것처럼
일반화하지 않고 장애 판정 quorum과 전체 과반수 승인, 실제 노드 배치를 구분한다.
TCP timeout 예시는 Java 전용 현상으로 설명하지 않는다. 선택한 드라이버·OS의 실제
설정으로 검증하며, 전원 차단·패킷 DROP 시험을 정상 종료 시험과 구분한다.

복제와 백업은 다른 요구다. 복제본은 잘못된 삭제를 함께 받을 수 있다. HA를 채택할 때
승격만 아니라 클라이언트 재연결과 쓰기 주체 격리를 포함한다.
Kubernetes·Helm은 복구를 자동 보장하는 제품으로 설명하지 않고 운영 요구에 따라 선택한다.

mutation score는 품질 전체를 대표하지 않는다. 살아남은 변이의 원인을 기록하고
동등 변이를 구분한다. 문서 정합성도 링크 검사와 의미 검토를 구분한다.

MCP 지원은 규격 날짜·전송·기능 조합으로 검증한다. Apps 전달과 renderer 구현,
일반 resources/tools 스킬 제공과 공식 Skills 확장 준수를 따로 기록한다.
위 외부 도구는 설치·실접속 시험 없이 검증된 통합으로 광고하지 않는다.

이 판단은 `skills/engineering-playbook/references/`의 §25–§27 자료와
`docs/architecture/02-compatibility.md`에 반영했다.
