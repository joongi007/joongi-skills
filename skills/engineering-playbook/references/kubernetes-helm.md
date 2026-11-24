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

## 여러 프로젝트의 로컬 개발 환경

프로젝트가 많으면 k3s도 후보지만 개수만으로 Compose보다 리소스가 적거나 관리가 쉬워지지는 않는다.
포트·프로젝트 이름 충돌만 문제라면 Compose project 분리와 필요한 서비스만 켜는 방식부터 검토한다.

| 필요한 검증 | 선택 후보 | 부담 |
|---|---|---|
| API·worker·DB 개발, 간단한 네트워크·볼륨 | 프로젝트별 Compose | 프로젝트 간 포트·이미지·볼륨 이름 관리 |
| Helm·Ingress·RBAC·CronJob·probe를 운영과 비슷하게 검증 | 로컬 k3s, 컨테이너형 k3d·kind 등 비교 | control plane·이미지 반입·스토리지·기동 시간 |
| 작은 Linux 장비에 여러 프로젝트를 상시 운영·실험 | 단일 k3s + 프로젝트별 namespace | 자원 경합·업그레이드·백업·장애 영향 공유 |

namespace는 이름과 권한 범위를 나누지만 강한 보안 격리나 VM 경계는 아니다.
불신 코드·회사와 개인의 비밀·다른 신뢰 수준의 프로젝트는 별도 VM/클러스터도 검토한다.
프로젝트별 ServiceAccount/RBAC·ResourceQuota·LimitRange·NetworkPolicy를 설정하고 실제 차단을 확인한다.
kubeconfig는 관리자 자격증명으로 취급하고 API server·Ingress·DB를 불필요하게 외부에 노출하지 않는다.

운영과 같은 chart/image에 개발용 values를 덮어쓰고, 환경 차이·로컬 이미지 사용법·hot reload를 문서화한다.
CPU·메모리·디스크·inode·기동 시간을 실측한다. K3s 최소 요구량에는 애플리케이션 부하가 포함되지 않는다.
WSL이라면 Linux 내부 경로의 빌드·볼륨과 Windows mount 비용·VHDX 증가도 함께 확인한다.
설치는 선택한 버전과 OS 조건을 확인한 뒤 진행하며 예제만 보고 클러스터를 자동 생성하지 않는다.

휴식 시 workload 중단과 클러스터 중단을 구분한다. scale-to-zero만으로 control plane·DB가 중단되지는 않는다.
시작·중지·재시작·불필요한 이미지 정리·데이터 백업·볼륨 삭제 범위를 runbook에 적고,
중단 전후 작업·PVC 데이터 보존을 확인한다. 클러스터 삭제를 일반적인 중지 명령으로 안내하지 않는다.
단일 머신의 복제본·여러 Pod는 호스트 장애에 대한 HA가 아니다.

관련: [Compose](docker.md), [WSL](wsl-development.md).
근거: [K3s 요구사항](https://docs.k3s.io/installation/requirements),
[Kubernetes namespace 경계](https://kubernetes.io/docs/concepts/security/multi-tenancy/).

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
