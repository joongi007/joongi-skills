# 새 프로젝트 구성 (PLAYBOOK §8)

## 목차

- 호스트에 Python/Node 안 깔고 시작하기
- 초기화 직후 해야 할 일
- Docker Compose 초기 구성
- UI–API 연결 검증 순서 (§11.3)
- .gitignore 기본

## 호스트에 Python/Node 안 깔고 시작하기

다른 사람이 "어떻게 초기화했냐"고 물으면 **아래를 그대로 안내**.

### Python (uv, Python 3.14 이미지)

```bash
docker run --rm -v "$(pwd)":/app -w /app ghcr.io/astral-sh/uv:python3.14-bookworm-slim uv init
```

### UI (Vite + React + TypeScript)

```bash
docker run --rm -it -v "$(pwd)":/app -w /app node:24-slim \
  npm create vite@latest . -- --template react-ts
```

**규칙:**
- **빈 디렉터리에서 실행**하는 것이 안전 (`.` 대신 새 폴더를 마운트해도 됨).
- 팀 표준 Node/uv 태그가 바뀌면 **이 문서의 버전만 갱신**.

## 초기화 직후 해야 할 일

### Python (FastAPI 백엔드)

1. **패키지 이름**: `<프로젝트 코드명>_<역할>` 한 단어로 정함 (예: `rc_api`). `python-api.md` §5 참고.
2. **폴더 골격** 만들기 (`python-api.md` §18.1 참고):
   - `<패키지>/{models,modules,nats,middleware,enums,utils}/`
   - `config/{env.py, constants.py, db.py}`
3. **의존성** (`pyproject.toml`): `fastapi`, `sqlalchemy[asyncio]`, `alembic`, `pydantic-settings`, `structlog`, `redis`, `bcrypt`, `pyjwt`, `nats-py` (필요 시).
4. **dev 의존성**: `ruff`, `pytest`, `pytest-asyncio`. **이미지 빌드에는 dev 도구 넣지 않음** (린트는 로컬/CI).
5. **Ruff 설정** (`lint-naming.md` §22.1).
6. **`logger.py`** (`logging.md` §21.1) — 모든 모듈에서 `from <패키지>.logger import logger`.
7. **`config/env.py`**: `pydantic-settings` + `API_` prefix, `quote_plus`로 URL 조립 (`config-secrets.md` 참고).
8. **`__init__.py`**: FastAPI app + lifespan + `register_routers()` 호출.
9. **첫 라우터**: `/api/v1/healthz` (인증 없는 짧은 JSON).
10. **Alembic** 초기화: `alembic init`, `env.py`에서 `target_metadata = Base.metadata` 연결.

### UI (React + TypeScript)

1. **폴더 골격** 만들기 (`frontend.md` §20.1 참고):
   - `src/{api,components/{features,layout,common},hooks,pages,stores,types,ws,constants,utils,theme}/`
2. **의존성**: `zustand`, `axios`, `react-router-dom`, `@mui/material`, `@emotion/react`, `tailwindcss`, `recharts`, `notistack`.
3. **dev 의존성**: `eslint`, `typescript-eslint`, `eslint-plugin-react-hooks`, `prettier` (선택).
4. **ESLint v9 flat config** (`lint-naming.md` §22.2).
5. **`tsconfig.json`** strict 모드.
6. **`api/http.ts`**: axios 인스턴스 + 인터셉터 (`frontend.md` §20.2).
7. **`stores/authStore.ts`** (`frontend.md` §20.3).
8. **`ws/wsClient.ts`** 싱글톤 (`frontend.md` §20.4).

## Docker Compose 초기 구성

`docker.md` 참고. 처음 만들 때 챙길 것:

- `name: <프로젝트>` 명시 (멀티 컴포즈 충돌 방지, §16.4).
- `env_file: .env` + 베이스 변수 참조 (§14.1).
- `build` + `image` 조합 + `pull_policy: never` (§16.1, §16.2).
- 인프라 이미지는 **버전 태그 고정** — `postgres:16-alpine`, `redis:7-alpine` (§16.3).
- 개발용 볼륨 마운트 + named volume으로 venv/node_modules 분리 (§14.2).
- `api-init` 컨테이너로 Alembic 마이그레이션 (§14.4).
- 로그 드라이버 옵션 명시 (§14.3).

## UI–API 연결 검증 순서 (§11.3)

처음 띄울 때 **단순 → 복잡** 순서로:

1. 브라우저 한 탭으로 진입 URL에서 UI가 뜨는지.
2. `/healthz`와 대표 API 한두 개가 기대대로 오는지.
3. 그 다음에만 추가 도메인·TLS 종단·이중 프록시·헤더 트릭으로 넓힌다.

**처음부터 복잡한 솔루션으로 가지 않는다.** Vite 단독으로 띄울지, 프록시 뒤에 넣을지는 `frontend.md` §11 참고.

## .gitignore 기본

```
# Python
__pycache__/
*.pyc
.venv/
.ruff_cache/
.pytest_cache/

# Node
node_modules/
dist/
build/

# Env (실제 값)
.env
.env.local

# IDE
.vscode/
.idea/

# OS
.DS_Store
```

`.env.example`은 커밋, `.env`는 gitignore.
