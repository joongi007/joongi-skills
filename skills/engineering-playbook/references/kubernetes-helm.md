# k3s·Kubernetes·Helm 운영 (PLAYBOOK §25.6)

## 도입 기준

Compose로 요구를 충족하면 먼저 단순한 구성을 유지한다.
다중 노드 스케줄링, 점진 배포, 자동 재배치가 필요하고 운영 담당자가 있을 때
k3s·관리형 Kubernetes를 비교한다. k3s도 스토리지·백업·네트워크 운영은 필요하다.

| 구성 | 용도 | 놓치기 쉬운 장애 |
|---|---|---|
| 단일 k3s server | 로컬·실습·의도적 단일 | server·디스크 장애 |
| k3s embedded etcd HA | 복수 control plane | quorum 상실, 느린 디스크 |
| 관리형 control plane | 운영 부담 일부 이전 | worker·스토리지·애플리케이션 장애 |

embedded etcd HA는 보통 3개 이상 홀수 server와 독립 장애 영역을 사용한다.
worker만 늘려서는 control plane 가용성이 올라가지 않는다. snapshot과 cluster token을
함께 보호하고, 빈 환경에서 복원하는 절차를 확인한다.

## 애플리케이션 배포 계약

- startup probe는 초기 기동, readiness는 트래픽 수신 가능, liveness는 재시작 필요 여부다.
- 외부 DB 일시 장애를 liveness 실패로 직결해 재시작 폭풍을 만들지 않는다.
- request/limit, 종료 유예, SIGTERM 처리, 진행 중 요청 drain을 정한다.
- 복제본을 topology spread / anti-affinity로 노드·존에 분산한다.
- PDB는 자발적 disruption을 제어한다. 노드 전원 차단 자체를 막지 않는다.
- PVC가 노드에 묶이는지, 다른 노드에서 재연결 가능한지 검증한다.
- ServiceAccount/RBAC 최소 권한, Secret 외부 주입, NetworkPolicy 적용 여부를 확인한다.

❌ `replicas: 3`만 적고 노드 하나가 죽어도 안전하다고 판단한다.

✅ 실제 배치와 스토리지 제약을 확인하고 노드 하나 중단 후 정상 서비스 여부를 측정한다.

## Helm 작성과 검증

최소 구성은 `Chart.yaml`, `values.yaml`, `templates/`다. 입력 검증이 필요한 chart에는
`values.schema.json`을 둔다. chart와 image 버전을 따로 고정하고 secret 값은 커밋하지 않는다.

```bash
# ❌ 렌더링도 확인하지 않고 운영에 적용
helm upgrade app ./chart

# ✅ 설치할 Helm/Kubernetes 버전을 명시한 환경에서 검증
helm lint ./chart
helm template app ./chart -f values-staging.yaml > rendered.yaml
kubectl apply --dry-run=server -f rendered.yaml
```

위 명령은 대상 클러스터에 대한 권한과 연결을 전제로 한다. API 폐기 여부,
기본값 변화와 플래그 차이를 선택한 Helm 버전에서 확인한다.
staging에서 신규 설치 → 업그레이드 → 실패 → rollback을 검증한다.
DB migration은 Helm rollback으로 자동 역변환되지 않는다. 확장·축소 migration과
백업 복원 조건을 따로 설계한다.

근거: `refs/research/2026-11-05-infrastructure-quality.md`.
