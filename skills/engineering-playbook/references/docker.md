# Docker Compose 패턴 (PLAYBOOK §14, §16)

## 목차

- env_file + 베이스 변수 참조 (§14.1)
- 개발용 볼륨 마운트 — Hot-reload (§14.2)
- 컨테이너 로그 설정 (§14.3)
- 초기화 컨테이너 — Initor (§14.4)
- build + image 조합 (§16.1)
- pull_policy: never (§16.2)
- 인프라 이미지 버전 태그 고정 (§16.3)
- 멀티 컴포즈 파일 충돌 방지 (§16.4)
- 전체 구조 요약 (§16.5)

## env_file + 베이스 변수 참조 (§14.1)

환경 변수는 **인프라 베이스 → 서비스별 변수 참조** 방식으로 `.env` 한 파일에서 관리.
docker-compose 서비스에는 **`env_file: .env` 한 줄**만, `environment:` 블록에 값 하드코딩 금지.

```dotenv
# 인프라 베이스
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=myapp
POSTGRES_PASSWORD=secret

# 서비스별 (베이스 참조)
API_POSTGRES_HOST=${POSTGRES_HOST}
API_POSTGRES_PORT=${POSTGRES_PORT}
API_POSTGRES_USER=${POSTGRES_USER}
API_POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

```yaml
services:
  api:
    env_file: .env   # API_POSTGRES_* 자동 주입
  worker:
    env_file: .env   # WORKER_POSTGRES_* 도 같은 파일에서
```

- **로컬(Docker 없이)**: `POSTGRES_HOST=localhost`로만 바꾸면 됨.
- **`.env`는 gitignore**, **`.env.example`은 커밋** — 실제 비밀은 `.env`에만.

## 개발용 볼륨 마운트 — Hot-reload (§14.2)

프로덕션 이미지는 코드를 COPY, **개발은 소스 폴더를 마운트**.
venv·node_modules 같은 **빌드 산출물은 named volume으로 분리** → 호스트 디렉터리 오염 방지.

```yaml
services:
  api:
    volumes:
      - ./api:/app/api          # 소스 — 호스트와 동기화
      - ./shared:/app/shared
      - api-venv:/app/.venv     # 패키지 — 컨테이너 전용 named volume

  sample-ui:
    volumes:
      - ./sample-ui:/app
      - sample_ui_node_modules:/app/node_modules

volumes:
  api-venv:
  sample_ui_node_modules:
```

## 컨테이너 로그 설정 (§14.3)

프로덕션·장기 실행 서비스는 **디스크 무제한 증가 방지**:

```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 초기화 컨테이너 — Initor (§14.4)

마이그레이션·설정 파일 생성 등 **1회성 초기화**는 별도 서비스로 분리.
본 서비스는 `service_completed_successfully`로 대기.

```yaml
services:
  api-init:
    image: myapp-api
    env_file: .env
    command: ["uv", "run", "alembic", "upgrade", "head"]
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"          # 완료 후 재시작 안 함

  api:
    image: myapp-api
    env_file: .env
    depends_on:
      api-init:
        condition: service_completed_successfully
```

## build + image 조합 (§16.1)

`build`만 쓰면 이미지 이름이 없어서 다른 서비스가 참조 못 함.
**`build` + `image`를 함께** 쓰면 빌드 결과에 이름이 붙어 **재사용 가능**.

```yaml
api:
  build:
    context: .
    dockerfile: docker/Dockerfile.api
  image: myapp-api          # 빌드 결과 이미지 이름
  pull_policy: never

api-init:
  image: myapp-api          # build 없음 — api가 먼저 빌드되어 있어야
  pull_policy: never
  command: ["uv", "run", "alembic", "upgrade", "head"]
  restart: "no"
```

> **주의**: `docker compose up`은 `depends_on` 순서와 무관하게 `api`를 먼저 빌드한다. `api-init`에 `build`가 없으면 `api` 이미지가 로컬에 존재해야 하므로, **첫 실행 시 반드시 `api`가 먼저 빌드**되어야 함. (`docker compose up --build`로 한 번에 해결.)

## pull_policy: never (§16.2)

로컬 전용 이미지에는 **반드시 추가**. 없으면 Docker가 동일 이름의 이미지를 레지스트리에서 pull하려다 실패하거나 예상과 다른 이미지가 내려옴.

```yaml
api:
  image: myapp-api
  pull_policy: never    # 레지스트리 조회 금지
```

공식 이미지(`postgres`, `redis` 등)는 `pull_policy` 생략 → 기본값(`missing`)이 안전.

## 인프라 이미지 버전 태그 고정 (§16.3)

**`latest` 사용 금지.** 메이저 버전 + `-alpine` / `-slim`:

```yaml
postgres:
  image: postgres:16-alpine   # ✅ 버전 고정
  # image: postgres:latest    # ❌ 업데이트 때 예기치 않은 변경

redis:
  image: redis:7-alpine

traefik:
  image: traefik:v3

ui:
  image: node:22-bookworm-slim
  working_dir: /app
  command:
    - sh
    - -c
    - npm ci --no-audit --no-fund && exec npm run dev
```

`-alpine` 작은 크기, `-bookworm-slim` Debian 호환성.

## 멀티 컴포즈 파일 충돌 방지 (§16.4)

같은 호스트에서 여러 컴포즈를 운영하면 이미지 이름 충돌. **각 컴포즈마다 이미지 이름과 `name:` 다르게.**

```yaml
# docker-compose.yml (내부 운영용)
name: myapp
api:
  image: myapp-api

# docker-compose.sample.yml (외주 샘플)
name: myapp-sample
api:
  image: myapp-sample-api    # suffix로 분리
```

`name:`이 다르면 컨테이너·볼륨 이름도 자동으로 분리.

## 전체 구조 요약 (§16.5)

```
docker-compose.yml          → 내부 운영/배포용
  name: myapp
  api:       build + image: myapp-api,        pull_policy: never
  api-init:  image: myapp-api,                pull_policy: never, restart: "no"
  collector: build + image: myapp-collector,  pull_policy: never
  ui:        image: node:22-bookworm-slim     (Dockerfile 없음)

docker-compose.sample.yml   → 외주 샘플 (포트 노출 + 코드 볼륨 마운트)
  name: myapp-sample
  api:       build + image: myapp-sample-api, pull_policy: never
  api-init:  image: myapp-sample-api,         pull_policy: never, restart: "no"
  collector: build + image: myapp-sample-collector, pull_policy: never
  ui:        image: node:22-bookworm-slim     (동일 — 빌드 불필요)
```

- 샘플용에서만 소스 코드를 볼륨 마운트해 핫리로드 지원.
- 인프라 포트(`5432`, `6379`)는 샘플용에서만 호스트로 노출.
