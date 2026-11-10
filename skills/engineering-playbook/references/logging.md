# 구조화된 로그 (PLAYBOOK §10, §21)

## 목차

- 원칙 (§10)
- logger.py 설정 (§21.1) — Docker/stdout 환경
- 사용 방법 (§21.2)
- 절대 규칙
- 좋은 vs 나쁜 예

## 원칙 (§10)

- **식별자·이벤트 키**: 영어 `snake_case`.
- **도메인 설명·운영 메모·사용자에게 보이는 짧은 문장**: 팀 언어(한국어 가능).
- 주석은 **비즈니스 규칙·보안/운영 주의·임시 우회(이슈 번호)** 에만. 자명한 한 줄은 이름으로 해결.
- 구조화 로그는 **한 줄 JSON + 고정 이벤트 이름**, **PII 금지**.

## logger.py 설정 (§21.1) — Docker/stdout 환경

stdlib logging을 structlog로 통합 → **모든 로그를 JSON 한 줄로** stdout. Docker/컨테이너 환경에서 로그 수집기(Loki, CloudWatch 등)가 stdout을 그대로 가져가는 구조에 최적.

```python
# <패키지>/logger.py
import logging
import sys
import structlog
from config import env  # LOG_LEVEL 환경변수

shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
    structlog.processors.CallsiteParameterAdder(
        {
            structlog.processors.CallsiteParameter.PATHNAME,
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.PROCESS_NAME,
            structlog.processors.CallsiteParameter.FUNC_NAME,
            structlog.processors.CallsiteParameter.LINENO,
        }
    ),
    structlog.stdlib.ExtraAdder(),
]

structlog.configure(
    processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=shared_processors,
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.JSONRenderer(),
    ],
)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

root_logger = logging.getLogger()
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)
root_logger.addHandler(handler)
root_logger.setLevel(logging.getLevelNamesMapping()[env.LOG_LEVEL.value])

# 서드파티 로거 억제 — 필요한 것만 남긴다
# 예: uvicorn access 로그는 미들웨어에서 직접 구조화 로그로 찍으므로 uvicorn 로거는 ERROR만
for name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
    lg = logging.getLogger(name)
    lg.setLevel(logging.ERROR)
    lg.handlers = []
    lg.propagate = True

logger = structlog.stdlib.get_logger()
```

**설계 포인트:**
- `shared_processors`: structlog 자체 로거 + stdlib `logging`으로 들어오는 외부 로그(uvicorn, sqlalchemy 등) 양쪽에 동일 처리기 적용.
- `foreign_pre_chain`: stdlib `logging` 경유 로그도 같은 JSON 포맷으로 통일.
- `cache_logger_on_first_use=True`: 로거 인스턴스 재사용으로 퍼포먼스 확보.
- `CallsiteParameterAdder`: `pathname`, `filename`, `func_name`, `lineno` 자동 포함 → 로그만 보고 위치 추적.

**env.py에 추가:**

```python
class LogLevel(StrEnum):
    CRITICAL = "CRITICAL"
    FATAL    = "FATAL"
    ERROR    = "ERROR"
    WARNING  = "WARNING"
    WARN     = "WARN"
    INFO     = "INFO"
    DEBUG    = "DEBUG"
    NOTSET   = "NOTSET"

class Settings(BaseSettings):
    LOG_LEVEL: LogLevel = LogLevel.INFO   # API_LOG_LEVEL
```

## 사용 방법 (§21.2)

```python
# 각 모듈 최상단
from <패키지>.logger import logger

# 사용
logger.info("job_session_started", job_id=1, entity_id="abc")
logger.warning("external_task_timeout", job_id=1, timeout_sec=20.0)
logger.error("storage_write_failed", job_id=1, exc_info=e)
```

## 절대 규칙

- **이벤트 이름**: `snake_case` 영어, **`동사_목적어`** 형태. 예: `job_session_started`, `cache_preloaded`, `external_task_timeout`.
- **컨텍스트는 key=value 키워드 인자**로 (위치 인자 사용 금지).
- **예외**: `exc_info=e` 추가 (스택트레이스 포함).
- **PII 금지**: 이름·이메일·비밀번호·주민번호·전화번호 → 절대 로그에 안 들어감.
- 출력 필드: `event`, `level`, `timestamp`, `pathname`, `lineno` + 커스텀 키.

## 좋은 vs 나쁜 예

```python
# ❌ 나쁨
logger.info(f"User {user.email} logged in at {timestamp}")  # PII + f-string + 자유형 메시지
logger.info("login", user.email)                            # 위치 인자

# ✅ 좋음
logger.info("user_login_success", user_idx=user.idx)        # PII 없음, snake_case 동사_목적어, kwargs

# ❌ 나쁨 (예외)
logger.error(f"Failed: {e}")

# ✅ 좋음
logger.error("storage_write_failed", job_id=1, exc_info=e)
```
