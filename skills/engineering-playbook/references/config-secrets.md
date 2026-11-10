# 설정과 비밀 관리 (PLAYBOOK §15)

## 비밀번호·URL 인코딩 — `quote_plus` (§15)

DB/Redis URL을 코드에서 직접 조립할 때, **비밀번호에 특수문자(`!@#$%` 등)가 들어오면 URL 파싱이 깨진다.**
반드시 `urllib.parse.quote_plus`로 인코딩.

```python
from urllib.parse import quote_plus

# ❌ 특수문자 비밀번호가 들어오면 파싱 오류
url = f"postgresql+asyncpg://{user}:{password}@{host}/{db}"

# ✅ quote_plus로 인코딩
url = f"postgresql+asyncpg://{user}:{quote_plus(password)}@{host}/{db}"
```

- **`.env`에서 비밀번호를 읽어 URL을 조립하는 모든 곳**에 적용.
- `quote_plus`는 공백을 `+`로, 나머지 특수문자를 `%XX`로 인코딩.
- `pydantic-settings`의 `@cached_property`로 URL을 한 번만 계산.

## pydantic-settings 패턴

```python
from functools import cached_property
from urllib.parse import quote_plus
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None

    @cached_property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @cached_property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{quote_plus(self.REDIS_PASSWORD)}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
```

## 환경 변수 prefix 통일 (§6 관련)

- 한 서비스는 **하나의 prefix**만 사용 (예: `API_`, `WORKER_`, `COLLECTOR_`).
- `pydantic-settings`의 `model_config = SettingsConfigDict(env_prefix="API_")`로 강제.
- 같은 인프라 변수도 서비스마다 prefix를 붙여서 분리 (`API_POSTGRES_HOST`, `WORKER_POSTGRES_HOST`).
- `.env`에서는 베이스 변수를 한 번 정의하고 서비스별로 참조 (`docker.md` §14.1 참고):
  ```dotenv
  POSTGRES_HOST=postgres
  API_POSTGRES_HOST=${POSTGRES_HOST}
  WORKER_POSTGRES_HOST=${POSTGRES_HOST}
  ```

## 비밀 관리 원칙 (§4 관련)

- **비밀·토큰은 저장소에 넣지 않는다.** 환경 변수만.
- **`.env`는 gitignore**, **`.env.example`은 커밋** — 키만, 값은 비워서.
- 빌드 타임 env (Vite의 `VITE_*`)에 시크릿 넣지 않음 — **브라우저 번들에 들어간다**.
- 프로덕션 비밀은 시크릿 매니저(AWS Secrets Manager, Vault 등)에서 주입.

## URL 노출용 description 힌트

`pydantic-settings`에서 `Field(description=…)`로 `.env` 편집자에게 힌트:

```python
from pydantic import Field

class Settings(BaseSettings):
    POSTGRES_PASSWORD: str = Field(
        description="Postgres 비밀번호. 특수문자 가능 — 코드에서 quote_plus로 인코딩됨."
    )
```
