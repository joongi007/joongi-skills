# Docker Compose 구성과 재현성 (PLAYBOOK §14, §16)

Compose를 선택한 프로젝트의 가이드다. 이미지·프로젝트 이름·환경변수 파일명은 예시이며 팀 계약을 따른다.
로컬 개발·테스트·배포 설정과 사용하는 Compose 버전을 구분한다.

## 환경변수와 비밀 (§14.1)

`.env`는 Compose의 변수 치환 입력이며 모든 값을 컨테이너에 자동 주입하지 않는다.
서비스의 `env_file`과 `environment`는 컨테이너 환경을 구성한다. `environment`가 같은 이름의
`env_file` 값보다 우선하는 등 실제 우선순위를 검증한다. 비밀의 출처는 [설정](config-secrets.md)을 따른다.

```yaml
services:
  api:
    env_file: ./api.env  # 해당 서비스에 필요한 값만
    environment:
      LOG_LEVEL: info   # 공개 가능한 설정값 예시
```

모든 서비스에 공용 비밀 파일 전체를 주입하지 않는다. Compose secrets를 사용해도 원본 파일·호스트 권한·
전송·사용 시점 보안은 별도다. 실제 자격증명이 포함된 `docker compose config` 출력도 공개하지 않는다.

## 개발 볼륨·로그 (§14.2, §14.3)

개발 시 소스 bind mount·named volume 기반 의존성 분리를 선택할 수 있다.
운영은 검증한 이미지 배포를 기본으로 하며 임의 소스 덮어쓰기를 피한다.
project 이름으로 격리되지 않는 명시적 image·external volume·bind path·host port의 충돌을 따로 확인한다.
로그 보관량은 driver·중앙 수집 정책에 맞춰 제한한다. `json-file`의 `max-size`·`max-file`은 한 선택지다.
volume 삭제를 일반적인 중지로 안내하지 않고 보존·백업·복구를 정한다.

## 일회성 초기화·마이그레이션 (§14.4)

migration job을 본 서비스와 분리할 수 있다. 같은 앱 이미지를 명시적으로 먼저 빌드한 예시:

```yaml
name: example-app
services:
  api-init:
    image: example-app-api:dev
    pull_policy: never
    command: ["uv", "run", "alembic", "upgrade", "head"]
    restart: "no"
  api:
    build: .
    image: example-app-api:dev
    pull_policy: never
    depends_on:
      api-init:
        condition: service_completed_successfully
```

```bash
docker compose build api
docker compose up -d
```

예시는 해당 Dockerfile·uv·Alembic·연결 설정을 전제로 하며 완성형 배포 파일이 아니다.
DB readiness·timeout·마이그레이션 동시 실행 방지·실패 시 중단·구버전 앱 호환성을 추가로 검증한다.
`depends_on`은 실행 의존성으로 이미지 빌드 의존성을 대체하지 않는다.
초기화 job은 멱등성 또는 명확한 일회성 상태를 갖게 한다. migration rollback은 이미지 rollback과 다르다.

## build·image·pull 정책 (§16.1, §16.2)

`build`만 있어도 Compose가 이미지 이름을 만든다. 다른 서비스·배포에서 명시적으로 재사용하려면
`image`도 지정할 수 있다. registry 배포는 검증한 이미지 push·pull 경로를 별도로 제공한다.
로컬 전용 이미지에 `pull_policy: never`를 선택하면 미리 빌드한 이미지가 있어야 한다.
배포 이미지는 update·offline·인증·실패 정책에 맞춰 pull 정책을 선택한다.
공식 이미지이거나 기본 pull 정책이라는 이유만으로 안전하다고 판단하지 않는다.

## 버전 선택과 불변 이미지 (§16.3)

`latest`뿐 아니라 메이저·마이너·patch 태그도 재지정될 수 있다. 태그 선택과 immutable digest 고정을 구분한다.
재현성이 필요한 배포는 검증한 digest·플랫폼·서명/출처·취약점 검사·업데이트·rollback 절차를 기록한다.
고정은 업데이트 중단을 뜻하지 않는다. 오래된 digest도 패치 검토 대상이다.
Alpine·slim은 크기·libc·native extension·운영 도구 호환성을 비교하며 선택한다.

## 프로젝트·환경 분리와 확인 (§16.4, §16.5)

Compose project 이름을 구분하고 필요한 경우 환경별 override·profile을 둔다.
project 이름만 바꿔도 명시적 image 이름·host port·external volume·공용 경로는 공유될 수 있다.
개발 DB 포트가 필요하면 loopback bind를 검토하고 운영 포트 노출을 그대로 복사하지 않는다.
설정 검증 → 이미지 준비 → 초기화 → 기동 → readiness·대표 요청 → 중지·재시작·데이터 보존을 확인한다.

관련: [Kubernetes 선택](kubernetes-helm.md), [취약점 관리](vulnerability-management.md).
근거(2026-11-27): [Compose 환경변수 우선순위](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/),
[Compose 서비스·이미지 구성](https://docs.docker.com/reference/compose-file/services/).
